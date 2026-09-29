# 아키텍처: 잔액조회 에이전트

## 디렉토리 구조
```
backend/
├── app/agents/balance/
│   ├── __init__.py        # agent, mock_router export (계약 3)
│   ├── agent.py           # BalanceAgent.handle() — cherry-pick 발판 위 (BAL-005)
│   ├── resolve.py         # 라벨 클릭 확인 + 대상 계좌 결정 (plain dict 반환)
│   ├── intent.py          # 의도 판단 3분기 (balance / transactions / general)
│   ├── prompt.py          # 시스템 프롬프트 + 메시지·슬롯·기본 문장
│   ├── validate.py        # 출력 검증
│   ├── mock_api.py        # mock_router + get_accounts(), get_transactions()
│   └── mock_data.json     # C001~C003 계좌·거래내역
├── tests/balance/         # test_<모듈>.py
├── training/balance/      # prepare.py(추출·마스킹·정제), train.py(QLoRA), export.md(GGUF 변환 절차)
└── models/balance/Modelfile
```

## TDD 착수점
- 첫 테스트: `tests/balance/test_mock_api.py` — `get_accounts(customer_id)`가 아래 mock 데이터대로 고객별 계좌를 돌려주는지 확인한다.
- 이후 순서: `get_transactions` → `resolve` → `intent` → `prompt` → `validate`(1차 구현, 모델 없이 도는 순수 함수) → `handle()`(`tests/balance/test_agent.py`, 모델은 목). `handle()`은 팀원C 커밋을 cherry-pick한 발판(`agents/base.py`·`llm`·스캐폴드) 위에서 만든다(BAL-005, 2026-09-29 변경).
- 테스트 명령: `cd backend && .venv/bin/python -m pytest` — backend 전체(발판의 `tests/router`·`tests/llm` 포함). importlib 모드 등은 `pyproject.toml`이 정한다.

## mock API
| 메서드 | 경로 | 응답 |
|--------|------|------|
| GET | `/mock/customers/{customer_id}/accounts` | `[{account_id, account_no, alias, balance}]` |
| GET | `/mock/accounts/{account_id}/transactions?limit=5` | `[{date, description, amount, balance_after}]` |
- 조회 함수: `get_accounts(customer_id: str) -> list[dict]`, `get_transactions(account_id: str, limit: int = 5) -> list[dict]`(날짜 내림차순, 앞에서 최대 `limit`건). 공통 규칙은 `docs/ARCHITECTURE.md` "코드·테스트 규칙"을 따른다.
- 금액은 정수(원)로 저장한다. 표시용 포맷(`1,234,567원`)은 에이전트가 슬롯을 만들 때 한다.
- `date`는 `"YYYY-MM-DD"` 문자열, `amount`는 입금 +·출금 − 정수(0 아님)다.
- `mock_data.json` 형식: `{"accounts": {customer_id: [계좌...]}, "transactions": {account_id: [거래...]}}`. 거래는 최신순으로 저장하고, 같은 날짜 거래도 나중 거래를 앞에 둔다.

### mock 데이터
| customer_id | account_id | account_no | alias | balance |
|-------------|-----------|------------|-------|---------|
| `C001` | `A001` | `110-1234-5678` | 입출금 | 1234567 |
| `C002` | `A002` | `110-2345-6789` | 입출금 | 850000 |
| `C002` | `A003` | `110-3456-7890` | 생활비 | 2400000 |
| `C003` | `A004` | `110-4567-8901` | 입출금 | 320000 |
- `alias`는 화면에 보이는 계좌 이름이다. `account_label` = `"{alias} ****{account_no 끝 4자리}"`(예: `입출금 ****5678`).
- 거래내역은 계좌마다 6건을 담당자가 만든다(5건 이상, `limit=5`로 잘리는지 확인할 수 있게). 적요(`description`)는 "급여"·"관리비"처럼 일반 명칭만 쓰고 숫자·실제 상호·상품명은 넣지 않는다.
- 잔액 사슬: `get_transactions`가 돌려준 최신순 목록 `arr`에서 `arr[0].balance_after == 계좌 balance`이고, 모든 `i`에 대해 `arr[i].balance_after == arr[i+1].balance_after + arr[i].amount`다.

