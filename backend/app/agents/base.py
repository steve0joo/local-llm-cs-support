from dataclasses import dataclass
from typing import Protocol


# 게이트웨이가 에이전트에게
@dataclass
class AgentRequest:
    session_id: str
    customer_id: str
    masked_text: str
    mask_map: dict[str, str]      # 마스킹 토큰 → 원본. Python 코드에서만 사용, 프롬프트 금지
    history: list[dict]           # 이전 턴 [{"role": "user" | "assistant", "content": str}] — Ollama messages 형식 그대로


# 에이전트가 게이트웨이에게
@dataclass
class AgentReply:
    text: str                     # {{슬롯}} 포함 가능
    slots: dict[str, str]         # 표시용 값. 프론트가 text의 {{슬롯}}을 이 값으로 치환한다
    options: list[dict]           # [{"label": ..., "choice": ...}] — 계좌 선택 등


# 에이전트가 갖추어야 할 모양
class Agent(Protocol):
    name: str                     # 예: "balance" | "loan" | "interest"

    def handle(self, req: AgentRequest) -> AgentReply: ...
