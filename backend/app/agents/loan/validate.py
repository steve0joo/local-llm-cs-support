import re

# 구체적인 서류명만 막는다. "서류"라는 일반 단어는 허용한다(LN-002: 일반 안내는 허용, LN-004 c)
DOCUMENT_KEYWORDS: tuple[str, ...] = (
    "증명서",
    "등본",
    "초본",
    "재직",
    "소득",
    "신분증",
    "인감",
    "원천징수",
    "사본",
)
ALLOWED_SLOTS: tuple[str, ...] = ("loan_label", "principal_remaining", "extendable_status")

_NEGATIONS = ("불가", "않", "어렵", "없")
_SLOT_PATTERN = re.compile(r"\{\{\s*([^{}]*?)\s*\}\}")
# 계약 4의 마스킹 토큰. 모델이 되풀이해도 원본 값이 아니므로 숫자 검사에서 제외한다(LN-004 a)
_MASK_TOKEN = re.compile(r"\[(?:주민번호|카드번호|계좌번호|전화번호|주소|금액)_\d+\]")
_SENTENCE_SPLIT = re.compile(r"[.!?\n]+")


def _strip_allowed_numbers(text: str, maturity_date: str) -> str:
    year, month, day = (int(part) for part in maturity_date.split("-"))
    korean = rf"{year}년\s*0?{month}월\s*0?{day}일"
    text = _MASK_TOKEN.sub("", text.replace(maturity_date, ""))
    return re.sub(korean, "", text)


def is_valid_output(text: str, *, maturity_date: str, extendable: bool) -> bool:
    if not text.strip():
        return False

    # a. 프롬프트에 준 만기일 표기와 마스킹 토큰 외에 숫자가 있으면 금액·퍼센트·다른 날짜·기간을 지어낸 것으로 본다
    if re.search(r"\d", _strip_allowed_numbers(text, maturity_date)):
        return False

    # b. 허용 밖 슬롯, 깨진 슬롯
    slots = _SLOT_PATTERN.findall(text)
    if any(name not in ALLOWED_SLOTS for name in slots):
        return False
    if text.count("{{") != len(slots) or text.count("}}") != len(slots):
        return False

    # c. 구체적인 서류 요건
    if any(keyword in text for keyword in DOCUMENT_KEYWORDS):
        return False

    # d. 연장 불가인데 같은 문장 안에 부정 표현 없이 "가능"이라고 한 경우
    if not extendable:
        for sentence in _SENTENCE_SPLIT.split(text):
            if "가능" in sentence and not any(n in sentence for n in _NEGATIONS):
                return False

    return True
