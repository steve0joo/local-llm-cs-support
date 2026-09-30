"""training/loan/golden_set_v3.jsonl — v3 개선 효과를 재는 새 문항 20건.

v2 Golden Set(golden_set.jsonl)에서 드러난 약점(복합 질문 누락, 수수료 주제 어긋남, 전반 조회 회피)을 겨냥한다.
시드와 겹치면 개선이 아니라 암기이므로, 시드·기존 Golden Set·개발 질문 어느 쪽과도 겹치지 않아야 한다.
시드를 새로 만들 때도 이 테스트가 통과해야 한다.
"""
import collections
import difflib
import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "training" / "loan"


def _load_jsonl(name: str) -> list[dict]:
    return [json.loads(l) for l in (ROOT / name).read_text(encoding="utf-8").splitlines() if l.strip()]


# tests/loan에는 __init__.py가 없어서(importlib 모드) 형제 테스트 파일은 경로로 불러온다.
_spec = importlib.util.spec_from_file_location("golden_v2_tests", Path(__file__).with_name("test_golden_set.py"))
_v2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_v2)

GOLDEN_V3 = _load_jsonl("golden_set_v3.jsonl")
GOLDEN_V2 = _v2.GOLDEN
SEEDS = _load_jsonl("manual_seed.jsonl")
DEV_QUESTIONS = _v2.DEV_QUESTIONS
EXPECT_CODES = _v2.EXPECT_CODES
CUSTOMERS = {"C002", "C003"}  # 대출이 있는 고객만. C001은 모델을 거치지 않는다.


def _norm(text: str) -> str:
    return re.sub(r"[\s?.!,]", "", text)


def test_sizes_follow_the_v3_plan():
    sizes = collections.Counter(g["category"] for g in GOLDEN_V3)
    assert sizes == {"복합": 10, "수수료": 5, "전반": 5}


def test_rows_are_well_formed():
    assert len({g["id"] for g in GOLDEN_V3}) == len(GOLDEN_V3)
    assert not {g["id"] for g in GOLDEN_V3} & {g["id"] for g in GOLDEN_V2}
    for g in GOLDEN_V3:
        assert g["set"] == "v3" and g["customer"] in CUSTOMERS and g["question"].strip()
        assert g["expect"] and set(g["expect"]) <= EXPECT_CODES, g
        assert g["history"] == []


def test_general_lookup_expects_all_three_facts():
    for g in GOLDEN_V3:
        if g["category"] == "전반":
            assert set(g["expect"]) == {"date", "slot_principal", "slot_extend"}, g


def test_fee_cases_expect_referral():
    for g in GOLDEN_V3:
        if g["category"] == "수수료":
            assert g["expect"] == ["refer"], g


def test_v3_questions_are_unique():
    norm = [_norm(g["question"]) for g in GOLDEN_V3]
    assert len(set(norm)) == len(norm)


@pytest.mark.parametrize("g", GOLDEN_V3, ids=[g["id"] for g in GOLDEN_V3])
def test_v3_question_does_not_overlap_seeds_golden_or_dev_questions(g):
    q = _norm(g["question"])
    pool = (
        [_norm(s["question"]) for s in SEEDS]
        + [_norm(o["question"]) for o in GOLDEN_V2]
        + [_norm(d) for d in DEV_QUESTIONS]
    )
    for other in pool:
        ratio = difflib.SequenceMatcher(None, q, other).ratio()
        assert q != other and ratio < 0.85, (g["question"], other, round(ratio, 2))
