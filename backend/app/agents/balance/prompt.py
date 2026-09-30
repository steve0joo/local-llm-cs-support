import copy

from app.agents.balance.resolve import account_label

SLOT_NAMES: dict[str, tuple[str, ...]] = {
    "balance": ("account_label", "balance"),
    "transactions": ("account_label", "recent_transactions"),
    "general": (),
}

SYSTEM_PROMPT = (
    "당신은 은행 잔액조회 상담 보조 AI입니다. 고객에게 항상 정중한 존댓말로 답변하세요.\n"
    "금액과 계좌 정보는 제공된 슬롯(예: {{account_label}}, {{balance}})만 사용하고, "
    "슬롯이 제공되지 않았다면 슬롯을 쓰지 마세요. 슬롯이 아닌 숫자는 절대 답변에 포함하지 마세요.\n"
    "금리, 상품명, 수수료, 필요 서류는 알지 못하므로 임의로 만들어 내지 말고, "
    "확실하지 않은 내용은 상담원에게 확인하라고 안내하세요."
)


def _transaction_line(tx: dict) -> str:
    sign = "+" if tx["amount"] > 0 else "-"
    return f"{tx['date']} · {tx['description']} · {sign}{abs(tx['amount']):,}원"


def build_slots(
    intent: str, account: dict | None, transactions: list[dict] | None = None
) -> dict[str, str]:
    if intent == "balance":
        return {
            "account_label": account_label(account),
            "balance": f"{account['balance']:,}원",
        }
    if intent == "transactions":
        return {
            "account_label": account_label(account),
            "recent_transactions": "\n".join(_transaction_line(tx) for tx in transactions),
        }
    return {}


def _slot_line(intent: str) -> str:
    names = SLOT_NAMES[intent]
    return "사용할 수 있는 슬롯: " + ", ".join(f"{{{{{name}}}}}" for name in names)


def build_messages(history: list[dict], masked_text: str, intent: str) -> list[dict]:
    if intent == "general":
        user_content = masked_text
    else:
        user_content = f"{masked_text}\n{_slot_line(intent)}"
    return (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + copy.deepcopy(history)
        + [{"role": "user", "content": user_content}]
    )


def fallback_text(intent: str) -> str:
    if intent == "balance":
        return "{{account_label}} 계좌의 현재 잔액은 {{balance}}입니다."
    if intent == "transactions":
        return "{{account_label}} 계좌의 최근 거래내역입니다.\n{{recent_transactions}}"
    return "해당 내용은 정확한 안내를 위해 상담원에게 확인해 주세요."
