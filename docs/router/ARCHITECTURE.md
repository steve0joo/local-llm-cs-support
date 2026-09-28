# 아키텍처: 라우터 + 게이트웨이

## 디렉토리 구조
```
backend/
├── app/
│   ├── main.py                 # FastAPI 앱, /api/chat + 세 에이전트 mock_router 등록
│   ├── gateway/
│   │   ├── api.py              # POST /api/chat (계약 1)
│   │   ├── session.py          # 메모리 세션 dict
│   │   └── dispatch.py         # topics → answer / clarify / unsupported 분기
│   ├── masking/
│   │   └── mask.py             # mask(text) -> MaskResult(masked_text, mask_map)
│   ├── llm/
│   │   └── client.py           # generate(model, messages) + model_inputs.jsonl 기록
│   ├── router/
│   │   └── classify.py         # classify(masked_text) -> RouteResult(topics)
│   └── agents/
│       ├── base.py             # AgentRequest, AgentReply, Agent (계약 3)
│       └── {balance,loan,interest}/__init__.py   # 스텁 → 각 담당이 교체
├── tests/{gateway,masking,router}/
├── training/
│   ├── common/                 # 은행 필터 + source_id 분할 → data/processed/split.json
│   └── router/                 # 라우터 학습 데이터 생성 + QLoRA 학습
└── models/router/Modelfile
```

## 게이트웨이 처리 순서
```
POST /api/chat
 1. session = sessions[session_id] (없으면 생성)
 2. mask(message) → masked_text, mask_map
 3. choice 있음 → target = choice
       session.pending이 있으면 pending의 masked_text·mask_map을 사용하고 pending을 비운다
    choice 없음 → topics = classify(masked_text)
       supported = [t for t in topics if t in {"balance","loan","interest"}]
       len(set(supported)) >= 2 → session.pending 저장, type=clarify, options=[{label, choice}...]
       len(supported) == 1      → target = supported[0]
       topics 있음, supported 없음 → type=unsupported
       topics 없음             → type=clarify, options=세 지원 주제
 4. reply = agents[target].handle(AgentRequest(...)) → type=answer
 5. session.history에 (masked_text, reply.text) 추가 → 응답 반환
```

## 마스킹 규칙 (초안 — 테스트로 확정)
| 종류 | 토큰 | 예시 입력 |
|------|------|----------|
| 주민번호 | `[주민번호_n]` | 900101-1234567 |
| 카드번호 | `[카드번호_n]` | 1234-5678-9012-3456 |
| 계좌번호 | `[계좌번호_n]` | 110-1234-5678 |
| 전화번호 | `[전화번호_n]` | 010-1234-5678 |
| 주소 | `[주소_n]` | 서울시 ○○구 ○○로 12 |
| 금액 | `[금액_n]` | 1,234,567원 / 50만원 |
- 적용 순서: 주민번호 → 카드번호 → 전화번호 → 계좌번호 → 금액 → 주소. 긴 패턴부터 적용해 서로 겹치지 않게 한다.
- 같은 원본 값은 같은 토큰으로 바꾼다.

## 라우터 모델
- 입력: 마스킹된 고객 문장. 출력: 주제 코드(계약 2) 문자열.
- 학습 데이터: `training/common` 분할의 train에서 9개 주제 전부. 고객 발화는 `qa_data[].input.question`(없으면 상담 원문 첫 고객 발화)을 쓰고, 라벨은 `consulting_topic`이다.
- 클래스 불균형(대출문의·이자/연체가 약 52%)은 주제별 상한 샘플링으로 맞춘다.
- `classify()`는 Ollama 출력을 파싱한다. 계약 2에 없는 값이면 빈 topics를 돌려준다.

## 제공하는 인터페이스
- `app.masking.mask(text) -> MaskResult` — 학습 스크립트도 이 함수를 import한다
- `app.llm.generate(model, messages, **options) -> str`
- `app.agents.base` — 계약 3
- `data/processed/split.json` — `{source_id: "train" | "val" | "test"}`
