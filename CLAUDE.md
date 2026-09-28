# 프로젝트: 로컬 LLM 은행 상담 보조 AI (MVP)

고객 문의를 주제 분류해 전문 에이전트 3개(잔액조회·대출문의·이자/연체)로 연결하는 챗봇. 모델은 AI Hub 71926 은행 상담 데이터로 파인튜닝한 로컬 양자화 모델이다.

## 기술 스택

- frontend: Next.js (App Router) + TypeScript strict mode + Tailwind CSS, 테스트 Vitest
- backend: Python 3.11 + FastAPI, 테스트 pytest
- 모델 추론: Ollama (GGUF — Windows CUDA / macOS Metal 공통)
- 학습: Hugging Face Transformers + PEFT(QLoRA) + TRL, GGUF 변환은 llama.cpp

## 아키텍처 규칙

- CRITICAL: 모든 모델 호출은 `backend/app/llm`의 `generate()`만 거칠 것. 라우터·에이전트에서 Ollama를 직접 호출하지 말 것 (모델 입력 로그를 한 곳에서 남기기 위해)
- CRITICAL: 고객 입력은 `backend/app/masking`을 거친 뒤에만 모델에 전달할 것. 주민등록번호·카드번호·계좌번호·전화번호·주소·금액 원본을 프롬프트에 넣지 말 것
- CRITICAL: mock API가 돌려준 금액은 프롬프트에 넣지 말 것. 모델은 `{{슬롯}}`만 쓰고, 실제 값은 응답 `slots`로 프론트에 전달해 화면에서만 치환할 것
- CRITICAL: 프론트엔드는 `/api/chat`만 호출할 것. Ollama나 mock API를 직접 호출하지 말 것
- CRITICAL: AI Hub 원본·가공 데이터와 모델 가중치(.gguf, .safetensors)를 git에 커밋하지 말 것 (데이터셋 이용조건: 제3자 제공 금지)
- 각 담당자는 자기 영역 디렉토리만 수정한다. 영역 간 계약(`/api/chat` 스키마, `backend/app/agents/base.py`, 주제 코드, 마스킹 토큰)을 바꾸려면 `docs/ARCHITECTURE.md`를 먼저 고치고 팀 합의 후 반영한다
- 작업 전 루트 `docs/`(공통)와 자기 영역 `docs/<영역>/`을 함께 읽는다. 영역: `frontend`, `router`, `agent-balance`, `agent-loan`, `agent-interest`

## 개발 프로세스

- CRITICAL: 새 기능 구현 시 반드시 테스트를 먼저 작성하고, 테스트가 통과하는 구현을 작성할 것 (TDD)
- 커밋 메시지는 conventional commits 형식을 따를 것 (feat:, fix:, docs:, refactor:)
- 브랜치는 영역별 `feat-<영역>`에서 작업하고 main으로 PR 머지한다

## 명령어

```bash
# frontend
cd frontend && npm run dev     # 개발 서버 (localhost:3000)
cd frontend && npm run build   # 프로덕션 빌드
cd frontend && npm run lint    # ESLint
cd frontend && npm run test    # Vitest

# backend
cd backend && uvicorn app.main:app --reload --port 8000   # API 서버
cd backend && pytest                                      # 전체 테스트
cd backend && pytest tests/<폴더>                          # 폴더별 테스트 — router 영역: gateway·masking·llm·router, 에이전트 영역: balance·loan·interest

# models — <모델>: router · balance · loan · interest (계약 5 이름: cs-router · cs-balance · cs-loan · cs-interest)
ollama create cs-<모델> -f backend/models/<모델>/Modelfile
```
