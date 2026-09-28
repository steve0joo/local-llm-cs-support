import json

import pytest

from app.agents.interest.prompt import SYSTEM_PROMPT
from training.interest.evaluate import (
    EXPECT_CODES,
    FORBIDDEN,
    GOLDEN,
    build_golden_cases,
    check_expect,
    load_split_cases,
    make_blind_sheet,
    save_results,
    score,
    summarize,
    tone_ok,
)
from training.interest.synth import TEMPLATES

MOCK = {
    "C001": [],
    "C002": [{"loan_id": "L001", "product_type": "신용대출", "repayment_method": "만기일시",
              "interest_type": "변동", "payment_method": "자동이체", "next_due_date": "2026-10-15",
              "interest_due": 58000, "overdue_amount": 0, "overdue_days": 0}],
    "C003": [{"loan_id": "L002", "product_type": "주택담보대출", "repayment_method": "원리금균등",
              "interest_type": "고정", "payment_method": "가상계좌 입금", "next_due_date": "2026-10-25",
              "interest_due": 312500, "overdue_amount": 625000, "overdue_days": 12}],
}
import json as _json
from pathlib import Path as _Path

MOCK.update({k: v for k, v in _json.loads(
    (_Path(__file__).resolve().parents[2] / "app/agents/interest/mock_data.json").read_text(encoding="utf-8")
).items() if k not in MOCK})
NORMAL, OVERDUE = MOCK["C002"][0], MOCK["C003"][0]


# --- Golden Set -----------------------------------------------------------------


def test_golden_set_size_and_coverage():
    # EVALUATION.md 질문 2: 30~50문항, 유형 골고루, 정상·연체 고객 모두
    assert 30 <= len(GOLDEN) <= 50
    assert {customer for customer, _, _ in GOLDEN} == {"C002", "C003", "C004", "C005", "C006", "C007"}
    assert {expect for _, _, expect in GOLDEN} == set(EXPECT_CODES)


def test_golden_questions_not_in_training_templates():
    # 학습 데이터와 겹치면 외운 것과 배운 것을 구분할 수 없다.
    template_questions = {q for t in TEMPLATES for q in t.questions} | {q for t in TEMPLATES for q, _ in t.history}
    assert not {q for _, q, _ in GOLDEN} & template_questions


def test_golden_questions_unique_per_customer():
    pairs = [(c, q) for c, q, _ in GOLDEN]
    assert len(pairs) == len(set(pairs))


def test_golden_cases_use_inference_prompt():
    cases = build_golden_cases(MOCK)
    assert len(cases) == len(GOLDEN)
    for c in cases:
        assert c["set"] == "golden" and c["expect"] in EXPECT_CODES
        assert c["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
        assert c["messages"][-1]["content"].startswith(c["question"] + "\n이자 정보: ")
        assert c["item"] == MOCK[c["customer"]][0]
        text = json.dumps(c["messages"], ensure_ascii=False)
        assert "58000" not in text and "312,500" not in text and "625000" not in text


def test_load_split_cases_have_no_expect(tmp_path):
    record = {"id": "Q1", "item": OVERDUE, "messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "연체된 거 있어요?\n이자 정보: ..."},
        {"role": "assistant", "content": "정답"},
    ]}
    (tmp_path / "test.jsonl").write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    [c] = load_split_cases(tmp_path, "test")
    assert c["set"] == "test" and c["expect"] is None
    assert c["messages"] == record["messages"][:-1] and c["reference"] == "정답"
    assert c["question"] == "연체된 거 있어요?"


# --- 문항별 기대 조건 ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("expect", "item", "answer", "ok"),
    [
        ("interest_amount", NORMAL, "납부하실 이자는 {{interest_due}}입니다.", True),
        ("interest_amount", NORMAL, "잔액과 금리를 확인한 후 알려드리겠습니다.", False),
        ("due_date", NORMAL, "다음 납부일은 2026-10-15입니다.", True),
        ("due_date", NORMAL, "다음 납부일은 10월 15일입니다.", True),
        ("due_date", NORMAL, "이자 빠지는 날은 {{interest_due}}입니다.", False),  # 날짜 질문에 금액 슬롯
        ("overdue_status", OVERDUE, "현재 12일 연체되어 연체 금액은 {{overdue_amount}}입니다.", True),
        ("overdue_status", OVERDUE, "현재 연체 금액은 {{overdue_amount}}입니다.", False),  # 일수 누락
        ("overdue_status", NORMAL, "현재 연체된 금액은 없습니다.", True),
        ("overdue_status", NORMAL, "연체 여부는 상담원에게 확인해 주세요.", False),
        ("overdue_action", OVERDUE, "12일 연체된 {{overdue_amount}}을 먼저 납부해 주세요.", True),
        ("false_premise", OVERDUE, "확인해 보니 12일 연체되어 있고 연체 금액은 {{overdue_amount}}입니다.", True),
        ("false_premise", OVERDUE, "네, 연체 없이 정상입니다.", False),
        ("rate", OVERDUE, "적용 금리 수치는 상담원에게 확인해 주세요.", True),
        ("rate", OVERDUE, "금리는 약정에 따라 다릅니다.", False),  # 안내 없음
        ("loan_terms_repay", OVERDUE, "원리금균등 방식으로 상환하고 계십니다.", True),
        ("loan_terms_interest_type", NORMAL, "변동금리 방식입니다.", True),
        ("loan_terms_payment", OVERDUE, "가상계좌 입금 방식으로 납부하고 계십니다.", True),
        ("loan_terms_payment", OVERDUE, "납부 방법은 상담원에게 확인해 주세요.", False),  # 조회값 무시
    ],
)
def test_check_expect(expect, item, answer, ok):
    assert check_expect(expect, item, answer) is ok


