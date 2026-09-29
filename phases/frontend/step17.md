# Step 17: landing-manual-check (human)

이 step은 사람이 직접 수행한다. executor는 여기서 멈춘다. 체크리스트를 끝낸 뒤 `phases/frontend/index.json`의 step 17 `status`를 `"completed"`로 바꾸면 이어서 실행된다.

백엔드 없이 할 수 있는 확인만 한다. 실제 응답으로 보는 확인은 `docs/frontend/ARCHITECTURE.md` "통합 후 확인"과 "발표 전 체크리스트"에서 한다(FE-005).

## 읽어야 할 파일

- `/docs/frontend/PRD.md` ("랜딩" 표, "챗 섹션", "예시 질문 칩")
- `/docs/frontend/ARCHITECTURE.md` ("랜딩 엔진 통합", "화면 동작 규칙", "시연 방식")
- `/docs/frontend/UI_GUIDE.md` (전체)
- `/frontend/README.md` (실행 방법)

## 체크리스트

준비:

- [ ] 백엔드(8000)는 띄우지 않는다
- [ ] A. dev: 일반 터미널에서 `cd frontend && npm run dev`, 브라우저로 `http://localhost:3000`을 연다
- [ ] B. 프로덕션: dev를 끄고 `cd frontend && npm run build && npm run start -- -H 127.0.0.1`, 브라우저로 `http://localhost:3000`을 연다
- [ ] 아래 "랜딩"과 "챗"은 A와 B에서 각각 한 번씩 확인한다. "dev 전용"은 A에서만 한다
- LAN IP로 열지 않는다. `crypto.randomUUID`가 보안 컨텍스트(localhost)에서만 동작한다

랜딩:

- [ ] 첫 화면에 01 장면(영상)과 "같은 질문이 매일 쌓입니다."가 보이고, 상단바에 "Local LLM", 장면 nav 4개, "직접 물어보기"가 있다. 아래쪽에 "스크롤해서 들어가기" 힌트가 있다
- [ ] 로드 직후 챗 섹션이 화면 맨 위에 번쩍 보였다 사라지지 않는다
- [ ] 01→04로 스크롤하면 장면이 크로스페이드되고, 카피와 태그가 PRD "랜딩" 표와 같다. 한국어 제목이 단어 중간에서 끊기지 않는다
- [ ] 04 장면의 "직접 물어보기"를 누르면 챗 섹션으로 간다. 01 장면에서 상단바 "직접 물어보기"를 눌러도 챗 섹션으로 간다
- [ ] 챗 섹션이 04 카피와 오른쪽 점 내비를 완전히 덮는다. 상단바가 챗 패널 상단(데모 고객·새 대화)을 가리지 않는다
- [ ] 주소가 `/#chat`인 상태에서 새로고침하면 챗 섹션에 도착한다(랜딩 중간이 아니다)
- [ ] 데스크톱에서 대화 목록 끝까지 스크롤한 뒤 더 굴려도 페이지가 위(랜딩)로 되감기지 않는다
- [ ] DevTools에서 폭 860px 이하(터치 에뮬레이션 포함): 장면 카피가 아래쪽에 고정되고 nav가 숨는다. 챗 섹션은 1열이다. 대화 목록 안쪽 스크롤이 되고, 끝에서 페이지가 되감기지 않는다
- [ ] DevTools Rendering → `prefers-reduced-motion: reduce`: 영상과 파티클이 없고 장면은 크로스페이드로 바뀐다. 챗 말풍선 fade는 그대로다
- [ ] DevTools Network에서 `scrub-engine.js` 요청을 차단하고 새로고침: 랜딩 없이 챗 섹션이 첫 화면이고, 챗이 동작한다(차단을 푼다)

챗 (백엔드 없음):

- [ ] 빈 대화: 대화 목록 가운데 안내 문구, 입력창 위에 칩 5개(PRD 표 문구)
- [ ] 칩 하나를 누르면 오른쪽에 고객 말풍선이 생기고 칩이 사라진다. 곧 빨간 글자 "잠시 후 다시 시도해 주세요"가 보인다
- [ ] "새 대화"를 누르면 대화가 비고 칩이 다시 보인다. 데모 고객 선택값은 그대로다
- [ ] 키보드만 사용: 페이지 맨 위에서 Tab으로 상단바 "직접 물어보기"에 가서 Enter → 다음 Tab이 챗 섹션 안(데모 고객 선택 등)으로 이어진다 → 칩·입력·Enter 전송·"새 대화"까지 키보드로 된다. 포커스가 챗 섹션으로 이어지지 않으면 이 step을 completed로 바꾸지 말고 아래 "정리"의 방법으로 `#chat` 섹션에 `tabIndex={-1}`을 넣는 fix step을 추가한다
- [ ] 색과 모양이 UI_GUIDE와 같다: 크림 배경, 잉크색 고객 말풍선, 크림색 봇 말풍선, 파란 테두리 선택지, 주황 틴트 칩, 알약형 입력·버튼, Pretendard 폰트. teal·회색 잔재가 없다
- [ ] UI_GUIDE 금지 사항(blur, 그라데이션 텍스트, 보라/인디고, 글로우, "Powered by AI" 배지)이 `src/`로 만든 영역에 없다(엔진 nav의 blur는 알려진 예외)

dev 전용 (A):

- [ ] `frontend/src/components/ScrollWorld.tsx`에 빈 줄을 하나 넣고 저장해 Fast Refresh를 일으킨다 → 장면이 두 겹으로 보이지 않고 스크롤·CTA가 정상이다 → 빈 줄을 지우고 저장한다

정리:

- [ ] 서버를 끈다
- [ ] `git status --short`에 `frontend/AGENTS.md`, `frontend/CLAUDE.md`, 그 밖의 변경·새 파일이 없다
- [ ] 어긋난 점이 있으면 이 step을 completed로 바꾸지 말고, 고칠 내용을 담은 pending step을 step 18(review) 앞에 추가한 뒤 다시 실행한다
