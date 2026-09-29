import copy

import pytest

from app.agents.balance import agent, mock_api, mock_router
from app.agents.balance.agent import BalanceAgent
from app.agents.balance.mock_api import get_accounts, get_transactions
from app.agents.balance.prompt import fallback_text
from app.agents.base import AgentReply, AgentRequest

A002, A003 = get_accounts("C002")
ALL_ACCOUNTS = [a for c in ("C001", "C002", "C003") for a in get_accounts(c)]

BALANCE_TEXT = "{{account_label}} 계좌 잔액은 {{balance}}입니다. 더 궁금하신 점이 있으시면 말씀해 주세요."
TRANSACTIONS_TEXT = "{{account_label}} 계좌의 최근 거래내역을 안내해 드립니다.\n{{recent_transactions}}"
GENERAL_TEXT = "잔액 조회는 모바일 앱이나 인터넷뱅킹에서 하실 수 있습니다."
LEAK_TEXT = "고객님 계좌 110-1234-5678의 잔액은 1,234,567원입니다."

C002_OPTIONS = [
    {"label": "입출금 ****6789", "choice": "balance"},
    {"label": "생활비 ****7890", "choice": "balance"},
]

# 거래내역 슬롯 기대값은 mock_data.json에서 옮겨 적은 리터럴이다(build_slots 결과를 기대값으로 쓰지 않는다).
A001_TRANSACTIONS = (
    "2026-09-28 · 이체입금 · +150,000원\n"
    "2026-09-20 · 편의점 · -8,000원\n"
    "2026-09-15 · 통신요금 · -65,000원\n"
    "2026-09-10 · 관리비 · -180,000원\n"
    "2026-09-05 · 카드대금 · -450,000원"
)
A003_TRANSACTIONS = (
    "2026-09-25 · 이체입금 · +120,000원\n"
    "2026-09-18 · 편의점 · -7,500원\n"
    "2026-09-13 · 통신요금 · -48,000원\n"
    "2026-09-09 · 관리비 · -145,000원\n"
    "2026-09-02 · 카드대금 · -380,000원"
)


def _money(value: int) -> list[str]:
    return [str(abs(value)), f"{abs(value):,}"]


def _raw_values() -> list[str]:
    """모델 입력에 있으면 안 되는 원본: 전체 계좌번호(하이픈 유무), 잔액·거래 금액."""
    values = []
    for a in ALL_ACCOUNTS:
        values += [a["account_no"], a["account_no"].replace("-", "")] + _money(a["balance"])
        for tx in get_transactions(a["account_id"], limit=100):
            values += _money(tx["amount"]) + _money(tx["balance_after"])
    return values


RAW_VALUES = _raw_values()


def _req(customer_id, masked_text, mask_map=None, history=None):
    return AgentRequest(
        session_id="s1", customer_id=customer_id, masked_text=masked_text,
        mask_map=mask_map or {}, history=history or [],
    )


def _fake_generate(monkeypatch, text):
    """가짜 generate. 호출마다 모델 입력에 원본이 없는지 확인하고 (model, messages)를 기록한다."""
    calls = []

    def fake(model, messages, **options):
        dumped = str(messages)
        leaked = [v for v in RAW_VALUES if v in dumped]
        assert not leaked, f"모델 입력에 원본이 있다: {leaked}"
        calls.append((model, copy.deepcopy(messages)))
        return text

    monkeypatch.setattr("app.llm.generate", fake)
    return calls


def _forbid_generate(monkeypatch):
    monkeypatch.setattr("app.llm.generate", lambda *a, **k: pytest.fail("모델을 부르면 안 된다"))


def test_package_exports_balance_agent_and_mock_router():
    assert mock_router is mock_api.mock_router
    assert mock_router.routes
    assert isinstance(agent, BalanceAgent)
    assert agent.name == "balance"


def test_balance_single_account(monkeypatch):
    calls = _fake_generate(monkeypatch, BALANCE_TEXT)

    reply = agent.handle(_req("C001", "잔액 알려줘"))

    assert reply == AgentReply(
        text=BALANCE_TEXT,
        slots={"account_label": "입출금 ****5678", "balance": "1,234,567원"},
        options=[],
    )
    assert [model for model, _ in calls] == ["cs-balance"]


