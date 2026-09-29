"""게이트웨이 분기 (docs/router/ARCHITECTURE.md 게이트웨이 처리 순서, docs/ARCHITECTURE.md 계약 1·3).

classify와 에이전트는 목, 마스킹은 진짜를 쓴다.
- 지원 주제 1개 → answer / 2개 이상 → clarify(되묻기 + pending 저장) / 미지원만 → unsupported / 없음 → clarify(3개 선택지)
- choice가 오면 라우팅을 건너뛴다. pending이 있으면 원래 질문을 에이전트에 넘기고 pending을 비운다.
- 에이전트와 classify는 마스킹된 문장만 본다. history에는 answer 턴만 쌓이고 원본 값·슬롯 값은 들어가지 않는다.
"""
import httpx
import pytest

from app.agents.base import AgentReply, AgentRequest
from app.gateway import dispatch as dispatch_module
from app.gateway.dispatch import dispatch
from app.gateway.session import get_session
from app.router import RouteResult
from app.router.topics import DISPLAY_NAMES, SUPPORTED


class FakeAgent:
    def __init__(self, name):
        self.name = name
        self.requests: list[AgentRequest] = []
        self.reply = AgentReply(text=f"{name} 답변 {{{{slot}}}}", slots={"slot": "1,234원"}, options=[])

    def handle(self, req):
        self.requests.append(req)
        return self.reply


class FakeClassify:
    def __init__(self):
        self.topics: list[str] = ["balance"]
        self.calls: list[str] = []

    def __call__(self, masked_text):
        self.calls.append(masked_text)
        return RouteResult(topics=list(self.topics))


@pytest.fixture(autouse=True)
def fresh_sessions(monkeypatch):
    monkeypatch.setattr("app.gateway.session.sessions", {})


@pytest.fixture
def agents(monkeypatch):
    fakes = {name: FakeAgent(name) for name in SUPPORTED}
    for name, fake in fakes.items():
        monkeypatch.setitem(dispatch_module.AGENTS, name, fake)
    return fakes


@pytest.fixture
def classifier(monkeypatch):
    fake = FakeClassify()
    monkeypatch.setattr("app.router.classify", fake)
    return fake


def option(topic):
    return {"label": DISPLAY_NAMES[topic], "choice": topic}


# ---------- 분기 ----------

def test_one_supported_topic_is_answered_by_that_agent(agents, classifier):
    classifier.topics = ["balance"]
    res = dispatch("s1", "C001", "잔액 알려줘")
    assert res == {
        "type": "answer", "agent": "balance", "topic": "balance",
        "text": "balance 답변 {{slot}}", "slots": {"slot": "1,234원"}, "options": [],
    }
    req = agents["balance"].requests[0]
    assert isinstance(req, AgentRequest)
    assert (req.session_id, req.customer_id, req.masked_text, req.mask_map, req.history) == ("s1", "C001", "잔액 알려줘", {}, [])


def test_two_supported_topics_ask_back_and_keep_the_question(agents, classifier):
    classifier.topics = ["loan", "interest"]
    res = dispatch("s1", "C002", "대출 잔액이랑 이자 얼마 남았어요?")
    assert res == {
        "type": "clarify", "agent": None, "topic": None,
        "text": "어느 쪽을 먼저 도와드릴까요?", "slots": {}, "options": [option("loan"), option("interest")],
    }
    assert all(fake.requests == [] for fake in agents.values())
    assert get_session("s1").pending.masked_text == "대출 잔액이랑 이자 얼마 남았어요?"


def test_clarify_options_follow_supported_order(agents, classifier):
    classifier.topics = ["interest", "balance"]
    res = dispatch("s1", "C001", "잔액이랑 이자")
    assert res["options"] == [option("balance"), option("interest")]


def test_only_unsupported_topics_is_unsupported_with_first_code(agents, classifier):
    classifier.topics = ["fx"]
    res = dispatch("s1", "C001", "환전하고 싶어요")
    assert res["type"] == "unsupported"
    assert res["topic"] == "fx"
    assert res["agent"] is None
    assert res["text"] == dispatch_module.UNSUPPORTED_TEXT
    assert res["options"] == []
    assert all(fake.requests == [] for fake in agents.values())


def test_supported_plus_unsupported_goes_to_the_supported_agent(agents, classifier):
    classifier.topics = ["fx", "loan"]
    res = dispatch("s1", "C002", "대출이랑 환전")
    assert res["type"] == "answer" and res["agent"] == "loan"


def test_no_topics_asks_which_service_with_all_three_options(agents, classifier):
    classifier.topics = []
    res = dispatch("s1", "C001", "안녕하세요")
    assert res["type"] == "clarify"
    assert res["text"] == "어떤 업무를 도와드릴까요?"
    assert res["options"] == [option(t) for t in SUPPORTED]


# ---------- choice ----------

def test_choice_after_clarify_sends_original_question_and_clears_pending(agents, classifier):
    classifier.topics = ["loan", "interest"]
    dispatch("s1", "C002", "대출 잔액이랑 이자 얼마 남았어요?")
    res = dispatch("s1", "C002", "대출문의", choice="loan")
    assert res["type"] == "answer" and res["agent"] == "loan"
    assert agents["loan"].requests[0].masked_text == "대출 잔액이랑 이자 얼마 남았어요?"
    assert len(classifier.calls) == 1          # 두 번째 요청은 라우팅을 건너뛴다
    assert get_session("s1").pending is None


