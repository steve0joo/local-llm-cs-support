import re
from dataclasses import dataclass

import httpx

from app import llm
from app.router.topics import KEYWORDS, SUPPORTED, SYSTEM_PROMPT, TOPIC_LABELS

MODEL = "cs-router"                                        # 계약 5 모델 이름
_LOAN_BALANCE = re.compile(r"대출\s*(?:잔액|잔고)")          # "대출 잔액"은 남은 원금 → balance 키워드로 세지 않는다 (RT-002)


# 계약 2 결과 타입. topics는 확신 높은 순, 0개 이상.
@dataclass
class RouteResult:
    topics: list[str]


# RT-002 키워드 규칙 — 문장에 걸린 지원 주제를 SUPPORTED 순서로 돌려준다
def keyword_topics(masked_text: str) -> list[str]:
    text = _LOAN_BALANCE.sub("대출", masked_text)
    return [topic for topic in SUPPORTED if any(word in text for word in KEYWORDS[topic])]


# 모델 출력 → 계약 2 코드. 공백·따옴표·대소문자만 정리하고 정확히 일치할 때만 채택한다.
def parse_topic(raw: str) -> str | None:
    code = raw.strip().strip("\"'`").strip().lower()
    return code if code in TOPIC_LABELS else None


def classify(masked_text: str) -> RouteResult:
    found = keyword_topics(masked_text)
    if len(found) >= 2:                                    # 복합 문의 → 모델을 부르지 않고 되묻기로
        return RouteResult(topics=found)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": masked_text}]
    try:
        raw = llm.generate(MODEL, messages, temperature=0)
    except httpx.HTTPError:                                # Ollama 없음·모델 없음·타임아웃 → 키워드 0~1개로 폴백
        return RouteResult(topics=found)

    code = parse_topic(raw)
    return RouteResult(topics=[code] if code else [])
