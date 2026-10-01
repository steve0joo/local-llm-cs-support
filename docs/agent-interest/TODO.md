# 할 일 목록: 이자/연체 에이전트 (팀원B)

> 기준일 2026-09-29. PRD 담당 범위·인수 기준, ARCHITECTURE "확인 필요", EVALUATION 남은 작업, REPORT_v03 다음 단계, FINETUNE 5절을 합쳐 다시 검토한 목록이다.
> 표시: ✅ 완료 · 🔶 일부 완료 · ⬜ 할 일 · ⏸ 다른 팀원·팀 합의 대기 · 💤 보류(결정됨)

## 1. 담당 범위별 진행 상황 (PRD)

| 범위 | 상태 | 내용 |
|---|---|---|
| mock 이자/연체 API와 데이터 | ✅ | `get_interest`, `/mock/customers/{id}/interest`, C001~C003(계약 6 값), `debit_account_id`. C004~C007은 평가용(합의 대기) |
| `agent.handle()` | 🔶 | 조회 → 슬롯 → 프롬프트 → `llm.generate` → 출력 검증 → 기본 문장, 모델 호출 실패 시 기본 문장, 자동이체 잔액 비교까지 구현했다. `base.py`·`llm`이 main에 없어 `test_agent.py`는 건너뛰는 상태(임시 스텁으로는 14개 통과). `__init__.py` export는 팀원C 스텁 병합 후 |
| `cs-interest` 모델 | 🔶 | 전처리·QLoRA 학습·평가는 v04까지 진행했다. GGUF 변환·Ollama 등록·응답 시간 측정은 아직 안 했다. Modelfile은 작성해 두었다(SYSTEM 일치 테스트 있음) |

## 2. 인수 기준 대비 (PRD, 루트 PRD 인수 기준)

| 기준 | 상태 | 근거·남은 일 |
|---|---|---|
| PM 고정 질문 10건 중 9건 이상 통과 | ⏸ | PM 셋이 아직 없다. 자체 점검: Golden 42 규칙 준수 v04 **88%**(v03 81%), hold30 사람 판정 대기 |
| 지어낸 사실 0건(금리 수치·연체 가산 이율·실제 상품명) | 🔶 | 서비스는 출력 검증이 기본 문장으로 바꿔 막는다. v04 모델 자체는 probe40에서 금리 수치 1건을 지어냈다(검증에 걸림) → v05 보강 |
| `pytest tests/interest` 통과 | ✅ | 306 passed, 1 skipped(`test_agent.py`, `base.py` 대기) |
| 응답 시간 10초 이내(Windows·Mac) | ⬜ | GGUF·Ollama 등록 후 측정. 참고: transformers 4bit 생성은 평균 약 5초 |
| 마스킹(모델 입력 로그에 원본 0건) | ⏸ | `app.masking` 병합 후 확인. 학습 데이터는 임시 마스킹으로 만들었다 |

## 3. 할 일

### 지금 할 것 (B 혼자 가능)
- [ ] **hold30 사람 판정** (v03·v04 같은 30문항): `training/interest/outputs/eval/ask-v03-hold.md`, `ask-v04-hold.md` — 사용자
- [ ] **v04 채택 판단** → `REPORT_v04.md` 작성(학습 곡선, Golden·AI Hub 질문 119·probe40·hold30 비교, 새 약점)
- [ ] **커밋·푸시**: 07 옵션(`--exclude-aihub-train`), `train --wandb`, `evaluate --wandb`·`--test-questions`, hold30, AI Hub 수정 도구, dry-run AI Hub 미출력, 문서
- [ ] **채점 오탐 수정**: "정상적으로 처리되었는지는 상담원에게"를 처리 주장으로 잡는 문제(`prepare._CLAIM`, `evaluate`)
- [ ] **검증 빈틈**: "연체 상태인가요?"가 연체 상태 질문으로 잡히지 않아 `{{overdue_amount}}`를 요구하지 않는다(`validate._OVERDUE_QUESTION`). 고치면 INT-004에 따라 데이터 재생성
- [ ] **v05 데이터 보강** (v04 평가에서 나온 약점)
  - [ ] 거절 뒤 "상담원에게 확인" 안내를 빼먹음(Golden 불합격 4건) → 거절 + 상담원 안내 모범 답
  - [ ] 이자 금액 질문에 슬롯 없이 상담원 안내만 함(probe-34) → 이자 금액은 반드시 `{{interest_due}}`
  - [ ] 원금균등·만기일시 설명이 틀림(hold30 109·121) → 상환 방식 설명 템플릿
  - [ ] 자동이체 원인 단정·잔액 비교 방향 오류(probe-22·23, hold30 124) → 비교 결과만 말하는 샘플
  - [ ] 변동금리 설명에 금리 수치를 지어냄(probe-40) → 용어 설명 템플릿 보강
  - [ ] 에폭 1 고정 검토(v04 val loss가 2에폭째 상승)
