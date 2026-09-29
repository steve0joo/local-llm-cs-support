from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.gateway.dispatch import dispatch


class ChatRequest(BaseModel):
    session_id: str
    customer_id: str
    message: str
    choice: str | None = None       # 선택지 클릭 시에만. 있으면 라우팅을 건너뛴다


class ChatOption(BaseModel):
    label: str
    choice: str


class ChatResponse(BaseModel):
    type: Literal["answer", "clarify", "unsupported"]
    agent: str | None
    topic: str | None
    text: str                       # {{슬롯}} 포함 가능
    slots: dict[str, str]           # 표시용으로 포맷이 끝난 문자열
    options: list[ChatOption]


router = APIRouter()


@router.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> dict:
    return dispatch(req.session_id, req.customer_id, req.message, req.choice)
