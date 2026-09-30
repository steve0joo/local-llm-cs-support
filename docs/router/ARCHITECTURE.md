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
│   └── router/
│       ├── prepare.py          # 학습 데이터 생성 → data/processed/router/{train,val,test}.jsonl (RT-005)
│       ├── train.py            # QLoRA 학습 → training/router/outputs/<run>/adapter (gitignore)
│       ├── export.py           # 병합 → GGUF → models/router/{cs-router.gguf, Modelfile} → ollama create
│       └── outputs/            # gitignore
└── models/router/
    ├── Modelfile               # export.py가 생성. 커밋
    └── cs-router.gguf          # Q4_K_M 약 1.1GB. gitignore, Mac에는 복사
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

### 게이트웨이 구현 결정 (`app/gateway/`, `app/main.py`)
- 파일: `session.py`(`Session`, 모듈 dict `sessions`, `get_session()`; 되묻기 대기 질문은 `MaskResult`를 그대로 보관), `dispatch.py`(`AGENTS`, 안내 문구 상수, `dispatch(session_id, customer_id, message, choice) -> dict`), `api.py`(pydantic `ChatRequest`·`ChatResponse`·`ChatOption`, `POST /api/chat`), `main.py`(`create_app()`이 `/api/chat`과 세 패키지의 `mock_router`를 prefix 없이 등록).
- 안내 문구: 지원 주제 2개 이상 "어느 쪽을 먼저 도와드릴까요?", 주제 없음 "어떤 업무를 도와드릴까요?", 미지원 "해당 주제는 아직 지원하지 않습니다. 상담원 연결을 도와드릴까요?"
- 되묻기 선택지는 `topics.SUPPORTED` 순서, 라벨은 `topics.DISPLAY_NAMES`.
- `topic` 값: answer = 에이전트 코드, unsupported = 모델이 낸 첫 코드(인수 기준 1 판정 근거), clarify = null. `agent`는 answer에서만 채운다.
- `choice`가 지원 에이전트가 아니면 422가 아니라 unsupported 응답이다. pending이 없는 `choice`(계좌 선택 등)는 현재 메시지를 그대로 에이전트에 넘긴다.
- history에는 answer 턴만 쌓는다. clarify·unsupported 문장은 게이트웨이가 만든 것이라 모델 문맥이 아니다. 에이전트에는 이번 턴 이전까지의 history 복사본을 넘긴다.
- `dispatch()`는 dict를 돌려주고 스키마 클래스는 `api.py`에만 둔다. `classify`는 `router.classify()`로 불러 테스트가 `app.router.classify` 한 곳만 바꾼다.
- 모델이 없어도 서버는 뜬다: `classify()`가 Ollama 호출 실패를 키워드 폴백으로 처리하고, 에이전트는 스텁이 답한다.
- `choice` 없는 새 메시지가 오면 `session.pending`을 비운다. 되묻기 뒤 버튼 대신 타이핑한 경우 이전 되묻기는 무효이며, 그 뒤 계좌 선택 `choice`에 옛 질문이 딸려가지 않는다.
- 에이전트의 모델 호출 실패(`httpx.HTTPError`: Ollama 없음·모델 미등록·타임아웃)는 게이트웨이가 잡아 answer 타입으로 "지금은 답변을 드릴 수 없습니다. 상담원 연결을 도와드릴까요?"를 돌려준다(500 아님). 이 문장은 history에 넣지 않는다. 그 밖의 예외(코드 버그)는 그대로 올려 500이 되게 한다.

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

### 학습·배포 절차 (`training/router/`, Windows/WSL2 학습 노트북)
```bash
cd backend
python -m training.common.split                  # split.json (1회)
python -m training.router.prepare                # train 22,615 · val 2,497 · test 2,473 건 (2026-09-29)
python -m training.router.train                  # 1 epoch, 20~40분 → outputs/<시각>/adapter (스모크는 MAX_STEPS=20으로 바꿔서)
python -m training.router.export training/router/outputs/<시각>/adapter   # 병합 → GGUF → Modelfile → ollama create
```
- 설정값은 `train.py` 상단 상수(`BASE_MODEL`, `EPOCHS`, `MAX_STEPS`, `MAX_LENGTH`)와 `SFTConfig`에 있다. 스모크는 `MAX_STEPS = 20`으로 바꿔 돌린다.
- `export.py`는 llama.cpp를 `LLAMA_CPP_DIR`(기본 `~/qlora_ft_ex/llama.cpp`)에서 찾는다. 변환에는 `sentencepiece`·`protobuf`가 필요하다(`training/requirements.txt`).
- 등록 확인은 서버를 띄워 `/api/chat`에 키워드 없는 문장(예: "환전하고 싶은데요")을 보내 `topic`에 코드가 실리는지 본다. 서버는 이 모델이 등록되는 순간 키워드 폴백에서 모델 분류로 바뀐다.

## 제공하는 인터페이스
- `app.masking.mask(text) -> MaskResult` — 학습 스크립트도 이 함수를 import한다
- `app.llm.generate(model, messages, **options) -> str` — 요청에 항상 `think: false`를 넣는다(RT-006)
- `app.agents.base` — 계약 3
- `data/processed/split.json` — `{source_id: "train" | "val" | "test"}`
