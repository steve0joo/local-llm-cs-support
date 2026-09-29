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
├── tests/balance/         # test_<모듈>.py (학습 진입점은 test_train.py)
├── training/balance/      # train.py·requirements-mac.txt·MAC_TRAINING.md, prepare.py(BAL-008)
└── models/balance/Modelfile   # cs-balance 등록용. .gguf는 GGUF 변환 검증 뒤 같은 폴더에 둔다(BAL-006)
```

## TDD 착수점
- 첫 테스트: `tests/balance/test_mock_api.py` — `get_accounts(customer_id)`가 아래 mock 데이터대로 고객별 계좌를 돌려주는지 확인한다.
- 이후 순서: `get_transactions` → `resolve` → `intent` → `prompt` → `validate`(1차 구현, 모델 없이 도는 순수 함수) → `handle()`(`tests/balance/test_agent.py`, 모델은 목). `handle()`은 팀원C 커밋을 cherry-pick한 발판(`agents/base.py`·`llm`·스캐폴드) 위에서 만든다(BAL-005, 2026-09-29 변경).
- 3차 순서(PRD "구현 진행", 실행 계획은 `phases/agent-balance/`): `intent`의 `입출금` 규칙 → `resolve.choose_account`의 별칭·끝 4자리 규칙 → `prepare.py`(`tests/balance/test_prepare.py`) → `Modelfile`(`tests/balance/test_modelfile.py`). 모두 모델 없이 테스트할 수 있다.
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
5. 대상 계좌 결정 — 라벨 클릭 턴이면 2의 계좌. 아니면 resolve.choose_account(accounts, mask_map, masked_text)
   - 결과에 "text"가 있으면 모델을 부르지 않고 AgentReply(text, slots={}, options)로 바로 답한다 (아래 "대상 계좌 결정")
6. slots = prompt.build_slots(intent, account, transactions)
   - transactions면 get_transactions(account_id)를 조회해 넘긴다
7. messages = prompt.build_messages(history, masked_text, intent) → llm.generate("cs-balance", messages)
8. 출력 검증 — validate.validate_output(text, intent): 규칙에 걸리면 그 의도의 기본 문장으로 대체
9. AgentReply(text, slots, options=[])
```
- 예: C002 "최근 거래내역 보여줘" → 되묻기 → 라벨 클릭 턴("생활비 ****7890")에서도 원래 질문으로 판단해 거래내역으로 답한다(테스트로 고정).
- 모델 호출 실패: 7의 `llm.generate`가 `httpx.HTTPError`(Ollama 없음·모델 미등록·타임아웃)를 올리면 `handle()`은 잡지 않는다. 게이트웨이가 잡아 "지금은 답변을 드릴 수 없습니다. 상담원 연결을 도와드릴까요?"로 답하고 그 턴을 history에 넣지 않는다(`docs/router/ARCHITECTURE.md` "게이트웨이 구현 결정", main 기준, BAL-007). 5에서 바로 답하는 되묻기·계좌 없음·본인 아님 턴은 모델을 부르지 않으므로 모델 없이도 동작한다.

## 대상 계좌 결정 (`resolve.py`)
계약 3 타입(`AgentReply`)을 쓰지 않고 plain dict를 돌려준다. `AgentReply` 포장은 `handle()` 안에서만 한다(BAL-005).
- `account_label(account) -> str` — `"{alias} ****{account_no 끝 4자리}"`
- `find_clicked(masked_text, history, accounts) -> dict | None` — 라벨 클릭 턴이면 `{"question": 원래 질문, "account": 계좌}`, 아니면 `None`
- `choose_account(accounts, mask_map, masked_text) -> dict` — 계좌를 정하면 `{"account": 계좌}`, 모델 없이 바로 답해야 하면 `{"text": 문구, "options": 선택지}`. 아래 순서로 첫 번째로 맞는 것:
  1. 계좌가 0개 → `{"text": "고객님 명의로 조회되는 계좌가 없습니다.", "options": []}`
  2. `mask_map`의 `[계좌번호_n]` 원본 중 숫자만 비교해(하이픈 무시) 본인 계좌 `account_no`와 같은 것이 있으면 → 그 계좌 (`n`이 작은 토큰 먼저)
  3. `[계좌번호_n]`이 있는데 본인 계좌와 하나도 맞지 않으면 → `{"text": "입력하신 계좌번호로 조회되는 계좌가 없습니다. 어느 계좌를 조회할까요?", "options": 본인 계좌 전체 선택지}` (계좌가 1개여도 선택지를 준다)
  4. `masked_text`에 별칭(`alias`)이나 `account_no` 끝 4자리가 부분 문자열로 들어 있는 본인 계좌가 정확히 1개 → 그 계좌. 0개나 2개 이상이면 다음 규칙으로 간다
  5. 계좌가 1개 → 그 계좌
  6. 그 외 → `{"text": "어느 계좌를 조회할까요?", "options": 본인 계좌 전체 선택지}`
