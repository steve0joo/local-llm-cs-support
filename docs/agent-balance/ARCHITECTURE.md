# 아키텍처: 잔액조회 에이전트

## 디렉토리 구조
```
backend/
├── app/agents/balance/
│   ├── __init__.py        # agent, mock_router export (계약 3)
│   ├── agent.py           # BalanceAgent.handle()
│   ├── prompt.py          # 시스템 프롬프트 + 메시지 구성
│   ├── mock_api.py        # mock_router + get_accounts(), get_transactions()
│   └── mock_data.json     # C001~C003 계좌·거래내역
├── tests/balance/
├── training/balance/      # prepare.py(추출·마스킹·정제), train.py(QLoRA), export.md(GGUF 변환 절차)
└── models/balance/Modelfile
```

## TDD 착수점
- 첫 테스트: `tests/balance/test_mock_api.py` — `get_accounts(customer_id)`가 아래 mock 데이터대로 고객별 계좌를 돌려주는지 확인한다.
- 이후 순서: `get_transactions` → `handle()`(계좌 결정 → 의도 판단 → 슬롯 → 출력 검증, 모델은 목). `agents/base.py` 스텁이 main에 오기 전이면 `handle()` 테스트는 import 실패 red로 시작한다.

## mock API
| 메서드 | 경로 | 응답 |
|--------|------|------|
| GET | `/mock/customers/{customer_id}/accounts` | `[{account_id, account_no, alias, balance}]` |
| GET | `/mock/accounts/{account_id}/transactions?limit=5` | `[{date, description, amount, balance_after}]` |
- 조회 함수: `get_accounts(customer_id: str) -> list[dict]`, `get_transactions(account_id: str, limit: int = 5) -> list[dict]`(날짜 내림차순). 공통 규칙은 `docs/ARCHITECTURE.md` "코드·테스트 규칙"을 따른다.
- 금액은 정수(원)로 저장한다. 표시용 포맷(`1,234,567원`)은 에이전트가 슬롯을 만들 때 한다.
- `date`는 `"YYYY-MM-DD"` 문자열, `amount`는 입금 +·출금 − 정수다.

### mock 데이터
| customer_id | account_id | account_no | alias | balance |
|-------------|-----------|------------|-------|---------|
| `C001` | `A001` | `110-1234-5678` | 입출금 | 1234567 |
| `C002` | `A002` | `110-2345-6789` | 입출금 | 850000 |
| `C002` | `A003` | `110-3456-7890` | 생활비 | 2400000 |
| `C003` | `A004` | `110-4567-8901` | 입출금 | 320000 |
- `alias`는 화면에 보이는 계좌 이름이다. `account_label` = `"{alias} ****{account_no 끝 4자리}"`(예: `입출금 ****5678`).
- 거래내역은 계좌마다 5건 이상을 담당자가 만든다.

## handle() 흐름
```
1. accounts = get_accounts(customer_id)
2. 대상 계좌 결정 (Python 코드)
   - mask_map에 [계좌번호_n]이 있으면 원본 번호로 매칭
   - 선택지 응답(masked_text가 account_label과 일치)이면 라벨로 매칭하고, 원래 질문은 history의 직전 user 메시지로 한다
   - 계좌가 1개면 그 계좌
   - 그 외 → AgentReply(text="어느 계좌의 잔액을 알려드릴까요?", options=[{label: account_label, choice: "balance"}...])
3. 의도 판단(원래 질문 기준): "거래내역·내역·입금·출금" 키워드가 있으면 거래내역, 없으면 잔액
   - 예: C002 "최근 거래내역 보여줘" → 계좌 선택 → 라벨 클릭 턴에서도 거래내역으로 답해야 한다(테스트로 고정)
4. slots 생성 (account_label, balance 또는 recent_transactions)
5. messages = 시스템 프롬프트 + history + masked_text + "사용할 수 있는 슬롯: {{account_label}}, {{balance}}"
   → llm.generate("cs-balance", messages)
6. 출력 검증: 필요한 슬롯(잔액: account_label·balance, 거래내역: account_label·recent_transactions)이 없거나 금액 형태의 숫자(예: 1,234원)가 있으면 기본 문장으로 대체
   기본 문장(잔액): "{{account_label}} 계좌의 현재 잔액은 {{balance}}입니다."
   기본 문장(거래내역): "{{account_label}} 계좌의 최근 거래내역입니다.\n{{recent_transactions}}"
7. AgentReply(text, slots, options=[])
```

## 학습 데이터
- 원천: `split.json`의 train 중 `consulting_topic == "거래내역/잔액조회"`인 라벨링 데이터 `qa_data[]` (필드명은 데이터 확인 전 가정 — 공통 ARCHITECTURE 학습 파이프라인)
- 한 항목 = 대화 1개: user(`input.question`) → assistant(`input.answer`) → user(`input.follow_up_question`) → **assistant 목표(`output`)**
- 전처리 순서: `masking.mask()`로 치환 → `output`에 `input`에 없는 수치·상품명이 있으면 제외 → 베이스 모델 채팅 템플릿 적용
- 검증: val 분할에서 샘플을 뽑아 사람이 읽어 확인한다. test 분할은 최종 점검에만 쓴다.
