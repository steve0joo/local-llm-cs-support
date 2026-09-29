"""cs-interest 합성 학습 샘플 (docs/agent-interest/TRAINING_DATA_PLAN.md 3·4절).

외부 사실(실제 금리·규정·상품명)은 넣지 않는다. 조회값(슬롯·다음 납부일·연체 일수)과 안내 문구만 쓴다.
템플릿은 사람이 검수한다. 검수한 템플릿 ID를 REVIEWED에 넣으면 그 템플릿의 레코드가 reviewed=true가 된다.
팀 합의 전에는 prepare.py가 --with-synth 없이 합성 샘플을 학습에 넣지 않는다.

답변 자리표시: {due} = 다음 납부일, {days} = 연체 일수, {repay} = 상환 방식, {rate_type} = 금리 방식,
{pay} = 납부 방법. {{슬롯}}은 그대로 남는다.

자동이체 조회값에는 서비스(balance_source.enrich)처럼 계좌 잔액 비교 결과(debit_status)와 잔액 슬롯(debit_balance)이 붙는다.
debit_split 템플릿은 답을 "{scenario}_short"(잔액이 적음)·"{scenario}_enough"(잔액이 이상)로 나눈다.
"""

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.agents.interest.balance_source import debit_check
from app.agents.interest.prompt import build_messages

# TRAINING_DATA_PLAN.md 3절 목표 비중(%)
CATEGORY_WEIGHTS = {
    "interest_amount": 15,
    "due_date": 8,
    "overdue_status": 15,
    "overdue_action": 8,
    "reason": 8,
    "term": 6,
    "rate": 12,
    "calculation": 6,
    "false_premise": 6,
    "guarantee": 6,
    "missing_info": 5,
    "staff": 5,
    "loan_terms": 8,
    "followup": 4,
}

PRODUCT_TYPES = ["신용대출", "주택담보대출", "전세자금대출"]  # 일반 명칭만(계약 6)
REPAYMENT_METHODS = ["원리금균등", "원금균등", "만기일시"]
INTEREST_TYPES = ["고정", "변동"]  # 금리는 수치 없이 방식만(INT-002)
PAYMENT_METHODS = ["자동이체", "가상계좌 입금"]
BOTH = ("normal", "overdue")

# 사람이 검수를 마친 템플릿 ID (2026-09-28 팀원B 검수: 18개 전체 확인)
REVIEWED: set[str] = {
    "tpl-interest_amount-01",
    "tpl-due_date-01",
    "tpl-overdue_status-01",
    "tpl-overdue_action-01",
    "tpl-reason-01",
    "tpl-term-overdue_interest",
    "tpl-term-fixed_variable",
    "tpl-rate-01",
    "tpl-calculation-01",
    "tpl-false_premise-normal",
    "tpl-false_premise-overdue",
    "tpl-guarantee-01",
    "tpl-missing_info-01",
    "tpl-staff-01",
    "tpl-loan_terms-repayment",
    "tpl-loan_terms-interest_type",
    "tpl-loan_terms-payment",
    "tpl-followup-01",
}


@dataclass(frozen=True)
class Template:
    id: str
    category: str
    questions: tuple[str, ...]
    answers: dict[str, tuple[str, ...]]  # scenario → 답변 후보
    scenarios: tuple[str, ...] = BOTH
    history: tuple[tuple[str, dict[str, str]], ...] = field(default=())  # (이전 질문, scenario → 이전 답변)
    payment: str | None = None  # 납부 방법 고정(자동이체 전용 질문)
    debit_split: bool = False  # 자동이체 계좌 잔액이 적은지에 따라 답을 나눈다


PAY_SOON = "가능한 빨리 납부해 주시기 바랍니다."
ASK_STAFF = "자세한 사항은 상담원에게 확인해 주세요."
NO_ASSERT = "약정과 기준에 따라 달라 제가 단정해 드리기 어렵습니다."

