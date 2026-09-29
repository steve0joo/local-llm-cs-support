import re
from collections import Counter

import pytest

from app.agents.interest.prompt import SYSTEM_PROMPT, build_slots, info_line, slot_line
from app.agents.interest.validate import is_valid, required_slots
from training.interest.synth import CATEGORY_WEIGHTS, REVIEWED, TEMPLATES, generate

RECORDS = generate(total=400, seed=7)

# docs/agent-interest/TRAINING_DATA.md 3절 "하지 말 것"
FORBIDDEN = re.compile(
    r"%|퍼센트|프로\b|서류|증명서|사본|하나은행|은행 앱|메뉴|영업일|\d+\s*시|"
    r"(?:처리|완료|적용|등록|변경|접수)(?:해\s?드렸|되었|됐|했|하였)|고객님께서는"
)


def last_user(record):
    return record["messages"][-2]["content"]


def answer(record):
    return record["messages"][-1]["content"]


def test_every_answer_passes_inference_validation():
    # INT-004: 추론 때 기본 문장으로 대체될 답은 학습하지 않는다.
    for r in RECORDS:
        item = r["item"]
        question = last_user(r).split("\n")[0]
        ok = is_valid(
            answer(r),
            allowed_slots=set(build_slots(item)),
            required_slots=required_slots(question, overdue=item["overdue_days"] > 0),
        )
        assert ok, (r["id"], question, answer(r))


def test_format_matches_prompt_module():
    for r in RECORDS:
        m = r["messages"]
        assert m[0] == {"role": "system", "content": SYSTEM_PROMPT}
        assert m[-1]["role"] == "assistant" and m[-2]["role"] == "user"
        lines = m[-2]["content"].split("\n")
        assert lines[1] == info_line(r["item"])
        assert lines[2] == slot_line(build_slots(r["item"]))


def test_record_fields():
    for r in RECORDS:
        assert r["origin"] == "synth"
        assert r["group_id"] == r["source_id"] and r["source_id"] in {t.id for t in TEMPLATES}
        assert r["category"] in CATEGORY_WEIGHTS
        assert r["scenario"] == ("overdue" if r["item"]["overdue_days"] > 0 else "normal")
        assert r["reviewed"] is (r["source_id"] in REVIEWED) and r["review_note"] == ""
    assert len({r["id"] for r in RECORDS}) == len(RECORDS)


def test_all_categories_and_both_scenarios_present():
    cats = Counter(r["category"] for r in RECORDS)
    assert set(cats) == set(CATEGORY_WEIGHTS)
    scenarios = Counter(r["scenario"] for r in RECORDS)
    assert 0.35 < scenarios["overdue"] / len(RECORDS) < 0.65


def test_category_share_follows_weights():
    cats = Counter(r["category"] for r in RECORDS)
    total_w = sum(CATEGORY_WEIGHTS.values())
    for cat, w in CATEGORY_WEIGHTS.items():
        assert cats[cat] == pytest.approx(len(RECORDS) * w / total_w, abs=2)


def test_normal_scenario_never_says_overdue():
    for r in RECORDS:
        if r["scenario"] == "normal":
            assert "연체 중" not in answer(r) and "연체되어" not in answer(r) and "{{overdue_amount}}" not in answer(r)


def test_overdue_scenario_states_days_when_amount_given():
    for r in RECORDS:
        if r["scenario"] == "overdue" and "{{overdue_amount}}" in answer(r):
            assert f"{r['item']['overdue_days']}일" in answer(r) or "연체" in answer(r)


def test_no_forbidden_expressions():
    for r in RECORDS:
        assert not FORBIDDEN.search(answer(r)), (r["id"], answer(r))


def test_dates_and_days_come_from_item():
    for r in RECORDS:
        for date in re.findall(r"\d{4}-\d{2}-\d{2}", answer(r)):
            assert date == r["item"]["next_due_date"]
        for days in re.findall(r"(\d+)일", answer(r).replace(r["item"]["next_due_date"], "")):
            assert int(days) == r["item"]["overdue_days"]


def test_deterministic():
    assert generate(total=50, seed=1) == generate(total=50, seed=1)


def test_loan_terms_answers_use_item_values():
    # 상환 방식·금리 방식·납부 방법은 이자 정보 줄의 값으로만 답한다(지어내지 않음).
    for r in RECORDS:
        if r["category"] == "loan_terms":
            item = r["item"]
            assert any(item[k] in answer(r) for k in ("repayment_method", "interest_type", "payment_method")), answer(r)


def test_reviewed_ids_are_real_templates():
    # 오타로 존재하지 않는 ID를 넣으면 그 템플릿이 검수 누락된 채 조용히 빠진다.
    assert REVIEWED <= {t.id for t in TEMPLATES}


# --- 자동이체 계좌 잔액 비교(balance_source.debit_check와 같은 기준) ------------------------

from app.agents.interest.balance_source import debit_check  # noqa: E402
from app.agents.interest.validate import phrase_problems  # noqa: E402

DEBIT_TEMPLATES = {"tpl-reason-autodebit", "tpl-loan_terms-debit_balance"}


def test_autodebit_items_carry_balance_like_service():
    # 서비스(agent.py)는 자동이체 고객이면 잔액 비교 결과를 이자 정보 줄에 넣는다. 학습 입력도 같아야 한다.
    for r in RECORDS:
        item = r["item"]
        if item["payment_method"] == "자동이체":
            assert item["debit_status"] == debit_check(item, item["debit_balance"])
            assert "자동이체 계좌 잔액=" + item["debit_status"] in last_user(r)
        else:
            assert "debit_status" not in item and "debit_balance" not in item


def test_autodebit_templates_force_autodebit_and_cover_both_statuses():
    debit = [r for r in RECORDS if r["source_id"] in DEBIT_TEMPLATES]
    assert debit and all(r["item"]["payment_method"] == "자동이체" for r in debit)
    statuses = Counter(r["item"]["debit_status"] for r in debit)
    assert {"연체 금액보다 적음", "연체 금액 이상", "납부 예정 이자보다 적음", "납부 예정 이자 이상"} <= set(statuses)


def test_autodebit_answers_match_status():
    for r in RECORDS:
        if r["source_id"] not in DEBIT_TEMPLATES:
            continue
        a, status = answer(r), r["item"]["debit_status"]
        if status.endswith("적음"):
            assert "적은 상태" in a, a
        else:
            assert "적은 상태" not in a and "이상" in a, a


def test_no_invented_phrases():
    # 결과 보장·규정 단정·지어낸 채널·약속은 서비스 검증에서 기본 문장으로 바뀐다.
    for r in RECORDS:
        assert phrase_problems(answer(r)) == [], (r["id"], answer(r))


def test_rule_questions_answered_without_assertion():
    rule = [r for r in RECORDS if r["source_id"] == "tpl-overdue_action-rule"]
    assert rule and all("상담원" in answer(r) and "단정" in answer(r) for r in rule)
