# 아키텍처 (공통)

> 영역 간 **계약**(디렉토리 소유권, API 스키마, 인터페이스)을 정의한다. 여기 적힌 계약을 바꾸려면 이 문서를 먼저 고치고 팀 합의 후 반영한다. 영역 내부 설계는 `docs/<영역>/ARCHITECTURE.md`에 적는다.
>
> "팀 합의 대기" 표기는 팀 합의 전의 임시 결정이다. 합의 전에도 그대로 따르고, 합의에서 바뀌면 이 문서를 먼저 고친다.

## 디렉토리 구조
```
.
├── CLAUDE.md
├── docs/                          # 공통 PRD·ARCHITECTURE·ADR
│   ├── frontend/                  # 나
│   ├── agent-balance/             # 나
│   ├── agent-loan/                # 팀원A
│   ├── agent-interest/            # 팀원B
│   └── router/                    # 팀원C
├── frontend/                      # Next.js 챗봇 UI — 나 (package.json·vitest 설정 등 스캐폴드 포함)
│   └── src/{app,components,lib,types}
└── backend/
    ├── pyproject.toml             # pytest 설정(pythonpath = ["."], --import-mode=importlib) — 팀원C
    ├── app/
    │   ├── __init__.py            # 빈 파일(agents/__init__.py도) — 팀원C
    │   ├── main.py                # FastAPI 진입점, 라우트 등록 — 팀원C
    │   ├── gateway/               # POST /api/chat, 세션, 분기 — 팀원C
    │   ├── masking/               # 개인정보 마스킹 — 팀원C
    │   ├── llm/                   # Ollama 호출 + 모델 입력 로그 — 팀원C
    │   ├── router/                # 주제 분류 — 팀원C
    │   └── agents/
    │       ├── base.py            # 에이전트 공통 인터페이스 — 팀원C (변경 시 합의)
    │       ├── balance/           # 잔액조회 에이전트 + mock API·데이터 — 나
    │       ├── loan/              # 대출문의 에이전트 + mock API·데이터 — 팀원A
    │       └── interest/          # 이자/연체 에이전트 + mock API·데이터 — 팀원B
    ├── requirements.txt           # 런타임 의존성(fastapi·uvicorn·pytest 등) — 팀원C, 추가는 PR로
    ├── tests/                     # pytest — gateway·masking·llm·router(팀원C), balance, loan, interest
    ├── training/
    │   ├── requirements.txt       # 학습 의존성(torch·transformers·peft·trl 등) — Windows 학습 장비 전용, Mac 데모에는 설치하지 않음
    │   ├── common/                # 은행 데이터 필터 + source_id 기준 분할 — 팀원C
    │   └── {router,balance,loan,interest}/   # 영역별 전처리·학습 스크립트
    ├── models/{router,balance,loan,interest}/Modelfile   # Ollama Modelfile은 커밋, .gguf는 커밋 금지
    ├── data/                      # gitignore — AI Hub 원본·가공본
    └── logs/                      # gitignore — model_inputs.jsonl
```
각 담당은 자기 영역 폴더와 `backend/tests/<폴더>/`, `backend/training/<폴더>/`, `backend/models/<폴더>/`만 수정한다. `<폴더>`는 `router`·`balance`·`loan`·`interest`이고, 팀원C는 `tests/{gateway,masking,llm}/`도 맡는다. 예외로 통합 순서 1단계의 에이전트 스텁(`app/agents/<영역>/__init__.py`)은 팀원C가 넣는다.

## 패턴
- 백엔드는 **FastAPI 단일 프로세스**다. 라우터·에이전트는 별도 서비스가 아니라 같은 프로세스 안의 Python 모듈이다.
- 모델은 **Ollama**가 별도 프로세스로 서빙한다. 모든 모델 호출은 `app/llm`의 `generate()` 하나를 거친다.
- mock API는 각 에이전트 모듈 안의 FastAPI 라우트(`/mock/...`)로 제공한다. 에이전트는 같은 모듈의 조회 함수를 직접 호출한다. 같은 프로세스라 HTTP 왕복이 필요 없고, 라우트는 데모·인수 때 데이터를 확인하는 용도다.

