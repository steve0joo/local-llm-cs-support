import argparse
import json
from pathlib import Path

import pytest

from training.balance.train import build_command, check_dataset, check_model


def _write_chat(path: Path, answer: str = "{{account_label}} 계좌의 잔액은 {{balance}}입니다.") -> None:
    path.write_text(
        json.dumps({"messages": [
            {"role": "user", "content": "잔액 알려줘"},
            {"role": "assistant", "content": answer},
        ]}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def test_check_dataset_requires_train_and_valid_and_keeps_test_separate(tmp_path):
    _write_chat(tmp_path / "train.jsonl")
    _write_chat(tmp_path / "valid.jsonl")
    assert check_dataset(tmp_path, "train") == {"train": 1, "valid": 1}
    with pytest.raises(ValueError, match="test.jsonl"):
        check_dataset(tmp_path, "test")


def test_check_dataset_rejects_bad_target(tmp_path):
    _write_chat(tmp_path / "train.jsonl")
    _write_chat(tmp_path / "valid.jsonl", answer=" ")
    with pytest.raises(ValueError, match="대화 역할·내용"):
        check_dataset(tmp_path, "train")


def test_check_model_requires_quantized_local_base(tmp_path):
    (tmp_path / "config.json").write_text('{"model_type":"qwen2"}', encoding="utf-8")
    with pytest.raises(ValueError, match="양자화"):
        check_model(tmp_path)
    (tmp_path / "config.json").write_text(
        '{"model_type":"qwen2","quantization":{"group_size":64,"bits":4}}',
        encoding="utf-8",
    )
    check_model(tmp_path)


def test_train_command_masks_prompt_and_test_does_not_train(tmp_path):
    args = argparse.Namespace(model=tmp_path / "model", data=tmp_path / "data",
                              adapter_path=tmp_path / "adapters", batch_size=1,
                              max_seq_length=1024, iters=10, num_layers=8, mode="train")
    command = build_command(args)
    assert "--train" in command and "--mask-prompt" in command
    args.mode = "test"
    command = build_command(args)
    assert "--test" in command and "--train" not in command
