PROCEDURE_WORDS = ("어디서", "어떻게", "방법", "절차")
LOOKUP_WORDS = ("알려", "보여", "얼마")
TRANSACTION_WORDS = ("거래내역", "내역", "입금", "출금")


def classify_intent(question: str) -> str:
    if any(word in question for word in PROCEDURE_WORDS) and not any(
        word in question for word in LOOKUP_WORDS
    ):
        return "general"
    if any(word in question for word in TRANSACTION_WORDS):
        return "transactions"
    return "balance"
