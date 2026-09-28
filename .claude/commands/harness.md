이 프로젝트는 Harness 프레임워크를 사용한다. 아래 워크플로우에 따라 작업을 진행하라.

---

## 워크플로우

### A. 탐색

`/docs/` 하위 문서(PRD, ARCHITECTURE, ADR 등)를 읽고 프로젝트의 기획·아키텍처·설계 의도를 파악한다. 필요시 Explore 에이전트를 병렬로 사용한다.

### B. 논의

구현을 위해 구체화하거나 기술적으로 결정해야 할 사항이 있으면 사용자에게 제시하고 논의한다.

### C. Step 설계

사용자가 구현 계획 작성을 지시하면 여러 step으로 나뉜 초안을 작성해 피드백을 요청한다.

설계 원칙:

1. **Scope 최소화** — 하나의 step에서 하나의 레이어 또는 모듈만 다룬다. 여러 모듈을 동시에 수정해야 하면 step을 쪼갠다.
2. **자기완결성** — 각 step 파일은 독립된 Claude 세션에서 실행된다. "이전 대화에서 논의한 바와 같이" 같은 외부 참조는 금지한다. 필요한 정보는 전부 파일 안에 적는다.
3. **사전 준비 강제** — 관련 문서 경로와 이전 step에서 생성/수정된 파일 경로를 명시한다. 세션이 코드를 읽고 맥락을 파악한 뒤 작업하도록 유도한다.
4. **시그니처 수준 지시** — 함수/클래스의 인터페이스만 제시하고 내부 구현은 에이전트 재량에 맡긴다. 단, 설계 의도에서 벗어나면 안 되는 핵심 규칙(멱등성, 보안, 데이터 무결성 등)은 반드시 명시한다.
5. **AC는 실행 가능한 커맨드** — "~가 동작해야 한다" 같은 추상적 서술이 아닌 `npm run build && npm test` 같은 실제 실행 가능한 검증 커맨드를 포함한다.
6. **주의사항은 구체적으로** — "조심해라" 대신 "X를 하지 마라. 이유: Y" 형식으로 적는다.
7. **네이밍** — step name은 kebab-case slug로, 해당 step의 핵심 모듈/작업을 한두 단어로 표현한다 (예: `project-setup`, `api-layer`, `auth-flow`).
8. **AC는 executor가 다시 실행한다** — `## Acceptance Criteria`의 첫 ```bash 블록을 execute.py가 세션 종료 후 `bash -e -o pipefail`로 직접 실행하고, 이어서 `scripts/verify.sh`를 실행한다. 둘 다 통과해야 completed다. 그러므로 블록에는 **실제로 실행되는 커맨드만** 넣는다. 수동 확인·주석으로 적은 기대값은 넣지 마라(검증 절차나 human step으로 옮긴다). 외부 자격증명(API 키 등)이 필요한데 없으면 세션이 `blocked`로 표시한다.
9. **버그를 막는 테스트를 AC에** — "동작한다" 스모크만으로는 부족하다. 핵심 규칙(멱등성·권한·금전 처리 등)은 그 규칙을 깨는 입력을 재현하는 테스트를 AC에 포함한다.
10. **설계는 참조하고 복사하지 않는다** — step 파일에는 설계 문서의 절(§)을 가리키고 규칙은 한 곳에만 둔다. 구현이 설계와 달라지면 summary에 `deviation:`으로 적는다(설계 문서가 여러 곳에 복사되면 드리프트가 생긴다).
11. **사람 확인은 human step으로** — 브라우저 수동 확인·라벨링처럼 사람이 해야 하는 일은 `"type": "human"` step으로 분리한다. executor는 이 step에서 멈추고, 사람이 체크리스트를 끝낸 뒤 status를 `completed`로 바꾸면 이어서 실행된다.
12. **마지막 step은 리뷰** — phase의 마지막 step은 `/review` 체크리스트로 phase 전체 diff를 검토하는 `review` step으로 둔다. CRITICAL 위반이나 치명 결함이 있으면 `blocked`로 멈춘다.

### D. 파일 생성

사용자가 승인하면 아래 파일들을 생성한다.

#### D-1. `phases/index.json` (전체 현황)

여러 task를 관리하는 top-level 인덱스. 이미 존재하면 `phases` 배열에 새 항목을 추가한다.

```json
{
  "phases": [
    {
      "dir": "0-mvp",
      "status": "pending"
    }
  ]
}
```

- `dir`: task 디렉토리명.
- `status`: `"pending"` | `"completed"` | `"error"` | `"blocked"`. execute.py가 실행 중 자동으로 업데이트한다.
- 타임스탬프(`completed_at`, `failed_at`, `blocked_at`)는 execute.py가 상태 변경 시 자동 기록한다. 생성 시 넣지 않는다.

#### D-2. `phases/{task-name}/index.json` (task 상세)

```json
{
  "project": "<프로젝트명>",
  "phase": "<task-name>",
  "guardrail_docs": ["docs/ARCHITECTURE.md", "docs/ADR.md"],
  "steps": [
    { "step": 0, "name": "project-setup", "status": "pending" },
    { "step": 1, "name": "core-types", "status": "pending" },
    { "step": 2, "name": "manual-check", "status": "pending", "type": "human" },
    { "step": 3, "name": "review", "status": "pending" }
  ]
}
```

필드 규칙:

- `project`: 프로젝트명 (CLAUDE.md 참조).
- `phase`: task 이름. 디렉토리명과 일치시킨다.
- `steps[].step`: 0부터 시작하는 순번.
- `steps[].name`: kebab-case slug.
- `steps[].status`: 초기값은 모두 `"pending"`.
- `steps[].type` (선택): `"human"`이면 executor가 Claude를 호출하지 않고 멈춘다(원칙 11).
- `guardrail_docs` (선택): 매 step 프롬프트에 주입할 문서 목록. 생략하면 `docs/*.md` 전부. 문서가 늘어나면 프롬프트가 비대해지므로 phase에 필요한 문서만 적는다. CLAUDE.md는 `claude -p`가 자동으로 읽으므로 주입하지 않는다.

이 저장소 규칙: task(phase) 이름은 영역 이름(`frontend`, `router`, `agent-balance`, `agent-loan`, `agent-interest`)으로 한다. 그러면 execute.py가 `feat-<영역>` 브랜치에서 실행된다. `guardrail_docs`에는 `docs/ARCHITECTURE.md`, `docs/ADR.md`와 `docs/<영역>/`의 ARCHITECTURE·ADR를 적는다.

상태 전이와 자동 기록 필드:

| 전이 | 기록되는 필드 | 기록 주체 |
|------|-------------|----------|
| → `completed` | `completed_at`, `summary`, `ac_verified`, `files`, `cost_usd`, `num_turns` | Claude 세션 (summary), execute.py (나머지: AC 재실행 결과·변경 파일·비용) |
| → `error` | `failed_at`, `error_message` | Claude 세션 (message), execute.py (timestamp) |
| → `blocked` | `blocked_at`, `blocked_reason` | Claude 세션 (reason), execute.py (timestamp) |

`summary`는 step 완료 시 산출물을 한 줄로 요약한 것으로, execute.py가 다음 step 프롬프트에 컨텍스트로 누적 전달한다. 따라서 다음 step에 유용한 정보(생성된 파일, 핵심 결정 등)를 담아야 한다.

`created_at`은 execute.py가 최초 실행 시 task 레벨에 한 번만 기록한다. step 레벨의 `started_at`도 execute.py가 각 step 시작 시 자동 기록한다. 생성 시 넣지 않는다.

#### D-3. `phases/{task-name}/step{N}.md` (각 step마다 1개)

```markdown
# Step {N}: {이름}

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- {이전 step에서 생성/수정된 파일 경로}

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

{구체적인 구현 지시. 파일 경로, 클래스/함수 시그니처, 로직 설명을 포함.
코드 스니펫은 인터페이스/시그니처 수준만 제시하고, 구현체는 에이전트에게 맡겨라.
단, 설계 의도에서 벗어나면 안 되는 핵심 규칙은 명확히 박아넣어라.}

## Acceptance Criteria

```bash
npm run build   # 컴파일 에러 없음
npm test        # 테스트 통과
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - ARCHITECTURE.md 디렉토리 구조를 따르는가?
   - ADR 기술 스택을 벗어나지 않았는가?
   - CLAUDE.md CRITICAL 규칙을 위반하지 않았는가?
3. 결과에 따라 `phases/{task-name}/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 (API 키, 외부 인증, 수동 설정 등) → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- {이 step에서 하지 말아야 할 것. "X를 하지 마라. 이유: Y" 형식}
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
```

### E. 실행

```bash
python3 scripts/execute.py {task-name}                # 순차 실행 (작업 트리가 깨끗해야 시작)
python3 scripts/execute.py {task-name} --base main    # 새 브랜치를 main에서 분기
python3 scripts/execute.py {task-name} --push         # 실행 후 push
```

execute.py가 자동으로 처리하는 것:

- 시작 전 점검 — 작업 트리가 깨끗하지 않으면 중단(미추적 파일이 커밋에 휩쓸려 들어가는 것 방지), CLAUDE.md가 git에 추적되지 않으면 경고(새 클론에서 규칙 누락)
- `feat-{task-name}` 브랜치 생성/checkout (`--base`로 분기 기준 지정)
- 가드레일 주입 — CLAUDE.md + docs/*.md 내용을 매 step 프롬프트에 포함
- 컨텍스트 누적 — 완료된 step의 summary를 다음 step 프롬프트에 전달
- AC 재검증 — 세션이 completed로 보고해도 AC 블록과 `scripts/verify.sh`를 직접 실행해 통과해야 완료로 인정한다(`ac_verified`)
- 자가 교정 — 실패(AC 실패·타임아웃 포함) 시 최대 3회 재시도하며, 이전 에러 메시지를 프롬프트에 피드백
- 2단계 커밋 — 코드 변경(`feat`)과 메타데이터(`chore`)를 분리 커밋. 커밋은 executor만 한다(세션이 커밋하면 되감아 합친다)
- 커밋 가드 — `.env*`·키 파일·`.claude/worktrees/`·gitlink(서브모듈)가 스테이징되면 커밋하지 않고 `blocked`로 멈춘다
- 실패 격리 — 최종 실패 시 코드를 커밋하지 않고 작업 트리에 남긴다(메타데이터만 `chore: step N failed`로 커밋)
- 비용 기록 — step별 `cost_usd`·`num_turns`, phase 합계 `total_cost_usd`
- 타임스탬프 — started_at, completed_at, failed_at, blocked_at 자동 기록

스택 번안(웹앱이 아닌 프로젝트):

- `scripts/verify.sh` — 프로젝트 전역 검증 커맨드. Stop 훅과 executor가 함께 쓴다. 템플릿은 npm이다. 다른 스택이면 이 파일만 고친다(예: Python `python -m py_compile ... && python -m pytest -q`).
- `.claude/hooks/tdd-guard.sh` — TS/JS와 Python(`test_<모듈>.py`·`test_<모듈>_*.py`·`<모듈>_test.py`)을 지원한다. 다른 언어는 case를 추가한다.

에러 복구:

- **error 발생 시**: `phases/{task-name}/index.json`에서 해당 step의 `status`를 `"pending"`으로 바꾸고 `error_message`를 삭제한 뒤 재실행한다.
- **blocked 발생 시**: `blocked_reason`에 적힌 사유를 해결한 뒤, `status`를 `"pending"`으로 바꾸고 `blocked_reason`을 삭제한 뒤 재실행한다.
