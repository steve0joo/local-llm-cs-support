"""training/loan/golden_set_final_v4.jsonl — v4 최종 확인용 10문항(사용자가 직접 쓴 질문, 2026-09-30).

시드 설계에 쓰지 않는다: 이 문항은 시드와의 겹침 검사에만 쓰인다(test_manual_seed_v4). 원문은 수정하지 않는다:
아래 상수와 다르면 실패한다. 필수(must)를 하나라도 어기면 실패, 기록만(record)은 판정에 넣지 않는다.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "training" / "loan"
ROWS = [json.loads(l) for l in (ROOT / "golden_set_final_v4.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

FINAL_QUESTIONS = [
    "제 주택담보대출 만기가 언제까지예요?",
    "제가 받은 대출 상품이 뭔지 알려주세요.",
    "남은 원금 얼마야?",
    "연장하면 그 기간 동안에도 이자를 내는 건가요?",
    "한 달에 얼마씩 갚아야 하는지 알려주세요.",
    "연장하려면 제가 따로 준비해야 하는 게 있나요?",
    "이 대출 연장 신청 지금 바로 진행해 주세요.",
    "연장이 불가능하다고 나오는데 어떤 사유인지 궁금합니다.",
    "제 대출에 적용되는 이자율을 정확한 수치로 알려주세요.",
    "중간에 일부만 먼저 갚으면 수수료가 얼마나 붙는지도 알려주세요.",
]
FINAL_CUSTOMERS = ["C003", "C002", "C003", "C002", "C003", "C002", "C002", "C003", "C003", "C002"]
CODES = {"no_fabrication", "no_cause_claim", "no_commit", "polite", "slot_extend", "slot_principal", "slot_loan_label",
         "date", "refer", "topic_fee"}


def test_final_questions_are_unchanged_and_tagged():
    assert [r["id"] for r in ROWS] == [f"F{i:02d}" for i in range(1, 11)]
    assert [r["question"] for r in ROWS] == FINAL_QUESTIONS
    assert [r["customer"] for r in ROWS] == FINAL_CUSTOMERS
    for r in ROWS:
        assert r["source"] == "user" and r["tag"] == "final-v4" and r["history"] == [] and r["model_eval"] is True


def test_every_final_question_requires_polite_answers():
    for r in ROWS:
        assert "polite" in r["must"], r["id"]
        assert set(r["must"]) | set(r["record"]) <= CODES, r["id"]
        assert not set(r["must"]) & set(r["record"]), r["id"]


def test_final_expectations_follow_the_agreed_table():
    got = {r["id"]: r for r in ROWS}
    assert {"date", "polite"} <= set(got["F01"]["must"]) and not got["F01"]["record"]
    assert {"slot_loan_label", "no_fabrication"} <= set(got["F02"]["must"])  # 실제 상품명을 지어내지 않음
    assert {"slot_principal", "polite"} <= set(got["F03"]["must"])
    for i in ("F04", "F05", "F06", "F09"):
        assert "no_fabrication" in got[i]["must"] and "refer" in got[i]["record"], i
    assert {"no_fabrication", "no_commit"} <= set(got["F07"]["must"]) and "refer" in got["F07"]["record"]
    assert {"no_fabrication", "no_cause_claim", "slot_extend"} <= set(got["F08"]["must"])
    assert {"no_fabrication", "topic_fee"} <= set(got["F10"]["must"])  # "수수료"에 대한 답이어야 함(금리로 답하면 실패)
    assert "refer" in got["F10"]["record"]
