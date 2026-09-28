"""cs-interest 모델의 입력 형식. 학습 데이터(training/interest)도 이 함수들로 같은 형식을 만든다."""

SYSTEM_PROMPT = (
    "당신은 은행의 대출 이자·연체 상담원입니다. 고객에게 존댓말로 정중하고 간결하게 답합니다.\n"
    "- 금액은 숫자로 쓰지 말고 '사용할 수 있는 슬롯'에 있는 {{슬롯}}만 그대로 씁니다.\n"
    "- '이자 정보'에 있는 사실만 말합니다. 없는 내용은 지어내지 않습니다.\n"
    "- 금리·연체 이율 같은 퍼센트 수치, 실제 상품명, 은행명, 필요 서류는 말하지 않고 상담원 확인을 안내합니다.\n"
    "- 모르는 내용은 상담원에게 확인해 달라고 안내합니다."
)


def format_won(amount: int) -> str:
    return f"{amount:,}원"


def _is_overdue(item: dict) -> bool:
    return item["overdue_days"] > 0


def build_slots(item: dict) -> dict[str, str]:
    slots = {
        "loan_label": item["product_type"],
        "interest_due": format_won(item["interest_due"]),
    }
    if _is_overdue(item):
        slots["overdue_amount"] = format_won(item["overdue_amount"])
    return slots


def info_line(item: dict) -> str:
    """금액이 아닌 조회 정보만 담는다. 금액은 슬롯으로만 전달한다. 금리는 수치 없이 방식(고정·변동)만."""
    parts = [
        f"종류={item['product_type']}",
        f"상환 방식={item['repayment_method']}",
        f"금리 방식={item['interest_type']}",
        f"납부 방법={item['payment_method']}",
        f"다음 납부일={item['next_due_date']}",
    ]
    if _is_overdue(item):
        parts += ["연체 여부=연체 중", f"연체 일수={item['overdue_days']}"]
    else:
        parts.append("연체 여부=연체 없음")
    return "이자 정보: " + ", ".join(parts)


def slot_line(slot_names) -> str:
    return "사용할 수 있는 슬롯: " + ", ".join(f"{{{{{name}}}}}" for name in slot_names)


def build_messages(masked_text: str, history: list[dict], item: dict) -> list[dict]:
    user = "\n".join([masked_text, info_line(item), slot_line(build_slots(item))])
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": user},
    ]


def fallback_text(item: dict) -> str:
    text = (
        f"{{{{loan_label}}}}의 다음 납부일은 {item['next_due_date']}이고, "
        "납부 예정 이자는 {{interest_due}}입니다."
    )
    if _is_overdue(item):
        text += f" 현재 {item['overdue_days']}일 연체 중이며 연체 금액은 {{{{overdue_amount}}}}입니다."
    return text + " 자세한 사항은 상담원에게 확인해 주세요."
