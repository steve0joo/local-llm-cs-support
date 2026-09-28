# Step 1: prompt-validate

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/ARCHITECTURE.md` (계약 3~5: 에이전트 인터페이스, 마스킹 토큰·슬롯, 모델 호출)
- `/docs/ADR.md`
- `/docs/agent-loan/PRD.md`
- `/docs/agent-loan/ARCHITECTURE.md` (handle() 흐름 5~6단계, 테스트 절)
- `/docs/agent-loan/ADR.md` (LN-001, LN-002, LN-004, LN-005)
- `/backend/app/agents/loan/mock_api.py`, `/backend/app/agents/loan/mock_data.json` (step 0 산출물 — 대출 dict의 키와 값 형태)

step 0에서 만들어진 코드를 읽고 대출 dict 구조(`loan_id, product_type, principal_remaining, maturity_date, extendable`)를 이해한 뒤 작업하라.

## 작업

수정 가능한 범위는 `backend/app/agents/loan/`과 `backend/tests/loan/`뿐이다. 이 step은 순수 함수만 만든다. `llm`·`agents/base.py`·`masking`을 import하지 마라(아직 없을 수 있다).

**테스트를 먼저** 작성한다(TDD 가드).

1. `backend/tests/loan/test_validate.py`, `backend/tests/loan/test_prompt.py`
2. `backend/app/agents/loan/validate.py`
   ```python
   DOCUMENT_KEYWORDS: tuple[str, ...]        # ("서류", "증명서", "등본", "재직", "소득") 이상
   ALLOWED_SLOTS: tuple[str, ...]            # ("loan_label", "principal_remaining")
   def is_valid_output(text: str, *, maturity_date: str, extendable: bool) -> bool: ...
   ```
   `False`가 되는 조건(하나라도 해당) — `docs/agent-loan/ARCHITECTURE.md` handle() 6단계 a~d가 기준이다:
   - a. 허용 날짜(`maturity_date`의 `YYYY-MM-DD`, `YYYY년 M월 D일` 표기)를 지운 뒤에도 아라비아 숫자가 남음
   - b. `ALLOWED_SLOTS` 밖 이름의 `{{...}}`가 있음
   - c. `DOCUMENT_KEYWORDS` 중 하나가 있음
   - d. `extendable=False`인데 부정 표현(불가·않·어렵·없) 없이 "가능"이 있음
3. `backend/app/agents/loan/prompt.py`
   ```python
   NO_LOAN_TEXT = "고객님 명의로 조회되는 대출이 없습니다."
   SYSTEM_PROMPT: str
   def build_messages(history: list[dict], masked_text: str, loan: dict) -> list[dict]: ...
   def build_slots(loan: dict) -> dict[str, str]: ...      # {"loan_label": "신용대출", "principal_remaining": "12,000,000원"}
   def fallback_text(loan: dict) -> str: ...               # ARCHITECTURE의 기본 문장 규칙 그대로
   ```
   - `build_messages` 순서: system → history → user(`masked_text` + 대출 정보 줄 + 슬롯 안내 줄). 대출 정보 줄 형식은 ARCHITECTURE 5단계 예시를 따르고, 연장 불가는 `연장 가능=아니오(사유는 알 수 없음)`.
   - `SYSTEM_PROMPT`에는 반드시 담는다: 존댓말 상담 톤 / 금리·서류 요건·연장 사유를 지어내지 말고 상담원 확인을 안내 / 금액은 `{{principal_remaining}}` 슬롯으로만 / 제공된 정보에 없는 숫자 금지.

## 테스트로 고정할 핵심 규칙

- `is_valid_output`: "금리는 연 3.5%입니다", "1,200만원입니다", "2027-04-01까지 연장됩니다"(허용 만기일이 다른 날짜일 때), "3영업일 걸립니다", "재직증명서가 필요합니다", "{{balance}}입니다" → 모두 `False`
- `is_valid_output`: "만기일은 2027-03-31입니다. {{principal_remaining}} 남았습니다." → `True`. 같은 날짜를 "2027년 3월 31일"로 쓴 경우도 `True`
- `extendable=False`: "연장이 가능합니다" → `False`, "연장이 어렵습니다"·"연장 가능으로 조회되지 않습니다" → `True`
- `build_messages` 결과 전체 문자열에 `12000000`·`12,000,000`이 없다(원금은 프롬프트 금지 — LN-001)
- `build_messages`는 전달받은 `history`를 변경하지 않는다
- `build_slots`가 만드는 금액 문자열은 `12,000,000원`, `85,000,000원` 형태다
- `fallback_text`는 `extendable` 참/거짓에 따라 문구가 다르고, 항상 `{{loan_label}}`·`{{principal_remaining}}`를 포함하며 `is_valid_output(fallback_text(loan), ...)`가 `True`다(기본 문장이 자기 검증에 걸리면 무한히 대체되는 버그다)

## Acceptance Criteria

```bash
cd backend && python -m pytest tests/loan/test_validate.py tests/loan/test_prompt.py --import-mode=importlib -q
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - ARCHITECTURE.md 디렉토리 구조(`validate.py`, `prompt.py`)를 따르는가?
   - 검증이 금지 목록이 아니라 **허용 목록 방식**(LN-004)인가?
   - `llm`·`agents.base`·`masking`을 import하지 않았는가?
3. 결과에 따라 `phases/agent-loan/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"` (함수 시그니처와 서류 키워드 목록을 요약에 포함)
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 원금 숫자를 프롬프트에 넣지 마라. 이유: 마스킹 필수 항목이 금액이고, 금액은 슬롯으로만 전달한다(PRD 핵심 기능 6, LN-001).
- 검증을 "금액 형태 정규식 + 퍼센트"만으로 만들지 마라. 이유: 만기일 표기와 구분이 안 되고 지어낸 날짜·기간을 놓친다(LN-004).
- 시스템 프롬프트에 실제 상품명·금리 예시를 넣지 마라. 이유: 모델이 예시를 그대로 답할 수 있고, 사실 생성 1건이 즉시 불합격이다.
- 다른 영역 소유 파일(`agents/base.py`, `llm/`, `masking/`)을 만들거나 고치지 마라. 이유: 소유자가 팀원C다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
