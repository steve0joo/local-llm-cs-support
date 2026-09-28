"""cs-interest QLoRA 학습.

입력: prepare.py가 만든 data/processed/interest/{train,val}.jsonl
출력: training/interest/outputs/runs/v<NN>-<날짜-시각>[-태그]/ (gitignore, 자동 버전·덮어쓰기 금지)
  adapter/(LoRA 가중치·토크나이저), run_info.json, settings.json, log_history.json, data_stats.json
  버전 목록: outputs/runs/index.jsonl

실행(학습 장비, training/interest/.venv):
  cd backend && training/interest/.venv/bin/python -m training.interest.train
  짧은 확인: ... -m training.interest.train --max-steps 5
  변환 미리보기(모델 로드 없음): ... -m training.interest.train --dry-run

채팅 템플릿은 공식 Qwen/Qwen3-4B-Instruct-2507 것(chat_template.jinja)을 쓴다. unsloth 체크포인트에 딸린
템플릿은 학습 때만 마지막 답변 앞에 빈 <think> 블록을 넣어(unslothai/unsloth#3383) 학습·추론이 어긋난다.
"""

import argparse
import hashlib
import json
import math
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND / "data/processed/interest"
OUTPUT_DIR = BACKEND / "training/interest/outputs"
RUNS_DIR = OUTPUT_DIR / "runs"

DEFAULT_BASE_MODEL = "unsloth/Qwen3-4B-Instruct-2507-unsloth-bnb-4bit"
CHAT_TEMPLATE_FILE = Path(__file__).resolve().parent / "chat_template.jinja"
LORA_TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


@dataclass
class TrainSettings:
    base_model: str = DEFAULT_BASE_MODEL
    data_dir: Path = DATA_DIR
    output_dir: Path | None = None  # None이면 RUNS_DIR 아래 새 버전 폴더
    tag: str = ""  # 버전 폴더 이름 끝에 붙는 설명(예: 04)
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    learning_rate: float = 1e-4  # 어댑터 학습 권장값(TRL SFT 문서)
    epochs: float = 2
    max_steps: int = -1  # 양수면 epochs 대신 이 스텝만 돈다(동작 확인용)
    max_length: int = 1024
    batch_size: int = 2
    grad_accum: int = 8  # 유효 배치 16
    seed: int = 42
    target_modules: list[str] = field(default_factory=lambda: list(LORA_TARGET_MODULES))
    dry_run: bool = False


def summarize_log(log_history: list[dict]) -> dict:
    """학습 안정성 요약(EVALUATION.md 질문 1): train/eval loss, grad_norm, learning_rate."""
    train = [h["loss"] for h in log_history if "loss" in h]
    evals = [{"epoch": h.get("epoch"), "loss": h["eval_loss"]} for h in log_history if "eval_loss" in h]
    grads = [h["grad_norm"] for h in log_history if "grad_norm" in h]
    lrs = [h["learning_rate"] for h in log_history if "learning_rate" in h]
    return {
        "train_loss": {"first": train[0], "last": train[-1], "min": min(train)} if train else None,
        "eval_loss": evals,
        "eval_loss_rising": len(evals) > 1 and evals[-1]["loss"] > min(e["loss"] for e in evals),
        "grad_norm": {"max": max(grads), "last": grads[-1], "nan": any(math.isnan(g) for g in grads)} if grads else None,
        "learning_rate": {"first": lrs[0], "max": max(lrs), "last": lrs[-1]} if lrs else None,
    }


_RUN_NAME = re.compile(r"^v(\d{2,})-")


def next_run_dir(runs_dir: Path, tag: str = "", now: datetime | None = None) -> Path:
    """다음 버전 폴더 경로: v<NN>-<YYYYMMDD-HHMM>[-tag]. 번호는 기존 최대값 + 1."""
    runs_dir = Path(runs_dir)
    numbers = [int(m.group(1)) for d in runs_dir.glob("v*") if (m := _RUN_NAME.match(d.name))] if runs_dir.exists() else []
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M")
    return runs_dir / (f"v{max(numbers, default=0) + 1:02d}-{stamp}" + (f"-{tag}" if tag else ""))