- 규칙 4 예(C002): "생활비 계좌 잔액 알려줘" → A003, "7890 계좌 잔액" → A003, "입출금 계좌 잔액 알려줘" → A002, "잔액 알려줘" → 되묻기(규칙 6). 첫 턴에 라벨을 그대로 쳐도("생활비 ****7890") 규칙 4로 A003이 된다.
- 선택지 = `[{"label": account_label, "choice": "balance"}, ...]`, accounts 순서. 되묻기 문구는 의도(잔액·거래내역)와 상관없이 하나다.
- `mask_map`의 다른 토큰(`[전화번호_1]` 등)은 계좌 결정에 쓰지 않는다.

## 의도 판단 (`intent.py`)
`classify_intent(question: str) -> str`. 원래 질문에 단어가 부분 문자열로 들어 있는지로 판단하고, 아래 순서로 첫 번째로 맞는 것을 돌려준다.
1. `"general"` — 절차 표현(`어디서`·`어떻게`·`방법`·`절차`) 중 하나가 있고, 조회 요청 표현(`알려`·`보여`·`얼마`)이 하나도 없다
2. `"transactions"` — 질문에서 `입출금`을 모두 지운 뒤 거래내역 키워드(`거래내역`·`내역`·`입금`·`출금`) 중 하나가 있다. `입출금`은 계좌 별칭이라 `출금`으로 세지 않는다
3. `"balance"` — 그 외

| 원래 질문 | 의도 |
|----------|------|
| 잔액 알려줘 | `balance` |
| 최근 거래내역 보여줘 | `transactions` |
| 잔액 조회는 어디서 해요? | `general` |
| 거래내역은 어디서 봐요? | `general` |
| 입출금 계좌 잔액 알려줘 | `balance` |
| 입출금 ****6789 | `balance` |
| 입출금 내역 보여줘 | `transactions` |

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
- `test_train.py` (BAL-006) — MLX LM을 실제로 돌리지 않는다
  - `check_dataset`: train 모드는 `train.jsonl`·`valid.jsonl`, test 모드는 `test.jsonl`만 본다. 마지막 메시지가 assistant가 아니거나 내용이 공백이면 거절한다
  - `check_model`: `config.json`에 `quantization`이 없으면 거절한다(양자화 베이스만 QLoRA)
  - `build_command`: train은 `--train --mask-prompt`, test는 `--test`만(`--train` 없음)
