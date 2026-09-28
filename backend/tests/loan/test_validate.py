import pytest

from app.agents.loan.validate import (
    ALLOWED_SLOTS,
    DOCUMENT_KEYWORDS,
    is_valid_output,
)

MATURITY = "2027-03-31"


def valid(text: str, *, extendable: bool = True, maturity: str = MATURITY) -> bool:
    return is_valid_output(text, maturity_date=maturity, extendable=extendable)


def test_constants():
    assert ALLOWED_SLOTS == ("loan_label", "principal_remaining")
    for keyword in ("서류", "증명서", "등본", "재직", "소득"):
        assert keyword in DOCUMENT_KEYWORDS


@pytest.mark.parametrize(
    "text",
    [
        "금리는 연 3.5%입니다.",  # 퍼센트 수치
        "1,200만원입니다.",  # 금액
        "12000000원입니다.",  # 금액 원본
        "2027-04-01까지 연장됩니다.",  # 만기일이 아닌 다른 날짜
        "2028년 3월 31일까지 연장됩니다.",  # 다른 날짜(한글 표기)
        "3영업일 걸립니다.",  # 지어낸 기간
        "2027-03-31에 3일 남았어요.",  # 허용 날짜 + 다른 숫자
        "1. 상담원에게 문의해 주세요.",  # 번호 목록도 숫자로 취급
        "",  # 빈 출력
        "   ",
    ],
)
def test_digits_or_empty_are_rejected(text):
    assert valid(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "{{balance}}입니다.",  # 허용 밖 슬롯
        "{{loan_label}}의 잔액은 {{balance}}입니다.",  # 허용 슬롯과 섞임
        "{{loan_label}의 만기일입니다.",  # 깨진 슬롯
        "{{ interest_due }}입니다.",
    ],
)
def test_unknown_or_broken_slots_are_rejected(text):
    assert valid(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "재직증명서가 필요합니다.",
        "필요한 서류는 상담원에게 확인해 주세요.",  # 서류 언급 자체를 막는다
        "등본을 준비해 주세요.",
        "소득 확인이 필요합니다.",
    ],
)
def test_document_keywords_are_rejected(text):
    assert valid(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "만기일은 2027-03-31입니다. {{principal_remaining}} 남았습니다.",
        "만기일은 2027년 3월 31일입니다.",
        "만기일은 2027년 03월 31일입니다.",  # 0 패딩 표기
        "{{loan_label}}의 남은 원금은 {{principal_remaining}}입니다. 자세한 사항은 상담원에게 확인해 주세요.",
        "연장 조건은 상담원에게 확인해 주세요.",
    ],
)
def test_valid_outputs_pass(text):
    assert valid(text) is True


def test_allowed_date_follows_the_given_maturity():
    assert valid("만기일은 2035-06-30입니다.", maturity="2035-06-30") is True
    assert valid("만기일은 2027-03-31입니다.", maturity="2035-06-30") is False


def test_non_extendable_rejects_affirmative_extension():
    assert valid("연장이 가능합니다.", extendable=False) is False
    assert valid("연장 가능합니다. 상담원에게 확인해 주세요.", extendable=False) is False


@pytest.mark.parametrize(
    "text",
    [
        "연장이 어렵습니다. 상담원에게 확인해 주세요.",
        "현재 연장 가능으로 조회되지 않습니다.",
        "연장은 불가로 조회됩니다.",
        "연장에 대해서는 상담원에게 확인해 주세요.",
    ],
)
def test_non_extendable_accepts_negative_or_neutral(text):
    assert valid(text, extendable=False) is True


def test_extendable_true_may_say_possible():
    assert valid("연장이 가능합니다.", extendable=True) is True