def ensure_new_run_dir(run_dir: Path) -> Path:
    """학습 결과를 덮어쓰지 않는다. 이미 어댑터가 있으면 멈춘다."""
    if (Path(run_dir) / "adapter").exists():
        raise FileExistsError(f"{run_dir}에 이미 학습 결과가 있다. 다른 --output-dir이나 --tag를 쓴다.")
    Path(run_dir).mkdir(parents=True, exist_ok=True)
    return Path(run_dir)


def _git_state() -> dict:
    def run(*args):
        try:
            return subprocess.run(["git", *args], cwd=BACKEND, capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None

    return {"git_commit": run("rev-parse", "HEAD"), "git_dirty": bool(run("status", "--porcelain"))}


def write_run_info(s: "TrainSettings", run_dir: Path, metrics: dict, log_summary: dict, runs_dir: Path = RUNS_DIR) -> dict:
    """어떤 데이터·코드·설정으로 만든 모델인지 버전 폴더에 남기고 버전 목록(index.jsonl)에 추가한다."""
    data_dir = Path(s.data_dir)
    info = {
        "version": run_dir.name,
        "created": datetime.now().isoformat(timespec="seconds"),
        "tag": s.tag,
        "base_model": s.base_model,
        "data_dir": str(data_dir),
        "data_sha256": {
            name: hashlib.sha256((data_dir / name).read_bytes()).hexdigest()
            for name in ("train.jsonl", "val.jsonl")
            if (data_dir / name).exists()
        },
        "settings": {k: v for k, v in asdict(s).items() if k not in ("data_dir", "output_dir")},
        "metrics": metrics,
        "log_summary": log_summary,
        **_git_state(),
    }
    (run_dir / "run_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    for src, dst in (("stats.json", "data_stats.json"), ("_manifest.json", "data_manifest.json")):
        if (data_dir / src).exists():
            (run_dir / dst).write_bytes((data_dir / src).read_bytes())
    runs_dir.mkdir(parents=True, exist_ok=True)
    summary = {k: info[k] for k in ("version", "created", "tag", "base_model", "data_dir", "git_commit")}
    summary["eval_loss"] = metrics.get("eval_loss")
    with (runs_dir / "index.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(summary, ensure_ascii=False, default=str) + "\n")
    return info


def load_chat_template() -> str:
    return CHAT_TEMPLATE_FILE.read_text(encoding="utf-8")


def load_tokenizer(base_model: str):
    """공식 채팅 템플릿을 입힌 토크나이저. 학습·평가가 같이 쓴다."""
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(base_model)
    tokenizer.chat_template = load_chat_template()
    return tokenizer


def preview(s: "TrainSettings") -> None:
    """학습 샘플 1건의 템플릿 적용 결과와 학습 대상(completion) 구간을 출력한다."""
    tokenizer = load_tokenizer(s.base_model)
    row = load_split(s.data_dir, "train")[0]
    prompt = tokenizer.apply_chat_template(row["prompt"], tokenize=False, add_generation_prompt=True)
    full = tokenizer.apply_chat_template(row["prompt"] + row["completion"], tokenize=False)
    assert full.startswith(prompt), "프롬프트가 전체 대화의 앞부분과 다르다"
    print("=== prompt (loss 제외) 끝부분 ===\n" + prompt[-300:])
    print("=== completion (학습 대상) ===\n" + full[len(prompt):])
    print(f"<think> 포함: {'<think>' in full} | eos: {tokenizer.eos_token} | pad: {tokenizer.pad_token}")


def to_prompt_completion(sample: dict) -> dict:
    """마지막 assistant 턴만 completion으로 둔다. TRL은 completion에만 loss를 건다."""
    messages = sample["messages"]
    if not messages or messages[-1]["role"] != "assistant":
        raise ValueError(f"마지막 메시지가 assistant가 아니다: {sample.get('qa_id')}")
    return {"prompt": messages[:-1], "completion": [messages[-1]]}


def load_split(data_dir: Path, split: str) -> list[dict]:
    path = Path(data_dir) / f"{split}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"{path}가 없다. 먼저 `python -m training.interest.prepare`를 실행한다.")
    lines = path.read_text(encoding="utf-8").splitlines()
    return [to_prompt_completion(json.loads(line)) for line in lines if line.strip()]


def parse_args(argv: list[str] | None = None) -> TrainSettings:
    d = TrainSettings()
    p = argparse.ArgumentParser(description="cs-interest QLoRA 학습")
    p.add_argument("--base-model", default=d.base_model)
    p.add_argument("--data-dir", type=Path, default=d.data_dir)
    p.add_argument("--output-dir", type=Path, default=d.output_dir, help="생략하면 outputs/runs/ 아래 새 버전 폴더")
    p.add_argument("--tag", default=d.tag, help="버전 폴더 이름에 붙일 설명")
    p.add_argument("--epochs", type=float, default=d.epochs)
    p.add_argument("--max-steps", type=int, default=d.max_steps)
    p.add_argument("--learning-rate", type=float, default=d.learning_rate)
    p.add_argument("--lora-r", type=int, default=d.lora_r)
    p.add_argument("--max-length", type=int, default=d.max_length)
    p.add_argument("--dry-run", action="store_true", help="템플릿 적용 결과만 출력하고 끝낸다")
    a = p.parse_args(argv)
    return TrainSettings(
        base_model=a.base_model,
        data_dir=a.data_dir,
        output_dir=a.output_dir,
        tag=a.tag,
        epochs=a.epochs,
        max_steps=a.max_steps,
        learning_rate=a.learning_rate,
        lora_r=a.lora_r,
        lora_alpha=a.lora_r * 2,
        max_length=a.max_length,
        dry_run=a.dry_run,
    )


def train(s: TrainSettings) -> Path:
    # 무거운 의존성은 학습 장비에서만 필요하다(테스트·앱 환경에는 없음).
    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM
    from trl import SFTConfig, SFTTrainer

    run_dir = ensure_new_run_dir(s.output_dir or next_run_dir(RUNS_DIR, s.tag))
    print(f"run: {run_dir}")
    train_rows, val_rows = load_split(s.data_dir, "train"), load_split(s.data_dir, "val")
    print(f"train {len(train_rows)} / val {len(val_rows)} | base {s.base_model}")

    tokenizer = load_tokenizer(s.base_model)
    # unsloth bnb-4bit 체크포인트는 config에 4bit 양자화 설정이 들어 있어 그대로 QLoRA 베이스가 된다.
    model = AutoModelForCausalLM.from_pretrained(s.base_model, dtype=torch.bfloat16, device_map={"": 0})

    peft_config = LoraConfig(
        r=s.lora_r,
        lora_alpha=s.lora_alpha,
        lora_dropout=s.lora_dropout,
        target_modules=s.target_modules,
        task_type="CAUSAL_LM",
    )
    args = SFTConfig(
        output_dir=str(run_dir / "checkpoints"),
        num_train_epochs=s.epochs,
        max_steps=s.max_steps,
        per_device_train_batch_size=s.batch_size,
        per_device_eval_batch_size=s.batch_size,
        gradient_accumulation_steps=s.grad_accum,
        learning_rate=s.learning_rate,
        lr_scheduler_type="cosine",
        warmup_steps=0.05,
        max_length=s.max_length,
        completion_only_loss=True,
        eos_token="<|im_end|>",  # 답변 끝을 템플릿의 턴 종료와 맞춘다(TRL SFT 문서)
        gradient_checkpointing=True,
        bf16=True,
        eval_strategy="epoch" if s.max_steps < 0 else "no",
        save_strategy="epoch" if s.max_steps < 0 else "no",
        load_best_model_at_end=s.max_steps < 0,
        metric_for_best_model="eval_loss",
        save_total_limit=2,
        logging_steps=5,
        report_to="none",
        seed=s.seed,
    )
    trainer = SFTTrainer(
        model=model,
        args=args,
        train_dataset=Dataset.from_list(train_rows),
        eval_dataset=Dataset.from_list(val_rows),
        processing_class=tokenizer,
        peft_config=peft_config,
    )
    trainer.train()

    adapter_dir = run_dir / "adapter"
    trainer.save_model(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    metrics = trainer.evaluate() if val_rows else {}
    log_history = trainer.state.log_history
    (run_dir / "log_history.json").write_text(json.dumps(log_history, ensure_ascii=False, indent=2), encoding="utf-8")
    log_summary = summarize_log(log_history)
    (run_dir / "settings.json").write_text(
        json.dumps({**asdict(s), "metrics": metrics, "log_summary": log_summary}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    write_run_info(s, run_dir, metrics, log_summary)
    print(f"saved {adapter_dir} | {metrics}")
    return adapter_dir


if __name__ == "__main__":
    settings = parse_args()
    preview(settings) if settings.dry_run else train(settings)
