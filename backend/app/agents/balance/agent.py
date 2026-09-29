from app import llm
from app.agents.balance.intent import classify_intent
from app.agents.balance.mock_api import get_accounts, get_transactions
from app.agents.balance.prompt import build_messages, build_slots
from app.agents.balance.resolve import choose_account, find_clicked
from app.agents.balance.validate import validate_output
from app.agents.base import AgentReply, AgentRequest

MODEL = "cs-balance"


class BalanceAgent:
    name = "balance"

    def handle(self, req: AgentRequest) -> AgentReply:
        accounts = get_accounts(req.customer_id)
        clicked = find_clicked(req.masked_text, req.history, accounts)
        intent = classify_intent(clicked["question"] if clicked else req.masked_text)

        slots = {}
        if intent != "general":
            if clicked:
                account = clicked["account"]
            else:
                chosen = choose_account(accounts, req.mask_map)
                if "text" in chosen:
                    return AgentReply(text=chosen["text"], slots={}, options=chosen["options"])
                account = chosen["account"]
            transactions = get_transactions(account["account_id"]) if intent == "transactions" else None
            slots = build_slots(intent, account, transactions)

        messages = build_messages(req.history, req.masked_text, intent)
        text = validate_output(llm.generate(MODEL, messages), intent)
        return AgentReply(text=text, slots=slots, options=[])
