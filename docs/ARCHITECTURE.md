# 아키텍처 (공통)

> 영역 간 **계약**(디렉토리 소유권, API 스키마, 인터페이스)을 정의한다. 여기 적힌 계약을 바꾸려면 이 문서를 먼저 고치고 팀 합의 후 반영한다. 영역 내부 설계는 `docs/<영역>/ARCHITECTURE.md`에 적는다.

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
├── frontend/                      # Next.js 챗봇 UI — 나
│   └── src/{app,components,lib,types}
└── backend/
    ├── app/
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
    ├── tests/<영역>/              # pytest, 영역별 폴더
    ├── training/
    │   ├── common/                # 은행 데이터 필터 + source_id 기준 분할 — 팀원C
    │   └── {router,balance,loan,interest}/   # 영역별 전처리·학습 스크립트
    ├── models/<영역>/Modelfile    # Ollama Modelfile은 커밋, .gguf는 커밋 금지
    ├── data/                      # gitignore — AI Hub 원본·가공본
    └── logs/                      # gitignore — model_inputs.jsonl
```
각 담당은 자기 영역 폴더와 `backend/tests/<영역>/`, `backend/training/<영역>/`, `backend/models/<영역>/`만 수정한다.

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
| `loan` | 대출문의(만기/연장/조회 등) | 대출문의 에이전트 |
| `interest` | 이자/연체금액 | 이자/연체 에이전트 |
| `auto_transfer` | 자동이체조회 | 미지원 안내 |
| `transfer_error` | 중계요청/착오송금 | 미지원 안내 |
| `deposit` | 만기, 연장/해지, 수신 | 미지원 안내 |
| `limit` | 금융거래한도/비대면한도계좌 | 미지원 안내 |
| `rate_discount` | 부수거래금리감면 | 미지원 안내 |
| `fx` | 환전문의 | 미지원 안내 |

`router.classify(masked_text: str) -> RouteResult` — `RouteResult.topics: list[str]`(확신 높은 순, 0개 이상).

## 계약 3 — 에이전트 인터페이스 (`backend/app/agents/base.py`)
```python
@dataclass
class AgentRequest:
    session_id: str
    customer_id: str
    masked_text: str
    mask_map: dict[str, str]      # 마스킹 토큰 → 원본. Python 코드에서만 사용, 프롬프트 금지
    history: list[dict]           # 이전 턴 (마스킹본만)

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

## 계약 4 — 마스킹 토큰과 슬롯
- 마스킹 토큰(입력 → 모델): `[주민번호_1]`, `[카드번호_1]`, `[계좌번호_1]`, `[전화번호_1]`, `[주소_1]`, `[금액_1]`. 같은 종류가 여러 개면 번호가 증가한다.
- 슬롯(모델 → 화면): `{{snake_case}}`. 슬롯 이름은 각 에이전트 문서에 정의한다.
- 학습 데이터도 같은 `masking.mask()`로 치환한 뒤 학습한다. 학습 입력과 추론 입력의 분포를 맞추기 위해서다.

## 계약 5 — 모델 호출과 로그 (`backend/app/llm`)
- `generate(model: str, messages: list[dict], **options) -> str` — Ollama `/api/chat` 비스트리밍 호출.
- 호출할 때마다 `backend/logs/model_inputs.jsonl`에 `{ts, model, messages}`를 한 줄로 남긴다. PM은 인수 때 이 파일로 마스킹을 확인한다.
- Ollama 모델 이름: `cs-router`, `cs-balance`, `cs-loan`, `cs-interest`.

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

## 통합 순서
1. 팀원C가 `agents/base.py`, 세 에이전트의 스텁 패키지(고정 문구를 돌려줌), `llm`, `masking`, `/api/chat`을 먼저 main에 머지한다.
2. 각 에이전트 담당은 스텁을 실제 구현으로 교체한다. 프론트는 스텁 응답으로 먼저 개발한다.
3. 모델이 준비되기 전에는 각 영역이 `llm.generate`를 목(mock)으로 바꿔 테스트한다.