- 3차에 추가할 테스트
  - `test_intent.py`: 위 표의 `입출금` 세 예문
  - `test_resolve.py`: 규칙 4 예 네 개. C001 + "생활비 계좌 잔액"은 A001(규칙 5), C002 + 본인 아닌 `[계좌번호_1]` + "생활비"는 본인 아님 안내(규칙 3이 먼저). 기존 케이스는 세 번째 인자로 masked_text를 넘긴다
  - `test_agent.py`: 2턴 — C002 "잔액 알려줘" → 되묻기 → "생활비 계좌 잔액 알려줘" 턴에서 A003 잔액 slots(J9)
  - `test_prepare.py`: 아래 "`prepare.py` 인터페이스" 규칙. 픽스처는 `tmp_path`에 합성 zip·`split.json`으로 만들고 실제 데이터를 쓰지 않는다
    - 분할: val·test 상담이나 다른 `consulting_topic`, `qa_topic`이 다른 QA가 train 결과에 섞이지 않는다
    - 마스킹: 입력에 계좌번호·전화번호·주민번호 원본을 넣으면 결과 파일 어디에도 원본 문자열이 없다
    - 제외: 숫자가 든 `output`, 서류 키워드가 든 `output`, 입력에 없는 상품명(예: `○○자유통장`)이 든 `output`은 빠지고, 허용 목록 명칭(`체크카드`)만 든 `output`은 남는다
    - 합성: 모든 합성 질문의 `classify_intent`가 자기 의도, 모든 응답 템플릿이 `is_valid` 통과, 합성 샘플 전체 문자열에 mock 계좌번호(하이픈 유무)·잔액(원 단위 정수·쉼표 표기)이 없다
    - 형식: 기록한 파일이 `training.balance.train.check_dataset(out_dir, "train")`과 `"test"` 모드를 통과한다
  - `test_modelfile.py`: `Modelfile`의 `SYSTEM """..."""` 내용이 `prompt.SYSTEM_PROMPT`와 같고, `FROM ./cs-balance.gguf`와 `stop "<|im_end|>"`가 있다

## 에러 처리·보안 (2026-09-29 점검)
MVP 원칙: 데모에서 실제로 생기는 경우만 코드로 막고, 나머지는 여기에 기록만 한다.
- 에러 처리 담당: 모델 호출 실패 → 게이트웨이 공통 문구(BAL-007), 모델의 이상한 출력 → 출력 검증 후 기본 문장(BAL-002), 코드 버그 → 게이트웨이가 500으로 올리고 프론트가 오류 말풍선을 보인다. 모델 호출 제한(`llm` 60초)이 프론트 프록시 제한(120초) 안에 있다. `handle()`에 따로 넣을 예외 처리는 없다.
- 처리하지 않는 경우: 거래가 0건인 계좌(mock 데이터에 없다), `get_accounts`·`mock_data.json` 읽기 실패(서버가 뜰 때 드러난다).
- 테스트로 막힌 보안 규칙: 모델 입력에 잔액·거래 금액 원본과 전체 계좌번호가 없다. `mask_map`은 계좌번호 비교에만 쓰고 프롬프트에 넣지 않는다. 본인 계좌가 아닌 번호는 조회하지 않는다.
- 프롬프트 공격("숫자로 말해" 등): 모델은 원래 값을 받지 않고, 출력 검증이 숫자·마스킹 토큰을 막는다. 입력 문장과 상관없이 성립하므로 따로 방어 코드를 두지 않는다.
- 학습 산출물: `backend/data/`, `backend/training/**/outputs/`, `*.gguf`, `*.safetensors`는 `.gitignore`로 제외된다. 합성 샘플에는 실제 값이 없어야 하고, `test_prepare.py`로 확인한다.
- MVP에서 받아들이는 위험(기록만):
  - `customer_id`를 클라이언트가 보내므로 누구나 아무 데모 고객을 조회할 수 있다. 실제 본인 인증은 공통 PRD 제외 사항이다.
  - `/mock/customers/{id}/accounts`는 인증 없이 전체 계좌번호·잔액을 돌려준다. 데모·인수용 라우트다. 백엔드는 기본값(127.0.0.1)으로만 띄우고 `--host 0.0.0.0`으로 열지 않는다.
  - 하이픈 없는 계좌번호는 마스킹되지 않는다(PRD 영역 간 요청 R3).

