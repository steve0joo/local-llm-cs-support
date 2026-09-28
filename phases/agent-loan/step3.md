# Step 3: train-prepare

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/ARCHITECTURE.md` (학습 파이프라인, 계약 4 마스킹 토큰)
- `/docs/ADR.md` (ADR-005 정제 원칙, ADR-008 공통 분할)
- `/docs/PRD.md` (제약 — 데이터·가중치는 git 금지)
- `/docs/agent-loan/ARCHITECTURE.md` (학습 데이터 절)
- `/docs/agent-loan/ADR.md` (LN-002)
- `/docs/agent-balance/ARCHITECTURE.md` (학습 데이터 절 — 대화 구성·마스킹·정제 규칙의 기준)
- `/backend/app/masking/` (**팀원C 소유** — `mask(text) -> MaskResult(masked_text, mask_map)`)
- `/backend/app/agents/loan/prompt.py` (SYSTEM_PROMPT — 학습 대화의 system 메시지로 재사용)

## 사전 점검 (가장 먼저)

`backend/app/masking/`가 없으면 아무것도 만들지 말고 `blocked`로 표시한다.
`blocked_reason`: "팀원C의 masking 모듈이 main에 머지되어야 함. 학습 입력과 추론 입력의 분포를 맞추려면 학습도 같은 mask()를 써야 한다(계약 4)".

## 작업

수정 가능한 범위는 `backend/training/loan/`과 `backend/tests/loan/`뿐이다. **실제 AI Hub 데이터는 아직 없다.** 이 step은 합성 픽스처로 로직만 검증한다.

**테스트를 먼저** 작성한다(TDD 가드).

1. `backend/tests/loan/test_prepare.py` — 픽스처는 테스트 안에서 `tmp_path`에 합성 JSON으로 만든다. 실제 데이터·가공본을 저장소에 넣지 마라.
2. `backend/training/loan/prepare.py`
   ```python
   TOPIC = "대출문의(만기/연장/조회 등)"
   def iter_conversations(raw_dir: Path, split_path: Path, split: str = "train") -> Iterator[dict]: ...
   def to_messages(item: dict) -> list[dict]: ...        # system → user → assistant → user → assistant(목표)
   def is_clean(item: dict) -> bool: ...                 # 정제 규칙
   def build_dataset(raw_dir: Path, split_path: Path, out_path: Path, split: str = "train", limit: int | None = None) -> int: ...  # 기록한 샘플 수 반환
   ```
   - 원천은 `split_path`(`{source_id: "train"|"val"|"test"}`)의 해당 분할 중 `consulting_topic == TOPIC`인 항목이다.
   - **원본 필드명은 가정이다**(`consulting_topic`, `source_id`, `qa_data[].input.question`·`input.answer`·`input.follow_up_question`·`output`). 필드 접근은 `_extract_turns(item)` 같은 **한 곳의 어댑터 함수로 모은다**. 실제 데이터 구조가 다르면 그 함수만 고치면 되게 한다.
   - 모든 user·assistant 발화에 `app.masking.mask()`를 적용한 `masked_text`를 쓴다. 원본 텍스트를 결과 파일에 남기지 마라.
   - `is_clean` 정제 규칙(`output` 기준, `input`에 없는 것이 있으면 **제외**):
     - 숫자(금액·퍼센트·기간)
     - `validate.DOCUMENT_KEYWORDS`의 서류 키워드
     - 일반 명칭이 아닌 상품명으로 보이는 표현(예: `○○대출`, `○○통장`처럼 일반 명칭 허용 목록 `신용대출`·`주택담보대출`·`전세자금대출` 등에 없는 것). 휴리스틱이다. 규칙을 코드 상수로 두고 요약에 적는다.
   - 출력은 JSONL(`{"messages": [...]}` 한 줄 한 대화) — `backend/data/processed/loan_train.jsonl`이 기본 경로다. `backend/data/`는 gitignore 대상이다.
   - CLI 진입점(`python -m training.loan.prepare --raw ... --split ... --out ... [--limit N]`)을 둔다.

## 테스트로 고정할 핵심 규칙

- 분할 필터: `val`·`test` 항목이나 다른 `consulting_topic` 항목이 `train` 결과에 섞이지 않는다(누수 방지 — ADR-008)
- 마스킹: 합성 입력에 주민번호·계좌번호·금액 원본이 있으면 결과 JSONL 어디에도 그 원본 문자열이 없다
- 정제: `output`에 `input`에 없는 퍼센트("연 3.5%")·서류 키워드("재직증명서")·일반 명칭 밖 상품명이 있으면 제외되고, `input`에도 같은 값이 있으면 유지된다
- 어댑터 격리: 필드명을 바꾼 합성 데이터는 `_extract_turns`만 교체해 처리된다(다른 함수에 필드명 하드코딩 없음)
- `limit`이 결과 수를 제한한다

## Acceptance Criteria

```bash
cd backend && python -m pytest tests/loan/test_prepare.py --import-mode=importlib -q
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - 산출물 경로가 `backend/data/` 아래(gitignore)이고, 저장소에 데이터·가공본이 추가되지 않았는가? (`git status --short`로 확인)
   - 마스킹에 팀원C의 `app.masking.mask`를 그대로 import했는가(자체 정규식 복제 금지)?
   - 학습 스크립트가 `backend/training/loan/` 밖에 만들어지지 않았는가?
3. 결과에 따라 `phases/agent-loan/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"` (어댑터 함수명, 정제 규칙 상수, 기본 출력 경로 포함. 원본 필드명이 가정임을 명시)
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- AI Hub 원본·가공본·합성이 아닌 실제 발화를 저장소에 커밋하거나 테스트 픽스처로 넣지 마라. 이유: 데이터셋 이용조건이 제3자 제공 금지이며 저장소는 공유된다(PRD 제약).
- `masking`을 재구현하지 마라. 이유: 학습과 추론의 마스킹 규칙이 어긋나면 분포가 달라진다(계약 4).
- train 학습 스크립트(`train.py`)를 이 step에서 만들지 마라. 이유: GPU가 필요하고 다음 human step에서 사람이 실제 데이터 구조를 확인한 뒤 진행한다.
- 다른 영역의 `backend/training/` 폴더나 `training/common`을 고치지 마라. 이유: 소유자가 다르다(팀원C).
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
