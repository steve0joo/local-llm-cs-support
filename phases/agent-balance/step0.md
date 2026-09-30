# Step 0: main-merge (human)

이 step은 사람이 직접 수행한다. executor는 여기서 멈춘다. 체크리스트를 끝낸 뒤 `phases/agent-balance/index.json`의 step 0 `status`를 `"completed"`로 바꾸면 이어서 실행된다.

사람이 하는 이유: 머지 커밋이 필요하다. execute.py는 세션이 만든 커밋을 soft reset으로 합치므로 Claude 세션에서 병합하면 머지 부모가 사라진다.

## 읽어야 할 파일

- `/docs/agent-balance/ADR.md` (BAL-005 "현황"·"병합 시험 결과")
- `/docs/agent-balance/ARCHITECTURE.md` ("알려진 한계"의 `test_base.py`·`test_api.py` 예외)
- `/docs/agent-balance/PRD.md` ("구현 진행" 3차 계획 0)

## 체크리스트

시작 전:

- [ ] 현재 브랜치가 `feat-agent-balance`이고 작업 트리가 깨끗하다(`git status --short`가 비어 있다). phase 파일(`phases/`)도 커밋되어 있다

병합:

- [ ] `git fetch origin && git merge --no-ff origin/main`
- [ ] 충돌을 BAL-005 "병합 시험 결과"대로 푼다
  - `backend/app/agents/balance/__init__.py`, `backend/tests/router/test_base.py`, `backend/training/requirements.txt` → `git checkout --ours -- <파일>`
  - `backend/README.md` → 이 브랜치의 Mac 학습 안내 한 줄 뒤에 main의 "구동 절차" 이하를 붙인다
  - `phases/index.json` → 충돌이 나면 이 브랜치 파일을 쓴다(main 쪽 차이는 끝 줄바꿈뿐이고, 이 브랜치 파일에 `agent-loan`·`agent-balance` 항목이 모두 있다)
- [ ] `backend/tests/gateway/test_api.py`의 `client` fixture에서 `classify`가 `RouteResult(topics=["loan"])`를 돌려주게 바꾸고, `test_response_has_exactly_the_contract_fields`의 기대 `agent`를 `"loan"`으로 바꾼다(요청의 `message`는 그대로 둔다). ARCHITECTURE "알려진 한계"의 세 번째 예외다
- [ ] `cd backend && .venv/bin/python -m pytest -q`가 전부 통과한다
- [ ] `git add` 경로를 지정해 스테이징하고(`git add -A` 금지 — `scripts/`·`.ouroboros/`는 로컬 전용) 머지 커밋을 만든다: `git commit -m "Merge origin/main into feat-agent-balance"`

확인:

- [ ] `git log --oneline -1`이 머지 커밋이다
- [ ] `docs/router/ADR.md`에 RT-005·RT-006이 있다(main 문서가 들어왔다)
- [ ] `git diff --stat origin/main...HEAD -- backend/app/agents/base.py backend/app/llm backend/app/masking backend/app/gateway`가 비어 있다(발판 파일이 main과 같다)
