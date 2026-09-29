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


# --- 필수 슬롯 판정: 연체 상태를 묻는 질문에만 {{overdue_amount}}를 요구한다 ------------

from app.agents.interest.validate import required_slots  # noqa: E402


@pytest.mark.parametrize(
    "question",
    ["연체된 거 있어요?", "제 대출 연체됐어요?", "연체 금액 얼마예요?", "저 연체 없죠?", "밀린 거 있나요?", "미납된 이자 있는지 봐 주세요"],
)
def test_overdue_question_requires_overdue_amount(question):
    assert required_slots(question, overdue=True) == {"overdue_amount"}


@pytest.mark.parametrize(
    "question",
    ["대출 금리가 몇 %예요?", "연체 가산금리는 얼마예요?", "이자가 왜 이렇게 많이 나왔어요?", "연체이자가 뭐예요?", "납부일 바꿔 주세요"],
)
def test_other_questions_do_not_require_overdue_amount(question):
    # 연체 고객이 금리를 물을 때 상담원 안내만 한 좋은 답이 기본 문장으로 바뀌지 않게 한다.
    assert required_slots(question, overdue=True) == set()


def test_not_overdue_requires_nothing():
    assert required_slots("연체된 거 있어요?", overdue=False) == set()


# --- 금지 표현: 자동 채점이 놓친 v03 약점(결과 보장·규정 단정·지어낸 채널·절차·약속) -----------

from app.agents.interest.validate import phrase_problems  # noqa: E402


@pytest.mark.parametrize(
    "text, problem",
    [
        ("입금하시면 연체가 해소됩니다.", "결과 보장"),
        ("연체 금액을 납부하시면 연체 상태는 해제됩니다.", "결과 보장"),
        ("잔액이 많으니 납부일에 정상적으로 이체됩니다.", "결과 보장"),
        ("이 금액을 먼저 납부해 주시면 자동이체가 정상적으로 이루어집니다.", "결과 보장"),
        ("잔액이 충분해지면 자동이체가 다시 진행됩니다.", "결과 보장"),
        ("연체가 금리에 영향을 주는 것은 아니며, 먼저 납부해 주세요.", "규정 단정"),
        ("연체 기록은 신용점수에 영향을 줄 수 있습니다.", "규정 단정"),
        ("연체 기간이 길어지면 법적 조치가 가능할 수 있습니다.", "규정 단정"),
        ("이자 미납은 가능하지만, 자동이체로 납부해 주세요.", "규정 단정"),
        ("자동이체 계좌의 잔액이 연체 금액보다 적어 연체가 발생하고 있습니다.", "규정 단정"),
        ("앱에서 납부하실 수 있습니다.", "지어낸 채널"),
        ("고객센터로 연락해 주세요.", "지어낸 채널"),
        ("가까운 영업점을 방문해 주세요.", "지어낸 채널"),
        ("계좌번호와 예금주명을 입력해 주세요.", "지어낸 절차"),
        ("로그인 후 납부 버튼을 누르시면 됩니다.", "지어낸 절차"),
        ("입금 확인 문자를 발송해 드리겠습니다.", "행동 약속"),
        ("변경은 제가 처리해 드립니다.", "행동 약속"),
        ("결과는 추후 안내 드릴 예정입니다.", "행동 약속"),
        ("재직증명서를 준비해 주세요.", "서류"),
        ("주민등록번호를 알려 주세요.", "개인정보 요구"),
        ("**납부일**은 2026-10-25입니다.", "마크다운"),
        ("- 납부일: 2026-10-25", "마크다운"),
        ("다음 납부일은 2026-10-25입니다. 다음 납부일은 2026-10-25입니다.", "반복"),
    ],
)
def test_rejects_forbidden_phrases(text, problem):
    assert problem in phrase_problems(text)
    assert not check(text)


@pytest.mark.parametrize(
    "text",
    [
        "입금 확인 문자는 제가 보내 드릴 수 없습니다. 입금 반영 여부는 상담원에게 확인해 주세요.",
        "변경 가능 여부와 변경 절차는 상담원이 안내해 드립니다.",
        "제가 안내해 드릴 수 있는 것은 다음 납부일입니다.",
        "현재 자동이체 계좌 잔액은 {{debit_balance}}이며, 연체 금액 {{overdue_amount}}보다 적은 상태입니다.",
        "연체가 앞으로 어떤 영향을 주는지는 약정과 기준에 따라 달라 제가 단정해 드리기 어렵습니다.",
        "연체 기록 정정이나 이자 감면은 제가 처리하거나 약속드릴 수 없습니다.",
        "출금이 되지 않은 정확한 이유는 상담원에게 확인해 주세요.",
        "현재 {{loan_label}}은 연체 없이 정상적으로 납부되고 있습니다.",
        "연체가 신용점수에 어떤 영향을 주는지는 상담원에게 확인해 주세요.",
    ],
)
def test_accepts_safe_counselor_phrases(text):
    # 거절·상담원 안내·조회 사실 전달은 막지 않는다. 막으면 좋은 답이 기본 문장으로 바뀐다.
    assert phrase_problems(text) == []
