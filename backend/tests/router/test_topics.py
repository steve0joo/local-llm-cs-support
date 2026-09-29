"""topics.py 표들 사이의 일관성. 값 자체(라벨 원문)는 docs/ARCHITECTURE.md 계약 2가 기준이라 여기서 다시 적지 않는다."""
from app.router.topics import DISPLAY_NAMES, KEYWORDS, SUPPORTED, SYSTEM_PROMPT, TOPIC_LABELS


def test_nine_codes_and_supported_are_subset():
    assert len(TOPIC_LABELS) == 9
    assert set(SUPPORTED) == {"balance", "loan", "interest"} <= set(TOPIC_LABELS)


def test_supported_tables_cover_exactly_the_supported_topics():
    assert set(DISPLAY_NAMES) == set(SUPPORTED)
    assert set(KEYWORDS) == set(SUPPORTED)


def test_system_prompt_lists_every_code():
    """프롬프트의 코드 목록이 표와 어긋나면 모델이 없는 코드를 내거나 빠진 코드를 못 낸다."""
    for code in TOPIC_LABELS:
        assert code in SYSTEM_PROMPT
