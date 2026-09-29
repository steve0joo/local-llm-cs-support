"""대출문의 에이전트 handle() (docs/agent-loan/ARCHITECTURE.md handle() 1~7단계)."""
from app import llm
from app.agents.base import AgentReply, AgentRequest
from app.agents.loan import prompt, validate
from app.agents.loan.mock_api import get_loans


class LoanAgent:
    name = "loan"

    def handle(self, req: AgentRequest) -> AgentReply:
        loans = get_loans(req.customer_id)
        if not loans:
            return AgentReply(text=prompt.NO_LOAN_TEXT, slots={}, options=[])

        loan = loans[0]  # mock 고객은 대출이 최대 1건(계약 6). 2건 이상이면 첫 번째를 쓴다.
        slots = prompt.build_slots(loan)
        messages = prompt.build_messages(req.history, req.masked_text, loan)
        text = llm.generate("cs-loan", messages)

        if not validate.is_valid_output(
            text, maturity_date=loan["maturity_date"], extendable=loan["extendable"]
        ):
            text = prompt.fallback_text(loan)

        return AgentReply(text=text, slots=slots, options=[])


agent = LoanAgent()
