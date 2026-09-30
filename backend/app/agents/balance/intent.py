PROCEDURE_WORDS = ("어디서", "어떻게", "방법", "절차")
LOOKUP_WORDS = ("알려", "보여", "얼마")
TRANSACTION_WORDS = ("거래내역", "내역", "입금", "출금")


def classify_intent(question: str) -> str:
    if any(word in question for word in PROCEDURE_WORDS) and not any(
        word in question for word in LOOKUP_WORDS
    ):
        return "general"
    # '입출금'은 계좌 별칭이라 '출금'으로 세지 않는다
    without_alias = question.replace("입출금", "")
    if any(word in without_alias for word in TRANSACTION_WORDS):
        return "transactions"
    return "balance"
