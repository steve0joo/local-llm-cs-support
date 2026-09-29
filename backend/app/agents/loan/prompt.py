NO_LOAN_TEXT = "고객님 명의로 조회되는 대출이 없습니다."

SYSTEM_PROMPT = (
    "당신은 은행의 대출문의 상담 도우미입니다. 항상 정중한 존댓말로 답하세요.\n"
    "- 대출 만기, 연장 가능 여부, 대출 조회에 대한 질문에만 답하세요.\n"
    "- 남은 원금은 숫자를 쓰지 말고 {{principal_remaining}} 슬롯으로만 표현하고, "
    "대출 종류는 {{loan_label}} 슬롯으로 표현할 수 있습니다.\n"
    "- 연장 가능 여부는 '가능합니다'/'불가합니다'라고 직접 쓰지 말고 {{extendable_status}} 슬롯으로 표현하세요.\n"
    "- 금리, 연장에 필요한 서류나 조건, 연장이 안 되는 이유는 지어내지 마세요. "
    "제공된 정보로 알 수 없으면 상담원에게 확인해 달라고 안내하세요.\n"
    "- 제공된 대출 정보에 없는 숫자와 날짜는 말하지 마세요."
)


def build_messages(history: list[dict], masked_text: str, loan: dict) -> list[dict]:
    extendable = "예" if loan["extendable"] else "아니오(사유는 알 수 없음)"
    user_content = (
        f"{masked_text}\n"
        f"대출 정보: 종류={loan['product_type']}, 만기일={loan['maturity_date']}, 연장 가능={extendable}\n"
        "사용할 수 있는 슬롯: {{loan_label}}, {{principal_remaining}}, {{extendable_status}}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        *(dict(turn) for turn in history),
        {"role": "user", "content": user_content},
    ]


def build_slots(loan: dict) -> dict[str, str]:
    return {
        "loan_label": loan["product_type"],
        "principal_remaining": f"{loan['principal_remaining']:,}원",
        "extendable_status": (
            "연장 가능 대상으로 조회됩니다."
            if loan["extendable"]
            else "현재 연장 가능으로 조회되지 않습니다."
        ),
    }


def fallback_text(loan: dict) -> str:
    return (
        "{{loan_label}}의 만기일은 " + loan["maturity_date"] + "이고, "
        "남은 원금은 {{principal_remaining}}입니다."
        " {{extendable_status}}"
        " 연장 조건 등 자세한 사항은 상담원에게 확인해 주세요."
    )
