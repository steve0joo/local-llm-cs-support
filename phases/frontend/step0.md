# Step 0: project-setup

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/ARCHITECTURE.md` (계약 1 채팅 API, 계약 6 데모 고객 ID, 코드·테스트 규칙)
- `/docs/ADR.md` (ADR-002 프론트엔드 스택)
- `/docs/frontend/ARCHITECTURE.md` (디렉토리 구조, **스캐폴드·테스트 설정**, 상태 관리, 타입·API 규칙)
- `/docs/frontend/ADR.md` (FE-004~006)
- `/docs/frontend/UI_GUIDE.md` (레이아웃의 서비스 이름·`lang`)
- `/.claude/hooks/tdd-guard.sh` (테스트 없이 만들 수 있는 경로: 설정 파일, `types/`, `page.tsx`·`layout.tsx`·`globals.css`, `*/test/*`)
- `/frontend/README.md` (이 step에서 내용을 바꾸지 않는다)

## 사전 점검 (가장 먼저)

- `git branch --show-current`가 `feat-frontend`가 아니면 아무것도 만들지 말고 `blocked`로 표시한다(`blocked_reason`: "feat-frontend 브랜치가 아님 — frontend 작업 트리에서 execute.py를 실행해야 함").
- `node -v`가 24.0 미만이면 `blocked`로 표시한다(`blocked_reason`: "Node 24.0 이상 필요").

## 작업

수정 가능한 범위는 `frontend/`와 `phases/frontend/`뿐이다.

1. **스캐폴드** — `docs/frontend/ARCHITECTURE.md` "스캐폴드·테스트 설정"대로 만든다. `frontend/`에 `README.md`가 있으면 create-next-app이 "빈 폴더가 아니다"로 실패하므로, 지웠다가 git에서 복원한다. `frontend/package.json`이 이미 있으면(재시도) 이 항목은 건너뛴다.
   ```bash
   rm frontend/README.md
   npx --yes create-next-app@16.3.6 frontend --ts --tailwind --eslint --app --src-dir --empty \
     --no-import-alias --no-react-compiler --no-agents-md --use-npm --disable-git --yes
   git checkout HEAD -- frontend/README.md
   ```
   - 입력을 기다리는 프롬프트가 뜨지 않게 플래그를 모두 준다. 세션은 대화형 입력을 받을 수 없다.
   - 템플릿의 `biome.json`처럼 쓰지 않는 파일이 생기면 지운다.
2. **테스트 도구 설치** — `frontend/`에서:
   ```bash
   npm install -D @types/node@^24 vitest@^5 vite@^8 @vitejs/plugin-react@^6 jsdom@^29 \
     @testing-library/react@^16 @testing-library/dom@^10 @testing-library/user-event@^14 @testing-library/jest-dom@^7
   ```
   - `typescript`·`eslint`는 템플릿 버전을 그대로 둔다(`@latest`로 올리지 않는다).
3. **`frontend/package.json` scripts** — `dev: next dev`, `build: next build`, `start: next start`, `lint: eslint`, `test: vitest run --passWithNoTests`.
4. **`frontend/next.config.ts`**
   ```ts
   const nextConfig: NextConfig = {
     agentRules: false,
     experimental: { proxyTimeout: 120_000 },
     async rewrites() { /* /api/:path* → http://localhost:8000/api/:path* */ },
   };
   ```
5. **`frontend/vitest.config.ts`** — `@vitejs/plugin-react`, `test.environment: "jsdom"`, `test.setupFiles: ["./src/test/setup.ts"]`. `passWithNoTests`는 넣지 않는다.
6. **`frontend/src/test/setup.ts`** — `@testing-library/jest-dom/vitest` import, `afterEach(cleanup)`.
7. **`frontend/src/types/chat.ts`** — 계약 1 타입과 화면 타입. 필드 규칙은 `docs/frontend/ARCHITECTURE.md` "타입·API 규칙"·"상태 관리"를 따른다.
   ```ts
   export type ChatOption = { label: string; choice: string };
   export type ChatRequest = { session_id: string; customer_id: string; message: string; choice?: string };
   export type ChatResponse = { type: "answer" | "clarify" | "unsupported"; agent: "balance" | "loan" | "interest" | null;
     topic: string | null; text: string; slots: Record<string, string>; options: ChatOption[] };
   export type CustomerId = "C001" | "C002" | "C003";
   export const CUSTOMER_IDS: readonly CustomerId[];
   export type ChatMessage = { role: "user" | "bot"; text: string; slots?: Record<string, string>; options?: ChatOption[]; error?: true };
   ```
8. **`frontend/src/app/layout.tsx`** — `<html lang="ko">`, 메타데이터 제목 "은행 상담". children 타입은 `Readonly<{ children: React.ReactNode }>`처럼 직접 적는다(전역 `LayoutProps`를 쓰면 `tsc --noEmit`이 `next typegen` 없이 실패한다).
9. **`frontend/src/app/page.tsx`** — 템플릿의 최소 페이지를 둔다. step 7에서 교체한다. `globals.css`는 `@import "tailwindcss";`만 있으면 된다(애니메이션은 step 7).

## Acceptance Criteria

```bash
cd frontend
test -f package-lock.json
test -f src/test/setup.ts
test -f src/types/chat.ts
test ! -e AGENTS.md
test ! -e CLAUDE.md
git diff --quiet HEAD -- README.md
grep -q "proxyTimeout: 120_000" next.config.ts
grep -q "agentRules: false" next.config.ts
grep -q "localhost:8000" next.config.ts
npm run lint
npx tsc --noEmit
npm run build
npm run test
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `docs/frontend/ARCHITECTURE.md` 디렉토리 구조와 "스캐폴드·테스트 설정"을 따르는가? import alias(`@/`)가 없는가?
   - `npx vitest run src/없는파일.test.ts`가 실패하는가? (`passWithNoTests`가 설정 파일에 들어가지 않았는지 확인)
   - `git status --short`에 `frontend/`, `phases/frontend/` 밖의 변경이 없는가?
3. 결과에 따라 `phases/frontend/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"` (설치된 next·vitest·jsdom 버전을 포함)
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- `frontend/`, `phases/frontend/` 밖의 파일을 만들거나 고치지 마라(루트 `.gitignore`, `docs/`, `backend/`, `CLAUDE.md`, `.claude/`, `phases/index.json` 포함). 이유: 다른 영역이 다른 작업 트리에서 병렬로 작업 중이라 공통 파일을 고치면 main 병합 때 충돌한다.
- `git stash`, `git checkout <브랜치>`, `git switch`, `git worktree`를 쓰지 마라. 이유: stash 스택은 작업 트리끼리 공유되고, 다른 브랜치는 다른 작업 트리에 체크아웃돼 있다. (`git checkout HEAD -- frontend/README.md`처럼 파일 복원만 허용)
- `rm -rf`를 쓰지 마라. 이유: bash-guard 훅이 막는다. 지울 파일은 하나씩 지운다.
- `npm run dev`를 띄우지 마라. 이유: 이 step에서는 필요 없고, 세션이 끝나도 dev 서버 프로세스가 남는다.
- `jsdom`을 30 이상으로, `typescript`·`eslint`를 템플릿보다 높은 메이저로 올리지 마라. 이유: jsdom 30은 Node 24.15 이상을 요구하고, 상위 메이저는 템플릿 설정과 맞는지 확인되지 않았다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
