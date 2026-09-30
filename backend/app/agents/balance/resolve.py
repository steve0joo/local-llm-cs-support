import re

ASK_TEXT = "어느 계좌를 조회할까요?"
NOT_OWN_ACCOUNT_TEXT = "입력하신 계좌번호로 조회되는 계좌가 없습니다. 어느 계좌를 조회할까요?"
NO_ACCOUNT_TEXT = "고객님 명의로 조회되는 계좌가 없습니다."

_ACCOUNT_TOKEN = re.compile(r"\[계좌번호_(\d+)\]")


def account_label(account: dict) -> str:
    return f"{account['alias']} ****{account['account_no'][-4:]}"


def find_clicked(masked_text: str, history: list[dict], accounts: list[dict]) -> dict | None:
    user_contents = [m["content"] for m in history if m["role"] == "user"]
    if not user_contents:
        return None
    for account in accounts:
        if masked_text == account_label(account):
            return {"question": user_contents[-1], "account": account}
    return None


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def _options(accounts: list[dict]) -> list[dict]:
    return [{"label": account_label(a), "choice": "balance"} for a in accounts]


def choose_account(accounts: list[dict], mask_map: dict[str, str], masked_text: str) -> dict:
    if not accounts:
        return {"text": NO_ACCOUNT_TEXT, "options": []}
    tokens = sorted(
        (int(m.group(1)), value)
        for key, value in mask_map.items()
        if (m := _ACCOUNT_TOKEN.fullmatch(key))
    )
    for _, value in tokens:
        for account in accounts:
            if _digits(value) == _digits(account["account_no"]):
                return {"account": account}
    if tokens:
        return {"text": NOT_OWN_ACCOUNT_TEXT, "options": _options(accounts)}
    typed = [a for a in accounts if a["alias"] in masked_text or a["account_no"][-4:] in masked_text]
    if len(typed) == 1:
        return {"account": typed[0]}
    if len(accounts) == 1:
        return {"account": accounts[0]}
    return {"text": ASK_TEXT, "options": _options(accounts)}
