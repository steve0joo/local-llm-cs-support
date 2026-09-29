# frontend

Next.js 챗봇 UI. 담당: 나 · 브랜치 `feat-frontend`

문서: `docs/frontend/` (PRD · ARCHITECTURE · ADR · UI_GUIDE)

## 실행
Node 24.0 이상, npm이 필요하다.

```bash
cd frontend
npm ci            # package-lock.json 그대로 설치
npm run dev       # http://localhost:3000
npm run lint
npm run build
npm run test      # Vitest
```

- `/api/*` 요청은 `next.config.ts` rewrites로 `http://localhost:8000`(FastAPI)에 프록시된다. 백엔드 없이 띄우면 요청이 실패해 "잠시 후 다시 시도해 주세요" 오류 말풍선이 보이는데, 정상이다.
- 브라우저는 `http://localhost:3000`으로 연다. `session_id`를 만드는 `crypto.randomUUID()`는 보안 컨텍스트(localhost 또는 https)에서만 동작해서 LAN IP로 열면 안 된다.
