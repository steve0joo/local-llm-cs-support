# 아키텍처: 대출문의 에이전트

## 디렉토리 구조
```
backend/
├── app/agents/loan/
│   ├── __init__.py        # agent, mock_router export (계약 3)
│   ├── agent.py           # LoanAgent.handle()
│   ├── prompt.py
│   ├── mock_api.py        # mock_router + get_loans()
│   └── mock_data.json     # C002: L001 신용대출, C003: L002 주택담보대출
├── tests/loan/
├── training/loan/         # prepare.py, train.py, export.md
└── models/loan/Modelfile
```

## mock API
| 메서드 | 경로 | 응답 |
|--------|------|------|
| GET | `/mock/customers/{customer_id}/loans` | `[{loan_id, product_type, principal_remaining, maturity_date, extendable}]` |
- `product_type`에는 일반 명칭만 쓴다. 실제 상품명은 쓰지 않는다. 금리 필드는 두지 않는다.

## handle() 흐름
```
1. loans = get_loans(customer_id)
2. 대출 없음 → 고정 문장 "고객님 명의로 조회되는 대출이 없습니다." (모델 호출 없음)
3. 대상 대출: mock 고객은 대출이 최대 1건이다(계약 6). 여러 건 선택 되묻기는 만들지 않는다
4. slots 생성 (loan_label, principal_remaining)
5. messages = 시스템 프롬프트 + history + masked_text
            + "대출 정보: 종류=신용대출, 만기일=2027-03-31, 연장 가능=예"
            + "사용할 수 있는 슬롯: {{loan_label}}, {{principal_remaining}}"
   → llm.generate("cs-loan", messages)
6. 출력 검증: 금액 형태의 숫자나 퍼센트(%) 수치가 있으면 기본 문장으로 대체
   기본 문장(코드가 조립, <…>는 조회값): "{{loan_label}}의 만기일은 <만기일>이고, 남은 원금은 {{principal_remaining}}입니다. 연장 조건 등 자세한 사항은 상담원에게 확인해 주세요."
7. AgentReply(text, slots, options=[])
```

## 학습 데이터
- 원천: `split.json`의 train 중 `consulting_topic == "대출문의(만기/연장/조회 등)"` (가장 큰 주제 — 필요하면 샘플 수를 줄여 학습 시간을 맞춘다)
- 대화 구성·마스킹·정제 규칙은 잔액조회와 같다(`docs/agent-balance/ARCHITECTURE.md` 학습 데이터 절 참고)
- 정제 시 특히 `output`의 금리(%)·상품명·서류 목록 중 `input`에 없는 것은 제외한다