@pytest.mark.parametrize(
    ("answer", "ok"),
    [
        ("다음 납부일은 2026-10-15입니다. 납부하실 이자는 {{interest_due}}입니다.", True),
        ("금리는 상담원에게 확인해 주세요", True),
        ("**납부일**은 2026-10-15입니다.", False),  # 마크다운
        ("안내드립니다.\n1. 가상계좌 확인\n2. 입금", False),  # 목록
        ("고객님께서는 이자를 확인하고자 하셨습니다.", False),  # 요약체
        ("이자는 {{interest_due}}야.", False),  # 반말
        ("가. 나. 다. 라. 마. 바. 사입니다.", False),  # 너무 김
    ],
)
def test_tone_ok(answer, ok):
    assert tone_ok(answer) is ok


# --- 채점·집계 --------------------------------------------------------------------


def golden_case(question="혹시 제 대출 연체된 거 있나요?", expect="overdue_status", item=OVERDUE):
    return {"set": "golden", "item": item, "question": question, "expect": expect}


def test_score_rule_success_needs_all_four():
    good = "현재 12일 연체되어 있고 연체 금액은 {{overdue_amount}}입니다."
    s = score(golden_case(), good)
    assert s["valid"] and s["expect"] and s["tone"] and s["forbidden"] == [] and s["rule"] is True
    assert score(golden_case(), "현재 연체 중입니다.")["rule"] is False  # 슬롯·일수 누락


def test_score_without_expect_has_no_rule():
    s = score({"set": "test", "item": NORMAL, "question": "이자요", "expect": None}, "상담원에게 확인해 주세요.")
    assert s["expect"] is None and s["rule"] is None


@pytest.mark.parametrize(
    ("text", "hit"),
    [
        ("적용 금리는 4.5%입니다.", "%"),
        ("신분증 사본이 필요합니다.", "서류·증빙"),
        ("하나은행 앱에서 확인하세요.", "은행·앱"),
        ("밤 11시까지 입금해 주세요.", "시각·기간"),
        ("신청을 완료해 드렸습니다.", "처리 주장"),
        ("비밀번호를 알려 주세요.", "개인정보 요구"),
    ],
)
def test_forbidden_patterns(text, hit):
    assert hit in [name for name, pattern in FORBIDDEN if pattern.search(text)]


def test_summarize():
    def row(set_, valid, slot, forbidden, length, expect=None, tone=True, rule=None):
        return {"set": set_, "score": {"valid": valid, "slot": slot, "forbidden": forbidden,
                                       "length": length, "expect": expect, "tone": tone, "rule": rule}}

    rows = [
        row("golden", True, True, [], 10, expect=True, rule=True),
        row("golden", False, False, ["%"], 30, expect=False, tone=False, rule=False),
        row("test", True, False, [], 20),
    ]
    s = summarize(rows)
    assert s["golden"] == {"n": 2, "valid": 0.5, "slot": 0.5, "forbidden": 0.5, "avg_length": 20.0,
                           "tone": 0.5, "expect": 0.5, "rule": 0.5}
    assert s["test"]["expect"] is None and s["test"]["rule"] is None
    assert s["all"]["n"] == 3


# --- 사람 블라인드 평가 시트 ---------------------------------------------------------


def test_blind_sheet_hides_model_names_and_keeps_key():
    a = [{"set": "golden", "id": f"g{i}", "customer": "C002", "question": f"q{i}", "answer": f"A{i}"} for i in range(10)]
    b = [{"set": "golden", "id": f"g{i}", "customer": "C002", "question": f"q{i}", "answer": f"B{i}"} for i in range(10)]
    sheet, key = make_blind_sheet(a, b, "base", "tuned", seed=1)

    assert len(sheet) == 10
    assert "base" not in json.dumps(sheet) and "tuned" not in json.dumps(sheet)
    for row in sheet:
        k = key[row["no"]]
        by_model = {k["1"]: row["answer_1"], k["2"]: row["answer_2"]}
        assert by_model["base"].startswith("A") and by_model["tuned"].startswith("B")
    # 순서를 섞어 먼저 나온 답을 선호하는 편향을 줄인다.
    assert {key[r["no"]]["1"] for r in sheet} == {"base", "tuned"}
    assert make_blind_sheet(a, b, "base", "tuned", seed=1) == (sheet, key)


# --- 결과 저장: 덮어쓰지 않고, 어댑터 버전 폴더에도 사본 ------------------------------------


def test_save_results_copies_into_run_and_never_overwrites(tmp_path):
    eval_dir = tmp_path / "eval"
    run = tmp_path / "runs" / "v03-20260928-1730-04"
    adapter = run / "adapter"
    adapter.mkdir(parents=True)
    rows = [{"id": "golden-00", "answer": "x"}]
    summary = {"all": {"n": 1}}

    save_results(rows, summary, "tuned-04", eval_dir, adapter)

    for d in (eval_dir, run / "eval"):
        assert (d / "tuned-04.jsonl").exists() and (d / "tuned-04.summary.json").exists()
    with pytest.raises(FileExistsError):
        save_results(rows, summary, "tuned-04", eval_dir, adapter)
    save_results(rows, summary, "tuned-04", eval_dir, adapter, overwrite=True)


def test_save_results_base_model_has_no_run_copy(tmp_path):
    save_results([{"id": "g"}], {}, "base", tmp_path / "eval", None)
    assert (tmp_path / "eval" / "base.jsonl").exists()
