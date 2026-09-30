import pytest

from app.agents.balance.prompt import fallback_text
from app.agents.balance.validate import DOCUMENT_KEYWORDS, is_valid, validate_output

INTENTS = ("balance", "transactions", "general")

# 기본 문장은 prompt.py를 거치지 않고 리터럴로 고정한다.
FALLBACK = {
    "balance": "{{account_label}} 계좌의 현재 잔액은 {{balance}}입니다.",
    "transactions": "{{account_label}} 계좌의 최근 거래내역입니다.\n{{recent_transactions}}",
    "general": "해당 내용은 정확한 안내를 위해 상담원에게 확인해 주세요.",
}

BASE = {
    "balance": "{{account_label}} 계좌의 현재 잔액은 {{balance}}입니다. 더 궁금하신 점이 있으시면 말씀해 주세요.",
    "transactions": "{{account_label}} 계좌의 최근 거래내역을 안내해 드립니다.\n{{recent_transactions}}",
    "general": "잔액 조회는 모바일 뱅킹이나 인터넷 뱅킹에서 하실 수 있습니다.",
}

# 규칙 1~7 트리거를 하나씩 넣은 문장 (general은 필수 슬롯이 없어 규칙 2 제외)
FAILING_CASES = [
    # 규칙 1: 빈 문자열·공백만
    ("balance", "rule1-empty", ""),
    ("balance", "rule1-blank", "  \n\t "),
    ("transactions", "rule1-empty", ""),
    ("transactions", "rule1-blank", "  \n\t "),
    ("general", "rule1-empty", ""),
    ("general", "rule1-blank", "  \n\t "),
    # 규칙 2: 필수 슬롯 누락
    ("balance", "rule2-no-balance", "{{account_label}} 계좌의 현재 잔액을 안내해 드립니다."),
    ("balance", "rule2-no-label", "고객님 계좌의 현재 잔액은 {{balance}}입니다."),
    ("transactions", "rule2-no-list", "{{account_label}} 계좌의 최근 거래내역을 안내해 드립니다."),
    ("transactions", "rule2-no-label", "고객님 계좌의 최근 거래내역입니다.\n{{recent_transactions}}"),
    # 규칙 3: 숫자 (과대 대체 감수 — BAL-002)
    ("balance", "rule3-digit", BASE["balance"] + " 최근 5건의 거래가 반영된 금액입니다."),
    ("transactions", "rule3-digit", "{{account_label}} 계좌의 최근 5건 거래내역입니다.\n{{recent_transactions}}"),
    ("general", "rule3-digit", "잔액 조회는 모바일 뱅킹에서 24시간 하실 수 있습니다."),
    # 규칙 4: % (숫자 없이)
    ("balance", "rule4-percent", BASE["balance"] + " 우대 금리는 몇 %입니다."),
    ("transactions", "rule4-percent", BASE["transactions"] + "\n수수료는 몇 %입니다."),
    ("general", "rule4-percent", BASE["general"] + " 우대 금리는 몇 %입니다."),
    # 규칙 5: 마스킹 토큰
    ("balance", "rule5-mask", "{{account_label}} 계좌([계좌번호_1])의 현재 잔액은 {{balance}}입니다."),
    ("transactions", "rule5-mask", "[계좌번호_1] {{account_label}} 계좌의 최근 거래내역입니다.\n{{recent_transactions}}"),
    ("general", "rule5-mask", "[계좌번호_1] " + BASE["general"]),
    # 규칙 6: 허용 밖 슬롯 (빈 이름 포함)
    ("balance", "rule6-other-slot", BASE["balance"] + " 이자는 {{interest_due}}입니다."),
    ("balance", "rule6-empty-name", BASE["balance"] + " {{}}"),
    ("balance", "rule6-blank-name", BASE["balance"] + " {{ }}"),
    ("transactions", "rule6-other-slot", BASE["transactions"] + "\n이자는 {{interest_due}}입니다."),
    ("transactions", "rule6-empty-name", BASE["transactions"] + "\n{{}}"),
    ("transactions", "rule6-blank-name", BASE["transactions"] + "\n{{ }}"),
    ("general", "rule6-other-slot", BASE["general"] + " 현재 잔액은 {{balance}}입니다."),
    ("general", "rule6-empty-name", BASE["general"] + " {{}}"),
    ("general", "rule6-blank-name", BASE["general"] + " {{ }}"),
]


