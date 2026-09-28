from fastapi import APIRouter

from app.agents.base import AgentReply, AgentRequest


class _StubAgent:
    name = "interest"

    def handle(self, req: AgentRequest) -> AgentReply:
        return AgentReply(text="준비 중인 기능입니다.", slots={}, options=[])


agent = _StubAgent()
mock_router = APIRouter()   # 비어 있음. /mock/... 라우트는 담당이 넣는다
