# Step 10: landing-assets

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/docs/frontend/ARCHITECTURE.md` (디렉토리 구조, "랜딩 엔진 통합", 핵심 규칙의 원본 일치)
- `/docs/frontend/ADR.md` (FE-008)
- `/docs/frontend/UI_GUIDE.md` ("에셋 규칙")
- `/frontend/eslint.config.mjs`

## 작업

스크롤 월드 웹사이트의 엔진과 에셋을 frontend로 가져온다. 수정 가능한 범위는 `frontend/public/scroll-world/`, `frontend/eslint.config.mjs`, `phases/frontend/`뿐이다.

1. 원본 폴더 `$HOME/Projects/local-llm-cs-support-website/`에서 아래 6개 파일을 **`cp`로** 복사한다. 디렉토리가 없으면 만든다.

   | 원본 (`$HOME/Projects/local-llm-cs-support-website/` 기준) | 대상 |
   |------|------|
   | `scrub-engine.js` | `frontend/public/scroll-world/scrub-engine.js` |
   | `assets/scene02.webp` | `frontend/public/scroll-world/scene02.webp` |
   | `assets/finetune.webp` | `frontend/public/scroll-world/finetune.webp` |
   | `assets/reception.webp` | `frontend/public/scroll-world/reception.webp` |
   | `assets/office.webp` | `frontend/public/scroll-world/office.webp` |
   | `assets/vid/scene02.mp4` | `frontend/public/scroll-world/vid/scene02.mp4` |

2. `frontend/eslint.config.mjs`의 `globalIgnores([...])` 배열에 `"public/scroll-world/**"`를 추가한다. 기존 항목과 주석은 그대로 둔다. 추가한 줄 위에 이유를 한 줄 주석으로 적는다(엔진 원본은 lint하지 않는다, FE-008). 지금 엔진 파일을 lint하면 경고 4건이 나온다.

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
test "$(find public/scroll-world -type f | wc -l | tr -d ' ')" = 6
grep -q 'public/scroll-world/\*\*' eslint.config.mjs
npm run lint
npm run build
npm run test
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `public/scroll-world/` 구조가 `docs/frontend/ARCHITECTURE.md` 디렉토리 구조와 같은가?
   - `git status --short`에 `frontend/public/scroll-world/`, `frontend/eslint.config.mjs`, `phases/frontend/` 밖의 변경이 없는가? `.DS_Store`가 들어가지 않았는가?
3. 결과에 따라 `phases/frontend/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 원본 폴더나 파일이 없거나 해시가 다름 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 복사한 파일을 수정·재인코딩·압축하지 마라. Write 도구로 다시 쓰지도 마라(반드시 `cp`). 이유: 원본과 바이트 단위로 같아야 한다(FE-008). 해시가 다르면 AC가 실패한다.
- 원본 폴더(`$HOME/Projects/local-llm-cs-support-website/`)의 파일을 고치거나 옮기지 마라. 이유: 원본은 이 저장소 밖에 있고 git이 아니라서 되돌릴 수 없다.
- 웹사이트의 `index.html`, `docs/`, `scripts/`, `.claude/`, `README.md`, `CLAUDE.md`를 가져오지 마라. 이유: 필요한 규칙은 이미 `docs/frontend/`에 옮겨 적었다. 다른 파일이 섞이면 파일 수 AC가 실패한다.
- 엔진을 `src/`로 import하거나 번들링하지 마라. 이유: `public/`의 정적 파일을 `next/script`로 불러오는 것이 설계다(FE-008).
- `npm run dev`를 띄우지 마라. 이유: 브라우저 확인은 step 17(사람)이 한다. 세션이 끝나도 dev 서버 프로세스가 남는다.
- `git stash`, `git checkout <브랜치>`, `git switch`, `git worktree`를 쓰지 마라. 이유: stash 스택은 작업 트리끼리 공유되고, 다른 브랜치는 다른 작업 트리에 체크아웃돼 있다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
