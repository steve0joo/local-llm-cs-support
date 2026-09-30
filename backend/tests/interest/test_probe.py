import json
from pathlib import Path

from training.interest.ask import TEST_QUESTIONS
from training.interest.evaluate import EXPECT_CODES, GOLDEN
from training.interest.manual_data import load_manual
from training.interest.probe import PROBE_QUESTIONS, build_probe_cases, wandb_payload
from training.interest.synth import TEMPLATES

MOCK = json.loads((Path(__file__).resolve().parents[2] / "app/agents/interest/mock_data.json").read_text(encoding="utf-8"))


def test_forty_new_questions_cover_customers_and_types():
    assert len(PROBE_QUESTIONS) == 20
    assert {c for c, _, _ in PROBE_QUESTIONS} == {"C002", "C003"}
    assert {e for _, _, e in PROBE_QUESTIONS} <= set(EXPECT_CODES)
    assert len({e for _, _, e in PROBE_QUESTIONS}) >= 12


def test_questions_are_new():
    # 평가·수동 테스트·학습 템플릿·수동 학습 샘플과 겹치면 외운 것과 배운 것을 구분할 수 없다.
    used = (
        {q for _, q, _ in GOLDEN}
        | {q for _, q, _ in TEST_QUESTIONS}
        | {q for t in TEMPLATES for q in t.questions}
        | {q for t in TEMPLATES for q, _ in t.history}
        | {r["question"] for r in load_manual()}
    )
    probe = [q for _, q, _ in PROBE_QUESTIONS]
    assert not set(probe) & used
    assert len(probe) == len(set(probe))


def test_cases_use_inference_prompt():
    cases = build_probe_cases(MOCK)
    assert len(cases) == 20
    for c in cases:
        assert c["set"] == "probe" and c["expect"] in EXPECT_CODES
        assert c["messages"][-1]["content"].startswith(c["question"] + "\n이자 정보: ")


def test_wandb_payload_has_numbers_only():
    rows = [
        {"set": "probe", "id": "probe-01", "customer": "C002", "expect": "due_date", "question": "비밀 질문", "answer": "비밀 답",
         "seconds": 2.0, "score": {"valid": True, "slot": False, "forbidden": [], "length": 30, "tone": True,
                                   "expect": True, "rule": True}},
        {"set": "probe", "id": "probe-02", "customer": "C003", "expect": "rate", "question": "q", "answer": "a",
         "seconds": 4.0, "score": {"valid": True, "slot": True, "forbidden": ["%"], "length": 50, "tone": True,
                                   "expect": False, "rule": False}},
    ]
    summary, per_category, table_rows, columns = wandb_payload(rows)
    assert summary["rule"] == 0.5 and summary["avg_seconds"] == 3.0 and summary["n"] == 2
    assert per_category == {"category/due_date": 1.0, "category/rate": 0.0}
    assert "question" not in columns and "answer" not in columns  # 원문은 올리지 않는다
    assert "비밀" not in json.dumps(table_rows, ensure_ascii=False)
    assert table_rows[1][columns.index("forbidden_count")] == 1


def test_wandb_local_files_go_to_gitignored_outputs(monkeypatch, tmp_path):
    # wandb는 실행 기록을 dir/wandb/에 남긴다. 저장소 안(backend/wandb/)에 남으면 커밋될 수 있다.
    import sys
    import types

    from training.interest import probe

    calls = {}

    class Run:
        url = "https://wandb.ai/x"
        summary = {}

        def log(self, data):
            calls["log"] = data

        def finish(self):
            calls["finished"] = True

    fake = types.SimpleNamespace(init=lambda **kw: calls.update(init=kw) or Run(), Table=lambda **kw: kw)
    monkeypatch.setitem(sys.modules, "wandb", fake)
    rows = [{"set": "probe", "id": "probe-01", "customer": "C002", "expect": "due_date", "question": "q", "answer": "a",
             "seconds": 1.0, "score": {"valid": True, "slot": True, "forbidden": [], "length": 10, "tone": True,
                                       "expect": True, "rule": True}}]
    probe.log_to_wandb(rows, "t", "base-model", None)

    wandb_dir = Path(calls["init"]["dir"])
    assert wandb_dir.parts[-3:] == ("training", "interest", "outputs")
    assert calls["finished"]