def test_transactions_single_account(monkeypatch):
    calls = _fake_generate(monkeypatch, TRANSACTIONS_TEXT)

    reply = agent.handle(_req("C001", "최근 거래내역 보여줘"))

    assert reply == AgentReply(
        text=TRANSACTIONS_TEXT,
        slots={"account_label": "입출금 ****5678", "recent_transactions": A001_TRANSACTIONS},
        options=[],
    )
    assert [model for model, _ in calls] == ["cs-balance"]


def test_general_skips_account_choice_and_hides_accounts(monkeypatch):
    calls = _fake_generate(monkeypatch, GENERAL_TEXT)

    reply = agent.handle(_req("C002", "잔액 조회는 어디서 해요?"))

    assert reply == AgentReply(text=GENERAL_TEXT, slots={}, options=[])
    assert [model for model, _ in calls] == ["cs-balance"]
    dumped = str(calls[0][1])
    for a in (A002, A003):
        label = f"{a['alias']} ****{a['account_no'][-4:]}"
        for value in (a["alias"], label, a["account_no"][-4:]):
            assert value not in dumped


def test_account_number_in_mask_map_picks_account_without_asking(monkeypatch):
    calls = _fake_generate(monkeypatch, BALANCE_TEXT)

    reply = agent.handle(_req("C002", "[계좌번호_1] 잔액 알려줘", mask_map={"[계좌번호_1]": "110-3456-7890"}))

    assert reply == AgentReply(
        text=BALANCE_TEXT,
        slots={"account_label": "생활비 ****7890", "balance": "2,400,000원"},
        options=[],
    )
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("customer_id", "masked_text", "mask_map", "expected"),
    [
        ("C002", "잔액 알려줘", {}, AgentReply(text="어느 계좌를 조회할까요?", slots={}, options=C002_OPTIONS)),
        ("C999", "잔액 알려줘", {}, AgentReply(text="고객님 명의로 조회되는 계좌가 없습니다.", slots={}, options=[])),
        (
            "C001", "[계좌번호_1] 잔액 알려줘", {"[계좌번호_1]": "110-9999-0000"},
            AgentReply(
                text="입력하신 계좌번호로 조회되는 계좌가 없습니다. 어느 계좌를 조회할까요?",
                slots={},
                options=[{"label": "입출금 ****5678", "choice": "balance"}],
            ),
        ),
    ],
    ids=["ask-c002", "no-account", "not-own-account"],
)
def test_replies_without_model(monkeypatch, customer_id, masked_text, mask_map, expected):
    _forbid_generate(monkeypatch)

    assert agent.handle(_req(customer_id, masked_text, mask_map=mask_map)) == expected


@pytest.mark.parametrize(
    ("question", "label", "slots", "text"),
    [
        (
            "최근 거래내역 보여줘", "생활비 ****7890",
            {"account_label": "생활비 ****7890", "recent_transactions": A003_TRANSACTIONS}, TRANSACTIONS_TEXT,
        ),
        ("잔액 알려줘", "입출금 ****6789", {"account_label": "입출금 ****6789", "balance": "850,000원"}, BALANCE_TEXT),
    ],
    ids=["transactions", "balance"],
)
def test_label_click_answers_original_question(monkeypatch, question, label, slots, text):
    _forbid_generate(monkeypatch)
    first = agent.handle(_req("C002", question))
    assert first.options == C002_OPTIONS

    calls = _fake_generate(monkeypatch, text)
    history = [{"role": "user", "content": question}, {"role": "assistant", "content": first.text}]
    second = agent.handle(_req("C002", label, history=history))

    assert second == AgentReply(text=text, slots=slots, options=[])
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("question", "intent"),
    [("잔액 알려줘", "balance"), ("최근 거래내역 보여줘", "transactions"), ("잔액 조회는 어디서 해요?", "general")],
    ids=["balance", "transactions", "general"],
)
def test_leaking_model_output_is_replaced_with_fallback(monkeypatch, question, intent):
    _fake_generate(monkeypatch, LEAK_TEXT)

    reply = agent.handle(_req("C001", question))

    assert reply.text == fallback_text(intent)
