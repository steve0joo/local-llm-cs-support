import re

DOCUMENT_KEYWORDS: tuple[str, ...] = ("서류", "증명서", "등본", "재직", "소득")
ALLOWED_SLOTS: tuple[str, ...] = ("loan_label", "principal_remaining")

_NEGATIONS = ("불가", "않", "어렵", "없")
_SLOT_PATTERN = re.compile(r"\{\{\s*([^{}]*?)\s*\}\}")


def _strip_allowed_dates(text: str, maturity_date: str) -> str:
    year, month, day = (int(part) for part in maturity_date.split("-"))
    korean = rf"{year}년\s*0?{month}월\s*0?{day}일"
    return re.sub(korean, "", text.replace(maturity_date, ""))


def is_valid_output(text: str, *, maturity_date: str, extendable: bool) -> bool:
    if not text.strip():
        return False

    # a. 프롬프트에 준 만기일 표기 외에 숫자가 있으면 금액·퍼센트·다른 날짜·기간을 지어낸 것으로 본다
    if re.search(r"\d", _strip_allowed_dates(text, maturity_date)):
        return False

    # b. 허용 밖 슬롯, 깨진 슬롯
    slots = _SLOT_PATTERN.findall(text)
    if any(name not in ALLOWED_SLOTS for name in slots):
        return False
    if text.count("{{") != len(slots) or text.count("}}") != len(slots):
        return False

    # c. 서류 요건
    if any(keyword in text for keyword in DOCUMENT_KEYWORDS):
        return False

    # d. 연장 불가인데 부정 표현 없이 "가능"이라고 한 경우
    if not extendable and "가능" in text and not any(n in text for n in _NEGATIONS):
        return False

    return True
