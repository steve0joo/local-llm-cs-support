import pytest

from app.agents.loan.validate import (
    ALLOWED_SLOTS,
    CHANNEL_KEYWORDS,
    DOCUMENT_KEYWORDS,
    PROMISE_PATTERNS,
    is_valid_output,
)

MATURITY = "2027-03-31"


def valid(text: str, *, extendable: bool = True, maturity: str = MATURITY) -> bool:
    return is_valid_output(text, maturity_date=maturity, extendable=extendable)


def test_constants():
    assert ALLOWED_SLOTS == ("loan_label", "principal_remaining", "extendable_status")
    for keyword in ("증명서", "등본", "재직", "소득"):
        assert keyword in DOCUMENT_KEYWORDS
    # "서류"라는 일반 단어는 막지 않는다(LN-002: 일반 안내는 허용). 구체적인 서류명만 막는다
    assert "서류" not in DOCUMENT_KEYWORDS
    # v1 모델이 지어낸 서류명(2026-09-29 실측)
    for keyword in ("명세서", "등기부", "계약서", "증빙"):
        assert keyword in DOCUMENT_KEYWORDS
    for keyword in ("앱", "어플", "모바일", "뱅킹", "고객센터", "콜센터", "영업점", "홈페이지"):
        assert keyword in CHANNEL_KEYWORDS
    assert PROMISE_PATTERNS


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
        "[금액_1]이 아니라 1,200원입니다.",  # 마스킹 토큰을 지워도 남는 숫자
        "[임의_1]에 대해 안내드립니다.",  # 계약 4에 없는 토큰은 예외가 아니다
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
        "등본을 준비해 주세요.",
        "초본과 신분증이 필요합니다.",
        "소득 확인이 필요합니다.",
        "인감도장을 지참해 주세요.",
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
        "필요한 서류는 상담원에게 확인해 주세요.",  # 일반 안내는 허용(LN-002)
        "[금액_1]에 대한 안내는 상담원에게 확인해 주세요.",  # 마스킹 토큰의 숫자는 검사에서 제외
        "[계좌번호_2]와 관련된 내용은 확인이 어렵습니다.",
        "{{extendable_status}} 연장 조건 등 자세한 사항은 상담원에게 확인해 주세요.",  # extendable_status 슬롯(2026-09-29)
        "{{loan_label}}의 만기일은 2027-03-31입니다. {{extendable_status}}",
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
        # 부정 표현은 "가능"과 같은 문장 안에 있어야 한다
        "연장은 불가합니다. 다른 조건은 가능합니다.",
        "연장이 가능합니다. 다만 다른 안내는 없습니다.",
        "연장이 가능합니다\n연장은 어렵지 않습니다",
    ],
)
def test_negation_is_checked_per_sentence(text):
    assert valid(text, extendable=False) is False


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


@pytest.mark.parametrize(
    "text",
    [
        "연장 신청은 모바일 앱에서 간편하게 진행하실 수 있습니다.",  # 없는 채널(실측)
        "자세한 내용은 저희 ★★ 어플을 통해 확인하실 수 있습니다.",
        "인터넷뱅킹이나 스마트뱅킹에서 조회하실 수 있습니다.",
        "고객센터로 연락 주시기 바랍니다.",
        "콜센터에서 안내해 드립니다.",
        "가까운 영업점을 방문해 주세요.",
        "홈페이지에서 확인해 주세요.",
    ],
)
def test_unavailable_channels_are_rejected(text):
    assert valid(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "정확한 금리는 확인 후 안내해 드리겠습니다.",  # 못 지키는 약속(실측)
        "상세 내역은 문자로 보내드리겠습니다.",
        "잠시만 기다려 주세요.",
        "조회해 보겠습니다.",
        "상담원을 연결해 드리겠습니다.",
        "처리해 드리겠습니다.",
        "알려드리겠습니다.",
        "확인한 후 알려 드리겠습니다.",  # 공백이 섞여도 잡는다
    ],
)
def test_unkeepable_promises_are_rejected(text):
    assert valid(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "연장 신청 시 기존 대출 계약서와 급여명세서가 필요합니다.",  # 실측
        "최근 소득증명서가 필요합니다.",
        "등기부등본을 준비해 주세요.",
        "소득 증빙 자료가 필요합니다.",
    ],
)
def test_more_document_names_are_rejected(text):
    assert valid(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "제공된 정보로는 알 수 없어 상담원에게 확인해 주세요.",
        "연장 조건은 상담원에게 확인해 주시기 바랍니다.",
        "{{loan_label}}의 만기일은 2027-03-31입니다. {{extendable_status}} 자세한 사항은 상담원에게 문의해 주세요.",
    ],
)
def test_counselor_referral_is_not_blocked(text):
    assert valid(text) is True
