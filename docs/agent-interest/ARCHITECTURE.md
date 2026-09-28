# 아키텍처: 이자/연체 에이전트

> 코드 작성 규칙(모델 호출, mock 조회 함수, 테스트 파일)은 루트 `docs/ARCHITECTURE.md`의 "코드·테스트 규칙"과 "통합 순서"를 따른다. 이 문서에는 이 영역에만 해당하는 내용을 적는다.

## 디렉토리 구조
```
backend/
├── app/agents/interest/
│   ├── __init__.py        # agent, mock_router export (계약 3) — 팀원C 스텁 전에는 빈 파일
│   ├── agent.py           # InterestAgent.handle()
│   ├── prompt.py          # 시스템 프롬프트, 이자 정보 줄, 슬롯, 기본 문장 — 학습 데이터도 이 형식을 쓴다
│   ├── validate.py        # is_valid(text, allowed_slots, required_slots) — 출력 검증
│   ├── mock_api.py        # mock_router + get_interest()
│   └── mock_data.json     # C002: L001(정상), C003: L002(연체)
├── tests/interest/        # test_<구현 모듈명>.py, __init__.py 없음
├── training/interest/     # prepare.py(학습 데이터), train.py, export.md
└── models/interest/Modelfile
```
- `__init__.py`: 팀원C가 스텁(`agent` + 빈 `mock_router`)을 넣는다. 스텁이 오기 전에는 빈 파일로 두고, main 병합 때 충돌하면 스텁 쪽을 받은 뒤 실제 구현으로 바꾼다.

## TDD 착수점
- 첫 테스트: `tests/interest/test_mock_api.py` — `get_interest(customer_id)`가 아래 mock 데이터대로 돌려주는지 확인한다.
- 이후 순서: `handle()` 내역 없음 고정 문장(INT-003) → 슬롯·프롬프트 구성 → 출력 검증(모델은 목). `agents/base.py` 스텁이 main에 오기 전이면 `handle()` 테스트는 import 실패 red로 시작한다.
- 진행 상황: `test_mock_api.py`, 슬롯·프롬프트(`test_prompt.py`), 출력 검증(`test_validate.py`)은 작성·통과했다. `handle()`(`test_agent.py`)은 `base.py` 스텁을 기다린다.

## mock API
| 메서드 | 경로 | 응답 |
|--------|------|------|
| GET | `/mock/customers/{customer_id}/interest` | `[{loan_id, product_type, repayment_method, interest_type, payment_method, next_due_date, interest_due, overdue_amount, overdue_days}]` |
- 조회 함수: `get_interest(customer_id: str) -> list[dict]`. 공통 규칙은 `docs/ARCHITECTURE.md` "코드·테스트 규칙"을 따른다. 에이전트는 라우트가 아니라 이 함수를 직접 호출한다.
- 금리·이율 수치 필드는 두지 않는다(INT-002). 금액은 정수(원)로 저장한다.
- `repayment_method`(원리금균등·원금균등·만기일시), `interest_type`(고정·변동, 수치 없이 방식만), `payment_method`(자동이체·가상계좌 입금)는 문자열이다. 모델이 상환·금리 방식·납부 방법 질문에 상담원 안내 대신 조회값으로 답하게 한다(사용자 스토리 2의 납부 방법 안내).
- 타입: `next_due_date`는 `"YYYY-MM-DD"` 문자열, `overdue_days`는 정수다. 연체가 없으면 `overdue_amount`와 `overdue_days`가 모두 0이다.
- `interest_due`: 다음 납부일에 낼 이자. `overdue_amount`: 납부일이 지나 아직 내지 않은 금액 합계.
- `mock_data.json` 내부 형식은 이 영역 재량이다. 테스트는 반환값만 본다.

