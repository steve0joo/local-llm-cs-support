# 아키텍처: 대출문의 에이전트

## 디렉토리 구조
```
backend/
├── app/agents/loan/
│   ├── __init__.py        # agent, mock_router export (계약 3)
│   ├── agent.py           # LoanAgent.handle()
│   ├── prompt.py          # 시스템 프롬프트, build_messages(), build_slots(), fallback_text()
│   ├── validate.py        # 출력 검증(LN-004) — 서류 키워드 목록·허용 슬롯 상수 포함
│   ├── mock_api.py        # mock_router + get_loans()
│   └── mock_data.json     # C001: 대출 없음, C002: L001 신용대출, C003: L002 주택담보대출
├── tests/loan/
├── training/loan/         # prepare.py, train.py, export.md
└── models/loan/Modelfile
```

## mock API
| 메서드 | 경로 | 응답 |
|--------|------|------|
| GET | `/mock/customers/{customer_id}/loans` | `[{loan_id, product_type, principal_remaining, maturity_date, extendable}]` |
- `product_type`에는 일반 명칭만 쓴다. 실제 상품명은 쓰지 않는다. 금리 필드는 두지 않는다.
- 대출이 없거나 모르는 `customer_id`는 404가 아니라 `[]`를 돌려준다.
- 금액은 정수(원), 날짜는 `YYYY-MM-DD` 문자열, `extendable`은 boolean으로 저장한다. 표시용 포맷(`12,000,000원`)은 에이전트가 슬롯을 만들 때 한다.

## mock 데이터 (`mock_data.json`)
| customer_id | loan_id | product_type | principal_remaining | maturity_date | extendable |
|-------------|---------|--------------|--------------------:|---------------|------------|
| `C001` | (없음, `[]`) | | | | |
| `C002` | `L001` | 신용대출 | 12000000 | 2027-03-31 | true |
| `C003` | `L002` | 주택담보대출 | 85000000 | 2035-06-30 | false |
- `loan_id`와 `product_type`은 이자/연체 mock과 같은 값이어야 한다(계약 6). 나머지 필드는 이 영역만 쓴다.
- `L002`는 연체 중인 대출이라 `extendable=false`로 둔다. 사유는 데이터에 두지 않는다(모델이 사유를 지어낼 근거를 없앤다).

## handle() 흐름
```
1. loans = get_loans(customer_id)
2. 대출 없음 → 고정 문장 "고객님 명의로 조회되는 대출이 없습니다." (모델 호출 없음)
3. 대상 대출: mock 고객은 대출이 최대 1건이다(계약 6). 여러 건 선택 되묻기는 만들지 않는다. 2건 이상이면 첫 번째를 쓴다.
4. slots 생성: loan_label = product_type, principal_remaining = "12,000,000원" 형태
5. messages = 시스템 프롬프트 + history + masked_text
            + "대출 정보: 종류=신용대출, 만기일=2027-03-31, 연장 가능=예"   (연장 불가면 "연장 가능=아니오(사유는 알 수 없음)")
            + "사용할 수 있는 슬롯: {{loan_label}}, {{principal_remaining}}"
   → llm.generate("cs-loan", messages)
   - 만기·연장·조회 중 무엇을 묻는지는 코드가 나누지 않는다. 슬롯이 항상 같으므로 모델이 질문에 맞춰 답한다.
   - 남은 원금 숫자는 프롬프트에 넣지 않는다(LN-001).
6. 출력 검증(LN-004) — 아래 중 하나라도 걸리면 기본 문장으로 대체
   a. 허용 날짜(프롬프트에 준 만기일의 `YYYY-MM-DD`·`YYYY년 M월 D일` 표기)를 제거한 뒤 아라비아 숫자가 남아 있음(금액·퍼센트·다른 날짜·기간 포함)
   b. 사용하도록 준 슬롯(`{{loan_label}}`, `{{principal_remaining}}`) 밖의 `{{...}}`가 있음
   c. 서류 요건 키워드가 있음(서류·증명서·등본·재직·소득 — 목록은 `validate.py` 상수)
   d. `extendable=false`인데 부정 표현(불가·않·어렵·없) 없이 "가능"이 있음
   기본 문장(코드가 조립, <…>는 조회값):
     "{{loan_label}}의 만기일은 <만기일>이고, 남은 원금은 {{principal_remaining}}입니다."
     + extendable=true  → " 연장 가능 대상으로 조회됩니다."
       extendable=false → " 현재 연장 가능으로 조회되지 않습니다."
     + " 연장 조건 등 자세한 사항은 상담원에게 확인해 주세요."
7. AgentReply(text, slots, options=[])
```

## 학습 데이터
- 원천: `split.json`의 train 중 `consulting_topic == "대출문의(만기/연장/조회 등)"` (가장 큰 주제 — 필요하면 샘플 수를 줄여 학습 시간을 맞춘다)
- 대화 구성·마스킹·정제 규칙은 잔액조회와 같다(`docs/agent-balance/ARCHITECTURE.md` 학습 데이터 절 참고)
- 정제 시 특히 `output`의 금리(%)·상품명·서류 목록 중 `input`에 없는 것은 제외한다

## 테스트 (`backend/tests/loan/`, 모델 호출은 목으로 대체)
핵심 규칙을 깨는 입력을 재현해 고정한다.
- 대출 없음(`C001`): `llm.generate`가 호출되지 않고 고정 문장이 나온다.
- 프롬프트 누출: `C002` 호출 시 `generate`에 넘어간 messages 어디에도 `12000000`·`12,000,000`이 없다.
- 검증 대체: 목이 각각 "금리는 연 3.5%입니다", "1,200만원입니다", "2027-04-01까지 연장됩니다", "재직증명서가 필요합니다", "{{balance}}입니다"를 돌려주면 기본 문장으로 바뀐다.
- 날짜 허용: 목이 "만기일은 2027-03-31입니다. {{principal_remaining}} 남았습니다."를 돌려주면 그대로 통과한다.
- 연장 불가(`C003`): 목이 "연장이 가능합니다"를 돌려주면 기본 문장(연장 가능으로 조회되지 않음)으로 바뀐다.
- mock API: `/mock/customers/C002/loans`가 위 표 값과 같고, `C001`은 `[]`다. `loan_id`·`product_type`이 이자/연체 mock 데이터와 일치한다.
