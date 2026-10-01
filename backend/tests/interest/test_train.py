import json

import pytest

from training.interest.train import (
    CHAT_TEMPLATE_FILE,
    load_chat_template,
    DEFAULT_BASE_MODEL,
    LORA_TARGET_MODULES,
    TrainSettings,
    load_split,
    parse_args,
    to_prompt_completion,
)

SAMPLE = {
    "source_id": "S1",
    "qa_id": "S1_001",
    "messages": [
        {"role": "system", "content": "시스템"},
        {"role": "user", "content": "질문"},
        {"role": "assistant", "content": "중간 답변"},
        {"role": "user", "content": "후속 질문\n이자 정보: 종류=신용대출"},
        {"role": "assistant", "content": "납부 예정 이자는 {{interest_due}}입니다."},
    ],
}


def test_only_last_assistant_turn_is_completion():
    # 중간 answer 턴은 정제하지 않은 원문이라 학습 대상(loss)에서 뺀다.
    row = to_prompt_completion(SAMPLE)
    assert row["prompt"] == SAMPLE["messages"][:-1]
    assert row["completion"] == [SAMPLE["messages"][-1]]
    assert set(row) == {"prompt", "completion"}


def test_rejects_sample_not_ending_with_assistant():
    bad = {**SAMPLE, "messages": SAMPLE["messages"][:-1]}
    with pytest.raises(ValueError):
        to_prompt_completion(bad)


