# 계약 2 (docs/ARCHITECTURE.md) — 주제 코드 ↔ 데이터셋 consulting_topic 원문. 원문은 띄어쓰기 없음(실제 데이터 기준).
# 학습 스크립트(training/router/prepare.py)가 라벨 → 코드 변환에 같은 표를 쓴다.
TOPIC_LABELS: dict[str, str] = {
    "balance": "거래내역/잔액조회",
    "loan": "대출문의(만기/연장/조회등)",
    "interest": "이자/연체금액",
    "auto_transfer": "자동이체조회",
    "transfer_error": "중계요청/착오송금",
    "deposit": "만기,연장/해지,수신",
    "limit": "금융거래한도/비대면한도계좌",
    "rate_discount": "부수거래금리감면",
    "fx": "환전문의",
}

# 에이전트가 있는 주제. 순서는 되묻기 선택지 순서다.
SUPPORTED: tuple[str, ...] = ("balance", "loan", "interest")

# 되묻기 선택지 라벨 (docs/PRD.md 핵심 기능 2의 표기)
DISPLAY_NAMES: dict[str, str] = {"balance": "잔액조회", "loan": "대출문의", "interest": "이자/연체"}

# RT-002 복합 문의 키워드. 2개 이상 걸리면 되묻는다. 단어는 실패 사례가 나올 때 테스트와 함께 추가한다.
KEYWORDS: dict[str, tuple[str, ...]] = {
    "balance": ("잔액", "잔고"),
    "loan": ("대출",),
    "interest": ("이자", "연체"),
}

# cs-router 시스템 프롬프트. 학습 데이터(training/router/prepare.py)와 추론이 같은 문구를 써야 한다.
SYSTEM_PROMPT = "고객 문의를 다음 코드 중 하나로 분류하고 코드만 출력하세요.\n" + "\n".join(
    f"{code}: {label}" for code, label in TOPIC_LABELS.items()
)