### mock 데이터
| customer_id | loan_id | product_type | repayment_method | interest_type | payment_method | next_due_date | interest_due | overdue_amount | overdue_days |
|---|---|---|---|---|---|---|---|---|---|
| `C002` | `L001` | 신용대출 | 만기일시 | 변동 | 자동이체 | 2026-10-15 | 58000 | 0 | 0 |
| `C003` | `L002` | 주택담보대출 | 원리금균등 | 고정 | 가상계좌 입금 | 2026-10-25 | 312500 | 625000 | 12 |
| `C004`* | `L003` | 신용대출 | 원리금균등 | 변동 | 자동이체 | 2026-10-20 | 41500 | 890000 | 65 |
| `C005`* | `L004` | 전세자금대출 | 원금균등 | 고정 | 가상계좌 입금 | 2026-10-10 | 176000 | 0 | 0 |
| `C006`* | `L005` | 주택담보대출 | 원리금균등 | 고정 | 자동이체 | 2026-10-26 | 405000 | 548000 | 2 |
| `C007`* | `L006` | 신용대출 | 만기일시 | 변동 | 자동이체 | 2026-09-30 | 27500 | 0 | 0 |
- `C001`은 대출이 없어 `[]`다.
- \* C004~C007은 **계약 6 확장 제안값(팀 합의 대기)**이다. 시연 장면을 넓히려고 이 영역 목업에 먼저 넣었다: C004 장기 연체·자동이체(잔액 부족 이야기), C005 정상·가상계좌 입금·원금균등, C006 막 시작된 연체(2일), C007 납부일 임박·만기일시(대출문의의 만기 임박과 함께 쓰는 고객). 합의 전까지는 화면 고객 선택(FE-003)·대출문의·잔액조회 목업에 없으므로 시연에 쓸 수 없고, 평가(Golden Set)에만 쓴다. `loan_id`·`product_type`은 대출문의 목업과 맞춰야 한다(계약 6). C007의 다음 납부일은 시연 날짜에 맞춰 조정한다.
- 대출문의 mock과 공유하는 값은 `loan_id`·`product_type`뿐이다(계약 6). 나머지 필드는 이 영역만 쓴다.
- mock 데이터는 팀 결정에 따라 각 영역 브랜치에서 만들어 쓰고, 나중에 병합하거나 파일을 나눈다. 이 표는 이자/연체 버전이다.
- 다음 납부일은 대출문의 만기일(L001 2027-03-31, L002 2035-06-30)보다 앞이다. L002는 대출문의에서도 연체로 연장 불가(`extendable=false`)다.
- 이자·연체 금액은 계산 없이 저장한 데모 값이다(INT-001). 원금·잔액·금리는 두지 않는다. 잔액은 대출문의 슬롯(`{{principal_remaining}}`) 담당이다.

## handle() 흐름
```
1. items = get_interest(customer_id)
2. 없음 → AgentReply(text="고객님 명의로 조회되는 대출 이자 내역이 없습니다.", slots={}, options=[]) (모델 호출 없음)
3. 대상 대출: mock 고객은 대출이 최대 1건이다(계약 6). 여러 건 선택 되묻기는 만들지 않는다. 2건 이상이면 첫 번째를 쓴다.
4. slots = prompt.build_slots(item) — loan_label, interest_due, 연체가 있으면 overdue_amount ("312,500원" 형태)
5. messages = prompt.build_messages(masked_text, history, item)
     [system: SYSTEM_PROMPT] + history + [user: masked_text
                                               + "\n이자 정보: 종류=주택담보대출, 상환 방식=원리금균등, 금리 방식=고정, 납부 방법=가상계좌 입금, 다음 납부일=2026-10-25, 연체 여부=연체 중, 연체 일수=12"
                                               + "\n사용할 수 있는 슬롯: {{loan_label}}, {{interest_due}}, {{overdue_amount}}"]
     - 이자 정보·슬롯 줄은 마지막 user 메시지 끝에 붙인다.
     - 연체가 없으면 "연체 여부=연체 없음" — 모델이 연체를 지어내지 않게 명시한다.
     - 금액 숫자는 프롬프트에 넣지 않는다(슬롯으로만 전달).
   → from app import llm; llm.generate("cs-interest", messages)
6. 출력 검증(validate.is_valid): 아래 중 하나면 기본 문장으로 대체
   - 금액 형태(1,234 / 312500원 / 30만원)나 퍼센트 수치(%·퍼센트·프로) — 날짜(2026-10-25)·연체 일수(12일)는 통과
   - 마스킹 토큰([금액_1] 등) — 프론트가 치환하지 않아 화면에 노출된다
   - 사용할 수 있는 슬롯 목록에 없는 {{슬롯}}
   - 연체 상태이고 질문이 연체 상태를 묻는데(validate.required_slots: 연체된·연체 금액·밀린·미납 등) {{overdue_amount}}가 없음
     ("연체 가산금리는요?"·"연체이자가 뭐예요?"처럼 규정·용어를 묻는 질문은 요구하지 않는다 — 상담원 안내만 한 답이 대체되지 않게)
   기본 문장(prompt.fallback_text, <…>는 조회값): "{{loan_label}}의 다음 납부일은 <다음 납부일>이고, 납부 예정 이자는 {{interest_due}}입니다."
   + 연체가 있으면 " 현재 <연체 일수>일 연체 중이며 연체 금액은 {{overdue_amount}}입니다."
   + " 자세한 사항은 상담원에게 확인해 주세요."
7. AgentReply(text, slots, options=[])
```

