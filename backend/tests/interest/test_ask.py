import json
from pathlib import Path

from training.interest.ask import NO_LOAN_TEXT, TEST_QUESTIONS, build_cases, fill_slots, finalize, render_sheet
from training.interest.evaluate import GOLDEN
from training.interest.synth import TEMPLATES

MOCK = json.loads((Path(__file__).resolve().parents[2] / "app/agents/interest/mock_data.json").read_text(encoding="utf-8"))
C002, C003 = MOCK["C002"][0], MOCK["C003"][0]


def test_thirty_questions_over_demo_and_eval_customers():
    assert len(TEST_QUESTIONS) == 22
    assert {c for c, _, _ in TEST_QUESTIONS} <= set(MOCK)
    assert any(c == "C001" for c, _, _ in TEST_QUESTIONS)  # 대출 없음 경로도 확인


def test_questions_not_in_golden_or_templates():
    used = {q for _, q, _ in GOLDEN} | {q for t in TEMPLATES for q in t.questions}
    assert not {q for _, q, _ in TEST_QUESTIONS} & used


def test_build_cases_uses_inference_prompt_and_skips_no_loan():
    cases = build_cases(MOCK)
    assert len(cases) == 21  # C001은 모델을 부르지 않는다
    assert all(c["messages"][-1]["content"].startswith(c["question"] + "\n이자 정보: ") for c in cases)


def test_finalize_passes_valid_answer():
    out = finalize(C002, "이번 달 이자 얼마야?", "납부하실 이자는 {{interest_due}}입니다.")
    assert out["replaced"] is False
    assert out["final"] == "납부하실 이자는 {{interest_due}}입니다."
    assert out["screen"] == "납부하실 이자는 58,000원입니다."


def test_finalize_falls_back_on_invalid_answer():
    out = finalize(C003, "연체 이자율 알려 주세요", "연체 이자율은 연 12%입니다.")
    assert out["replaced"] is True
    assert "12일 연체 중" in out["final"] and "{{overdue_amount}}" in out["final"]
    assert "625,000원" in out["screen"] and "{{" not in out["screen"]


def test_fill_slots_unknown_slot_becomes_notice():
    # 계약 1: 치환되지 않은 {{...}}는 "확인할 수 없습니다"로 표시한다.
    assert fill_slots("잔액은 {{balance}}입니다.", {"interest_due": "1원"}) == "잔액은 확인할 수 없습니다입니다."


def test_render_sheet_has_scoring_columns():
    rows = [{"no": 1, "customer": "C002", "question": "q", "check": "c", "raw": "r", "replaced": False,
             "screen": "s", "seconds": 1.0}]
    sheet = render_sheet(rows, "v03")
    assert "주제 적합" in sheet and "지어내지 않음" in sheet and "존댓말" in sheet
    assert "| 1 | C002 | q |" in sheet
    assert NO_LOAN_TEXT.startswith("고객님 명의로")


# --- 약점 보강용 질문 세트(weak30, 31~60번) ---------------------------------------------


def test_weak30_targets_known_weaknesses_and_is_new():
    from training.interest.ask import QUESTION_SETS, WEAK_QUESTIONS
    from training.interest.manual_data import load_manual
    from training.interest.probe import PROBE_QUESTIONS

    assert set(QUESTION_SETS) == {"ask30", "weak30", "debit10", "hold30"}
    assert len(WEAK_QUESTIONS) == 13 and {c for c, _, _ in WEAK_QUESTIONS} <= set(MOCK) - {"C001"}
    used = (
        {q for _, q, _ in GOLDEN} | {q for _, q, _ in TEST_QUESTIONS} | {q for _, q, _ in PROBE_QUESTIONS}
        | {q for t in TEMPLATES for q in t.questions} | {r["question"] for r in load_manual() if r["no"] < 31}
    )  # weak30 자신은 수동 검수 후 q31~q60 학습 샘플이 됐으므로 그 이전 샘플과만 비교한다
    weak = [q for _, q, _ in WEAK_QUESTIONS]
    assert not set(weak) & used and len(weak) == len(set(weak))


def test_build_cases_numbering_per_set():
    from training.interest.ask import build_cases

    cases = build_cases(MOCK, "weak30")
    assert [c["no"] for c in cases] == list(range(31, 44))
    assert cases[0]["id"] == "weak30-31"


def test_debit10_is_new_and_numbered():
    from training.interest.ask import DEBIT_QUESTIONS, WEAK_QUESTIONS, build_cases
    from training.interest.manual_data import load_manual
    from training.interest.probe import PROBE_QUESTIONS

    used = (
        {q for _, q, _ in GOLDEN} | {q for _, q, _ in TEST_QUESTIONS} | {q for _, q, _ in WEAK_QUESTIONS}
        | {q for _, q, _ in PROBE_QUESTIONS} | {q for t in TEMPLATES for q in t.questions}
        | {r["question"] for r in load_manual() if r["no"] < 61}
    )  # debit10 자신은 수동 검수 후 q61~q70 학습 샘플이 됐으므로 그 이전 샘플과만 비교한다
    assert len(DEBIT_QUESTIONS) == 3 and not {q for _, q, _ in DEBIT_QUESTIONS} & used
    assert [c["no"] for c in build_cases(MOCK, "debit10")] == list(range(61, 64))


# --- 평가 전용 세트(hold30, 101~130번): 학습에 절대 넣지 않는다 ---------------------------


def test_hold30_is_new_and_covers_all_customers():
    from training.interest.ask import DEBIT_QUESTIONS, HOLD_QUESTIONS, QUESTION_SETS, WEAK_QUESTIONS
    from training.interest.manual_data import load_manual
    from training.interest.probe import PROBE_QUESTIONS

    # ask30·weak30·debit10은 모범 답으로 학습에 들어가 v04 이후 모델 평가에는 외운 답이 나온다. hold30은 그 대신 쓴다.
    assert QUESTION_SETS["hold30"] == (101, HOLD_QUESTIONS)
    used = (
        {q for _, q, _ in GOLDEN} | {q for _, q, _ in TEST_QUESTIONS} | {q for _, q, _ in WEAK_QUESTIONS}
        | {q for _, q, _ in DEBIT_QUESTIONS} | {q for _, q, _ in PROBE_QUESTIONS}
        | {q for t in TEMPLATES for q in t.questions} | {r["question"] for r in load_manual()}
    )
    hold = [q for _, q, _ in HOLD_QUESTIONS]
    assert len(hold) == 13 and len(set(hold)) == 13 and not set(hold) & used
    assert {c for c, _, _ in HOLD_QUESTIONS} == set(MOCK)  # C001(대출 없음)~C007 모두


def test_hold30_numbering():
    cases = build_cases(MOCK, "hold30")
    assert cases[0]["id"] == "hold30-101" and cases[-1]["no"] == 113
    assert len(cases) == 12  # C001은 모델을 부르지 않는다
