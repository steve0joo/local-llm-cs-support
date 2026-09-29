from dataclasses import dataclass, field

from app.masking import MaskResult


@dataclass
class Session:
    history: list[dict] = field(default_factory=list)   # answer 턴의 [{"role", "content"}] — 계약 3 형식
    pending: MaskResult | None = None                    # 되묻기(clarify) 뒤 선택지를 누를 때까지 보관하는 원래 질문


sessions: dict[str, Session] = {}


def get_session(session_id: str) -> Session:
    return sessions.setdefault(session_id, Session())
