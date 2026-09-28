import pytest

from app.agents.interest.validate import is_valid

ALLOWED = {"loan_label", "interest_due", "overdue_amount"}


def check(text, required=()):
    return is_valid(text, allowed_slots=ALLOWED, required_slots=set(required))


@pytest.mark.parametrize(
    "text",
    [
        "{{loan_label}}의 다음 납부일은 2026-10-25이고, 납부 예정 이자는 {{interest_due}}입니다.",
        "다음 납부일은 2026년 10월 25일입니다. 납부 예정 이자는 {{interest_due}}입니다.",
        "현재 12일 연체 중이며 연체 금액은 {{overdue_amount}}입니다.",
        "금리는 상담원에게 확인해 주세요.",
    ],
)
def test_accepts_dates_days_and_slots(text):
    # 날짜·연체 일수는 금액이 아니다. 걸러내면 정상 답변이 전부 기본 문장으로 바뀐다.
    assert check(text)


@pytest.mark.parametrize(
    "text",
    [
        "납부 예정 이자는 312,500원입니다.",
        "납부 예정 이자는 312500원입니다.",
        "연체 금액은 62만 5천원입니다.",
        "이자는 약 30만원 정도입니다.",
        "잔액은 1,234,567입니다.",
    ],
)
def test_rejects_amounts(text):
    assert not check(text)


@pytest.mark.parametrize(
    "text",
    [
        "적용 금리는 4.5%입니다.",
        "연체 가산 이율은 3 %입니다.",
        "연 5퍼센트가 적용됩니다.",
        "3프로 가산됩니다.",
    ],
)
def test_rejects_rates(text):
    # INT-002: 지어낸 금리 수치 1건이면 즉시 불합격.
    assert not check(text)


def test_rejects_unknown_slot():
    assert not check("이자는 {{interest}}입니다.")


def test_rejects_mask_token():
    # 프론트는 {{슬롯}}만 치환한다. 마스킹 토큰이 나가면 화면에 그대로 보인다.
    assert not check("말씀하신 [금액_1]은 납부 예정 이자와 다릅니다.")


def test_requires_required_slots():
    text = "{{loan_label}} 납부 예정 이자는 {{interest_due}}입니다."
    assert not check(text, required={"overdue_amount"})
    assert check(text + " 연체 금액은 {{overdue_amount}}입니다.", required={"overdue_amount"})


def test_rejects_empty():
    assert not check("")
    assert not check("   ")
