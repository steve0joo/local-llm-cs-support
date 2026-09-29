"""대출문의 QLoRA 학습 (ADR-005, docs/agent-loan/ARCHITECTURE.md 학습 파이프라인, phases/agent-loan/step4.md).

이 스크립트는 사람이 실행한다(step 4). 여기서 자동으로 학습을 돌리지 않는다.
입력은 backend/training/loan/prepare.py가 만든 JSONL({"messages": [...]})이다.

베이스 모델(2026-09-29 결정, 이 영역 한정 — 공통 PRD의 "팀 공통 베이스 1종"은 실제로는 영역별로
다르게 쓰고 있어 해당 없음. phases/agent-loan/step4.md 선행 조건 참고):
  1순위 Qwen/Qwen3-4B-Instruct-2507 (Apache 2.0, thinking 모드 없음, 4.0B)
  대안   Qwen/Qwen3-1.7B            (Apache 2.0, 1.7B) — 8GB에서 4B가 OOM나면 --model만 바꿔서 재실행
둘 다 학습 데이터 형식이 모델과 무관한 범용 messages라 --model 교체 외에는 아무것도 안 바뀐다.

시퀀스 길이 1024는 실측 기준이다(2026-09-29, Qwen3 토크나이저로 loan_train.jsonl 10,168건 측정):
512는 99.3%가 잘리고, 1024는 0.3%(26건)만 잘린다.

8GB VRAM 대응: 4bit QLoRA(nf4) + gradient checkpointing + paged_adamw_8bit + micro-batch=1(사용자 지정)
+ gradient accumulation으로 실효 배치를 만든다. 그래도 OOM이면 --micro-batch-size는 이미 1이므로
--max-seq-len을 낮추거나(768) --model을 Qwen3-1.7B로 바꾼다(export.md 참고).

assistant_only_loss=True 관련(2026-09-29, 드라이런에서 발견): Qwen3-4B-Instruct-2507의 원본
chat_template에는 `{% generation %}` 태그가 없어서 `return_assistant_tokens_mask=True`가 실패한다.
학습 때만(추론·Ollama에는 영향 없음) 그 태그를 추가한 TRAIN_CHAT_TEMPLATE으로 바꿔 쓴다 —
`{% generation %}`/`{% endgeneration %}`는 렌더링되는 문자열에 아무 글자도 찍지 않는 순수 마스킹용
태그라서, 렌더링 결과(=Ollama가 보는 것과 같은 ChatML 형식)는 원본 템플릿과 한 글자도 다르지 않다.
`build_model_and_tokenizer`가 적용 직후 원본과 렌더링 결과를 비교해 같은지 자동 검증하고 다르면 멈춘다
(다른 모델로 바꿔서 템플릿 구조가 달라졌는데 이 사실을 모르고 학습하는 것을 막기 위해서다).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import torch
from datasets import load_dataset
from peft import LoraConfig, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from trl import SFTConfig, SFTTrainer

DEFAULT_MODEL = "Qwen/Qwen3-4B-Instruct-2507"
DEFAULT_MAX_SEQ_LEN = 1024

# Qwen 계열 공통 선형층 이름. LoRA를 여기에 전부 건다(ADR-005 QLoRA).
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]

# Qwen/Qwen3-4B-Instruct-2507의 실제 chat_template(2026-09-29 huggingface.co에서 확인)에
# {% generation %}/{% endgeneration %}만 추가한 학습 전용 버전. assistant 메시지 블록
# ("<|im_start|>assistant\n"부터 "<|im_end|>\n"까지, tool_calls 포함)을 그대로 감싼다 —
# HF 문서가 예시로 드는 방식과 같다(역할 헤더도 마스크에 포함해 턴 전환 자체도 학습하게 한다).
# 다른 모델(예: Qwen3-1.7B)로 바꾸면 이 문자열은 그 모델의 실제 chat_template에 맞춰 다시 만들어야
# 한다 — _apply_generation_markers()의 렌더링 비교 검증이 안 맞으면 에러로 알려준다.
TRAIN_CHAT_TEMPLATE = r"""{%- if tools %}
    {{- '<|im_start|>system\n' }}
    {%- if messages[0].role == 'system' %}
        {{- messages[0].content + '\n\n' }}
    {%- endif %}
    {{- "# Tools\n\nYou may call one or more functions to assist with the user query.\n\nYou are provided with function signatures within <tools></tools> XML tags:\n<tools>" }}
    {%- for tool in tools %}
        {{- "\n" }}
        {{- tool | tojson }}
    {%- endfor %}
    {{- "\n</tools>\n\nFor each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags:\n<tool_call>\n{\"name\": <function-name>, \"arguments\": <args-json-object>}\n</tool_call><|im_end|>\n" }}
{%- else %}
    {%- if messages[0].role == 'system' %}
        {{- '<|im_start|>system\n' + messages[0].content + '<|im_end|>\n' }}
    {%- endif %}
{%- endif %}
{%- for message in messages %}
    {%- if message.content is string %}
        {%- set content = message.content %}
    {%- else %}
        {%- set content = '' %}
    {%- endif %}
    {%- if (message.role == "user") or (message.role == "system" and not loop.first) %}
        {{- '<|im_start|>' + message.role + '\n' + content + '<|im_end|>' + '\n' }}
    {%- elif message.role == "assistant" %}
        {%- generation %}
        {{- '<|im_start|>' + message.role + '\n' + content }}
        {%- if message.tool_calls %}
            {%- for tool_call in message.tool_calls %}
                {%- if (loop.first and content) or (not loop.first) %}
                    {{- '\n' }}
                {%- endif %}
                {%- if tool_call.function %}
                    {%- set tool_call = tool_call.function %}
                {%- endif %}
                {{- '<tool_call>\n{"name": "' }}
                {{- tool_call.name }}
                {{- '", "arguments": ' }}
                {%- if tool_call.arguments is string %}
                    {{- tool_call.arguments }}
                {%- else %}
                    {{- tool_call.arguments | tojson }}
                {%- endif %}
                {{- '}\n</tool_call>' }}
            {%- endfor %}
        {%- endif %}
        {{- '<|im_end|>\n' }}
        {%- endgeneration %}
    {%- elif message.role == "tool" %}
        {%- if loop.first or (messages[loop.index0 - 1].role != "tool") %}
            {{- '<|im_start|>user' }}
        {%- endif %}
        {{- '\n<tool_response>\n' }}
        {{- content }}
        {{- '\n</tool_response>' }}
        {%- if loop.last or (messages[loop.index0 + 1].role != "tool") %}
            {{- '<|im_end|>\n' }}
        {%- endif %}
    {%- endif %}
{%- endfor %}
{%- if add_generation_prompt %}
    {{- '<|im_start|>assistant\n' }}
{%- endif %}"""


def _apply_generation_markers(tokenizer) -> None:
    """assistant_only_loss=True가 요구하는 `{% generation %}` 태그를 chat_template에 넣는다.

    렌더링 결과가 원본 템플릿과 정말 같은지(=Ollama 추론 형식과 어긋나지 않는지) 여기서 검증한다.
    다르면(베이스 모델을 바꿔서 템플릿 구조가 달라진 경우 등) 조용히 넘어가지 않고 에러를 낸다.
    """
    original_template = tokenizer.chat_template
    sample_messages = [
        {"role": "system", "content": "시스템 메시지"},
        {"role": "user", "content": "질문"},
        {"role": "assistant", "content": "답변"},
        {"role": "user", "content": "재질문"},
        {"role": "assistant", "content": "목표 답변"},
    ]
    before = tokenizer.apply_chat_template(sample_messages, tokenize=False, add_generation_prompt=False)

    tokenizer.chat_template = TRAIN_CHAT_TEMPLATE
    after = tokenizer.apply_chat_template(sample_messages, tokenize=False, add_generation_prompt=False)

    if after != before:
        raise ValueError(
            "생성 마스크용 TRAIN_CHAT_TEMPLATE이 원본 chat_template과 다른 문자열을 렌더링한다. "
            "베이스 모델을 바꿨다면(--model) 그 모델의 실제 chat_template을 기준으로 "
            "train.py의 TRAIN_CHAT_TEMPLATE을 다시 만들어야 한다(export.md·Modelfile의 추론 형식과 "
            "어긋난 채로 학습하지 않기 위한 안전장치)."
        )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="대출문의 QLoRA 학습")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="HF 모델 이름")
    parser.add_argument("--train-data", type=Path, default=Path("data/processed/loan_train.jsonl"))
    parser.add_argument("--val-data", type=Path, default=Path("data/processed/loan_val.jsonl"),
                         help="없으면(파일 미존재) 평가 없이 학습만 한다")
    parser.add_argument("--out", type=Path, default=Path("training/loan/outputs"),
                         help="체크포인트·어댑터 출력(gitignore 대상)")
    parser.add_argument("--max-seq-len", type=int, default=DEFAULT_MAX_SEQ_LEN)
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--micro-batch-size", type=int, default=1,
                         help="장치당 배치. 8GB VRAM 대응으로 1을 기본값으로 둔다")
    parser.add_argument("--grad-accum", type=int, default=16,
                         help="실효 배치 = micro-batch-size * grad-accum")
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--resume-from-checkpoint", type=str, default=None)
    parser.add_argument("--limit", type=int, default=None,
                         help="train_dataset 앞에서 N개만 쓴다(시간 측정용 드라이런). eval은 자르지 않는다")
    parser.add_argument("--max-steps", type=int, default=-1,
                         help="지정하면 --epochs 대신 이 스텝 수에서 멈춘다(드라이런용, 예: 20)")
    return parser.parse_args(argv)


def build_model_and_tokenizer(model_name: str) -> tuple[AutoModelForCausalLM, AutoTokenizer]:
    """4bit(nf4) QLoRA용 모델·토크나이저를 만든다(ADR-005)."""
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    _apply_generation_markers(tokenizer)  # assistant_only_loss=True용 — 검증 통과해야 다음으로 간다

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=bnb_config,
        device_map={"": 0},
        torch_dtype=torch.bfloat16,
    )
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    return model, tokenizer


def build_peft_config(args: argparse.Namespace) -> LoraConfig:
    return LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=TARGET_MODULES,
        bias="none",
        task_type="CAUSAL_LM",
    )


def build_sft_config(args: argparse.Namespace, has_eval: bool) -> SFTConfig:
    return SFTConfig(
        output_dir=str(args.out),
        per_device_train_batch_size=args.micro_batch_size,
        per_device_eval_batch_size=args.micro_batch_size,
        gradient_accumulation_steps=args.grad_accum,
        num_train_epochs=args.epochs,
        max_steps=args.max_steps,  # -1(기본)이면 무시되고 epochs를 따른다. 드라이런에서만 양수로 준다
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        max_length=args.max_seq_len,
        # assistant 답변 토큰에만 loss(CLAUDE.md 개발 프로세스). messages 형식(대화형) 데이터라 지원된다.
        assistant_only_loss=True,
        packing=False,  # 대화 경계를 유지한다 — 패킹하면 정보 줄·슬롯 형식이 다른 샘플과 섞일 수 있다
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        optim="paged_adamw_8bit",  # 8GB VRAM 대응 — 옵티마이저 상태를 8bit로 둔다
        bf16=True,
        logging_steps=10,
        save_strategy="epoch",
        save_total_limit=2,
        eval_strategy="epoch" if has_eval else "no",
        report_to=[],
        seed=args.seed,
    )


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    train_dataset = load_dataset("json", data_files=str(args.train_data), split="train")
    if args.limit is not None:
        train_dataset = train_dataset.select(range(min(args.limit, len(train_dataset))))
    eval_dataset = None
    if args.val_data.exists():
        eval_dataset = load_dataset("json", data_files=str(args.val_data), split="train")

    model, tokenizer = build_model_and_tokenizer(args.model)
    peft_config = build_peft_config(args)
    sft_config = build_sft_config(args, has_eval=eval_dataset is not None)

    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        processing_class=tokenizer,
        peft_config=peft_config,
    )

    trainer.train(resume_from_checkpoint=args.resume_from_checkpoint)

    adapter_dir = args.out / "adapter"
    trainer.save_model(str(adapter_dir))
    # 저장은 원본 chat_template으로 한다 — tokenizer는 학습 중 TRAIN_CHAT_TEMPLATE(생성 마스크용)으로
    # 바뀐 상태라, 그대로 저장하면 export.md 이후 단계가 이 어댑터 폴더에서 토크나이저를 불러올 때
    # 학습 전용 템플릿을 물려받는다. 렌더링 결과는 원본과 같지만(검증 완료) 혼동을 막기 위해 깨끗한
    # 사본을 다시 받아 저장한다.
    AutoTokenizer.from_pretrained(args.model).save_pretrained(str(adapter_dir))
    print(f"어댑터 저장 완료: {adapter_dir}")


if __name__ == "__main__":
    main()