## handle() 흐름
```
1. accounts = get_accounts(customer_id)
2. 라벨 클릭 확인 — resolve.find_clicked(masked_text, history, accounts)
   - history에 user 메시지가 있고 masked_text가 accounts 중 한 계좌의 account_label과 정확히 같으면 라벨 클릭 턴이다
     → 원래 질문 = history의 마지막 user 메시지 content, 대상 계좌 = 그 라벨의 계좌
   - 아니면 원래 질문 = masked_text. history가 빈 첫 턴은 라벨과 같아도 라벨 클릭으로 보지 않는다
3. 의도 판단(원래 질문 기준) — intent.classify_intent(원래 질문) → "balance" | "transactions" | "general"
4. general이면 계좌 결정·되묻기·슬롯을 건너뛰고 7로 간다. get_accounts는 2의 라벨 확인에 이미 썼고, 모델 입력에는 계좌 정보를 넣지 않는다
5. 대상 계좌 결정 — 라벨 클릭 턴이면 2의 계좌. 아니면 resolve.choose_account(accounts, mask_map)
   - 결과에 "text"가 있으면 모델을 부르지 않고 AgentReply(text, slots={}, options)로 바로 답한다 (아래 "대상 계좌 결정")
6. slots = prompt.build_slots(intent, account, transactions)
   - transactions면 get_transactions(account_id)를 조회해 넘긴다
7. messages = prompt.build_messages(history, masked_text, intent) → llm.generate("cs-balance", messages)
8. 출력 검증 — validate.validate_output(text, intent): 규칙에 걸리면 그 의도의 기본 문장으로 대체
9. AgentReply(text, slots, options=[])
```
- 예: C002 "최근 거래내역 보여줘" → 되묻기 → 라벨 클릭 턴("생활비 ****7890")에서도 원래 질문으로 판단해 거래내역으로 답한다(테스트로 고정).

## 대상 계좌 결정 (`resolve.py`)
계약 3 타입(`AgentReply`)을 쓰지 않고 plain dict를 돌려준다. `AgentReply` 포장은 `handle()` 안에서만 한다(BAL-005).
- `account_label(account) -> str` — `"{alias} ****{account_no 끝 4자리}"`
- `find_clicked(masked_text, history, accounts) -> dict | None` — 라벨 클릭 턴이면 `{"question": 원래 질문, "account": 계좌}`, 아니면 `None`
- `choose_account(accounts, mask_map) -> dict` — 계좌를 정하면 `{"account": 계좌}`, 모델 없이 바로 답해야 하면 `{"text": 문구, "options": 선택지}`. 아래 순서로 첫 번째로 맞는 것:
  1. 계좌가 0개 → `{"text": "고객님 명의로 조회되는 계좌가 없습니다.", "options": []}`
  2. `mask_map`의 `[계좌번호_n]` 원본 중 숫자만 비교해(하이픈 무시) 본인 계좌 `account_no`와 같은 것이 있으면 → 그 계좌 (`n`이 작은 토큰 먼저)
  3. `[계좌번호_n]`이 있는데 본인 계좌와 하나도 맞지 않으면 → `{"text": "입력하신 계좌번호로 조회되는 계좌가 없습니다. 어느 계좌를 조회할까요?", "options": 본인 계좌 전체 선택지}` (계좌가 1개여도 선택지를 준다)
  4. 계좌가 1개 → 그 계좌
  5. 그 외 → `{"text": "어느 계좌를 조회할까요?", "options": 본인 계좌 전체 선택지}`
- 선택지 = `[{"label": account_label, "choice": "balance"}, ...]`, accounts 순서. 되묻기 문구는 의도(잔액·거래내역)와 상관없이 하나다.
- `mask_map`의 다른 토큰(`[전화번호_1]` 등)은 계좌 결정에 쓰지 않는다.

## 의도 판단 (`intent.py`)
`classify_intent(question: str) -> str`. 원래 질문에 단어가 부분 문자열로 들어 있는지로 판단하고, 아래 순서로 첫 번째로 맞는 것을 돌려준다.
1. `"general"` — 절차 표현(`어디서`·`어떻게`·`방법`·`절차`) 중 하나가 있고, 조회 요청 표현(`알려`·`보여`·`얼마`)이 하나도 없다
2. `"transactions"` — 거래내역 키워드(`거래내역`·`내역`·`입금`·`출금`) 중 하나가 있다
3. `"balance"` — 그 외

| 원래 질문 | 의도 |
|----------|------|
| 잔액 알려줘 | `balance` |
| 최근 거래내역 보여줘 | `transactions` |
| 잔액 조회는 어디서 해요? | `general` |
| 거래내역은 어디서 봐요? | `general` |

단어 목록은 담당자가 자체 점검 셋으로 늘릴 수 있다. 늘리면 이 절과 테스트를 함께 고친다.

