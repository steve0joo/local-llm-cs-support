"""training/loan/wandb_backfill.py — 저장된 trainer_state를 HF wandb 콜백과 같은 키 이름으로 바꾼다(업로드는 하지 않고 변환만 검사)."""
import importlib.util
import json
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("wandb_backfill", Path(__file__).resolve().parents[2] / "training" / "loan" / "wandb_backfill.py")
backfill = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backfill)


def test_keys_follow_the_hf_wandb_callback_names():
    got = backfill.to_wandb_keys({"step": 10, "loss": 0.5, "eval_loss": 0.1, "eval_mean_token_accuracy": 0.9, "learning_rate": 2e-4, "note": "x"})
    assert got == {"train/loss": 0.5, "eval/loss": 0.1, "eval/mean_token_accuracy": 0.9, "train/learning_rate": 2e-4}  # step·문자열은 제외


def test_history_is_read_from_the_latest_checkpoint(tmp_path):
    for step, hist in ((88, [{"step": 88}]), (176, [{"step": 176}]), (264, [{"step": 264}])):
        d = tmp_path / f"checkpoint-{step}"
        d.mkdir()
        (d / "trainer_state.json").write_text(json.dumps({"log_history": hist}), encoding="utf-8")
    assert backfill.load_history(tmp_path) == [{"step": 264}]  # 문자열 정렬이 아니라 숫자 정렬


def test_missing_checkpoints_stop_with_a_clear_message(tmp_path):
    with pytest.raises(SystemExit):
        backfill.load_history(tmp_path)
