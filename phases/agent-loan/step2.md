# Step 2: agent-handle

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/ARCHITECTURE.md` (계약 3 에이전트 인터페이스, 계약 5 모델 호출, 통합 순서)
- `/docs/ADR.md`
- `/docs/agent-loan/ARCHITECTURE.md` (handle() 흐름, 테스트 절)
- `/docs/agent-loan/ADR.md`
- `/backend/app/agents/base.py` (**팀원C 소유** — `AgentRequest`, `AgentReply`, `Agent`의 실제 필드·시그니처를 읽고 그대로 따른다)
- `/backend/app/llm/` (`generate(model, messages, **options) -> str`의 실제 시그니처)
- `/backend/app/agents/loan/` 전체 (step 0·1 산출물: `mock_api.py`, `prompt.py`, `validate.py`)

## 사전 점검 (가장 먼저)

`backend/app/agents/base.py`와 `backend/app/llm/` 중 하나라도 없으면 아무것도 만들지 말고 즉시 `blocked`로 표시한다.
`blocked_reason`: "팀원C의 agents/base.py·llm 스텁이 main에 머지되어야 함(공통 ARCHITECTURE 통합 순서 1단계). main을 이 브랜치에 병합한 뒤 pending으로 되돌려 재실행".
`base.py`의 실제 정의가 공통 ARCHITECTURE 계약 3과 다르면 코드를 맞추지 말고 `blocked`로 표시하고 차이를 `blocked_reason`에 적는다.

## 작업

수정 가능한 범위는 `backend/app/agents/loan/`과 `backend/tests/loan/`뿐이다.

**테스트를 먼저** 작성한다(TDD 가드).

1. `backend/tests/loan/test_agent_loan.py` — `llm.generate`는 목으로 대체한다. 이 파일에서 모델·Ollama를 실제로 호출하면 안 된다.
2. `backend/app/agents/loan/agent.py`
   ```python
   class LoanAgent:
       name = "loan"
       def handle(self, req: AgentRequest) -> AgentReply: ...
   agent: LoanAgent
   ```
   흐름은 `docs/agent-loan/ARCHITECTURE.md` handle() 1~7단계를 따른다. 규칙 요약이 아니라 그 절이 기준이다.
   - 모델 호출은 `from app import llm` 후 `llm.generate("cs-loan", messages)`로 **모듈 속성 경유**로 부른다. 이유: 테스트가 `monkeypatch.setattr("app.llm.generate", ...)`로 바꿀 수 있어야 한다.
   - 검증 실패 시 `prompt.fallback_text(loan)`을 쓴다. 대출 없음이면 `prompt.NO_LOAN_TEXT`이며 모델을 호출하지 않는다.
   - `req.mask_map`을 프롬프트에 넣지 마라(계약 3).
3. `backend/app/agents/loan/__init__.py` — `agent`와 `mock_router`를 export한다(`from .agent import agent`, `from .mock_api import mock_router`). 팀원C가 만든 스텁이 이미 있으면 **교체**한다(통합 순서 2단계).

## 테스트로 고정할 핵심 규칙

- `C001`: `generate`가 한 번도 호출되지 않고 `text == NO_LOAN_TEXT`, `slots == {}`
- `C002`: `generate`에 넘어간 messages 전체에 `12000000`·`12,000,000`이 없다. `reply.slots["principal_remaining"] == "12,000,000원"`, `reply.slots["loan_label"] == "신용대출"`
- 목이 "금리는 연 3.5%입니다" / "재직증명서가 필요합니다" / "{{balance}}입니다" / "1,200만원입니다"를 돌려주면 `reply.text`가 기본 문장이다
- 목이 정상 문장("만기일은 2027-03-31입니다. 남은 원금은 {{principal_remaining}}입니다.")을 돌려주면 그대로 통과한다
- `C003`에서 목이 "연장이 가능합니다"를 돌려주면 기본 문장(연장 가능으로 조회되지 않음)으로 바뀐다
- `reply.options == []`, 호출한 모델 이름은 `"cs-loan"`
- `history`가 프롬프트에 순서대로 포함된다

## Acceptance Criteria

```bash
cd backend && python -m pytest tests/loan -q
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - 에이전트가 `Agent` Protocol(`name`, `handle`)을 만족하고 패키지가 `agent`·`mock_router`만 export하는가?
   - 모델 호출이 `llm.generate` 하나를 거치는가(직접 `requests`/`ollama` 호출 금지)?
   - 원금 숫자가 프롬프트·history 어디에도 없는가?
3. 결과에 따라 `phases/agent-loan/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`. `base.py`가 계약과 달라 맞춘 부분이 있으면 `deviation:`으로 적는다.
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- `agents/base.py`·`llm/`를 만들거나 고치지 마라. 이유: 소유자가 팀원C이고, 계약 3은 합의 없이 바꿀 수 없다.
- 이 step에서 Ollama·실제 모델을 호출하지 마라. 이유: `cs-loan`은 아직 학습 전이며 AC는 모델 없이 통과해야 한다.
- 검증(`validate.py`)을 우회하는 경로를 만들지 마라(예: 디버그 플래그). 이유: 지어낸 사실 1건이 인수 불합격이다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