## 테스트 (`backend/tests/interest/`, 모델 호출은 목으로 대체)
실행: `cd backend && pytest tests/interest` (`--import-mode=importlib`). 핵심 규칙을 깨는 입력을 재현해 고정한다.
- mock API(`test_mock_api.py`): `get_interest("C002")`·`get_interest("C003")`가 데모 값 표와 같고, `C001`·모르는 고객은 `[]`다. 금리 관련 키가 없다. `loan_id`·`product_type`은 계약 6 값(C002=L001 신용대출, C003=L002 주택담보대출)을 기대값으로 두어 확인하고, 대출문의 모듈은 import하지 않는다. 라우트 테스트는 선택이다.
- 프롬프트(`test_prompt.py`): messages 어디에도 `312500`·`312,500`·`625,000`이 없다. 연체 여부 줄이 조회값과 맞다.
- 출력 검증(`test_validate.py`): 날짜·연체 일수는 통과하고, 금액·금리·마스킹 토큰·허용 밖 슬롯·필수 슬롯 누락은 걸린다.
- 에이전트(`test_agent.py`, `base.py` 머지 후): `monkeypatch.setattr("app.llm.generate", 가짜_함수)`로 대체한다.
  - `C001`: `generate`가 호출되지 않고 고정 문장, `slots={}`가 나온다.
  - 목이 "적용 금리는 4.5%입니다", "이자는 312,500원입니다", "{{balance}}입니다", "[금액_1]입니다"를 돌려주면 기본 문장으로 바뀐다.
  - `C003`: "연체된 거 있어요?"에 목이 `{{overdue_amount}}` 없는 답을 돌려주면 기본 문장(연체 문구 포함)으로 바뀐다. "대출 금리가 몇 %예요?"에 상담원 안내만 한 답은 그대로 통과한다.
- 학습 데이터(`test_prepare.py`): 제외 규칙별로 원본에서 나온 문장을 재현한다.

## 학습 데이터 (`training/interest/prepare.py`, `synth.py`)
> 구성·검수·분할 방침은 `TRAINING_DATA_PLAN.md`, 형식·답변 기준은 `TRAINING_DATA.md`.

실행: `cd backend && python -m training.interest.prepare [--with-synth] [--include-unreviewed]` → `data/processed/interest/{candidates,train,val,test}.jsonl`, `stats.json` (gitignore). 검수 결과는 같은 폴더의 `reviews.json`에서 읽는다.

- 원천: `data/raw/03_interest/*.json` — 라벨링데이터 `02_labeled/VL_bank/06`에서 `qa_topic == "이자/연체금액"`인 파일만 복사한 폴더(QA 1,104건, 설명은 `_manifest.json`, `_`로 시작하는 파일은 읽지 않음). 원본 `02_labeled`는 공통 분할(팀원C)이 읽으므로 그대로 둔다. 원천데이터(`01_source`)는 상담 요약뿐이라 쓰지 않는다.
- 샘플 1건 = `{"source_id", "qa_id", "messages"}`. messages는 추론과 같은 형식이다(`prompt.build_messages`):
  `system` → `user: question` → `assistant: answer` → `user: follow_up_question + 이자 정보 줄 + 슬롯 줄` → **`assistant: output`(학습 대상은 이 턴만)**