TEMPLATES: tuple[Template, ...] = (
    Template(
        "tpl-interest_amount-01",
        "interest_amount",
        ("이번 달 이자 얼마예요?", "이자 얼마 나가요?", "이번에 내야 하는 이자 알려 주세요", "대출 이자 금액 확인하고 싶어요", "이자 얼마야"),
        {
            "normal": (
                "{{loan_label}}의 다음 납부일은 {due}이고, 납부하실 이자는 {{interest_due}}입니다.",
                "다음 납부일({due})에 납부하실 {{loan_label}} 이자는 {{interest_due}}입니다. 납부일에 맞춰 {pay} 방식으로 납부해 주세요.",
                "조회 결과 {{loan_label}}의 납부 예정 이자는 {{interest_due}}이며, 납부일은 {due}입니다.",
            ),
            "overdue": (
                "{{loan_label}}의 다음 납부일({due})에 납부하실 이자는 {{interest_due}}입니다. 현재 {days}일 연체된 금액 {{overdue_amount}}도 함께 확인해 주세요.",
                "납부 예정 이자는 {{interest_due}}이고 다음 납부일은 {due}입니다. 이와 별도로 {days}일째 연체된 금액 {{overdue_amount}}이 있어 " + PAY_SOON,
            ),
        },
    ),
    Template(
        "tpl-due_date-01",
        "due_date",
        ("이자 언제 빠져나가요?", "다음 납부일이 언제예요?", "이자 내는 날 알려 주세요", "이번 달 이자 며칠에 나가요?"),
        {
            "normal": (
                "{{loan_label}}의 다음 이자 납부일은 {due}입니다.",
                "다음 납부일은 {due}이며, 이날 납부하실 이자는 {{interest_due}}입니다.",
            ),
            "overdue": (
                "다음 납부일은 {due}입니다. 다만 현재 {days}일 연체된 금액 {{overdue_amount}}이 있어 납부일 전이라도 먼저 납부해 주시기 바랍니다.",
                "{{loan_label}}의 다음 납부일은 {due}이고, 납부하실 이자는 {{interest_due}}입니다. 현재 {days}일 연체 중이니 연체 금액 {{overdue_amount}}도 확인해 주세요.",
            ),
        },
    ),
    Template(
        "tpl-overdue_status-01",
        "overdue_status",
        ("연체된 거 있어요?", "밀린 거 있나요?", "제 대출 연체됐어요?", "연체 금액 얼마예요?", "미납된 이자 있는지 봐 주세요"),
        {
            "normal": (
                "현재 {{loan_label}}은 연체 없이 정상적으로 납부되고 있습니다. 다음 납부일은 {due}입니다.",
                "조회 결과 연체된 금액은 없습니다. 다음 납부일 {due}에 납부하실 이자는 {{interest_due}}입니다.",
            ),
            "overdue": (
                "네, 현재 {{loan_label}}이 {days}일 연체되어 있으며 연체 금액은 {{overdue_amount}}입니다. " + PAY_SOON,
                "조회 결과 {days}일째 연체 중이고, 연체된 금액은 {{overdue_amount}}입니다. 고객님 대출의 납부 방법은 {pay}이니 " + PAY_SOON,
            ),
        },
    ),
    Template(
        "tpl-overdue_action-01",
        "overdue_action",
        ("연체되면 어떻게 돼요?", "연체된 거 빨리 해결하려면 어떻게 해야 돼요?", "연체 계속되면 불이익 있어요?", "밀린 거 어떻게 갚아요?"),
        {
            "normal": (
                "현재 {{loan_label}}은 연체 없이 정상 상태입니다. 연체가 생기면 연체 이자가 붙을 수 있으니 다음 납부일 {due}에 맞춰 납부해 주세요. " + ASK_STAFF,
            ),
            "overdue": (
                "현재 {days}일 연체된 금액 {{overdue_amount}}이 있습니다. 연체가 길어지면 불이익이 커질 수 있으니 " + PAY_SOON + " 적용 기준은 상담원에게 확인해 주세요.",
                "{{loan_label}}이 {days}일 연체되어 연체 금액 {{overdue_amount}}이 남아 있습니다. 고객님 대출의 납부 방법은 {pay}이며, 연체 금액부터 먼저 납부하시는 것이 좋습니다.",
                "현재 {days}일 연체된 금액 {{overdue_amount}}이 있습니다. 고객님 대출은 {pay} 방식으로 납부하고 계시며, 지금 바로 납부하는 절차는 상담원에게 확인해 주세요.",
            ),
        },
    ),
    Template(
        "tpl-overdue_action-rule",
        "overdue_action",
        ("연체하면 신용점수 떨어져요?", "연체되면 금리도 올라가요?", "며칠 연체되면 기록이 남아요?", "연체 중이어도 대출 연장 되나요?"),
        {
            "normal": (
                "연체가 신용이나 대출 조건에 어떤 영향을 주는지는 " + NO_ASSERT + " 현재 {{loan_label}}은 연체 없이 정상 상태이며, 적용 기준은 상담원에게 확인해 주세요.",
            ),
            "overdue": (
                "연체가 신용이나 대출 조건에 어떤 영향을 주는지는 " + NO_ASSERT + " 현재 {days}일 연체된 금액 {{overdue_amount}}이 있으니 " + PAY_SOON + " 적용 기준은 상담원에게 확인해 주세요.",
            ),
        },
    ),
    Template(
        "tpl-reason-01",
        "reason",
        ("이자가 왜 이렇게 많이 나왔어요?", "이번 달 이자가 평소보다 많은 것 같아요", "이자가 늘어난 이유가 뭐예요?"),
        {
            "normal": (
                "이번 납부 예정 이자는 {{interest_due}}이며, 현재 연체는 없습니다. 이자가 달라진 구체적인 이유는 금리와 약정 조건에 따라 다를 수 있어 상담원에게 확인해 주세요.",
                "현재 연체는 없고, {{loan_label}}은 {rate_type}금리 방식입니다. 이번 납부 예정 이자는 {{interest_due}}이며, 이자가 달라진 구체적인 이유는 상담원에게 확인해 주세요.",
            ),
            "overdue": (
                "현재 {{loan_label}}이 {days}일 연체되어 연체 금액 {{overdue_amount}}이 남아 있습니다. 연체가 있으면 납부할 금액이 늘어날 수 있습니다. 정확한 계산 내역은 상담원에게 확인해 주세요.",
            ),
        },
    ),
    Template(
        "tpl-reason-autodebit",
        "reason",
        ("자동이체 해 뒀는데 왜 연체예요?", "자동이체인데 연체된 이유가 뭐예요?", "통장에서 이자가 왜 안 빠져나갔어요?"),
        {
            "overdue_short": (
                "현재 {{loan_label}}은 {days}일 연체 중이며, 자동이체 계좌 잔액 {{debit_balance}}이 연체 금액 {{overdue_amount}}보다 적은 상태입니다. 출금이 되지 않은 정확한 이유는 상담원에게 확인해 주세요.",
            ),
            "overdue_enough": (
                "현재 {{loan_label}}은 {days}일 연체 중이며 연체 금액은 {{overdue_amount}}입니다. 자동이체 계좌 잔액은 연체 금액 이상으로 조회되며, 출금이 되지 않은 이유는 상담원에게 확인해 주세요.",
            ),
            "normal_short": (
                "조회 결과 현재 {{loan_label}}에는 연체된 금액이 없습니다. 다만 자동이체 계좌 잔액 {{debit_balance}}이 납부 예정 이자 {{interest_due}}보다 적은 상태이니 다음 납부일 {due} 전에 확인해 주세요.",
            ),
            "normal_enough": (
                "조회 결과 현재 {{loan_label}}에는 연체된 금액이 없고, 자동이체 계좌 잔액도 납부 예정 이자 이상입니다. 다음 납부일은 {due}이며, 출금 내역은 상담원에게 확인해 주세요.",
            ),
        },
        payment="자동이체",
        debit_split=True,
    ),
    Template(
        "tpl-term-overdue_interest",
        "term",
        ("연체이자가 뭐예요?", "연체 이자는 무슨 뜻이에요?", "연체이자라는 게 정확히 뭔가요?"),
        {
            "normal": ("연체이자는 약정한 납부일까지 내지 않은 금액에 붙는 이자입니다. 적용 기준은 상품 약정에 따라 다르니 상담원에게 확인해 주세요.",),
            "overdue": (
                "연체이자는 약정한 납부일까지 내지 않은 금액에 붙는 이자입니다. 현재 고객님은 {days}일 연체 중이며, 적용 기준은 상담원에게 확인해 주세요.",
            ),
        },
    ),
    Template(
        "tpl-term-fixed_variable",
        "term",
        ("고정금리랑 변동금리 차이가 뭐예요?", "변동금리가 뭐예요?", "고정금리는 어떤 거예요?"),
        {
            s: (
                "고정금리는 약정 기간 동안 금리가 바뀌지 않고, 변동금리는 기준이 되는 금리에 따라 금리가 바뀌는 방식입니다. 고객님의 {{loan_label}}은 {rate_type}금리 방식이며, 적용 금리 수치는 상담원에게 확인해 주세요.",
            )
            for s in BOTH
        },
    ),
    Template(
        "tpl-rate-01",
        "rate",
        ("대출 금리가 몇 %예요?", "제 대출 이자율 알려 주세요", "연체 가산금리는 얼마예요?", "요즘 금리 올랐어요?", "금리 몇 프로 적용돼요?"),
        {
            s: (
                "적용 금리 수치는 상담원을 통해 정확히 확인하실 수 있습니다. 조회되는 정보로는 {{loan_label}}이 {rate_type}금리 방식이며, 납부 예정 이자는 {{interest_due}}입니다.",
                "금리와 연체 가산 이율은 약정과 시점에 따라 달라 이 상담에서는 안내해 드리기 어렵습니다. 상담원에게 확인해 주세요.",
            )
            for s in BOTH
        },
    ),
    Template(
        "tpl-calculation-01",
        "calculation",
        ("하루 연체하면 이자 얼마 붙어요?", "이자 계산 어떻게 한 거예요?", "다음 달 이자 미리 계산해 줄 수 있어요?", "[금액_1] 빌렸으면 이자 얼마예요?"),
        {
            "normal": (
                "이자 계산은 금리와 약정 조건에 따라 달라 제가 직접 계산해 드리기 어렵습니다. 현재 조회되는 납부 예정 이자는 {{interest_due}}이고, 계산 기준은 상담원에게 확인해 주세요.",
            ),
            "overdue": (
                "이자 계산은 금리와 약정 조건에 따라 달라 제가 직접 계산해 드리기 어렵습니다. 현재 납부 예정 이자는 {{interest_due}}, 연체 금액은 {{overdue_amount}}이며, 계산 기준은 상담원에게 확인해 주세요.",
            ),
        },
    ),
    Template(
        "tpl-false_premise-normal",
        "false_premise",
        ("연체 이자가 왜 붙었어요?", "저 연체됐다고 문자 받았는데요", "이자 두 번 빠져나간 것 같아요"),
        {
            "normal": (
                "조회 결과 현재 {{loan_label}}에는 연체된 금액이 없습니다. 다음 납부일은 {due}이며 납부 예정 이자는 {{interest_due}}입니다. 출금 내역이나 받으신 안내는 상담원에게 확인해 주세요.",
            ),
        },
        scenarios=("normal",),
    ),
    Template(
        "tpl-false_premise-overdue",
        "false_premise",
        ("저 연체 없죠?", "이번 달은 다 냈으니까 문제없죠?", "연체 하루밖에 안 됐죠?"),
        {
            "overdue": (
                "확인해 보니 현재 {{loan_label}}이 {days}일 연체되어 있고, 연체 금액은 {{overdue_amount}}입니다. " + PAY_SOON,
            ),
        },
        scenarios=("overdue",),
    ),
    Template(
        "tpl-guarantee-01",
        "guarantee",
        ("연체 기록 지워 주세요", "이자 좀 깎아 줄 수 있죠?", "이번만 연체 이자 면제해 주세요", "금리 낮춰 주실 수 있죠?"),
        {
            "normal": ("연체 기록 정정이나 이자 감면, 금리 조정은 제가 처리하거나 약속드릴 수 없습니다. 가능 여부는 상담원에게 확인해 주세요.",),
            "overdue": (
                "연체 기록 정정이나 이자 감면은 제가 처리하거나 약속드릴 수 없습니다. 현재 {days}일 연체된 금액 {{overdue_amount}}은 먼저 납부해 주시고, 가능 여부는 상담원에게 확인해 주세요.",
            ),
        },
    ),
    Template(
        "tpl-missing_info-01",
        "missing_info",
        ("다른 대출 이자도 알려 주세요", "카드값 연체된 것도 봐 주세요", "가족 명의 대출 이자도 확인돼요?", "마이너스통장 이자는요?"),
        {
            "normal": (
                "현재 조회되는 대출은 {{loan_label}} 한 건이며, 납부 예정 이자는 {{interest_due}}입니다. 다른 상품이나 다른 분 명의의 내역은 여기서 확인해 드리기 어려우니 상담원에게 문의해 주세요.",
            ),
            "overdue": (
                "현재 조회되는 대출은 {{loan_label}} 한 건이며, {days}일 연체된 금액 {{overdue_amount}}이 있습니다. 다른 상품이나 다른 분 명의의 내역은 여기서 확인해 드리기 어려우니 상담원에게 문의해 주세요.",
            ),
        },
    ),
    Template(
        "tpl-staff-01",
        "staff",
        ("납부일 바꿔 주세요", "자동이체 계좌 변경하고 싶어요", "대출 연장하려면 뭐 준비해야 돼요?", "상환 방식 바꿀 수 있어요?"),
        {
            s: (
                "요청하신 변경이나 준비 사항 안내는 제가 처리해 드릴 수 없습니다. 상담원에게 확인해 주시면 자세히 안내받으실 수 있습니다.",
                "해당 내용은 상담원 확인이 필요합니다. 제가 안내해 드릴 수 있는 것은 {{loan_label}}의 다음 납부일({due})과 납부 예정 이자 {{interest_due}}입니다.",
            )
            for s in BOTH
        },
    ),
    Template(
        "tpl-loan_terms-repayment",
        "loan_terms",
        ("제 대출 상환 방식이 어떻게 돼요?", "원금도 매달 같이 나가요?", "상환은 어떤 방식이에요?"),
        {
            s: ("{{loan_label}}은 {repay} 방식으로 상환하고 계십니다. 상환 방식 변경 가능 여부는 상담원에게 확인해 주세요.",)
            for s in BOTH
        },
    ),
    Template(
        "tpl-loan_terms-interest_type",
        "loan_terms",
        ("제 대출 금리가 고정이에요 변동이에요?", "제 금리는 바뀌는 거예요?", "금리 방식이 뭐로 돼 있어요?"),
        {
            s: ("{{loan_label}}은 {rate_type}금리 방식입니다. 적용 금리 수치는 상담원에게 확인해 주세요.",)
            for s in BOTH
        },
    ),
    Template(
        "tpl-loan_terms-payment",
        "loan_terms",
        ("이자는 어떻게 내는 거예요?", "납부는 어떤 방법으로 해요?", "이자 자동으로 빠져나가요?"),
        {
            "normal": ("{{loan_label}} 이자는 {pay} 방식으로 납부하고 계십니다. 다음 납부일은 {due}입니다.",),
            "overdue": (
                "{{loan_label}} 이자는 {pay} 방식으로 납부하고 계십니다. 현재 {days}일 연체된 금액 {{overdue_amount}}이 있으니 " + PAY_SOON,
            ),
        },
    ),
    Template(
        "tpl-loan_terms-debit_balance",
        "loan_terms",
        ("자동이체 통장 잔액으로 충분해요?", "이번 이자 빠져나갈 돈 통장에 있어요?", "자동이체 계좌에 돈 얼마 있어요?"),
        {
            "normal_short": (
                "자동이체 계좌 잔액은 {{debit_balance}}으로, 납부 예정 이자 {{interest_due}}보다 적은 상태입니다. 다음 납부일 {due} 전에 잔액을 확인해 주세요.",
            ),
            "normal_enough": (
                "자동이체 계좌 잔액은 {{debit_balance}}으로, 납부 예정 이자 {{interest_due}} 이상입니다. 다음 납부일은 {due}입니다.",
            ),
            "overdue_short": (
                "자동이체 계좌 잔액은 {{debit_balance}}으로, 현재 {days}일 연체된 금액 {{overdue_amount}}보다 적은 상태입니다. " + PAY_SOON,
            ),
            "overdue_enough": (
                "자동이체 계좌 잔액은 {{debit_balance}}으로, {days}일 연체된 금액 {{overdue_amount}} 이상입니다. 연체 금액이 언제 출금되는지는 상담원에게 확인해 주세요.",
            ),
        },
        payment="자동이체",
        debit_split=True,
    ),
    Template(
        "tpl-followup-01",
        "followup",
        ("그럼 연체된 건요?", "연체 금액은요?", "그건 언제까지 내야 돼요?"),
        {
            "normal": ("이자는 다음 납부일인 {due}까지 납부해 주시면 되며, 현재 연체된 금액은 없습니다.",),
            "overdue": (
                "현재 {days}일 연체된 금액 {{overdue_amount}}이 있어 가능한 빨리 납부해 주셔야 하며, 이자는 다음 납부일인 {due}까지 납부해 주시면 됩니다.",
            ),
        },
        history=(
            (
                "이번 달 이자 얼마예요?",
                {
                    "normal": "{{loan_label}}의 다음 납부일은 {due}이고, 납부하실 이자는 {{interest_due}}입니다.",
                    "overdue": "{{loan_label}}의 다음 납부일은 {due}이고, 납부하실 이자는 {{interest_due}}입니다.",
                },
            ),
        ),
    ),
)


