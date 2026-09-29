# Step 8: manual-check (human)

이 step은 사람이 직접 수행한다. executor는 여기서 멈춘다. 체크리스트를 끝낸 뒤 `phases/frontend/index.json`의 step 8 `status`를 `"completed"`로 바꾸면 이어서 실행된다.

백엔드 없이 할 수 있는 확인만 한다. 실제 응답으로 보는 확인(금액·계좌 선택·거래내역 줄바꿈)은 `docs/frontend/ARCHITECTURE.md` "통합 후 확인"에서 한다(FE-005).

## 읽어야 할 파일

- `/docs/frontend/PRD.md` (기능 범위)
- `/docs/frontend/ARCHITECTURE.md` (화면 동작 규칙)
- `/docs/frontend/UI_GUIDE.md` (전체)
- `/frontend/README.md` (실행 방법)

## 체크리스트

준비:

- [ ] 백엔드(8000)는 띄우지 않는다
- [ ] 일반 터미널에서 `cd frontend && npm run dev`를 실행하고 브라우저로 `http://localhost:3000`을 연다(LAN IP로 열지 않는다 — `crypto.randomUUID`는 localhost에서만 동작)

화면:

- [ ] 상단에 "은행 상담"과 "데모 고객" 선택 상자(`C001`~`C003`)가 있다
- [ ] 대화 영역이 가운데 `max-w-2xl` 폭이고, 대화가 비어 있으면 안내 문구 "잔액·거래내역, 대출, 이자·연체 문의를 입력해 주세요."가 보인다
- [ ] 입력창이 비었거나 공백만 있으면 전송 버튼이 흐리게(비활성) 보인다
- [ ] "잔액 알려줘"를 Enter로 보내면 오른쪽에 검은 고객 말풍선이 생기고 입력창이 빈다
- [ ] 백엔드가 없으므로 곧 왼쪽에 빨간 글자 "잠시 후 다시 시도해 주세요" 말풍선이 생긴다(응답을 기다리는 동안 점 3개가 잠깐 보일 수 있다)
- [ ] 말풍선을 여러 개 만들면 대화 목록만 스크롤되고, 새 말풍선이 생길 때 맨 아래로 내려간다
- [ ] 새 말풍선이 짧게 fade-in 된다. 그 밖의 움직임이 없다
- [ ] 고객을 `C002`로 바꾸면 말풍선이 모두 사라지고 안내 문구가 다시 보인다
- [ ] UI_GUIDE 금지 사항(blur, 그라데이션 텍스트, 보라/인디고, 글로우, "Powered by AI" 배지)이 보이지 않는다
- [ ] 포인트 색(teal-700)이 전송 버튼·포커스 테두리에 쓰였다

정리:

- [ ] dev 서버를 끈다
- [ ] `git status --short`에 `frontend/AGENTS.md`, `frontend/CLAUDE.md`, 그 밖의 새 파일이 없다
- [ ] 어긋난 점이 있으면 이 step을 completed로 바꾸지 말고, 고칠 내용을 담은 pending step을 step 9 앞에 추가한 뒤 다시 실행한다