- 이자 정보 줄은 `qa_id`로 시드를 고정한 가상 조회값이다. 정답과 모순되지 않게 맞춘다: 연체 여부는 output이 연체 금액·연체 상태를 말할 때만 "연체 중", 종류·납부 방법·상환 방식·금리 방식은 output이 말하는 값(신용대출·가상계좌·원리금균등·변동금리 등)이 있으면 그 값.
- output 정제 — 아래는 샘플 제외(사유별 건수는 `stats.json`):
  - 금리·이율 수치(%·퍼센트·프로)
  - 슬롯으로 바꿀 수 없는 금액: 금액 앞 절이 "연체 금액·미납 금액"이면 `{{overdue_amount}}`, "이자"면 `{{interest_due}}`로 바꾸고, 원금·잔액·합계·총액·연체 이자 등은 제외
  - 남은 비식별 기호(`●월 ●●일` 등), 아라비아 숫자(시각·기간 등 지어낸 값이 될 수 있음)
  - 은행명(하나은행 등), 서류 요건 키워드, 앱 메뉴
  - 이자 정보에 없는 상품명(청약·소상공인·마이너스 통장 등), 통화 요약체로 시작하는 답("고객님께서는 ~하고자 하셨습니다"), 처리 완료 주장(완료해 드렸·적용되었 등)
  - 고객에게 개인정보·인증정보를 요구하는 답(주민번호·비밀번호·생년월일·인증번호 등). 통화 상담원의 본인 확인 절차라 챗봇에는 맞지 않는다(원본 기준 61건)
  - 최종 output이 `validate.is_valid`를 통과하지 못함(INT-004). 필수 슬롯은 `required_slots(follow_up_question, 연체 여부)`
- input 정규화: `★★은행`→`은행`, 비식별 금액(`●●●원`)→`[금액_n]`, 그 밖의 비식별 기호→`○○`. 그 뒤 user 턴에 `masking.mask()` 적용.
- 분할: `data/processed/split.json`(팀원C)이 있으면 따르고, 없으면 `source_id` 해시 8:1:1. 마스킹: `app.masking`이 없으면 계약 4 토큰을 쓰는 임시 함수. 둘 다 머지되면 자동으로 공통 쪽을 쓴다.
- 합성 샘플(`synth.py`): 유형별 템플릿 18개로 400건. 모든 정답이 추론 검증을 통과하는지 `test_synth.py`가 확인한다. 검수한 템플릿 ID를 `REVIEWED`에 넣는다.
- 현재 결과(임시 분할·마스킹, 검수 전): AI Hub 1,105건 중 284건 후보(train 218 / val 25 / test 41), 합성 400건(train만).

## 확인 필요
- 시스템 프롬프트 위치: 지금은 `prompt.py`가 messages의 system으로 넣는다. 계약 5("영역별 Modelfile, 같은 GGUF에 SYSTEM만 다름")가 main에 반영되면 Modelfile SYSTEM으로 옮길지 정한다. 학습 데이터와 추론의 시스템 프롬프트는 같은 문자열이어야 한다.
- `cd backend && pytest tests/interest`가 `app`을 import하려면 backend를 경로에 넣는 pytest 설정(`pythonpath`)이 필요하다. 공통 설정이 main에 오기 전에는 `python -m pytest --import-mode=importlib tests/interest`로 실행한다.
- 출력 검증 방식: 대출문의(LN-004)는 허용 목록(준 날짜 외 숫자 금지)이다. 이 영역은 금지 목록이라 지어낸 시각·기간("밤 11시까지", "3영업일")을 통과시킨다. 허용 목록(다음 납부일 표기·연체 일수만 허용)으로 바꿀지 정한다.
- 학습 데이터 품질: AI Hub 후보 284건 중 슬롯 사용 4건, 연체 8건, "고객님께서"로 시작하는 요약체 28건이 남아 있다. 슬롯 사용·연체·거절은 합성 샘플로 보강한다(팀 합의 필요). 요약체는 검수 때 고치거나 반려한다.