- [ ] **GGUF 변환 → Ollama `cs-interest` 등록 → 응답 시간 측정** (`training/interest/export.md`), Mac에서도 등록·추론 확인
- [ ] **사람 블라인드 평가** (`evaluate --blind v03-q v04-q`)
- [ ] **C007 다음 납부일 조정**: 2026-09-30이 지나면 모순 값이 된다. 시연 날짜가 정해지면 바꾸고 데이터 재생성

### 보류 (결정됨)
- [ ] 💤 **AI Hub 답 수정 227건** (`review.py --fix`, 사람 작업) → 08 데이터 → v05 이후 비교. 작업 시간이 길어 보류(2026-09-29)
- [ ] 💤 **AI Hub 통과 샘플 검수** (train 57 + val·test 18, `review.py`). v04는 AI Hub를 train에서 빼서 영향 없음
- [ ] 💤 로컬 LLM Judge (Judge 모델 선정 후, 선택)

### 다른 팀원·팀 합의 대기
- [ ] ⏸ **팀원C 스텁 병합**(`base.py`, `llm`, `masking`, 에이전트 `__init__.py`) → main 병합(사용자 요청 시) → `__init__.py`를 `agent`·`mock_router` export로 교체 → `test_agent.py` 실행
- [ ] ⏸ **`app.masking` 병합 후 학습 데이터 재생성**(임시 마스킹 교체), 재학습 필요 여부 판단
- [ ] ⏸ **공통 분할 `split.json`**, **TL(학습용) 원본** 수령(팀원C) → 데이터 재생성. AI Hub 샘플이 몇 배로 늘어남
- [ ] ⏸ **C004~C007 계약 6 확장 합의**: 대출문의(L003~L006)·잔액조회(A005~A008)·화면 고객 선택(FE-003)과 맞춰야 시연에 쓸 수 있다
- [ ] ⏸ **잔액조회 병합 후 `balance_source.get_accounts` 교체** → `app.agents.balance.mock_api.get_accounts`, `balance_mock.json` 삭제
- [ ] ⏸ **슬롯 `{{debit_balance}}` 공유**: 영역 문서(PRD)에 정의함. 프론트가 모든 슬롯을 치환하는지 확인
- [ ] ⏸ 계약 5 공통 예외 타입 → 에이전트의 예외 처리 범위 좁히기
- [ ] ⏸ 시스템 프롬프트 위치(messages vs Modelfile SYSTEM), 모델 1개 통합 여부(ADR-005, 10초 초과 시)
- [ ] ⏸ pytest `pythonpath` 공통 설정(`backend/pyproject.toml`)
- [ ] ⏸ 출력 검증을 허용 목록(대출문의 LN-004 방식)으로 바꿀지 결정
- [ ] ⏸ 학습 가상환경을 공통 버전(Python 3.11, trl 0.24, transformers 5.5, peft 0.19.1)에 맞출지 결정
- [ ] ⏸ PM 고정 질문 10건 수령 → 9/10 확인, `/api/chat` 통합 시나리오 확인

## 4. 완료한 일

| 분류 | 내용 |
|---|---|
| 서비스 코드 | mock API·데이터, `prompt`(시스템 프롬프트·이자 정보 줄·슬롯·기본 문장, 연체 시 납부 방법), `validate`(금액·금리·마스킹 토큰·슬롯 + 결과 보장·규정 단정·채널·절차·약속·서류·개인정보·마크다운·반복), `agent.handle()`, 모델 호출 실패 처리, 자동이체 잔액 비교(`balance_source`) |
| 학습 데이터 | AI Hub 전처리·제외 규칙(`prepare`), 합성 템플릿 21개 400건(모두 검수), 수동 모범 답 69문항 207건(q01~q70, 모두 확인), AI Hub 수정 대기열·도구(`fix_queue`, `review --fix`), 평가 질문 119건(`test_questions`), AI Hub train 제외 옵션, 데이터 폴더 04~07 |
| 학습 | 공식 Qwen 템플릿, 버전 폴더·데이터 해시·git 커밋 기록, 학습 곡선 wandb 기록, dry-run(AI Hub 미출력). v01~v04 학습 |
| 평가 | Golden 42(기대 조건·규칙 준수율), AI Hub test·질문 119, 블라인드 시트, probe40(wandb), ask30·weak30·debit10(학습에 사용), hold30(평가 전용, 학습 차단), 평가 요약 wandb 기록 |
| 결과 | v03: Golden 64% → 86%(옛 채점). v04: Golden 81% → 88%(새 채점, v03 대비), AI Hub 질문 119 금지 표현 70% → 17%, 검증 통과 33% → 82% |
| 문서 | PRD·ARCHITECTURE·ADR(INT-001~004)·TRAINING_DATA·TRAINING_DATA_PLAN·EVALUATION·FINETUNE·REPORT·REPORT_v03, 이 문서 |