def test_load_split_reads_jsonl(tmp_path):
    (tmp_path / "train.jsonl").write_text(
        json.dumps(SAMPLE, ensure_ascii=False) + "\n\n" + json.dumps(SAMPLE, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    rows = load_split(tmp_path, "train")
    assert len(rows) == 2
    assert rows[0]["completion"][0]["content"] == "납부 예정 이자는 {{interest_due}}입니다."


def test_load_split_missing_file_says_run_prepare(tmp_path):
    with pytest.raises(FileNotFoundError, match="prepare"):
        load_split(tmp_path, "train")


def test_defaults():
    s = parse_args([])
    assert s == TrainSettings()
    assert s.base_model == DEFAULT_BASE_MODEL == "unsloth/Qwen3-4B-Instruct-2507-unsloth-bnb-4bit"
    assert (s.lora_r, s.lora_alpha, s.lora_dropout) == (16, 32, 0.05)
    # 어댑터 학습 권장 학습률 ≈1e-4(TRL SFT 문서). 3 epoch·2e-4는 AI Hub 실험에서 베이스 능력을 덮어썼다.
    assert s.learning_rate == 1e-4 and s.epochs == 2 and s.max_length == 1024
    assert s.batch_size * s.grad_accum == 16
    assert s.max_steps == -1
    assert set(LORA_TARGET_MODULES) == {"q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"}


def test_default_output_is_new_versioned_run():
    # 출력 폴더를 안 주면 outputs/runs/ 아래 새 버전 폴더를 자동으로 만든다(.gitignore: backend/training/**/outputs/).
    from training.interest.train import RUNS_DIR

    s = parse_args([])
    assert s.output_dir is None and s.tag == ""
    assert RUNS_DIR.parts[-4:] == ("training", "interest", "outputs", "runs")
    assert parse_args(["--tag", "04"]).tag == "04"


def test_next_run_dir(tmp_path):
    from datetime import datetime

    from training.interest.train import next_run_dir

    now = datetime(2026, 9, 28, 16, 55)
    assert next_run_dir(tmp_path, "", now).name == "v01-20260928-1655"
    for name in ("v01-20260927-0900-a", "v03-20260928-1000", "notes", "v1-bad"):
        (tmp_path / name).mkdir()
    assert next_run_dir(tmp_path, "04", now).name == "v04-20260928-1655-04"


def test_ensure_new_run_dir_never_overwrites(tmp_path):
    from training.interest.train import ensure_new_run_dir

    run = tmp_path / "v01"
    ensure_new_run_dir(run)
    assert run.is_dir()
    (run / "adapter").mkdir()
    with pytest.raises(FileExistsError):
        ensure_new_run_dir(run)


def test_write_run_info_records_data_and_index(tmp_path):
    from training.interest.train import write_run_info

    data = tmp_path / "data"
    data.mkdir()
    (data / "train.jsonl").write_text('{"a": 1}\n', encoding="utf-8")
    (data / "val.jsonl").write_text('{"b": 2}\n', encoding="utf-8")
    (data / "stats.json").write_text('{"used": 1}', encoding="utf-8")
    (data / "_manifest.json").write_text('{"note": "x"}', encoding="utf-8")
    runs = tmp_path / "runs"
    run = runs / "v01-20260928-1655-04"
    run.mkdir(parents=True)
    s = TrainSettings(data_dir=data, output_dir=run, tag="04")

    info = write_run_info(s, run, metrics={"eval_loss": 0.8}, log_summary={"eval_loss_rising": False}, runs_dir=runs)

    assert info["version"] == "v01-20260928-1655-04" and info["tag"] == "04"
    assert set(info["data_sha256"]) == {"train.jsonl", "val.jsonl"} and len(info["data_sha256"]["train.jsonl"]) == 64
    assert info["metrics"] == {"eval_loss": 0.8} and "git_commit" in info
    assert json.loads((run / "run_info.json").read_text(encoding="utf-8"))["version"] == info["version"]
    assert (run / "data_stats.json").exists() and (run / "data_manifest.json").exists()
    [line] = (runs / "index.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(line)["version"] == info["version"]


def test_cli_overrides(tmp_path):
    s = parse_args(["--base-model", "Qwen/Qwen3-1.7B", "--epochs", "1", "--max-steps", "5", "--output-dir", str(tmp_path)])
    assert s.base_model == "Qwen/Qwen3-1.7B"
    assert s.epochs == 1 and s.max_steps == 5
    assert s.output_dir == tmp_path


def test_chat_template_is_official_qwen_without_think():
    # unsloth 체크포인트의 템플릿은 학습 때만 마지막 답변 앞에 빈 <think> 블록을 넣는다
    # (unslothai/unsloth#3383). 추론 때는 넣지 않아 모델이 이상한 토큰을 먼저 내보냈다.
    # 공식 Qwen/Qwen3-4B-Instruct-2507 템플릿으로 학습·평가·서빙을 맞춘다.
    template = load_chat_template()
    assert CHAT_TEMPLATE_FILE.parent.parts[-2:] == ("training", "interest")
    assert "<think>" not in template and "reasoning_content" not in template
    assert "{{- '<|im_start|>' + message.role + '\\n' + content }}" in template
    assert "{{- '<|im_start|>assistant\\n' }}" in template  # add_generation_prompt


def test_summarize_log_history():
    # EVALUATION.md 질문 1: train/eval loss, grad_norm, learning_rate를 실험 폴더에 남긴다.
    from training.interest.train import summarize_log

    log = [
        {"loss": 1.3, "grad_norm": 0.6, "learning_rate": 1e-4, "step": 5},
        {"loss": 1.0, "grad_norm": 0.5, "learning_rate": 8e-5, "step": 10},
        {"eval_loss": 0.95, "epoch": 1.0, "step": 12},
        {"loss": 0.8, "grad_norm": 2.5, "learning_rate": 2e-5, "step": 15},
        {"eval_loss": 0.99, "epoch": 2.0, "step": 24},
        {"train_runtime": 100.0, "step": 24},
    ]
    s = summarize_log(log)
    assert s["train_loss"] == {"first": 1.3, "last": 0.8, "min": 0.8}
    assert s["eval_loss"] == [{"epoch": 1.0, "loss": 0.95}, {"epoch": 2.0, "loss": 0.99}]
    assert s["eval_loss_rising"] is True  # 과적합 징후
    assert s["grad_norm"] == {"max": 2.5, "last": 2.5, "nan": False}
    assert s["learning_rate"] == {"first": 1e-4, "max": 1e-4, "last": 2e-5}


def test_preview_row_skips_aihub(tmp_path):
    # --dry-run 출력이 AI Hub 원문을 화면·로그에 남기지 않게 합성·수동 샘플을 보여 준다(데이터 제3자 제공 금지).
    import json

    from training.interest.train import preview_row

    def rec(origin, text):
        return {"origin": origin, "messages": [{"role": "user", "content": "q"}, {"role": "assistant", "content": text}]}

    (tmp_path / "train.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in [rec("aihub", "원문"), rec("synth", "합성 답")]),
        encoding="utf-8")
    row = preview_row(tmp_path)
    assert row["completion"][0]["content"] == "합성 답"

    (tmp_path / "train.jsonl").write_text(json.dumps(rec("aihub", "원문"), ensure_ascii=False) + "\n", encoding="utf-8")
    import pytest

    with pytest.raises(ValueError):
        preview_row(tmp_path)  # AI Hub만 있으면 출력하지 않는다


def test_wandb_reporting_is_opt_in(tmp_path, monkeypatch):
    # 학습 곡선(loss·grad_norm·학습률, 숫자만)을 개인 wandb 프로젝트에 올린다. 기본은 끔.
    from training.interest.train import OUTPUT_DIR, TrainSettings, report_settings

    monkeypatch.delenv("WANDB_PROJECT", raising=False)
    monkeypatch.delenv("WANDB_DIR", raising=False)
    assert report_settings(TrainSettings(), tmp_path / "v04-x") == {"report_to": "none"}
    got = report_settings(TrainSettings(wandb=True), tmp_path / "v04-x")
    assert got == {"report_to": "wandb", "run_name": "train-v04-x"}
    import os

    assert os.environ["WANDB_PROJECT"] == "cs-interest"
    assert os.environ["WANDB_DIR"] == str(OUTPUT_DIR)  # 로컬 기록은 gitignore 폴더(outputs/wandb/)
    assert parse_args(["--wandb"]).wandb is True and parse_args([]).wandb is False
