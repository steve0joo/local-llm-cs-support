import pytest

from app.agents.balance.intent import classify_intent
from app.agents.balance.mock_api import get_accounts
from app.agents.balance.resolve import find_clicked


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("잔액 알려줘", "balance"),
        ("최근 거래내역 보여줘", "transactions"),
        ("잔액 조회는 어디서 해요?", "general"),
        ("거래내역은 어디서 봐요?", "general"),
        ("잔액을 어떻게 보여줘?", "balance"),
        ("입금 내역 알려줘", "transactions"),
        ("출금 내역", "transactions"),
        ("입출금 계좌 잔액 알려줘", "balance"),
        ("입출금 ****6789", "balance"),
        ("입출금 내역 보여줘", "transactions"),
        ("출금 내역 보여줘", "transactions"),
        ("어제 출금된 거 뭐예요?", "transactions"),
    ],
)
def test_classify_intent(question: str, expected: str) -> None:
    assert classify_intent(question) == expected


def test_label_click_keeps_original_intent() -> None:
    history = [
        {"role": "user", "content": "최근 거래내역 보여줘"},
        {"role": "assistant", "content": "어느 계좌를 조회할까요?"},
    ]
    clicked = find_clicked("생활비 ****7890", history, get_accounts("C002"))
    assert classify_intent(clicked["question"]) == "transactions"
