"""저장된 학습 기록(trainer_state.json)을 wandb 런으로 옮긴다. 재학습 없이 v3 곡선을 wandb에 남길 때 쓴다.

올라가는 것은 손실·학습률·grad_norm 같은 숫자와 하이퍼파라미터뿐이다. 학습 데이터 원문·모델·코드는 올리지 않는다.
키 이름은 HF wandb 콜백과 같게(train/…, eval/…) 맞춰서 v2 런과 같은 차트에 겹쳐 볼 수 있다.

    cd backend
    .venv/bin/python training/loan/wandb_backfill.py --dry-run     # 변환 결과만 출력(업로드 안 함)
    .venv/bin/python training/loan/wandb_backfill.py               # wandb login 된 계정으로 온라인 업로드
"""
import argparse
import glob
import json
from pathlib import Path


def load_history(out_dir: Path) -> list[dict]:
    states = sorted(glob.glob(str(out_dir / "checkpoint-*" / "trainer_state.json")), key=lambda p: int(p.split("checkpoint-")[1].split("/")[0]))
    if not states:
        raise SystemExit(f"{out_dir}에 checkpoint-*/trainer_state.json이 없습니다")
    return json.loads(Path(states[-1]).read_text(encoding="utf-8"))["log_history"]


def to_wandb_keys(entry: dict) -> dict:
    """HF wandb 콜백과 같은 이름: eval_x → eval/x, 그 외 → train/x. step은 x축으로 따로 넘긴다."""
    out = {}
    for key, value in entry.items():
        if key == "step" or not isinstance(value, (int, float)):
            continue
        out[("eval/" + key[len("eval_"):]) if key.startswith("eval_") else "train/" + key] = value
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("training/loan/outputs_v3"))
    parser.add_argument("--project", default="cs-loan")
    parser.add_argument("--name", default="outputs_v3")
    parser.add_argument("--dry-run", action="store_true", help="업로드하지 않고 변환 결과만 출력")
    args = parser.parse_args()

    history = load_history(args.out)
    steps = [(e["step"], to_wandb_keys(e)) for e in history if "step" in e and "train_runtime" not in e]
    summary = to_wandb_keys(next((e for e in history if "train_runtime" in e), {}))
    config = {  # train.py 기본값과 v3 데이터 규모. 실제 실행 인자는 outputs_v3_train.log 첫머리와 같다.
        "base_model": "Qwen/Qwen3-4B-Instruct-2507", "method": "QLoRA", "lora_r": 16, "lora_alpha": 32, "lora_dropout": 0.05,
        "learning_rate": 2e-4, "epochs": 3, "micro_batch_size": 1, "grad_accum": 16, "seed": 42,
        "train_rows": 1145, "val_rows": 185, "manual_seed_rows": 350, "manual_copies": 3,
        "train_runtime_s": 2222, "train_loss_mean": 0.2434,  # trainer_state에는 없고 outputs_v3_train.log 마지막 줄에 있다
        "backfilled_from": "trainer_state.json",
    }

    if args.dry_run:
        print(f"기록 {len(steps)}개, 요약 {summary}")
        for step, metrics in steps[:3] + steps[-2:]:
            print(step, metrics)
        return

    import wandb

    run = wandb.init(project=args.project, name=args.name, config=config, tags=["backfilled"],
                     notes="학습 종료 후 trainer_state.json에서 옮긴 런(실시간 기록 아님, 시스템 지표 없음)")
    for step, metrics in steps:
        run.log(metrics, step=step)
    for key, value in summary.items():
        run.summary[key] = value
    run.finish()


if __name__ == "__main__":
    main()
