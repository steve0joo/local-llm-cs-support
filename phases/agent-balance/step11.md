# Step 11: self-check (human)

이 step은 사람이 직접 수행한다. executor는 여기서 멈춘다. 체크리스트를 끝낸 뒤 `phases/agent-balance/index.json`의 step 11 `status`를 `"completed"`로 바꾸면 이어서 실행된다.

## 읽어야 할 파일

- `/docs/PRD.md` (인수 기준 3~7)
- `/docs/agent-balance/PRD.md` ("사용자 여정" J1~J12, "자체 점검 셋" Q1~Q10, "영역 간 요청")
- `/docs/agent-balance/ARCHITECTURE.md` ("에러 처리·보안", "알려진 한계")
- `/backend/README.md` (구동 절차)

## 체크리스트

선행 조건:

- [ ] `cs-balance`가 Ollama에 등록돼 있다(step 10)
- [ ] `rm -f backend/logs/model_inputs.jsonl`로 로그를 비웠다
- [ ] 백엔드를 기본 호스트로 띄웠다: `cd backend && .venv/bin/uvicorn app.main:app --port 8000` (`--host 0.0.0.0` 금지 — ARCHITECTURE "에러 처리·보안")

자체 점검 셋(라우터 영향 없이 에이전트만):

- [ ] Q1~Q10을 `"choice": "balance"`로 보냈다. 예: `curl -s -X POST localhost:8000/api/chat -H 'Content-Type: application/json' -d '{"session_id":"q1","customer_id":"C001","message":"잔액 얼마 남았어요?","choice":"balance"}'`. Q9는 같은 `session_id`로 계좌 라벨을 `choice`와 함께 한 번 더 보낸다
- [ ] 각 문항을 ① 주제 적합 ② 지어내지 않음 ③ 존댓말로 판정했다. 9/10 이상
- [ ] 기본 문장으로 대체된 횟수를 셌다(대체가 많으면 합성 비중·검증 규칙을 다시 본다)
- [ ] C001 "제 계좌 110-1234-5678 잔액 알려줘"를 보낸 뒤 `grep -c -e 1234567 -e 1,234,567 -e 110-1234-5678 backend/logs/model_inputs.jsonl`이 0이다
- [ ] 한 요청의 첫 응답이 10초 안에 온다(모델 워밍업 뒤, 공통 인수 기준 7)

사용자 여정(챗봇 UI, `cd frontend && npm run dev` 후 `http://localhost:3000`):

- [ ] J1·J2·J4·J5·J6·J7이 PRD 표대로 된다. 화면 금액이 `1,234,567원` 형식이고 `{{`가 남지 않는다
- [ ] J8("입출금 계좌 잔액 알려줘")이 잔액으로, J9(되묻기 뒤 "생활비 계좌 잔액 알려줘")가 되묻기 반복 없이 답한다
- [ ] 거래내역이 줄마다 나뉘어 보인다(J3). `cs-router`가 없으면 J3은 R1 때문에 주제 없음 되묻기로 빠지는 것이 예상 동작이다
- [ ] Ollama를 멈추고 잔액을 물으면 "지금은 답변을 드릴 수 없습니다. 상담원 연결을 도와드릴까요?"가 보인다(J12, BAL-007)

기록:

- [ ] 결과(점수, 실패 문항과 원인, 대체 횟수, 응답 시간)를 `docs/agent-balance/PRD.md` "자체 점검 셋"·"사용자 여정" 아래에 적었다. 새로 찾은 키워드 누락은 알려진 한계 (e)의 후보로 적는다
- [ ] 9/10 미만이면 원인별로 수정 step을 `phases/agent-balance/index.json`에 pending으로 추가하고 review 전에 끝낸다
- [ ] `docs(agent-balance): 자체 점검 결과` 형식으로 커밋했다
