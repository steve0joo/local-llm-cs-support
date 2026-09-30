import re
from collections.abc import Iterable

from app.agents.balance.prompt import SLOT_NAMES, fallback_text

DOCUMENT_KEYWORDS = ("서류", "증명서", "등본", "재직", "소득")

_DIGIT = re.compile(r"\d")
_MASK_TOKEN = re.compile(r"\[[가-힣]+_\d+\]")
_SLOT_TOKEN = re.compile(r"\{\{([^{}]*)\}\}")


def is_valid(text: str, allowed_slots: Iterable[str], required_slots: Iterable[str]) -> bool:
    used = {name.strip() for name in _SLOT_TOKEN.findall(text)}
    allowed = set(allowed_slots)
    if not text.strip():
        return False
    if any(name not in used for name in required_slots):
        return False
    if _DIGIT.search(text):
        return False
    if "%" in text:
        return False
    if _MASK_TOKEN.search(text):
        return False
    if any(name not in allowed for name in used):
        return False
    if any(keyword in text for keyword in DOCUMENT_KEYWORDS):
        return False
    return True


def validate_output(text: str, intent: str) -> str:
    slots = SLOT_NAMES[intent]
    if is_valid(text, slots, slots):
        return text
    return fallback_text(intent)
