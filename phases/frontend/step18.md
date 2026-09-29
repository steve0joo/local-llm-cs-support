# Step 18: landing-review

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md` (없으면 이 항목은 건너뛰고 요약에 "CLAUDE.md 없음"이라 적는다)
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/docs/frontend/PRD.md`, `/docs/frontend/ARCHITECTURE.md`, `/docs/frontend/ADR.md`, `/docs/frontend/UI_GUIDE.md`
- `/.claude/commands/review.md` (체크리스트 기준)
- `phases/frontend/index.json`의 step 10~16 summary와 `files`
- `git diff --stat main...HEAD`로 브랜치 전체 변경 파일 목록

## 작업

`/.claude/commands/review.md`의 체크리스트 7개 항목으로 `feat-frontend` 브랜치를 검토한다. 중점은 랜딩 통합 작업(step 10~16)의 변경이다. 이 step에서는 **코드를 수정하지 않는다**(발견 사항 보고만).

이 작업에서 특히 확인할 것:

- **엔진 원본 일치(FE-008)**: `public/scroll-world/`의 6개 파일이 원본과 해시가 같고(AC), `src/`에서 엔진을 import하거나 번들링하지 않는가?
- **ScrollWorld**: 초기화가 `onReady`이고 폴링이 없는가? 마운트 조건이 "컨테이너가 비었을 때"인가? 실패 세 경우(`onError`, 함수 없음, 마운트 예외)가 모두 컨테이너를 숨기는가? `LANDING`이 정적 문자열뿐이고 PRD "랜딩" 표와 같은가?
- **CSS 레이어**: 엔진 덮어쓰기(`--sw-*`, `keep-all`, `object-fit: contain`)가 `globals.css`에서 `@layer` 밖에 있는가? 색 hex가 `@theme`에만 있는가?
- **CRITICAL 규칙**: 프론트가 `/api/chat`만 부르는가? `src/`에 `localhost:8000`·`11434`·`/mock/`·`dangerouslySetInnerHTML`이 없는가? `sendChat` 호출이 `page.tsx` 한 곳인가? CDN 리소스가 `layout.tsx`의 Pretendard CSS 하나뿐이고 CDN JS가 없는가?
- **응답 확인**: `sendChat`이 `text` 비문자열·`options` 비배열만 reject하고, 항목 안쪽 검증이나 응답 정규화를 하지 않는가?
- **핵심 규칙 테스트**: 스모크만 있으면 ❌. 최소한 다음이 있어야 한다.
  - api: `text` null·숫자·누락, `options` 객체·문자열 → reject / `options` null·누락 → resolve
  - ScrollWorld: `onReady` 두 번 → mount 1회, `onError`·함수 없음·예외 → 숨김, hash `#chat` → `scrollIntoView`
  - ChatWindow: 칩은 빈 대화에서만, log 밖, `pending`이면 비활성, 클릭 → `onSend`
  - page: 칩 요청에 `choice` 키 없음, 더블클릭·Enter 연타 → 요청 1회, "새 대화" → 같은 고객·새 `session_id`·칩 다시 보임, 요청 중 "새 대화" 비활성
- **이전 규칙 유지**: fillSlots 규칙, FE-007 선택지 활성 판정, 고객 변경 초기화, 오류 말풍선, 런타임 목·타임아웃 없음(FE-005·006), `next.config.ts`의 `proxyTimeout: 120_000`·`agentRules: false`가 그대로인가?
- **UI_GUIDE**: `src/`에 teal·stone 클래스, 금지 패턴(`backdrop-blur`, `bg-gradient`·`bg-clip-text`, `purple`·`indigo`·`violet`, 글로우 그림자, "Powered by AI")이 없는가?
- **수정 범위**: `main...HEAD`의 변경이 다음 안에 있는가? `frontend/`, `phases/frontend/`, `docs/frontend/`, `docs/PRD.md`(디자인 절 한 줄만). `phases/index.json`은 execute.py가 다시 쓰면서 생긴 끝 줄바꿈 변경만 허용한다. 그 밖의 파일(`docs/ARCHITECTURE.md`·`docs/ADR.md`, `docs/agent-*`, `docs/router`, `backend/`, `CLAUDE.md`, `.claude/`)이 바뀌었으면 ❌
- **커밋 위생**: `frontend/AGENTS.md`·`frontend/CLAUDE.md`·`node_modules/`·`.next/`·`.env*`·`.DS_Store`가 커밋에 없는가?

## Acceptance Criteria

```bash
cd frontend
shasum -a 256 -c - <<'SUMS'
630bb1ab6101e5ed54eb1a24ab0be3f29e3744a95e156835b89541ea7c04752b  public/scroll-world/scrub-engine.js
071195dd22f820876eaa857d7e62748c75abe6045fd75de6f63f6358c0a6d103  public/scroll-world/scene02.webp
5e8708e120cfbf302b053e72eeba4f9e076b8970b89fa550cda3f7b877c9436c  public/scroll-world/finetune.webp
15e9ea40cd4a9e2c71fc6994682d9938c091130bbe1c6d5327ca568782716456  public/scroll-world/reception.webp
27ccb70f1bddac6b0f7d4f0572d85a30ea24d1e4cfe4facf29c8e375ba75ee61  public/scroll-world/office.webp
6d37fd8a82d52f23b5aee36b46d03c2a4c32d5a93665945e7c49db88ec141291  public/scroll-world/vid/scene02.mp4
SUMS
npm run lint
npx tsc --noEmit
npm run build
npm run test
test -z "$(grep -rlE 'localhost:8000|11434|/mock/|dangerouslySetInnerHTML' src || true)"
test -z "$(grep -rlE 'teal-|stone-|backdrop-blur|bg-clip-text|purple-|indigo-|violet-' src || true)"
test "$(grep -rl 'cdn.jsdelivr' src | tr -d ' ')" = "src/app/layout.tsx"
test "$(grep -rl 'sendChat(' src --include='*.tsx' --exclude='*.test.tsx' | tr -d ' ')" = "src/app/page.tsx"
test ! -e AGENTS.md
test ! -e CLAUDE.md
```

## 검증 절차

1. 위 AC 커맨드를 실행한다. 리뷰 체크리스트의 `bash scripts/verify.sh`는 파일이 있을 때만 실행한다.
2. 리뷰 결과를 `review.md`의 출력 형식(표)으로 정리해 summary에 담는다.
3. 결과에 따라 `phases/frontend/index.json`의 해당 step을 업데이트한다:
   - 모든 항목 ✅ → `"status": "completed"`, `"summary": "리뷰 결과 한 줄 요약"`
   - CRITICAL 위반이나 치명 결함 발견 → `"status": "blocked"`, `"blocked_reason": "위반 내용과 수정 방안"` 후 즉시 중단
   - 수정 3회 시도 후에도 AC 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`

## 금지사항

- 리뷰 중에 코드를 고치지 마라. 이유: 리뷰 결과와 수정 이력이 섞이면 무엇이 결함이었는지 추적이 안 된다. 결함은 `blocked`로 보고하고 사람이 pending step을 추가해 고친다.
- `git stash`, `git checkout <브랜치>`, `git switch`, `git worktree`를 쓰지 마라. 이유: stash 스택은 작업 트리끼리 공유되고, 다른 브랜치는 다른 작업 트리에 체크아웃돼 있다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