## 데이터 흐름
```
[고객] → frontend (챗봇 UI)
   → POST /api/chat {session_id, customer_id, message, choice?}
   → gateway
       1. masking.mask(message) → masked_text + mask_map (원본은 mask_map에만)
       2. choice가 없으면 router.classify(masked_text) → topics
          - 지원 주제 2개 이상  → type=clarify ("어느 쪽을 먼저 도와드릴까요?" + 선택지)
          - 지원 주제 1개       → 해당 에이전트
          - 미지원 주제만       → type=unsupported (안내 + 상담원 연결 안내)
       3. agent.handle(AgentRequest)
          - mock 조회 함수로 고객 데이터 조회 (customer_id 기준)
          - llm.generate(프롬프트: 마스킹된 텍스트 + 슬롯 이름만) → "현재 잔액은 {{balance}}입니다"
          - AgentReply {text, slots: {"balance": "1,234,567원"}}
   ← {type, agent, topic, text, slots, options}
frontend: text의 {{balance}}를 slots 값으로 치환해 화면에 표시
```
모델에는 마스킹된 텍스트와 슬롯 **이름**만 들어간다. 실제 금액은 `slots`로만 흐르고 화면에서 치환된다.

## 계약 1 — 채팅 API (frontend ↔ gateway)
`POST /api/chat`
```jsonc
// Request
{
  "session_id": "string",        // 프론트가 생성(uuid)해 대화 동안 유지
  "customer_id": "C001",         // 데모 고객 선택값
  "message": "string",
  "choice": "balance"            // 선택지 클릭 시에만. 값이 있으면 라우팅을 건너뛰고 해당 에이전트로 보냄
}
// Response
{
  "type": "answer" | "clarify" | "unsupported",
  "agent": "balance" | "loan" | "interest" | null,
  "topic": "<주제 코드>" | null,
  "text": "현재 잔액은 {{balance}}입니다.",    // {{슬롯}} 포함 가능
  "slots": { "balance": "1,234,567원" },       // 표시용으로 포맷이 끝난 문자열
  "options": [ { "label": "잔액조회", "choice": "balance" } ]  // 없으면 []
}
```
- 선택지를 클릭하면 프론트는 `{message: option.label, choice: option.choice}`를 보낸다.
- gateway 단계에서 되물은 경우(type=clarify), gateway가 세션에 보관한 원래 질문(마스킹본 + mask_map)을 선택된 에이전트에 넘긴다.
- 치환되지 않은 `{{...}}`가 남으면 프론트는 그대로 두지 않고 "확인할 수 없습니다"로 표시한다.

## 계약 2 — 주제 코드 (router 출력)
| 코드 | 데이터셋 `consulting_topic` | 처리 |
|------|---------------------------|------|
| `balance` | 거래내역/잔액조회 | 잔액조회 에이전트 |
| `loan` | 대출문의(만기/연장/조회등) | 대출문의 에이전트 |
| `interest` | 이자/연체금액 | 이자/연체 에이전트 |
| `auto_transfer` | 자동이체조회 | 미지원 안내 |
| `transfer_error` | 중계요청/착오송금 | 미지원 안내 |
| `deposit` | 만기,연장/해지,수신 | 미지원 안내 |
| `limit` | 금융거래한도/비대면한도계좌 | 미지원 안내 |
| `rate_discount` | 부수거래금리감면 | 미지원 안내 |
| `fx` | 환전문의 | 미지원 안내 |

라벨 문자열은 데이터셋 원문과 글자 단위로 같다(`조회등`·`만기,연장/해지,수신`에 공백 없음, 2026-09-28 확인). 코드에서는 `backend/app/router/topics.py`의 `TOPIC_LABELS`를 import하고 문자열을 다시 적지 않는다.

`router.classify(masked_text: str) -> RouteResult` — `RouteResult.topics: list[str]`(확신 높은 순, 0개 이상). 모델은 주제 1개를 출력하고, 키워드 규칙이 지원 주제 2개 이상을 감지하면 그 주제들을 돌려준다(`docs/router/ADR.md` RT-002).

## 계약 3 — 에이전트 인터페이스 (`backend/app/agents/base.py`)
```python
@dataclass
class AgentRequest:
    session_id: str
    customer_id: str
    masked_text: str
    mask_map: dict[str, str]      # 마스킹 토큰 → 원본. Python 코드에서만 사용, 프롬프트 금지
    history: list[dict]           # 이전 턴 [{"role": "user" | "assistant", "content": str}] — Ollama messages 형식 그대로

@dataclass
class AgentReply:
    text: str                     # {{슬롯}} 포함 가능
    slots: dict[str, str]         # 표시용 값
    options: list[dict]           # [{"label": ..., "choice": ...}] — 계좌 선택 등

class Agent(Protocol):
    name: str                     # "balance" | "loan" | "interest"
    def handle(self, req: AgentRequest) -> AgentReply: ...
```
각 에이전트 패키지(`app/agents/<영역>/__init__.py`)는 `agent: Agent`와 `mock_router: APIRouter`를 export한다. `main.py`와 gateway는 이 두 이름만 import한다.

