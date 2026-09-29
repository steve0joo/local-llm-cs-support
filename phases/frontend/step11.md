# Step 11: theme-tokens

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/docs/frontend/UI_GUIDE.md` ("색상", "랜딩 (엔진)", "타이포그래피", "애니메이션", 레이아웃의 메타데이터 제목)
- `/docs/frontend/ARCHITECTURE.md` ("랜딩 엔진 통합"의 CSS 레이어, "보안 규칙"의 외부 리소스)
- `/docs/frontend/ADR.md` (FE-008)
- `/frontend/src/app/globals.css`, `/frontend/src/app/layout.tsx`
- `/frontend/public/scroll-world/scrub-engine.js`의 `injectCSS()` (엔진이 쓰는 `--sw-*` 변수와 `@layer sw`)

## 작업

색·폰트 토큰과 엔진 테마 덮어쓰기를 한 곳에 정의한다. 수정 가능한 범위는 `frontend/src/app/globals.css`, `frontend/src/app/layout.tsx`, `phases/frontend/`뿐이다.

1. `frontend/src/app/globals.css`
   - `@import "tailwindcss";`와 기존 `@theme`의 `--animate-fade-in`·`@keyframes fade-in`을 유지한다.
   - `@theme`에 UI_GUIDE "색상" 표의 토큰 8개를 `--color-<토큰>: <값>;`으로 추가한다(`cream`, `surface`, `bubble`, `ink`, `ink-soft`, `accent-orange`, `accent-blue`, `accent-yellow`). hex 값은 표에 적힌 그대로 쓴다.
   - `@theme`에 `--font-sans`를 UI_GUIDE "타이포그래피"의 Pretendard 스택으로 둔다.
   - `@layer base`의 `body` 배경을 `var(--color-cream)`으로 바꾼다.
   - **어떤 `@layer`에도 넣지 않은** 규칙으로 UI_GUIDE "랜딩 (엔진)"의 덮어쓰기 세 가지를 추가한다. `--sw-*` 변수 값은 hex를 다시 적지 말고 `var(--color-…)`로 토큰을 가리킨다(토큰은 한 곳에만).
2. `frontend/src/app/layout.tsx`
   - `<head>`에 Pretendard CDN `<link rel="stylesheet" href="…">`를 둔다. URL은 UI_GUIDE "타이포그래피"에 있다(`https://cdn.jsdelivr.net/npm/` + 그 경로).
   - `metadata.title`을 `"Local LLM — 은행 상담 AI"`로 바꾼다.
   - `<html lang="ko">`와 children 타입을 직접 적는 방식은 유지한다.

컴포넌트는 이 step에서 바꾸지 않는다. 기존 컴포넌트가 teal·stone 클래스를 쓰고 있어도 된다(step 14~16에서 바꾼다).

## Acceptance Criteria

```bash
cd frontend
grep -qiE -- '--color-cream:[[:space:]]*#FCF1E6' src/app/globals.css
grep -qiE -- '--color-surface:[[:space:]]*#FFFBF6' src/app/globals.css
grep -qiE -- '--color-bubble:[[:space:]]*#F3E6D8' src/app/globals.css
grep -qiE -- '--color-ink:[[:space:]]*#2A2118' src/app/globals.css
grep -qiE -- '--color-ink-soft:[[:space:]]*#7A6A5C' src/app/globals.css
grep -qiE -- '--color-accent-orange:[[:space:]]*#E07B2E' src/app/globals.css
grep -qiE -- '--color-accent-blue:[[:space:]]*#3A6FD0' src/app/globals.css
grep -qiE -- '--color-accent-yellow:[[:space:]]*#E5A527' src/app/globals.css
grep -q -- '--font-sans' src/app/globals.css
grep -q -- '--animate-fade-in' src/app/globals.css
grep -q -- '--sw-bg' src/app/globals.css
grep -qE 'word-break:[[:space:]]*keep-all' src/app/globals.css
grep -qE 'object-fit:[[:space:]]*contain' src/app/globals.css
grep -q 'cdn.jsdelivr.net/npm/pretendard@1.3.9/dist/web/variable/pretendardvariable.min.css' src/app/layout.tsx
grep -q 'Local LLM — 은행 상담 AI' src/app/layout.tsx
grep -q 'lang="ko"' src/app/layout.tsx
npm run lint
npx tsc --noEmit
npm run build
npm run test
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `--sw-*` 덮어쓰기, `keep-all`, `object-fit: contain` 규칙이 `@layer` 블록 **밖**에 있는가? (grep으로는 확인할 수 없으니 파일을 직접 읽어 확인한다)
   - 색 hex가 `@theme`에만 있고 `--sw-*`는 `var(--color-…)`를 가리키는가?
   - `git status --short`에 `frontend/src/app/globals.css`, `frontend/src/app/layout.tsx`, `phases/frontend/` 밖의 변경이 없는가?
3. 결과에 따라 `phases/frontend/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 엔진 덮어쓰기를 `@layer base`나 다른 `@layer` 안에 넣지 마라. 이유: 엔진이 실행 중에 넣는 `@layer sw`가 Tailwind 레이어보다 나중에 선언돼서, 레이어 안의 규칙은 엔진 기본값에 진다. 레이어 밖 CSS만 이긴다.
- `next/font`나 폰트 파일 자체 호스팅을 쓰지 마라. 이유: 오프라인 시연이 없어서 CDN을 유지하기로 했다(UI_GUIDE 타이포그래피).
- CDN에서 JS를 불러오지 마라. 외부 리소스는 Pretendard CSS 하나뿐이다. 이유: ARCHITECTURE "보안 규칙".
- 컴포넌트(`src/components/`)와 `page.tsx`를 고치지 마라. 이유: 스타일 교체는 step 14~16에서 테스트와 함께 한다.
- `npm run dev`를 띄우지 마라. 이유: 브라우저 확인은 step 17(사람)이 한다. 세션이 끝나도 dev 서버 프로세스가 남는다.
- `git stash`, `git checkout <브랜치>`, `git switch`, `git worktree`를 쓰지 마라. 이유: stash 스택은 작업 트리끼리 공유되고, 다른 브랜치는 다른 작업 트리에 체크아웃돼 있다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
