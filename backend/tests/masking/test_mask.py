"""계약 4(마스킹 토큰)와 docs/router/ARCHITECTURE.md 마스킹 규칙.

- 6종(주민번호·카드번호·계좌번호·전화번호·주소·금액)을 `[종류_n]` 토큰으로 바꾼다.
- 같은 원본 값은 같은 토큰, 다른 값은 종류별로 번호가 증가한다.
- mask_map은 토큰 → 원본. masked_text에 원본 값이 남지 않는다.
- 토큰 밖의 글자(공백·조사)는 바꾸지 않는다.
- 멱등성: 이미 마스킹된 텍스트를 다시 넣어도 바뀌지 않는다.
"""
import pytest

from app.masking import MaskResult, mask


def test_prd_acceptance_scenario():
    """docs/router/PRD.md 인수 기준의 고정 시나리오."""
    r = mask("제 계좌 110-1234-5678이고 주민번호 900101-1234567인데 잔액 알려줘")
    assert isinstance(r, MaskResult)
    assert r.masked_text == "제 계좌 [계좌번호_1]이고 주민번호 [주민번호_1]인데 잔액 알려줘"
    assert r.mask_map == {"[계좌번호_1]": "110-1234-5678", "[주민번호_1]": "900101-1234567"}


@pytest.mark.parametrize(
    "text, expected, token, original",
    [
        ("900101-1234567 입니다", "[주민번호_1] 입니다", "[주민번호_1]", "900101-1234567"),
        ("카드 1234-5678-9012-3456 분실", "카드 [카드번호_1] 분실", "[카드번호_1]", "1234-5678-9012-3456"),
        ("계좌 110-1234-5678 잔액", "계좌 [계좌번호_1] 잔액", "[계좌번호_1]", "110-1234-5678"),
        ("010-1234-5678 로 연락", "[전화번호_1] 로 연락", "[전화번호_1]", "010-1234-5678"),
        ("서울시 ○○구 ○○로 12 입니다", "[주소_1] 입니다", "[주소_1]", "서울시 ○○구 ○○로 12"),
        ("잔액이 1,234,567원 맞나요", "잔액이 [금액_1] 맞나요", "[금액_1]", "1,234,567원"),
        ("50만원 이체", "[금액_1] 이체", "[금액_1]", "50만원"),
    ],
)
def test_each_kind_uses_documented_example(text, expected, token, original):
    r = mask(text)
    assert r.masked_text == expected
    assert r.mask_map == {token: original}


def test_text_without_pii_is_unchanged():
    r = mask("잔액 조회는 어디서 해요?")
    assert r.masked_text == "잔액 조회는 어디서 해요?"
    assert r.mask_map == {}


def test_same_value_gets_same_token_and_different_values_increment():
    r = mask("110-1234-5678 에서 220-9876-5432 로, 다시 110-1234-5678 로")
    assert r.masked_text == "[계좌번호_1] 에서 [계좌번호_2] 로, 다시 [계좌번호_1] 로"
    assert r.mask_map == {"[계좌번호_1]": "110-1234-5678", "[계좌번호_2]": "220-9876-5432"}


def test_numbering_is_independent_per_kind():
    r = mask("900101-1234567 / 1234-5678-9012-3456 / 010-1234-5678 / 110-1234-5678 / 1,234,567원 / 서울시 강남구 테헤란로 12")
    assert r.masked_text == "[주민번호_1] / [카드번호_1] / [전화번호_1] / [계좌번호_1] / [금액_1] / [주소_1]"


# ---------- 종류 간 겹침: 주민번호 → 카드번호 → 전화번호 → 계좌번호 → 금액 → 주소 순으로 적용 ----------

def test_card_is_not_split_into_smaller_numbers():
    assert mask("1234-5678-9012-3456").masked_text == "[카드번호_1]"


def test_rrn_is_not_taken_as_account_or_amount():
    assert mask("900101-1234567").masked_text == "[주민번호_1]"


def test_phone_is_only_numbers_starting_with_01():
    assert mask("010-1234-5678").masked_text == "[전화번호_1]"
    assert mask("01012345678").masked_text == "[전화번호_1]"
    assert mask("010 1234 5678").masked_text == "[전화번호_1]"
    # 그 밖의 하이픈 숫자열은 계좌번호다 (docs/router/ARCHITECTURE.md 마스킹 규칙)
    assert mask("02-1234-5678").masked_text == "[계좌번호_1]"


@pytest.mark.parametrize("text", ["11만 5천원", "3억 5천만원", "1만원", "500원", "100만 원"])
def test_amount_formats(text):
    r = mask(text)
    assert r.masked_text == "[금액_1]"
    assert r.mask_map == {"[금액_1]": text}


def test_particle_after_amount_is_kept():
    assert mask("1,234,567원이 맞나요").masked_text == "[금액_1]이 맞나요"


@pytest.mark.parametrize(
    "text",
    ["2023-10-15 에 이체했어요", "2024년 1월 3일", "3.5% 금리", "6자리 번호", "1~2일 이내", "거래번호 2023-07-15-001 건"],
)
def test_dates_percent_and_plain_numbers_are_not_masked(text):
    r = mask(text)
    assert r.masked_text == text
    assert r.mask_map == {}


def test_address_with_province_and_two_district_levels():
    r = mask("경기도 성남시 분당구 판교로 235 으로 보내주세요")
    assert r.masked_text == "[주소_1] 으로 보내주세요"
    assert r.mask_map == {"[주소_1]": "경기도 성남시 분당구 판교로 235"}


def test_mask_is_idempotent():
    once = mask("계좌 110-1234-5678, 전화 010-1234-5678, 금액 50만원, 주소 서울시 강남구 테헤란로 12")
    twice = mask(once.masked_text)
    assert twice.masked_text == once.masked_text
    assert twice.mask_map == {}