def make_item(rng: random.Random, scenario: str, payment: str | None = None) -> dict:
    """가상 조회 결과. 금액은 슬롯으로만 쓰여 모델 입력에 나타나지 않는다."""
    overdue = scenario == "overdue"
    item = {
        "loan_id": "L000",
        "product_type": rng.choice(PRODUCT_TYPES),
        "repayment_method": rng.choice(REPAYMENT_METHODS),
        "interest_type": rng.choice(INTEREST_TYPES),
        "payment_method": payment or rng.choice(PAYMENT_METHODS),
        "debit_account_id": "",
        "next_due_date": (date(2026, 10, 1) + timedelta(days=rng.randint(0, 90))).isoformat(),
        "interest_due": rng.randrange(10_000, 1_000_000, 10),
        "overdue_amount": rng.randrange(10_000, 3_000_000, 10) if overdue else 0,
        "overdue_days": rng.randint(2, 90) if overdue else 0,  # 2 이상: "하루밖에 안 됐죠?" 전제를 바로잡는 답과 맞춘다
    }
    if item["payment_method"] == "자동이체":  # 서비스의 balance_source.enrich와 같은 필드
        target = item["overdue_amount"] if overdue else item["interest_due"]
        balance = rng.randrange(0, target, 10) if rng.random() < 0.5 else rng.randrange(target, target * 3, 10)
        item |= {"debit_account_id": "A000", "debit_status": debit_check(item, balance), "debit_balance": balance}
    return item