## 프롬프트·슬롯 (`prompt.py`)
- 의도별 슬롯 이름 `SLOT_NAMES`: `balance` → `account_label`·`balance`, `transactions` → `account_label`·`recent_transactions`, `general` → 없음. 출력 검증의 허용 슬롯·필수 슬롯도 이 목록이다.
- `build_slots(intent, account, transactions=None) -> dict[str, str]` — 값은 모두 문자열(계약 3 `slots: dict[str, str]`)이다. general이면 `{}`.
  - `account_label`: `입출금 ****5678`
  - `balance`: 천 단위 쉼표 + `원` — `1,234,567원`
  - `recent_transactions`: `get_transactions(account_id)` 결과(최신순, 최대 5건)를 한 건당 한 줄로 만들고 `"\n"`으로 잇는다(끝에 줄바꿈 없음). 한 줄 형식은 `"YYYY-MM-DD · 적요 · ±금액원"` — 구분자는 공백·가운뎃점(U+00B7)·공백, 입금은 `+`, 출금은 ASCII `-`, 금액은 천 단위 쉼표, `balance_after`는 표시하지 않는다.
    - 예: `"2026-09-25 · 급여 · +2,500,000원\n2026-09-24 · 카드대금 · -350,000원"`
- `build_messages(history, masked_text, intent) -> list[dict]` = `[system: SYSTEM_PROMPT] + history(복사본, 원본은 바꾸지 않음) + [user]`
  - user content: balance → `masked_text + "\n사용할 수 있는 슬롯: {{account_label}}, {{balance}}"`, transactions → `masked_text + "\n사용할 수 있는 슬롯: {{account_label}}, {{recent_transactions}}"`, general → `masked_text` 그대로
  - messages에는 잔액·거래 금액 원본(`1234567`·`1,234,567`), 전체 계좌번호(`account_no`, 하이픈 유무 무관), 거래내역 내용을 넣지 않는다. 라벨의 끝 4자리(예: `입출금 ****5678`)는 masked_text·history로 들어올 수 있고 허용한다(계약 1·3).
- `SYSTEM_PROMPT`: 존댓말, 금액·계좌는 제공된 `{{슬롯}}`만 쓰기, 모르면 상담원 확인 안내. 숫자와 `%`는 넣지 않는다(모델이 예시 숫자를 따라 쓰지 않게).
- `fallback_text(intent) -> str` — 기본 문장:
  - balance: `"{{account_label}} 계좌의 현재 잔액은 {{balance}}입니다."`
  - transactions: `"{{account_label}} 계좌의 최근 거래내역입니다.\n{{recent_transactions}}"`
  - general: `"해당 내용은 정확한 안내를 위해 상담원에게 확인해 주세요."`

## 출력 검증 (`validate.py`, BAL-002)
세 의도(balance·transactions·general) 모두 같은 넓은 규칙을 쓴다. `is_valid(text, allowed_slots, required_slots) -> bool`은 아래 중 하나라도 있으면 `False`다. 각 검사는 서로 독립이다.
1. 빈 문자열(공백만 있는 경우 포함)
2. 필수 슬롯 누락 — `required_slots` 중 text에 없는 슬롯
3. 숫자 — 아라비아 숫자가 하나라도 있으면(정규식 `\d`). "최근 5건"처럼 정상 문장이 대체되는 과대 대체는 감수한다
4. `%`
5. 마스킹 토큰 — 계약 4 형식 `[종류_n]`(정규식 `\[[가-힣]+_\d+\]`)
6. 허용 밖 슬롯 — 슬롯 토큰(프론트 fillSlots와 같은 정규식 `\{\{([^{}]*)\}\}`, 이름은 앞뒤 공백 제거) 중 이름이 `allowed_slots`에 없는 것(빈 이름 포함)
7. 서류 키워드 — `서류`·`증명서`·`등본`·`재직`·`소득` 중 하나라도 있으면

`validate_output(text, intent) -> str` — `allowed_slots = required_slots = SLOT_NAMES[intent]`로 검사해 통과하면 text를, 아니면 `fallback_text(intent)`를 돌려준다. general은 허용 슬롯이 없으므로 `{{...}}`가 하나라도 있으면 대체한다.