`history`는 gateway가 턴마다 채운다. user에는 그 턴에 에이전트로 넘긴 `masked_text`(되묻기 선택이면 보관해 둔 원래 질문), assistant에는 `reply.text`(`{{슬롯}}` 그대로)를 넣는다. 원본 값이나 슬롯 값은 넣지 않는다. 에이전트가 선택지 응답(예: 계좌 라벨)을 받으면 history의 직전 user 메시지로 원래 질문을 알 수 있다.

## 계약 4 — 마스킹 토큰과 슬롯
- 마스킹 토큰(입력 → 모델): `[주민번호_1]`, `[카드번호_1]`, `[계좌번호_1]`, `[전화번호_1]`, `[주소_1]`, `[금액_1]`. 같은 종류가 여러 개면 번호가 증가한다.
- 슬롯(모델 → 화면): `{{snake_case}}`. 슬롯 이름은 각 에이전트 문서에 정의한다.
- 학습 데이터도 같은 `masking.mask()`로 치환한 뒤 학습한다. 학습 입력과 추론 입력의 분포를 맞추기 위해서다.

## 계약 5 — 모델 호출과 로그 (`backend/app/llm`)
- `generate(model: str, messages: list[dict], **options) -> str` — Ollama `/api/chat` 비스트리밍 호출.
- 호출할 때마다 `backend/logs/model_inputs.jsonl`에 `{ts, model, messages}`를 한 줄로 남긴다. PM은 인수 때 이 파일로 마스킹을 확인한다.
- Ollama 모델 이름: `cs-router`, `cs-balance`, `cs-loan`, `cs-interest`.
- (팀 합의 대기) 10초 초과로 4개 영역을 모델 1개로 합치더라도(ADR-005) Ollama 모델 이름 `cs-<영역>`(위 4개 이름)과 영역별 Modelfile(같은 GGUF를 `FROM`, `SYSTEM`만 다름)을 유지한다. 호출하는 코드는 모델 이름을 바꾸지 않는다.

## 계약 6 — mock 고객 데이터 공통 ID
모든 mock 데이터는 아래 데모 고객을 기준으로 만든다. 데이터 안의 상품명은 "신용대출", "주택담보대출"처럼 일반 명칭만 쓴다(실제 상품명 금지).
| customer_id | 설명 |
|-------------|------|
| `C001` | 입출금 계좌 1개, 대출 없음 |
| `C002` | 입출금 계좌 2개(계좌 선택 시나리오), 신용대출 1건(`L001`) |
| `C003` | 입출금 계좌 1개, 주택담보대출 1건(`L002`, 연체 있음) |

대출 ID(`L001`, `L002`)는 대출문의·이자/연체 mock이 같은 값을 쓴다.

## 상태 관리
- frontend: 대화 목록·입력값·선택 고객은 React `useState`로 관리한다. 전역 상태 라이브러리는 쓰지 않는다.
- backend: 세션(대화 이력 마스킹본, 되묻기 대기 중인 질문)은 gateway의 메모리 dict에 둔다. 재시작하면 사라져도 된다(MVP).

## 학습 파이프라인
```
AI Hub 원본(backend/data/raw)
  → training/common: 은행 필터 + source_id 기준 train/val/test 분할 (팀원C, 1회)
  → training/<영역>: 영역 데이터 추출 → masking.mask() 적용 → 정제 → QLoRA 학습 (공용 Windows 노트북)
  → LoRA 병합 → GGUF 변환(Q4_K_M) → models/<영역>/Modelfile → ollama create cs-<영역>
  → 같은 .gguf를 Mac에 복사해 ollama create (Mac에서도 로컬 추론)
```
원본 데이터는 아직 받지 않았다. 문서에 적은 폴더 구조와 필드명(`consulting_topic`, `qa_data[].input.question` 등)은 가정이다. 팀원C가 `training/common`을 시작할 때 실제 파일로 확인하고, 다르면 이 문서와 영역 문서를 고친다.

