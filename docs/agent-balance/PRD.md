# PRD: 잔액조회 에이전트 (거래내역/잔액조회)

- 담당: 나 · 브랜치: `feat-agent-balance`
- 먼저 읽을 문서: `docs/PRD.md`, `docs/ARCHITECTURE.md`(계약 3~6, 코드·테스트 규칙, 통합 순서), `docs/ADR.md`

## 목표
"내 잔액 얼마야?" 같은 문의에 mock 계좌 API를 조회해, 금액이 슬롯으로 채워진 존댓말 상담 답변을 돌려준다.

## 담당 범위
1. mock 계좌 API와 데이터(`C001`~`C003`, 계약 6)
2. `agent.handle()` — 조회, 계좌 선택 되묻기, 프롬프트 구성, 출력 검증
3. `cs-balance` 모델 — 전처리, QLoRA 학습, GGUF 변환, Modelfile

## 사용자 스토리
1. 계좌 1개 고객(`C001`)이 "잔액 알려줘"를 보내면 한 번에 "입출금 ****5678 계좌의 현재 잔액은 1,234,567원입니다" 형태로 받는다.
2. 계좌 2개 고객(`C002`)은 "어느 계좌를 조회할까요?"와 계좌 선택 버튼을 받고, 하나를 누르면 잔액을 받는다.
3. 고객이 "최근 거래내역 보여줘"를 보내면 최근 5건을 받는다.
4. 고객이 계좌번호를 직접 입력하면(마스킹됨) 해당 계좌를 바로 조회한다. 계좌 매칭은 Python 코드가 `mask_map`으로 하고, 모델은 원본을 보지 않는다.
5. 조회 외 일반 문의(예: "잔액 조회는 어디서 해요?")는 학습된 상담 톤으로 안내하고, 모르면 상담원 연결을 안내한다.
   - 처리: 코드의 의도 판단이 `general`이면 계좌 결정·되묻기·슬롯 없이 모델(`cs-balance`)이 안내한다. 모델 입력에는 계좌 정보를 넣지 않는다(BAL-004).

## 슬롯
| 슬롯 | 예시 값 |
|------|--------|
| `{{account_label}}` | 입출금 ****5678 |
| `{{balance}}` | 1,234,567원 |
| `{{recent_transactions}}` | 여러 줄 텍스트 (날짜 · 적요 · ±금액) |

## 인수 기준 (이 영역 책임)
- PM 고정 질문 10건 중 9건 이상 통과(주제 적합 · 지어내지 않음 · 존댓말 톤)
- 잔액 시나리오에서 모델 출력에 `{{balance}}`가 있고, 실제 금액 숫자는 없다
- 지어낸 사실 0건. 금리·상품명·서류 요건을 지어내면 즉시 불합격
- `cd backend && pytest tests/balance` 통과(모델 호출은 목으로 대체)

## 1차 구현 범위
위 담당 범위·인수 기준은 영역 전체 기준이고 그대로 둔다. 1차 구현은 `agents/base.py` 스텁(공통 ARCHITECTURE 통합 순서 1단계)이 main에 오기 전에 만들 수 있는 순수 로직까지다(BAL-005).
- 이번에 한다
  - mock 계좌 API와 데이터: `mock_api.py`(`get_accounts`·`get_transactions`·`mock_router`), `mock_data.json`
  - 대상 계좌 결정 `resolve.py`: 라벨 클릭 확인, 계좌번호 매칭, 자동 선택, 되묻기 — plain dict 반환
  - 의도 판단 `intent.py`: balance / transactions / general 3분기
  - 프롬프트 구성 `prompt.py`: 시스템 프롬프트, messages, 슬롯, 기본 문장
  - 출력 검증 `validate.py`: 세 의도 공통 넓은 규칙
  - 모듈별 테스트 `tests/balance/test_<모듈>.py`. 완료 기준은 `cd backend && .venv/bin/python -m pytest tests/balance --import-mode=importlib -q` 전체 통과(스캐폴드 전 명령)
- 미룬다
  - `BalanceAgent.handle()`(`agent.py`)와 `__init__.py`의 `agent`·`mock_router` export — base.py 스텁 병합 뒤. 그 전까지 `__init__.py`는 빈 파일이다
  - `training/balance/prepare.py` 등 학습 데이터 전처리·학습, Modelfile, `cs-balance` 모델
  - PM 고정 질문 9/10 인수 — 모델과 `handle()`이 있어야 판정할 수 있다
  - 프론트엔드에서 슬롯 값 속 줄바꿈(`{{recent_transactions}}`) 표시 — frontend 영역 후속 메모

## 제외
- 이체·송금 등 실제 거래, 계좌 개설, 기간 지정 거래내역 검색, 잔액 카드/표 UI

## 확인 필요
- PM 고정 질문 10건은 PM이 작성한다. 담당자는 같은 형식의 자체 점검 셋으로 미리 확인한다.
