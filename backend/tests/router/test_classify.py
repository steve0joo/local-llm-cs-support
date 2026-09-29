"""계약 2 `classify(masked_text) -> RouteResult`와 RT-002 복합 문의 규칙 (docs/ARCHITECTURE.md, docs/router/ADR.md).

- 키워드 규칙이 지원 주제 2개 이상을 감지하면 모델을 부르지 않고 그 주제들을 돌려준다.
- 1개 이하면 cs-router 출력을 파싱한다. 계약 2에 없는 값이면 빈 topics.
- 모델 호출이 실패하면(연결 거부·모델 없음·타임아웃) 키워드로 잡힌 지원 주제 0~1개로 폴백한다.
"""
import httpx
import pytest

from app.router import RouteResult, classify
from app.router.topics import SYSTEM_PROMPT, TOPIC_LABELS


class FakeModel:
    """llm.generate 자리에 들어가 호출을 기록하고 정해 둔 답을 돌려준다."""

    def __init__(self, reply="balance"):
        self.reply = reply
        self.calls = []

    def __call__(self, model, messages, **options):
        self.calls.append({"model": model, "messages": messages, "options": options})
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


@pytest.fixture
def model(monkeypatch):
    fake = FakeModel()
    monkeypatch.setattr("app.llm.generate", fake)
    return fake


# --- RT-002: 복합 문의는 키워드 규칙으로 판별 -------------------------------------------

@pytest.mark.parametrize("text", [
    "대출 잔액이랑 이자 얼마 남았어요?",       # "대출 잔액"은 계좌 잔액이 아니다 → balance 아님
    "대출 이자가 왜 이렇게 많이 나왔어요?",
])
def test_two_supported_topics_return_both_without_calling_model(model, text):
    assert classify(text) == RouteResult(topics=["loan", "interest"])
    assert model.calls == []


def test_single_topic_uses_model_output(model):
    model.reply = "balance"
    assert classify("내 잔액 얼마야?").topics == ["balance"]
    assert len(model.calls) == 1


def test_loan_balance_alone_is_not_balance(model):
    """'대출 잔액'만 있으면 키워드는 loan 1개 → 모델 출력을 쓴다."""
    model.reply = "loan"
    assert classify("대출 잔액 알려줘").topics == ["loan"]


# --- 모델 출력 파싱 ------------------------------------------------------------------

@pytest.mark.parametrize("code", sorted(TOPIC_LABELS))
def test_every_contract_2_code_is_accepted(model, code):
    model.reply = code
    assert classify("문의드립니다").topics == [code]


@pytest.mark.parametrize("raw", [" balance\n", '"balance"', "Balance", "`balance`"])
def test_whitespace_quotes_and_case_are_stripped(model, raw):
    model.reply = raw
    assert classify("문의드립니다").topics == ["balance"]


@pytest.mark.parametrize("raw", ["기타", "", "balance loan", "정답: balance"])
def test_value_not_in_contract_2_gives_empty_topics(model, raw):
    model.reply = raw
    assert classify("문의드립니다").topics == []


def test_unsupported_topic_is_returned_as_is(model):
    model.reply = "fx"
    assert classify("달러 환전하고 싶어요").topics == ["fx"]


# --- 모델 호출 형식 ------------------------------------------------------------------

def test_model_call_format(model):
    classify("[계좌번호_1] 잔액 알려줘")
    call = model.calls[0]
    assert call["model"] == "cs-router"
    assert call["messages"] == [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "[계좌번호_1] 잔액 알려줘"},   # 마스킹된 문장 그대로, 원본 없음
    ]
    assert call["options"] == {"temperature": 0}


# --- 폴백: 모델이 없거나 호출 실패 -------------------------------------------------------

@pytest.mark.parametrize("error", [
    httpx.ConnectError("connection refused"),
    httpx.HTTPStatusError("404", request=httpx.Request("POST", "http://x"), response=httpx.Response(404)),
    httpx.ReadTimeout("timeout"),
])
def test_model_failure_falls_back_to_single_keyword_topic(model, error):
    model.reply = error
    assert classify("내 잔액 얼마야?").topics == ["balance"]


def test_model_failure_without_keyword_gives_empty_topics(model):
    model.reply = httpx.ConnectError("connection refused")
    assert classify("안녕하세요").topics == []