@pytest.mark.parametrize(
    ("intent", "text"),
    [pytest.param(intent, text, id=f"{intent}-{rule}") for intent, rule, text in FAILING_CASES],
)
def test_rule_violation_returns_fallback(intent: str, text: str) -> None:
    assert validate_output(text, intent) == FALLBACK[intent]


def test_document_keywords() -> None:
    assert DOCUMENT_KEYWORDS == ("서류", "증명서", "등본", "재직", "소득")


# 규칙 7: 서류 키워드 — 키워드 목록은 리터럴로 적는다
@pytest.mark.parametrize("keyword", ["서류", "증명서", "등본", "재직", "소득"])
@pytest.mark.parametrize("intent", INTENTS)
def test_document_keyword_returns_fallback(intent: str, keyword: str) -> None:
    text = f"{BASE[intent]} 필요한 {keyword} 안내는 상담원에게 확인해 주세요."
    assert validate_output(text, intent) == FALLBACK[intent]


@pytest.mark.parametrize("intent", INTENTS)
def test_passing_base_is_returned_unchanged(intent: str) -> None:
    assert validate_output(BASE[intent], intent) == BASE[intent]


def test_slot_name_with_spaces_is_accepted() -> None:
    text = "{{ account_label }} 계좌의 현재 잔액은 {{ balance }}입니다."
    assert validate_output(text, "balance") == text


@pytest.mark.parametrize("intent", INTENTS)
def test_fallback_passes_its_own_validation(intent: str) -> None:
    assert fallback_text(intent) == FALLBACK[intent]
    assert validate_output(FALLBACK[intent], intent) == FALLBACK[intent]


def test_fallback_is_valid_with_its_slot_names() -> None:
    assert is_valid(FALLBACK["balance"], ("account_label", "balance"), ("account_label", "balance"))
    assert is_valid(
        FALLBACK["transactions"],
        ("account_label", "recent_transactions"),
        ("account_label", "recent_transactions"),
    )
    assert is_valid(FALLBACK["general"], (), ())


# is_valid 직접 검사 — 각 검사가 다른 검사에 기대지 않는지 확인한다
def test_is_valid_plain_sentence() -> None:
    assert is_valid("안내해 드립니다.", (), ()) is True


def test_is_valid_accepts_set_arguments() -> None:
    assert is_valid("잔액은 {{balance}}입니다.", {"balance"}, {"balance"}) is True
    assert is_valid("잔액을 안내해 드립니다.", {"balance"}, {"balance"}) is False


def test_is_valid_empty() -> None:
    assert is_valid("", (), ()) is False
    assert is_valid(" \n ", (), ()) is False


def test_is_valid_missing_required_slot() -> None:
    assert is_valid("잔액을 안내해 드립니다.", ("balance",), ("balance",)) is False


def test_is_valid_required_slot_must_be_a_token() -> None:
    # 슬롯 이름이 토큰이 아닌 글자로만 있으면 누락이다
    assert is_valid("balance 안내입니다.", ("balance",), ("balance",)) is False


def test_is_valid_digit_only_problem() -> None:
    assert is_valid("최근 5건입니다.", (), ()) is False


def test_is_valid_percent_without_digit() -> None:
    assert is_valid("금리는 몇 %입니다.", (), ()) is False


def test_is_valid_mask_token() -> None:
    # 마스킹 토큰 정규식은 숫자를 포함하므로 숫자 검사와 완전히 분리할 수는 없다
    assert is_valid("[계좌번호_1] 계좌입니다.", (), ()) is False


def test_is_valid_slot_outside_allowed() -> None:
    assert is_valid("잔액은 {{balance}}입니다.", (), ()) is False
    assert is_valid("잔액은 {{balance}}입니다.", ("balance",), ()) is True


def test_is_valid_empty_slot_name_is_never_allowed() -> None:
    assert is_valid("잔액은 {{}}입니다.", ("balance",), ()) is False
    assert is_valid("잔액은 {{ }}입니다.", ("balance",), ()) is False


def test_is_valid_document_keyword_only_problem() -> None:
    assert is_valid("재직 확인이 필요합니다.", (), ()) is False
