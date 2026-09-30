import json

import pytest

from training.interest.manual_data import expand, fill, load_manual, parse_answers_md, write_json

ITEM = {"loan_id": "L001", "product_type": "신용대출", "repayment_method": "만기일시", "interest_type": "변동",
        "payment_method": "자동이체", "next_due_date": "2026-10-15", "interest_due": 58000,
        "overdue_amount": 0, "overdue_days": 0}
OVERDUE = {**ITEM, "loan_id": "L002", "product_type": "주택담보대출", "overdue_days": 12, "overdue_amount": 625000}
MOCK = {"C001": [], "C002": [ITEM], "C003": [OVERDUE]}

MD = """# 제목

## 작성 규칙
- 규칙

---

## 01. [C002] 이번 달 이자 얼마야?

- 이자 정보: `종류=신용대출`
- 좋은 답의 조건: 이자 슬롯
- v03 답: {{loan_label}}의 다음 납부일은 2026-10-15이고, 납부하실 이자는 {{interest_due}}입니다.

수정 답: 그대로

---

## 09. [C002] 원금은 매달 안 내도 되는 거예요?

- 좋은 답의 조건: 만기일시
- v03 답: 원금을 매달 납부하실 수는 없습니다.
- 판정 메모: 🟠 잘못 말함

수정 답: {{loan_label}}은 {repay} 방식으로 상환하고 계십니다. 자세한 상환 일정은 상담원에게 확인해 주세요.

---

## 30. [C001] 제 대출 이자 얼마예요?

- v03 답: 고객님 명의로 조회되는 대출 이자 내역이 없습니다.

수정 답: (학습 제외)
"""


def test_parse_answers_md():
    rows = parse_answers_md(MD, source="ok")
    assert [r["no"] for r in rows] == [1, 9, 30]
    first = rows[0]
    assert first["customer"] == "C002" and first["question"] == "이번 달 이자 얼마야?"
    # "그대로"는 v03 답을 쓴다. 고객 값은 자리표시로 바꾼다(날짜 → {due}).
    assert first["answer"] == "{{loan_label}}의 다음 납부일은 {due}이고, 납부하실 이자는 {{interest_due}}입니다."
    assert first["train"] is True and first["check"] == "이자 슬롯"
    assert rows[1]["answer"].startswith("{{loan_label}}은 {repay} 방식") and rows[1]["note"] == "🟠 잘못 말함"
    assert rows[2]["train"] is False


def test_parse_rejects_empty_answer():
    with pytest.raises(ValueError, match="09"):
        parse_answers_md(MD.replace("수정 답: {{loan_label}}은 {repay} 방식으로 상환하고 계십니다. 자세한 상환 일정은 상담원에게 확인해 주세요.", "수정 답: "), "fix")


def test_templatize_customer_values_on_keep():
    md = MD.replace("{{loan_label}}의 다음 납부일은 2026-10-15이고", "현재 신용대출이 12일 연체되어 있고 다음 납부일은 2026-10-15이고")
    md = md.replace("## 01. [C002]", "## 01. [C003]")
    row = parse_answers_md(md, "ok")[0]
    assert row["answer"].startswith("현재 {{loan_label}}이 {days}일 연체되어 있고 다음 납부일은 {due}이고")


def test_fill():
    assert fill("{days}일 · {due} · {pay} · {repay} · {rate_type}금리", OVERDUE) == "12일 · 2026-10-15 · 자동이체 · 만기일시 · 변동금리"


def test_write_and_load_json(tmp_path):
    rows = parse_answers_md(MD, "ok")
    write_json(rows, tmp_path)
    assert sorted(p.name for p in tmp_path.glob("q*.json")) == ["q01.json", "q09.json", "q30.json"]
    assert load_manual(tmp_path) == rows


def test_expand_varies_only_product_type():
    rows = [r for r in parse_answers_md(MD, "ok") if r["train"]]
    records = expand(rows, MOCK)
    assert len(records) == 2 * 3
    for r in records:
        item, original = r["item"], MOCK[r["customer"]][0]
        # 질문이 특정 조회값(연체 일수·납부일·납부 방법)을 전제할 수 있어 대출 종류만 바꾼다.
        assert {k: v for k, v in item.items() if k != "product_type"} == {k: v for k, v in original.items() if k != "product_type"}
        assert r["origin"] == "manual" and r["reviewed"] is True and r["group_id"] == f"manual-q{r['no']:02d}"
        assert r["messages"][-1]["role"] == "assistant" and "{due}" not in r["messages"][-1]["content"]
        assert r["messages"][-2]["content"].startswith(r["question"] + "\n이자 정보: 종류=" + item["product_type"])
    assert {r["item"]["product_type"] for r in records} == {"신용대출", "주택담보대출", "전세자금대출"}


def test_expand_refuses_answer_that_fails_checks():
    rows = [{"no": 5, "customer": "C002", "question": "이자요?", "answer": "이자는 58,000원입니다.", "train": True}]
    with pytest.raises(ValueError, match="q05"):
        expand(rows, MOCK)
    rows[0]["answer"] = "확인 후 연락드리겠습니다."
    with pytest.raises(ValueError, match="q05"):
        expand(rows, MOCK)



def test_expand_refuses_hold30_questions():
    # 평가 전용 질문이 학습에 들어가면 그 세트로는 더 이상 공정하게 평가할 수 없다.
    from training.interest.ask import HOLD_QUESTIONS

    customer, question, _ = next(q for q in HOLD_QUESTIONS if q[0] == "C002")
    rows = [{"no": 71, "customer": customer, "question": question, "train": True,
             "answer": "{{loan_label}}의 다음 납부일은 {due}이고, 납부 예정 이자는 {{interest_due}}입니다."}]
    with pytest.raises(ValueError, match="평가 전용"):
        expand(rows, MOCK)