## 알려진 한계 (2026-09-29)
코드로 고치지 않고 기록만 한다.
- (a) `find_clicked`는 "history에 user 메시지가 있고 masked_text가 라벨과 같음"만 본다. 되묻기 직후가 아니어도 라벨과 같은 입력은 라벨 클릭으로 친다. 프론트는 가장 최근 봇 메시지의 선택지만 누를 수 있으므로(`docs/frontend/ARCHITECTURE.md` 핵심 규칙) 고객이 라벨을 직접 타이핑할 때만 생긴다.
- (b) 계약 3대로 gateway가 라벨 클릭 턴의 masked_text(라벨)를 history user로 넣으면, 그 뒤 다시 라벨 클릭으로 판단되는 턴에서는 직전 라벨이 "원래 질문"이 되어 의도가 라벨 문자열로 판단된다(`생활비 ****7890` → balance, `입출금 ****6789` → balance). 발생 조건은 (a)와 같다.
- (c) 직전에 고른 계좌를 이어가지 않는다(J10). 잔액을 본 뒤 "거래내역도 보여줘"라고 하면 계좌 2개 고객에게 다시 되묻는다. history의 assistant 문장은 `{{슬롯}}` 그대로라 어느 계좌였는지 알 수 없고, 이어가려면 "다른 계좌는요?" 같은 표현 규칙도 필요해서 MVP에서는 하지 않는다.
- (d) 되묻기 뒤 선택지를 누르지 않고 직접 입력하면(J9) 게이트웨이가 새 질문으로 라우팅하고, 에이전트도 원래 질문을 보지 않는다. 3차 규칙 4로 계좌는 정해지지만 의도는 새 입력으로 판단한다(원래 질문이 거래내역이어도 "생활비 계좌 잔액 알려줘"는 잔액). 라우터가 balance로 보내지 않는 입력("생활비 계좌요")은 규칙 4까지 오지 않는다.
- (e) 의도 키워드가 놓치는 표현이 있다(J11 "이번 달 급여 들어왔어?" → balance). 자체 점검 셋에서 나온 표현만 단어 목록에 더한다(BAL-001).
- `tests/router/test_base.py` 예외: 팀원C 영역 파일(cherry-pick 발판)이지만 스텁 전용 검사 2개(`test_stub_package_exports_agent_and_mock_router`, `test_stub_handle_returns_fixed_message`)의 `AREAS`에서 balance를 뺐다. 실제 export(라우트가 있는 `mock_router`)와 실제 `handle()`(모델 호출)로 바꾸면 이 두 검사는 반드시 실패하기 때문이다. loan·interest 스텁 검사와 계약 3 dataclass·Protocol 검사 3개는 그대로다. 발판 수정의 예외는 이 파일과 `app/agents/balance/__init__.py` 둘뿐이다(BAL-005). main 병합(feat-router는 PR #4로 main에 들어갔다) 때 이 파일이 충돌하면 main 쪽 최신 파일에서 balance만 뺀다.
- `tests/gateway/test_api.py` 예외(main 병합 때 추가, 2026-09-29 결정): `test_response_has_exactly_the_contract_fields`는 balance 스텁의 "준비 중인 기능입니다."를 기대한다. 병합할 때 fixture의 `classify`가 `["loan"]`을 돌려주게 하고 기대 `agent`를 `"loan"`으로 바꾼다. 계약 필드 검사와 "스텁까지 도달" 의도는 그대로다. 이 파일이 세 번째 예외다.
  - 후속(아직 안 함): loan·interest도 스텁을 실제 구현으로 바꿀 때 `test_base.py`·`test_api.py`에서 같은 문제가 생기므로 팀원C에게 알린다.

## 학습 데이터
- 원천: 로컬 은행 라벨링 ZIP의 JSON에서 `consulting.consulting_topic == "거래내역/잔액조회"`인 `qa_data[]`를 추출하고 `source.source_id`로 공통 `split.json`을 적용한다. 실제 확인된 건수는 Training 4,017건, Validation 503건이다. 원천 Training·Validation에 함께 있는 상담 2건은 공통 분할이 train으로 보낸다(main `docs/router/ADR.md` RT-005).
- RT-005의 영역 규칙을 따른다: 같은 QA의 `qa_topic`이 `consulting_topic`과 다르면 뺀다. 원본에서 가려진 금액 `●●●원`은 `[금액_n]`으로 바꾼 뒤 `mask()`를 적용한다.
- 한 항목 = 대화 1개: user(`input.question`) → assistant(`input.answer`) → user(`input.follow_up_question`) → **assistant 목표(`output`)**
- 전처리 순서: 게이트웨이와 같은 `app.masking.mask()`로 치환 → `output`에 `input`에 없는 수치·상품명이 있으면 제외 → `output`이 general 출력 검증(`validate.is_valid(output, (), ())`)에 걸리면 제외(BAL-008) → `prompt.build_messages([question, answer], follow_up_question, "general")`로 입력을 만든다. 채팅 템플릿은 MLX LM이 베이스 토크나이저로 입힌다. `app.masking` import 실패 시 전처리를 중단한다. 임시 정규식·fallback 마스킹은 허용하지 않는다(계약 4).
- 원천의 한계(2026-09-29 로컬 집계, Training 4,017건): `output`은 대부분 절차 안내형 장문이고 `{{슬롯}}`을 쓰는 답은 0건, 아라비아 숫자가 든 답이 1,311건(33%)이다. 이것만 학습하면 잔액·거래내역 턴의 모델 출력은 필수 슬롯 검사(BAL-002)에 걸려 거의 항상 기본 문장으로 바뀐다.
- 합성 슬롯 샘플(BAL-008): `prepare.py`가 잔액·거래내역 질문 변형 → `{{슬롯}}` 응답 변형 샘플을 템플릿으로 만들어 AI Hub 샘플과 섞는다.
  - 입력은 추론과 같은 `prompt.build_messages`로 만든다(`SYSTEM_PROMPT`, "사용할 수 있는 슬롯:" 줄 포함). 첫 턴 모양과 라벨 클릭 턴 모양 두 가지다(아래 "`prepare.py` 인터페이스"). 학습 입력과 추론 입력의 모양을 맞추기 위해서다(계약 4와 같은 이유).
  - 응답 템플릿은 그 의도로 `validate.is_valid`를 통과해야 한다(필수 슬롯 포함, 숫자·`%`·마스킹 토큰·서류 키워드 없음). 테스트로 고정한다.
  - 사실(금리·상품명·수수료·서류·메뉴 이름)은 넣지 않는다. 슬롯과 안내 문구만 쓴다.
  - 첫 실행은 아래 인터페이스의 기본값(질문 각 20개 이상 × 응답 각 5개 이상)으로 하고, 질문 목록과 합성 비중은 첫 소규모 학습 결과를 보고 조정한다.
- 검증: val 분할에서 샘플을 뽑아 사람이 읽어 확인한다. test 분할은 최종 점검에만 쓴다.
- 실행 환경: Hugging Face에서 받은 양자화 Qwen Instruct 베이스를 Mac의 MLX LM으로 학습하고 Ollama로 추론·평가한다. 데이터 형식·명령·GGUF 변환 게이트는 `backend/training/balance/MAC_TRAINING.md`를 따른다. `app.masking.mask()`·공통 split 코드는 가져왔고, 실제 가공 데이터는 step 5에서 만든다(`phases/agent-balance/`, 사람). main에서 마스킹·분할이 바뀌면 가공 데이터를 재생성한다.

### `prepare.py` 인터페이스
`backend/training/balance/prepare.py`. 원본 zip 경로와 분할 파일 경로는 `training.common.split`의 `TL_ZIP`·`VL_ZIP`·`OUT_PATH`를 import해서 쓴다(경로를 다시 적지 않는다).
```python
TOPIC = "거래내역/잔액조회"
OUT_DIR: Path                     # backend/data/processed/balance (gitignore)
SPLIT_FILES = {"train": "train.jsonl", "val": "valid.jsonl", "test": "test.jsonl"}   # MLX LM은 valid.jsonl 이름을 쓴다

def load_qas(zip_path: Path) -> Iterator[dict]: ...
    # {"source_id", "question", "answer", "follow_up", "output"}. 원본 필드 접근은 이 함수에만 둔다
    # consulting.consulting_topic == TOPIC 이고 qa_data[].qa_topic == TOPIC 인 QA만 (RT-005 라벨 규칙)
def normalize_amounts(text: str) -> str: ...        # 비식별 금액 "●…원" → "[금액_n]" (n은 1부터, RT-005). mask() 금액 규칙의 숫자 자리를 ●로 바꾼 모양(쉼표·억만천백십 허용)
def build_sample(qa: dict) -> dict | None: ...      # 제외면 None
def synth_samples() -> dict[str, list[dict]]: ...   # {"train": [...], "val": [...], "test": [...]}
def build_dataset(split_path: Path, out_dir: Path, zip_paths: list[Path]) -> dict[str, int]: ...  # 분할별 기록 수
def main(argv: list[str] | None = None) -> None: ...  # --split·--out-dir·--zip(여러 개), 인자 없으면 OUT_PATH·OUT_DIR·[TL_ZIP, VL_ZIP]
# CLI: cd backend && python -m training.balance.prepare
```
- `build_sample` 순서: 네 필드에 `normalize_amounts` → `mask()`(masked_text만 쓴다) → 제외 규칙 → `{"messages": prompt.build_messages([user: question, assistant: answer], follow_up, "general") + [assistant: output]}`.
- 제외 규칙(`output` 기준, 하나라도 걸리면 제외):
  1. `validate.is_valid(output, (), ())`가 `False`(숫자·`%`·마스킹 토큰·슬롯·서류 키워드, BAL-008). 공통 ADR-005의 "input에 없는 수치"는 숫자 전부 제외로 대신한다
  2. 상품명 휴리스틱(ADR-005): 정규식 `[가-힣A-Za-z]+(통장|적금|예금|카드|대출)`에 걸린 단어가 입력 세 필드에 없고 일반 명칭 허용 목록 `GENERIC_PRODUCT_NAMES`(`입출금통장`·`정기예금`·`정기적금`·`신용카드`·`체크카드`·`신용대출`·`주택담보대출`·`전세자금대출`)에도 없다
- 분할: `split.json`의 `source_id` 값으로 정한다. `split.json`에 없는 `source_id`는 버린다.
- `synth_samples` 규칙:
  - 질문 목록 `BALANCE_QUESTIONS`·`TRANSACTION_QUESTIONS`(각 20개 이상)의 모든 질문은 `intent.classify_intent`가 자기 의도로 판단해야 한다. 추론 때와 같은 분기로 들어가게 하기 위해서다.
  - 응답 템플릿 `BALANCE_ANSWERS`·`TRANSACTION_ANSWERS`(각 5개 이상)는 `validate.is_valid(답, SLOT_NAMES[의도], SLOT_NAMES[의도])`를 통과해야 한다.
  - 샘플 = 질문 × 응답 전체 조합(무작위 없음). 질문 인덱스 `i`가 짝수면 첫 턴 모양 `build_messages([], 질문, 의도)`, 홀수면 라벨 클릭 턴 모양 `build_messages([user: 질문, assistant: resolve.ASK_TEXT], 라벨, 의도)`다. 라벨은 mock 데이터 계좌의 `account_label`을 차례로 쓴다.
  - 분할: `i % 10 == 0`이면 test, `i % 10 == 1`이면 val, 나머지는 train.
- 출력: `OUT_DIR/{train,valid,test}.jsonl`, 한 줄에 `{"messages": [...]}` 하나. AI Hub 샘플과 합성 샘플을 한 파일에 쓴다. `train.py check`(`check_dataset`)를 통과하는 형식이다.

### Modelfile
`backend/models/balance/Modelfile`. `.gguf`는 같은 폴더에 두고 커밋하지 않는다(`*.gguf` gitignore).
- `FROM ./cs-balance.gguf`
- `TEMPLATE`: Qwen3-4B-Instruct-2507의 ChatML(생각 블록 없음). 학습 때 MLX LM이 입힌 채팅 템플릿과 같은 모양이어야 한다.
- `SYSTEM`: `prompt.SYSTEM_PROMPT`와 글자 단위로 같다. 에이전트는 매 요청에 system 메시지를 보내므로 이 값은 `ollama run` 직접 확인용이다.
- `PARAMETER`: `stop "<|im_end|>"`, `stop "<|endoftext|>"`, `temperature 0.2`(지어내기 억제), `num_ctx 2048`, `num_predict 256`.
- 등록: `ollama create cs-balance -f backend/models/balance/Modelfile` (계약 5 이름).
