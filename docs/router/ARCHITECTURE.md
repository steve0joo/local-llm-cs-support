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
│   │   ├── topics.py           # 주제 표: 코드↔라벨 원문, 지원 주제, 되묻기 표시명, 키워드, 시스템 프롬프트
│   │   └── classify.py         # classify(masked_text) -> RouteResult(topics)
│   └── agents/
│       ├── base.py             # AgentRequest, AgentReply, Agent (계약 3)
│       └── {balance,loan,interest}/__init__.py   # 스텁 → 각 담당이 교체
├── tests/{gateway,masking,llm,router}/
├── training/
│   ├── common/                 # 은행 필터 + source_id 분할 → data/processed/split.json
│   └── router/                 # 라우터 학습 데이터 생성 + QLoRA 학습
└── models/router/Modelfile
```

## TDD 착수점
- 첫 테스트: `tests/masking/test_mask.py` — `docs/router/PRD.md` 인수 기준의 마스킹 고정 시나리오를 `mask()`에 넣어 `masked_text`와 `mask_map`을 확인한다. 마스킹은 아무 모듈에도 의존하지 않고, 게이트웨이와 모든 학습 스크립트가 쓴다.
- 이후 순서: masking(나머지 종류) → llm(`generate` 호출·로그 기록, Ollama HTTP는 목) → router(`classify`, RT-002 사례) → `agents/base.py`·스텁 → gateway.

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
 5. session.history에 {"role": "user", "content": 에이전트에 넘긴 masked_text}, {"role": "assistant", "content": reply.text} 추가 (계약 3) → 응답 반환
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
- 전화번호는 `01`로 시작하는 번호(`010-1234-5678`, `01012345678`)만이다. 그 밖의 하이픈으로 이은 숫자열(예: `110-1234-5678`)은 계좌번호다.
- 번호는 종류별로 1부터 센다. `mask()`는 상태가 없는 함수라 호출마다 1부터 다시 센다. `mask_map`은 그 호출 결과에만 유효하다(되묻기 대기 질문은 `masked_text`와 `mask_map`을 함께 보관한다).
- 토큰 밖의 글자(공백·조사 포함)는 바꾸지 않는다.
- 표의 예시 입력과 토큰은 테스트 기대값으로 써도 된다.

### `mask()` 인터페이스
- `mask(text: str) -> MaskResult`. `MaskResult`는 `@dataclass`로 `masked_text: str`, `mask_map: dict[str, str]` 필드를 가진다. `app/masking/__init__.py`가 `mask`와 `MaskResult`를 export한다.
- `mask_map` 키는 대괄호를 포함한 토큰 문자열(`"[계좌번호_1]"`), 값은 원본 문자열이다. 마스킹한 항목만 들어가고, 없으면 `{}`다.

## 라우터 모델
- 입력: 마스킹된 고객 문장. 출력: 주제 코드(계약 2) 하나.
- 학습 데이터: `training/common` 분할의 train에서 9개 주제 전부. 고객 발화는 `qa_data[].input.question`, 라벨은 `consulting_topic`이다. 필드명은 2026-09-28 실제 데이터로 확인했다. 라벨 필터·`●` 금액 정규화·주제별 상한 샘플링(대출문의·이자/연체가 약 52%)은 RT-005.

### `classify()` 처리 순서 (`app/router/classify.py`)
```
1. 키워드 규칙(RT-002)으로 지원 주제를 센다
     2개 이상 → 모델을 부르지 않고 그 주제들을 topics로 (되묻기)
2. llm.generate("cs-router", [system, user], temperature=0)
     system = topics.SYSTEM_PROMPT, user = 마스킹 문장 그대로
     호출 실패(Ollama 없음·모델 없음·타임아웃) → 1에서 센 지원 주제 0~1개로 폴백
3. 출력을 파싱한다: 공백·따옴표·대소문자만 정리하고 계약 2 코드와 정확히 일치할 때만 채택
     없는 값 → 빈 topics
```
- 주제에 관한 표는 전부 `app/router/topics.py`에 둔다: 코드↔라벨 원문(`TOPIC_LABELS`), 지원 주제(`SUPPORTED`), 되묻기 표시명(`DISPLAY_NAMES`), 키워드(`KEYWORDS`), 시스템 프롬프트(`SYSTEM_PROMPT`). 게이트웨이와 학습 스크립트(`training/router/prepare.py`)가 여기서 import한다.
- `SYSTEM_PROMPT`는 학습 데이터와 추론이 글자 단위로 같아야 한다. 프롬프트 문구를 바꾸면 라우터를 다시 학습한다.

## 제공하는 인터페이스
- `app.masking.mask(text) -> MaskResult` — 학습 스크립트도 이 함수를 import한다
- `app.llm.generate(model, messages, **options) -> str` — 요청에 항상 `think: false`를 넣는다(RT-006)
- `app.agents.base` — 계약 3
- `data/processed/split.json` — `{source_id: "train" | "val" | "test"}`