def _answer_key(t: Template, scenario: str, item: dict) -> str:
    if not t.debit_split:
        return scenario
    return f"{scenario}_{'short' if item['debit_status'].endswith('적음') else 'enough'}"


def _fill(text: str, item: dict) -> str:
    for key, value in {
        "{due}": item["next_due_date"],
        "{days}": str(item["overdue_days"]),
        "{repay}": item["repayment_method"],
        "{rate_type}": item["interest_type"],
        "{pay}": item["payment_method"],
    }.items():
        text = text.replace(key, value)
    return text


def _counts(total: int) -> dict[str, int]:
    """비중대로 나누고, 반올림 오차는 비중이 큰 유형부터 채운다."""
    w_sum = sum(CATEGORY_WEIGHTS.values())
    exact = {c: total * w / w_sum for c, w in CATEGORY_WEIGHTS.items()}
    counts = {c: int(v) for c, v in exact.items()}
    for c in sorted(exact, key=lambda c: exact[c] - counts[c], reverse=True)[: total - sum(counts.values())]:
        counts[c] += 1
    return counts


def generate(total: int = 400, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    records = []
    for category, n in _counts(total).items():
        templates = [t for t in TEMPLATES if t.category == category]
        for i in range(n):
            t = templates[i % len(templates)]
            scenario = t.scenarios[(i // len(templates)) % len(t.scenarios)]
            item = make_item(rng, scenario, t.payment)
            question = t.questions[(i // len(templates)) % len(t.questions)]
            history = []
            for prev_q, prev_a in t.history:
                history += [{"role": "user", "content": prev_q}, {"role": "assistant", "content": _fill(prev_a[scenario], item)}]
            messages = build_messages(question, history, item)
            messages.append({"role": "assistant", "content": _fill(rng.choice(t.answers[_answer_key(t, scenario, item)]), item)})
            records.append(
                {
                    "id": f"synth-{t.id}-{i:03d}",
                    "origin": "synth",
                    "source_id": t.id,
                    "group_id": t.id,
                    "category": category,
                    "scenario": scenario,
                    "reviewed": t.id in REVIEWED,
                    "review_note": "",
                    "item": item,
                    "messages": messages,
                }
            )
    return records
