"""모델 출력 검증. 실패하면 에이전트가 기본 문장(prompt.fallback_text)으로 대체한다."""

import re

# 날짜(2026-10-25, 10월 25일)와 연체 일수(12일)는 걸리지 않아야 한다.
_AMOUNT = re.compile(r"\d{1,3}(?:,\d{3})+|\d+\s*[만천백]?\s*원")
_RATE = re.compile(r"\d+(?:\.\d+)?\s*(?:%|퍼센트|프로)")
_MASK_TOKEN = re.compile(r"\[[가-힣]+_\d+\]")
_SLOT = re.compile(r"\{\{\s*(\w+)\s*\}\}")
# 연체 "상태"를 묻는 질문. "연체 가산금리", "연체이자가 뭐예요"처럼 규정·용어를 묻는 질문은 제외한다.
_OVERDUE_QUESTION = re.compile(r"연체(?:된|됐|되었|되어|\s*금액|\s*중)|연체.{0,6}(?:있|없)|밀린|미납")


def is_valid(text: str, allowed_slots: set[str], required_slots: set[str]) -> bool:
    if not text.strip():
        return False
    if _AMOUNT.search(text) or _RATE.search(text) or _MASK_TOKEN.search(text):
        return False
    used = set(_SLOT.findall(text))
    return used <= allowed_slots and required_slots <= used


def required_slots(question: str, overdue: bool) -> set[str]:
    """연체 고객이 연체 상태를 물으면 답에 {{overdue_amount}}가 있어야 한다."""
    return {"overdue_amount"} if overdue and _OVERDUE_QUESTION.search(question) else set()
