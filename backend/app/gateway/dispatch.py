# 한 턴의 처리: 마스킹 → (choice 또는 분류) → answer / clarify / unsupported (docs/router/ARCHITECTURE.md 게이트웨이 처리 순서).

from collections.abc import Iterable

import httpx

from app import router
from app.agents import balance, interest, loan
from app.agents.base import Agent, AgentRequest
from app.gateway.session import Session, get_session
from app.masking import MaskResult, mask
from app.router.topics import DISPLAY_NAMES, SUPPORTED

AGENTS: dict[str, Agent] = {"balance": balance.agent, "loan": loan.agent, "interest": interest.agent}

CLARIFY_TEXT = "어느 쪽을 먼저 도와드릴까요?"
NO_TOPIC_TEXT = "어떤 업무를 도와드릴까요?"
UNSUPPORTED_TEXT = "해당 주제는 아직 지원하지 않습니다. 상담원 연결을 도와드릴까요?"
MODEL_UNAVAILABLE_TEXT = "지금은 답변을 드릴 수 없습니다. 상담원 연결을 도와드릴까요?"   # 에이전트의 모델 호출 실패(Ollama 없음·모델 없음·타임아웃)


def dispatch(session_id: str, customer_id: str, message: str, choice: str | None = None) -> dict:
    session = get_session(session_id)
    question = mask(message)                              # 이후 모델 쪽에는 question.masked_text만 간다

    if choice is not None:                                # 선택지 클릭 → 라우팅 생략
        if choice not in AGENTS:
            return _response("unsupported", text=UNSUPPORTED_TEXT)
        if session.pending is not None:                   # 되묻기 뒤라면 보관해 둔 원래 질문을 쓴다
            question, session.pending = session.pending, None
        return _answer(session, session_id, customer_id, choice, question)

    session.pending = None                                # 새 질문이 오면 이전 되묻기는 무효
    topics = router.classify(question.masked_text).topics
    supported = [t for t in SUPPORTED if t in topics]

    if len(supported) >= 2:
        session.pending = question
        return _response("clarify", text=CLARIFY_TEXT, options=_options(supported))
    if len(supported) == 1:
        return _answer(session, session_id, customer_id, supported[0], question)
    if topics:
        return _response("unsupported", topic=topics[0], text=UNSUPPORTED_TEXT)
    return _response("clarify", text=NO_TOPIC_TEXT, options=_options(SUPPORTED))


def _answer(session: Session, session_id: str, customer_id: str, target: str, question: MaskResult) -> dict:
    req = AgentRequest(
        session_id=session_id,
        customer_id=customer_id,
        masked_text=question.masked_text,
        mask_map=question.mask_map,
        history=list(session.history),                 # 이번 턴 이전까지의 복사본
    )
    try:
        reply = AGENTS[target].handle(req)
    except httpx.HTTPError:                                # 모델 호출 실패는 500 대신 안내 문장으로. 코드 버그는 그대로 올린다
        return _response("answer", agent=target, topic=target, text=MODEL_UNAVAILABLE_TEXT)
    session.history += [
        {"role": "user", "content": question.masked_text},
        {"role": "assistant", "content": reply.text},  # {{슬롯}} 그대로, 슬롯 값은 넣지 않는다
    ]
    return _response("answer", agent=target, topic=target, text=reply.text, slots=reply.slots, options=reply.options)


def _options(topics: Iterable[str]) -> list[dict]:
    return [{"label": DISPLAY_NAMES[t], "choice": t} for t in topics]


def _response(type_: str, *, agent=None, topic=None, text: str, slots=None, options=None) -> dict:
    return {"type": type_, "agent": agent, "topic": topic, "text": text, "slots": slots or {}, "options": options or []}
