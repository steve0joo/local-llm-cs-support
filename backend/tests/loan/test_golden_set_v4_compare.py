"""training/loan/golden_set_v4_compare.jsonl — v4 비교용 새 문항 20개 (2026-09-30, v4 시드 해시 고정 뒤에 작성).

v3 평가에서 확인한 결함 유형(범위 밖, 처리 요청, 조건+해당 여부, 손해·이득, 수수료↔금리, 원금+상환액)과 정상 질문(과다 거절 확인)으로
구성한다. v4 응답을 보기 전에 만들었다. 시드·기존 평가 세트·최종 확인용 10문항과 유사도 0.75 미만이어야 한다(짧고 흔한 질문 제외).
"""
import collections
import difflib
import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "training" / "loan"


def _load(name):
    return [json.loads(l) for l in (ROOT / name).read_text(encoding="utf-8").splitlines() if l.strip()]


def _module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_v2 = _module("v2_golden", "test_golden_set.py")
_final = _module("final_v4", "test_golden_set_final_v4.py")
ROWS = _load("golden_set_v4_compare.jsonl")
CODES = {"no_fabrication", "no_direction", "no_cause_claim", "no_commit", "no_echo_token", "polite", "slot_extend", "slot_principal",
         "date", "refer", "topic_fee", "topic_rate"}
TYPES = {"범위밖", "처리요청", "조건", "손해이득", "수수료", "금리", "복합", "기본"}


def _norm(t):
    return re.sub(r"[\s?.!,]", "", t)


def test_sizes_tags_and_schema():
    assert [r["id"] for r in ROWS] == [f"K{i:02d}" for i in range(1, 21)]
    for r in ROWS:
        assert r["source"] == "author" and r["tag"] == "compare-v4" and r["model_eval"] is True
        assert r["customer"] in {"C002", "C003"} and r["question"].strip() and r["type"] in TYPES
        assert r["register"] in {"존댓말", "반말", "단어형"} and isinstance(r["history"], list)
        assert set(r["must"]) | set(r["record"]) <= CODES and not set(r["must"]) & set(r["record"]), r["id"]
        assert "polite" in r["must"], r["id"]  # PM 기준: 존댓말은 모두 필수
        for turn in r["history"]:
            assert turn["role"] in {"user", "assistant"} and turn["content"]


def test_composition_covers_the_v3_defects_and_normal_questions():
    types = collections.Counter(r["type"] for r in ROWS)
    assert types["범위밖"] >= 3 and types["처리요청"] >= 2 and types["조건"] >= 2 and types["손해이득"] >= 2
    assert types["수수료"] >= 1 and types["금리"] >= 1 and types["복합"] >= 1
    normal = [r for r in ROWS if r["type"] == "기본"]
    assert len(normal) >= 6 and all({"date", "slot_principal", "slot_extend"} & set(r["must"]) for r in normal)  # 사실을 답해야 하는 정상 질문
    assert sum(bool(r["history"]) for r in ROWS) == 2  # 멀티턴
    assert sum(r["register"] == "반말" for r in ROWS) >= 2


def test_topic_codes_guard_the_fee_rate_confusion():
    assert any("topic_fee" in r["must"] for r in ROWS) and any("topic_rate" in r["must"] for r in ROWS)


@pytest.mark.parametrize("row", ROWS, ids=lambda r: r["id"])
def test_question_stays_below_075_against_seeds_and_every_eval_set(row):
    q = _norm(row["question"])
    if len(q) <= 8:  # 짧고 흔한 질문은 기각하지 않는다
        return
    seeds = _load("manual_seed_v4.jsonl")
    pool = (
        [_norm(s["question"]) for s in seeds] + [_norm(s["follow_up_question"]) for s in seeds if s["follow_up_question"]]
        + [_norm(r["question"]) for r in _load("golden_set_risk.jsonl")]
        + [_norm(g["question"]) for g in _v2.GOLDEN] + [_norm(g["question"]) for g in _load("golden_set_v3.jsonl")]
        + [_norm(d) for d in _v2.DEV_QUESTIONS] + [_norm(f) for f in _final.FINAL_QUESTIONS]
    )
    for other in pool:
        ratio = difflib.SequenceMatcher(None, q, other).ratio()
        assert q != other and ratio < 0.75, (row["question"], other, round(ratio, 2))


def test_criteria_file_records_the_frozen_hash_before_these_questions():
    text = (ROOT.parents[2] / "docs" / "agent-loan" / "EVAL_CRITERIA_v4.md").read_text(encoding="utf-8")
    assert "golden_set_v4_compare.jsonl" in text and "고정 해시" in text