## 테스트로 고정할 핵심 규칙
- `test_mock_api.py`
  - `get_accounts("C001") == [{"account_id": "A001", "account_no": "110-1234-5678", "alias": "입출금", "balance": 1234567}]`, `C002`는 `A002`·`A003` 순서, `C003`은 `A004`, 없는 고객은 `[]`. 계좌 dict 키는 정확히 4개
  - 모든 계좌: `mock_data.json`에 거래 5건 이상, `get_transactions(account_id)`는 5건, `limit=3`이면 3건, 없는 계좌는 `[]`
  - 거래 dict 키는 정확히 `date`·`description`·`amount`·`balance_after`, 날짜 내림차순(같은 날짜 허용), `arr[0].balance_after == 계좌 balance`, 잔액 사슬 `arr[i].balance_after == arr[i+1].balance_after + arr[i].amount`
- `test_resolve.py`
  - `account_label(A001) == "입출금 ****5678"`
  - C001: `choose_account(get_accounts("C001"), {}) == {"account": A001}`
  - C002: `choose_account(get_accounts("C002"), {}) == {"text": "어느 계좌를 조회할까요?", "options": [{"label": "입출금 ****6789", "choice": "balance"}, {"label": "생활비 ****7890", "choice": "balance"}]}`
  - mask_map 매칭: C002 + `{"[계좌번호_1]": "110-3456-7890"}` → A003, 하이픈 없는 `"11034567890"`도 A003
  - 본인 계좌 아님: C001 + `{"[계좌번호_1]": "110-9999-0000"}` → `{"text": "입력하신 계좌번호로 조회되는 계좌가 없습니다. 어느 계좌를 조회할까요?", "options": [{"label": "입출금 ****5678", "choice": "balance"}]}`
  - 계좌 0개: `choose_account([], {}) == {"text": "고객님 명의로 조회되는 계좌가 없습니다.", "options": []}`
  - 라벨 클릭: C002, history `[{"role": "user", "content": "최근 거래내역 보여줘"}, {"role": "assistant", "content": "어느 계좌를 조회할까요?"}]`, masked_text `"생활비 ****7890"` → `{"question": "최근 거래내역 보여줘", "account": A003}`. history가 빈 첫 턴이거나 masked_text가 라벨과 다르면 `None`
- `test_intent.py`
  - 위 표의 4개 예문
  - 라벨 클릭 턴: 위 라벨 클릭 예의 `find_clicked(...)["question"]`을 `classify_intent`에 넣으면 `"transactions"`
- `test_prompt.py`
  - `build_slots("balance", A001) == {"account_label": "입출금 ****5678", "balance": "1,234,567원"}`, general은 `{}`, 슬롯 값은 모두 `str`
  - `build_slots("transactions", A001, get_transactions("A001"))["recent_transactions"]`가 mock 데이터로 만든 위 리터럴 형식과 정확히 같다(5줄, 최신순, `balance_after` 없음)
  - 세 의도 모두 `build_messages` 결과 전체 문자열에 `1234567`·`1,234,567`·`110-1234-5678`·`11012345678`과 거래 금액이 없고, balance·transactions는 슬롯 이름 줄이 위 문자열과 같다. general의 user content는 masked_text 그대로다
  - `build_messages`는 전달받은 `history`를 바꾸지 않는다. `SYSTEM_PROMPT`에 숫자와 `%`가 없다
  - `fallback_text` 세 문장이 위 리터럴과 같다
- `test_validate.py`
  - balance·transactions·general 각각에서 규칙 1~7 트리거를 하나씩 넣은 문장 → `validate_output`이 그 의도의 기본 문장을 돌려준다(general은 필수 슬롯 규칙 제외)
  - 규칙에 안 걸리는 문장은 그대로 돌려준다. 예: `"{{account_label}} 계좌의 현재 잔액은 {{balance}}입니다. 더 궁금하신 점이 있으시면 말씀해 주세요."`
  - 세 기본 문장은 각자의 의도로 검증해도 통과한다(기본 문장이 자기 검증에 걸리면 안 된다)
