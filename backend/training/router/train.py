import json
import sys
from datetime import datetime
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from trl import SFTConfig, SFTTrainer

from training.router.prepare import OUT_DIR as DATA_DIR

BASE_MODEL = "Qwen/Qwen3-1.7B"
OUT_DIR = Path(__file__).resolve().parent / "outputs" / datetime.now().strftime("%Y%m%d-%H%M%S")
NO_THINK = "<think>\n\n</think>\n\n"     # Qwen3 템플릿이 assistant 앞에 넣는 빈 생각 블록. 추론(think:false)과 같아야 한다
EPOCHS = 1
MAX_STEPS = -1                          # 스모크는 20 (epoch 대신 이 step 수만)
MAX_LENGTH = 256


def load_rows(path: Path) -> list[dict]:
    """{"messages": [system, user, assistant]} → {"prompt": [system, user], "completion": [assistant]}. 손실은 completion에만."""
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [{"prompt": r["messages"][:-1], "completion": r["messages"][-1:]} for r in records]


def check_template(tokenizer, row: dict) -> str:
    """템플릿이 completion 앞에 빈 think 블록을 넣는지 확인하고 completion 문자열을 돌려준다. 다르면 학습 전에 멈춘다."""
    prompt = tokenizer.apply_chat_template(row["prompt"], tokenize=False, add_generation_prompt=True)
    full = tokenizer.apply_chat_template(row["prompt"] + row["completion"], tokenize=False)
    completion = full[len(prompt):]
    if not full.startswith(prompt) or not completion.startswith(NO_THINK):
        raise RuntimeError(f"템플릿이 RT-006과 다르다: {completion[:40]!r}")
    return completion


def load_model():
    # 베이스를 NF4 4bit로 GPU에 올리고 LoRA r=16 설정
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=BitsAndBytesConfig(load_in_4bit=True, 
                                               bnb_4bit_quant_type="nf4",
                                               bnb_4bit_use_double_quant=True, 
                                               bnb_4bit_compute_dtype=torch.bfloat16),
        device_map={"": 0},
    )
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    return get_peft_model(model, LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    ))


def main() -> None:
    train_rows = load_rows(DATA_DIR / "train.jsonl")
    val_rows = load_rows(DATA_DIR / "val.jsonl")               # epoch 끝 val 손실: 실험 간 비교용. 주제 정확도는 evaluate.py

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    check_template(tokenizer, train_rows[0])

    trainer = SFTTrainer(
        model=load_model(),
        processing_class=tokenizer,
        train_dataset=Dataset.from_list(train_rows),
        eval_dataset=Dataset.from_list(val_rows),
        args=SFTConfig(
            output_dir=str(OUT_DIR),
            num_train_epochs=EPOCHS,
            max_steps=MAX_STEPS,
            per_device_train_batch_size=8,
            gradient_accumulation_steps=2,          # 유효 배치 16. 학습 전 `ollama stop cs-router`로 VRAM을 비울 것 (안 비우면 10배 느려진다)
            per_device_eval_batch_size=16,
            gradient_checkpointing=True,
            learning_rate=2e-4,
            lr_scheduler_type="cosine",
            warmup_steps=50,
            optim="paged_adamw_8bit",
            bf16=True,
            max_length=MAX_LENGTH,
            completion_only_loss=True,              # 손실은 주제 코드에만
            eos_token="<|im_end|>",
            eval_strategy="no" if MAX_STEPS > 0 else "epoch",
            logging_steps=20,
            save_strategy="steps",                  # 100 step마다 체크포인트. 중단되면 `python -m training.router.train outputs/<시각>/checkpoint-N`으로 이어서
            save_steps=100,
            save_total_limit=1,
            report_to="none",
        ),
    )
    trainer.train(resume_from_checkpoint=sys.argv[1] if len(sys.argv) > 1 else None)
    if MAX_STEPS < 0:
        print("val:", trainer.evaluate())
    trainer.save_model(str(OUT_DIR / "adapter"))
    tokenizer.save_pretrained(str(OUT_DIR / "adapter"))
    print(f"adapter → {OUT_DIR / 'adapter'}")


if __name__ == "__main__":
    main()
