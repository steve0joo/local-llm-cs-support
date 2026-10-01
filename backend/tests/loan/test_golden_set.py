"""training/loan/golden_set.jsonl (docs/EVALUATION 공용틀 4절, 12-3).

Golden Set은 학습에 쓰지 않은 시험 문제다. 학습 시드·검증기 개발 때 본 질문과 겹치면 외운 것과 배운 것을 구분할 수 없다.
"""
import collections
import difflib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "training" / "loan"
GOLDEN = [json.loads(l) for l in (ROOT / "golden_set.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
SEEDS = [json.loads(l) for l in (ROOT / "manual_seed.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

EXPECT_CODES = {"date", "slot_principal", "slot_extend", "refer", "no_loan", "off_topic"}
CUSTOMERS = {"C001", "C002", "C003"}
# 2026-09-29 검증기 규칙을 만들 때 v1 모델에 던져 본 질문(개발용). Golden Set에 다시 쓰지 않는다.
DEV_QUESTIONS = [
    "대출 만기가 언제예요?", "만기일 좀 알려주세요", "언제까지 갚아야 해요?", "만기가 얼마나 남았나요?",
    "연장할 수 있나요?", "만기 연장 되나요?", "기간 연장 가능한지 알고 싶어요", "연장 신청하면 승인되나요?",
    "남은 원금이 얼마죠?", "대출 잔액 알려주세요", "아직 얼마 갚아야 해요?", "내 대출 좀 알려주세요",
    "제 대출 현황 확인해주세요", "어떤 대출 받았는지 알려주세요", "연장하려면 어떤 서류가 필요해요?",
    "연장 신청할 때 뭐 가져가야 하나요?", "소득 증빙 서류 필요한가요?", "금리는 몇 퍼센트예요?", "이자율이 얼마죠?",
    "연장하면 금리가 바뀌나요?", "이자 얼마 내야 해요?", "이번 달 이자가 얼마예요?", "연체 이자는 얼마인가요?",
    "연장 안 되는 이유가 뭔가요?", "왜 연장이 안 돼요?", "대출 상환은 어떻게 하나요?", "중도상환하면 수수료 있나요?",
    "일부만 먼저 갚을 수 있나요?", "오늘 날씨 어때요?", "잔액 조회해주세요", "카드 분실했어요", "주식 추천해줘",
    "너 누구야?", "제 계좌 [계좌번호_1] 대출 만기 알려주세요", "[금액_1] 대출 연장 되나요?",
]


def _norm(text: str) -> str:
    return re.sub(r"[\s?.!,]", "", text)


def test_sizes_follow_the_evaluation_frame():
    sizes = collections.Counter(g["set"] for g in GOLDEN)
    assert sizes == {"compare": 30, "final": 10, "regress": 20}


def test_rows_are_well_formed():
    assert len({g["id"] for g in GOLDEN}) == len(GOLDEN)
    for g in GOLDEN:
        assert g["customer"] in CUSTOMERS and g["question"].strip() and g["category"]
        assert g["expect"] and set(g["expect"]) <= EXPECT_CODES, g
        for turn in g["history"]:
            assert turn["role"] in {"user", "assistant"} and turn["content"]


def test_c001_cases_expect_the_fixed_no_loan_text():
    for g in GOLDEN:
        assert (g["customer"] == "C001") == (g["expect"] == ["no_loan"]), g


def test_final_set_covers_the_pm_question_types():
    cats = {g["category"] for g in GOLDEN if g["set"] == "final"}
    assert {"만기", "원금", "연장가능", "연장불가", "서류·조건", "금리", "연장불가사유", "대출없음", "수수료"} <= cats


def test_golden_questions_are_unique():
    norm = [_norm(g["question"]) for g in GOLDEN]
    assert len(set(norm)) == len(norm)


@pytest.mark.parametrize("g", GOLDEN, ids=[g["id"] for g in GOLDEN])
def test_golden_question_does_not_overlap_seeds_or_dev_questions(g):
    q = _norm(g["question"])
    pool = [_norm(s["question"]) for s in SEEDS] + [_norm(d) for d in DEV_QUESTIONS]
    for other in pool:
        ratio = difflib.SequenceMatcher(None, q, other).ratio()
        assert q != other and ratio < 0.85, (g["question"], other, round(ratio, 2))