- `test_agent.py` (2026-09-29 추가) — 순수 함수를 엮는 `handle()` 전체를 최종 `AgentReply`로 확인한다. `handle()`은 `from app import llm` 뒤 `llm.generate(...)`로 부르고, 테스트는 `monkeypatch.setattr("app.llm.generate", 가짜)` 한 곳만 패치한다. 순수 함수 세부 규칙은 위 모듈 테스트에 맡긴다
  - export: `from app.agents.balance import agent, mock_router`가 되고, `mock_router is mock_api.mock_router`(라우트 있음), `agent`는 `BalanceAgent` 인스턴스, `agent.name == "balance"`
  - 세 의도 정상 경로(모델 이름 `"cs-balance"`, `options == []`): C001 "잔액 알려줘" → slots `{"account_label": "입출금 ****5678", "balance": "1,234,567원"}` / C001 "최근 거래내역 보여줘" → slots `account_label`·`recent_transactions`(A001 거래 5건) / C002 "잔액 조회는 어디서 해요?" → 되묻기 없이 모델 호출, slots `{}`, messages에 계좌 별칭·라벨·계좌번호(하이픈 유무)·잔액·거래 금액 없음(`SYSTEM_PROMPT` 안의 슬롯 이름은 허용)
  - 계좌번호 입력: C002 + mask_map `{"[계좌번호_1]": "110-3456-7890"}` → 되묻기 없이 A003 잔액 slots
  - 모델 미호출(호출되면 바로 실패하는 가짜 generate): C002 "잔액 알려줘" 되묻기, 없는 고객 "잔액 알려줘"(계좌 0개), C001 + 본인 아닌 `[계좌번호_1]` — text·options는 "대상 계좌 결정"의 리터럴, slots `{}`
  - 2턴 라벨 클릭: C002 "최근 거래내역 보여줘" → 되묻기 → "생활비 ****7890" 턴에서 A003 거래내역 slots / C002 "잔액 알려줘" → 되묻기 → "입출금 ****6789" 턴에서 A002 잔액 slots. transactions면 `get_transactions` 결과를 `build_slots`에 넘기는지는 이 slots로 확인한다(`build_slots`는 transactions에 `None`을 받지 않는다)
  - 출력 검증: 가짜 generate가 금액(`1,234,567원`)·계좌번호(`110-1234-5678`)를 흘리면 text는 그 의도의 `fallback_text`
  - 모델 입력: 모델을 부르는 모든 케이스에서 generate에 넘긴 messages에 잔액·거래 금액 원본과 전체 계좌번호가 없다

## 알려진 한계 (2026-09-29)
코드로 고치지 않고 기록만 한다.
- (a) `find_clicked`는 "history에 user 메시지가 있고 masked_text가 라벨과 같음"만 본다. 되묻기 직후가 아니어도 라벨과 같은 입력은 라벨 클릭으로 친다. 프론트는 가장 최근 봇 메시지의 선택지만 누를 수 있으므로(`docs/frontend/ARCHITECTURE.md` 핵심 규칙) 고객이 라벨을 직접 타이핑할 때만 생긴다.
- (b) 계약 3대로 gateway가 라벨 클릭 턴의 masked_text(라벨)를 history user로 넣으면, 그 뒤 다시 라벨 클릭으로 판단되는 턴에서는 직전 라벨이 "원래 질문"이 되어 의도가 라벨 문자열로 판단된다(`생활비 ****7890` → balance, `입출금 ****6789` → `출금`을 포함해 transactions). 발생 조건은 (a)와 같다.
- `tests/router/test_base.py` 예외: 팀원C 영역 파일(cherry-pick 발판)이지만 스텁 전용 검사 2개(`test_stub_package_exports_agent_and_mock_router`, `test_stub_handle_returns_fixed_message`)의 `AREAS`에서 balance를 뺐다. 실제 export(라우트가 있는 `mock_router`)와 실제 `handle()`(모델 호출)로 바꾸면 이 두 검사는 반드시 실패하기 때문이다. loan·interest 스텁 검사와 계약 3 dataclass·Protocol 검사 3개는 그대로다. 발판 수정의 예외는 이 파일과 `app/agents/balance/__init__.py` 둘뿐이다(BAL-005). feat-router 병합 때 이 파일이 충돌하면 main 쪽 최신 파일에서 balance만 뺀다.
  - 후속(아직 안 함): loan·interest도 스텁을 실제 구현으로 바꿀 때 같은 문제가 생기므로 팀원C에게 알린다.

## 학습 데이터
- 원천: `split.json`의 train 중 `consulting_topic == "거래내역/잔액조회"`인 라벨링 데이터 `qa_data[]` (필드명은 데이터 확인 전 가정 — 공통 ARCHITECTURE 학습 파이프라인)
- 한 항목 = 대화 1개: user(`input.question`) → assistant(`input.answer`) → user(`input.follow_up_question`) → **assistant 목표(`output`)**
- 전처리 순서: `masking.mask()`로 치환 → `output`에 `input`에 없는 수치·상품명이 있으면 제외 → 베이스 모델 채팅 템플릿 적용
- 검증: val 분할에서 샘플을 뽑아 사람이 읽어 확인한다. test 분할은 최종 점검에만 쓴다.
