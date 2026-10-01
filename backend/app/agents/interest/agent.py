"""이자/연체 에이전트 (docs/agent-interest/ARCHITECTURE.md handle() 흐름).

조회·슬롯·검증은 코드가 하고, 모델은 슬롯 이름으로 상담 문장만 만든다.
"""

from app import llm
from app.agents.base import AgentReply, AgentRequest
from app.agents.interest.balance_source import enrich
from app.agents.interest.mock_api import get_interest
from app.agents.interest.prompt import build_messages, build_slots, fallback_text
from app.agents.interest.validate import is_valid, required_slots

MODEL = "cs-interest"  # 계약 5
NO_LOAN_TEXT = "고객님 명의로 조회되는 대출 이자 내역이 없습니다."


class InterestAgent:
    name = "interest"

    def handle(self, req: AgentRequest) -> AgentReply:
        items = get_interest(req.customer_id)
        if not items:  # INT-003: 없는 이자·연체를 지어낼 여지를 없앤다
            return AgentReply(text=NO_LOAN_TEXT, slots={}, options=[])

        item = enrich(items[0], req.customer_id)  # mock 고객은 대출이 최대 1건(계약 6). 자동이체 계좌 잔액 비교 결과를 붙인다
        slots = build_slots(item)
        try:
            text = llm.generate(MODEL, build_messages(req.masked_text, req.history, item)).strip()
        except Exception:  # Ollama 중단·시간 초과. 조회 사실만 담은 기본 문장으로 답한다
            text = ""  # 빈 답은 검증에서 떨어져 fallback_text로 바뀐다
        required = required_slots(req.masked_text, overdue=item["overdue_days"] > 0)
        if not is_valid(text, allowed_slots=set(slots), required_slots=required):
            text = fallback_text(item)
        return AgentReply(text=text, slots=slots, options=[])