def test_choice_without_pending_uses_the_current_message(agents, classifier):
    res = dispatch("s1", "C002", "입출금 ****5678", choice="balance")
    assert res["type"] == "answer"
    assert agents["balance"].requests[0].masked_text == "입출금 ****5678"
    assert classifier.calls == []


def test_unknown_choice_is_unsupported_not_an_error(agents, classifier):
    res = dispatch("s1", "C001", "환전", choice="fx")
    assert res["type"] == "unsupported"
    assert all(fake.requests == [] for fake in agents.values())
    assert classifier.calls == []


# ---------- 마스킹과 history ----------

def test_agent_and_classifier_see_masked_text_only(agents, classifier):
    dispatch("s1", "C001", "제 계좌 110-1234-5678 잔액 알려줘")
    req = agents["balance"].requests[0]
    assert req.masked_text == "제 계좌 [계좌번호_1] 잔액 알려줘"
    assert req.mask_map == {"[계좌번호_1]": "110-1234-5678"}
    assert classifier.calls == ["제 계좌 [계좌번호_1] 잔액 알려줘"]


def test_pending_keeps_the_original_mask_map(agents, classifier):
    classifier.topics = ["loan", "interest"]
    dispatch("s1", "C002", "계좌 110-1234-5678 대출 잔액이랑 이자")
    dispatch("s1", "C002", "이자/연체", choice="interest")
    req = agents["interest"].requests[0]
    assert req.masked_text == "계좌 [계좌번호_1] 대출 잔액이랑 이자"
    assert req.mask_map == {"[계좌번호_1]": "110-1234-5678"}


def test_history_accumulates_answer_turns_only(agents, classifier):
    classifier.topics = ["balance"]
    dispatch("s1", "C001", "잔액")                       # answer
    classifier.topics = ["loan", "interest"]
    dispatch("s1", "C001", "대출 이자")                  # clarify — history에 안 쌓임
    classifier.topics = ["fx"]
    dispatch("s1", "C001", "환전")                       # unsupported — history에 안 쌓임
    classifier.topics = ["balance"]
    dispatch("s1", "C001", "거래내역")                   # answer

    second = agents["balance"].requests[1]
    assert second.history == [
        {"role": "user", "content": "잔액"},
        {"role": "assistant", "content": "balance 답변 {{slot}}"},
    ]
    assert len(get_session("s1").history) == 4


def test_history_has_no_original_values_or_slot_values(agents, classifier):
    dispatch("s1", "C001", "제 계좌 110-1234-5678 잔액")
    contents = [turn["content"] for turn in get_session("s1").history]
    assert all("110-1234-5678" not in c and "1,234원" not in c for c in contents)
    assert contents == ["제 계좌 [계좌번호_1] 잔액", "balance 답변 {{slot}}"]


def test_sessions_are_isolated(agents, classifier):
    dispatch("s1", "C001", "잔액")
    dispatch("s2", "C001", "잔액")
    assert agents["balance"].requests[1].history == []


def test_new_message_after_clarify_discards_stale_pending(agents, classifier):
    """되묻기 뒤 버튼 대신 타이핑하면 이전 되묻기는 무효다. 이후 계좌 선택 choice에 옛 질문이 딸려가면 안 된다."""
    classifier.topics = ["loan", "interest"]
    dispatch("s1", "C002", "대출 잔액이랑 이자 얼마 남았어요?")      # clarify → pending 저장
    classifier.topics = ["balance"]
    dispatch("s1", "C002", "잔액 알려줘")                          # 타이핑 → pending 무효
    assert get_session("s1").pending is None
    dispatch("s1", "C002", "입출금 ****5678", choice="balance")    # 계좌 선택 버튼
    assert agents["balance"].requests[-1].masked_text == "입출금 ****5678"


# ---- 모델 호출 실패 안전망 ----

def test_agent_model_failure_returns_fallback_answer_not_500(agents, classifier, monkeypatch):
    def broken(req):
        raise httpx.ConnectError("Ollama down")

    monkeypatch.setattr(agents["balance"], "handle", broken)
    res = dispatch("s1", "C001", "잔액 알려줘")
    assert res["type"] == "answer" and res["agent"] == "balance" and res["topic"] == "balance"
    assert res["text"] == dispatch_module.MODEL_UNAVAILABLE_TEXT
    assert res["slots"] == {} and res["options"] == []
    assert get_session("s1").history == []      # 게이트웨이 문장은 모델 문맥이 아니다


def test_non_http_agent_errors_still_propagate(agents, classifier, monkeypatch):
    """코드 버그(KeyError 등)까지 삼키면 안 된다. 안전망은 모델 호출 실패에만 적용한다."""
    monkeypatch.setattr(agents["balance"], "handle", lambda req: (_ for _ in ()).throw(KeyError("bug")))
    with pytest.raises(KeyError):
        dispatch("s1", "C001", "잔액 알려줘")
