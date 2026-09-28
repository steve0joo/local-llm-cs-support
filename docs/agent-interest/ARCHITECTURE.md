# 아키텍처: 이자/연체 에이전트

## 디렉토리 구조
```
backend/
├── app/agents/interest/
│   ├── __init__.py        # agent, mock_router export (계약 3)
│   ├── agent.py           # InterestAgent.handle()
│   ├── prompt.py
│   ├── mock_api.py        # mock_router + get_interest()
│   └── mock_data.json     # C002: L001(정상), C003: L002(연체)
├── tests/interest/
├── training/interest/     # prepare.py, train.py, export.md
└── models/interest/Modelfile
```

## mock API
| 메서드 | 경로 | 응답 |
|--------|------|------|
| GET | `/mock/customers/{customer_id}/interest` | `[{loan_id, product_type, next_due_date, interest_due, overdue_amount, overdue_days}]` |
- 금리·이율 필드는 두지 않는다. 금액은 정수(원)로 저장한다.

## handle() 흐름
```
1. items = get_interest(customer_id)
2. 없음 → 고정 문장 "고객님 명의로 조회되는 대출 이자 내역이 없습니다." (모델 호출 없음)
3. 대상 대출 결정: 1건이면 그 대출, 여러 건이면 options(choice: "interest")로 되묻기
4. slots 생성 (loan_label, interest_due, 연체가 있으면 overdue_amount)
5. messages = 시스템 프롬프트 + history + masked_text
            + "이자 정보: 종류=주택담보대출, 다음 납부일=2026-10-25, 연체 일수=12"
            + "사용할 수 있는 슬롯: {{loan_label}}, {{interest_due}}, {{overdue_amount}}"
   → llm.generate("cs-interest", messages)
6. 출력 검증: 금액 형태의 숫자나 퍼센트(%) 수치가 있거나, 연체 상태인데 {{overdue_amount}}가 없으면 기본 문장으로 대체
7. AgentReply(text, slots, options)
```

## 학습 데이터
- 원천: `split.json`의 train 중 `consulting_topic == "이자/연체금액"`
- 대화 구성·마스킹·정제 규칙은 잔액조회와 같다(`docs/agent-balance/ARCHITECTURE.md` 학습 데이터 절 참고)
- 정제 시 특히 `output`의 금리·연체 이율(%) 수치 중 `input`에 없는 것은 제외한다