## 코드·테스트 규칙 (공통, 팀 합의 대기)
- 패키지의 공개 이름은 `__init__.py`에서 export한다: `from app.masking import mask`, `from app.llm import generate`, `from app.router import classify`, `from app.agents.<영역> import agent, mock_router`(계약 3). `agent`는 import하면 바로 쓸 수 있는 모듈 수준 인스턴스다. mock 조회 함수는 `app.agents.<영역>.mock_api`에서 import한다.
- 모델을 부르는 코드는 `from app import llm` 뒤 `llm.generate(...)`로 호출한다. 테스트는 `monkeypatch.setattr("app.llm.generate", 가짜_함수)` 한 곳만 바꾼다.
- mock 조회 함수(`get_accounts`, `get_loans`, `get_interest` 등)는 동기 함수이고 `list[dict]`를 돌려준다. dict의 키는 각 영역 문서의 mock API 표와 정확히 같고(추가 필드 없음), 값의 타입은 금액·일수는 정수(원·일), 여부는 bool, 그 밖의 필드(ID·번호·이름·종류·날짜)는 문자열이다. 결과는 mock 데이터 표의 행 순서를 따른다. 데모 고객이 아니거나 항목이 없으면 `[]`를 돌려준다. 데이터는 같은 폴더의 `mock_data.json`에서 읽고, mock 라우트는 함수 결과를 그대로 돌려준다.
- 테스트 파일 이름: backend는 `backend/tests/<폴더>/test_<구현 모듈 파일명>.py`(예: `app/masking/mask.py` → `tests/masking/test_mask.py`), frontend는 대상 파일 옆 `<이름>.test.ts(x)`다. TDD 훅(`.claude/hooks/tdd-guard.sh`)이 이 이름으로 테스트가 있는지 확인하고, 없으면 구현 파일 작성을 막는다. 폴더가 달라도 파일 이름이 같을 수 있어서 pytest는 `--import-mode=importlib`로 돌리고, 테스트 폴더(`tests/<폴더>/`)에는 `__init__.py`를 두지 않는다.
- 테스트 실행: `cd backend && pytest tests/<폴더>`, `cd frontend && npm run test`.
- 목은 pytest `monkeypatch`로 만든다. 조회·로직은 함수를 직접 테스트하고, HTTP 라우트 테스트(FastAPI `TestClient`)는 필요할 때만 쓴다.
- 첫 실패 테스트는 파일 하나로 시작하고 케이스 수는 자유다. 테스트 코드를 어떻게 쓸지(함수 이름·설명 문구의 언어, 주석, 예시 입력 문장, 테스트용 값, 테스트를 나누는 구조, assert·matcher 선택, 타입까지 import해 확인할지)는 작성자가 정한다.
- 각 영역의 첫 테스트는 `docs/<영역>/ARCHITECTURE.md`의 "TDD 착수점"을 따른다.

## 통합 순서
1. 팀원C가 스캐폴드(`backend/pyproject.toml`, `app/__init__.py`, `app/agents/__init__.py`), `agents/base.py`, 세 에이전트의 스텁 패키지, `llm`, `masking`, `/api/chat`을 먼저 main에 머지한다. 스텁 패키지는 `app/agents/<영역>/__init__.py` 하나이고, 계약 3의 `agent`(`handle()`이 고정 문구 "준비 중인 기능입니다."를 돌려줌)와 빈 `mock_router`만 담는다. `mock_api.py`·`agent.py` 등 나머지는 각 담당이 만든다. 스텁이 오기 전에는 각 담당이 자기 패키지의 `__init__.py`를 빈 파일로 두고 mock 조회 함수부터 만든다.
2. 스텁이 main에 머지되면 각 feat 브랜치는 main을 병합한 뒤 스텁을 실제 구현으로 교체한다. 프론트는 스텁 응답으로 먼저 개발한다.
3. 모델이 준비되기 전에는 각 영역이 `llm.generate`를 목(mock)으로 바꿔 테스트한다.

### 드라이런 판정 규칙 (팀 합의 대기)
드라이런은 사전 맥락 없는 새 에이전트가 루트 `docs/`, `docs/<영역>/`의 모든 문서, `CLAUDE.md`만 읽고 그 영역의 첫 실패 테스트를 작성해 보는 점검이다. 에이전트는 문서로 답할 수 없어 추측한 지점을 목록으로 남긴다.
- 통과로 세는 질문(면제):
  - `docs/PRD.md` '확인 필요'의 미결 4건을 가리키는 질문
  - 통합 순서 1단계 전이라 아직 없는 계약 3 스텁(`backend/app/agents/base.py`) 때문에 생긴 질문
  - 스캐폴드·설정 파일이 아직 없다(어떻게 초기화하나)는 질문
- 그 외 질문(테스트 위치, 무엇을 테스트할지, 계약 해석 등)이 1건이라도 있으면 불합격이다. 불합격한 영역은 그 영역 docs만 보강하고 그 영역만 다시 돌린다.
- 스텁이 아직 없을 때는 계약 3 스펙대로 작성한 import 실패 red 테스트를 첫 실패 테스트로 인정한다.
- 스캐폴드(`backend/pyproject.toml`, `app/__init__.py`, frontend `package.json` 등)가 아직 없어서 나는 import·실행 실패도 red로 인정한다. 이때 실행은 생략하거나 pyproject에 적을 설정을 명령줄로 넘겨 확인한다.

### 다음 라운드 체크리스트
- [ ] 팀원C 스텁(통합 순서 1단계) 병합 후 에이전트 3개 영역(balance·loan·interest) 재드라이런
- [ ] 실제 팀원 착수 검증
