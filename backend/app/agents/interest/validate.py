"""모델 출력 검증. 실패하면 에이전트가 기본 문장(prompt.fallback_text)으로 대체한다."""

import re

# 날짜(2026-10-25, 10월 25일)와 연체 일수(12일)는 걸리지 않아야 한다.
_AMOUNT = re.compile(r"\d{1,3}(?:,\d{3})+|\d+\s*[만천백]?\s*원")
_RATE = re.compile(r"\d+(?:\.\d+)?\s*(?:%|퍼센트|프로)")
_MASK_TOKEN = re.compile(r"\[[가-힣]+_\d+\]")
_SLOT = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def is_valid(text: str, allowed_slots: set[str], required_slots: set[str]) -> bool:
    if not text.strip():
        return False
    if _AMOUNT.search(text) or _RATE.search(text) or _MASK_TOKEN.search(text):
        return False
    used = set(_SLOT.findall(text))
    return used <= allowed_slots and required_slots <= used
