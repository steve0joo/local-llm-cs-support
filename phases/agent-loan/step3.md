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

수정 가능한 범위는 `backend/training/loan/`과 `backend/tests/loan/`뿐이다. 실제 AI Hub 데이터는 저장소 밖에 있지만(2026-09-28 구조 확인), **이 step은 합성 픽스처로 로직만 검증한다.** 실제 데이터를 저장소 안에 복사하거나 테스트에서 읽지 마라.

**테스트를 먼저** 작성한다(TDD 가드).

1. `backend/tests/loan/test_prepare.py` — 픽스처는 테스트 안에서 `tmp_path`에 합성 JSON으로 만든다. 실제 데이터·가공본을 저장소에 넣지 마라.
2. `backend/training/loan/prepare.py`
   ```python
   TOPIC = "대출문의(만기/연장/조회등)"   # 실제 데이터 값 — "조회"와 "등" 사이에 공백이 없다(docs의 표기와 다름)
   def iter_conversations(raw_dir: Path, split_path: Path, split: str = "train") -> Iterator[dict]: ...
   def to_messages(item: dict) -> list[dict]: ...        # system → user → assistant → user → assistant(목표)
   def is_clean(item: dict) -> bool: ...                 # 정제 규칙
   def infer_extendable(output: str, rng: random.Random) -> bool | None: ...  # 답변에 맞는 연장 가능 값, None이면 제외
   def build_dataset(raw_dir: Path, split_path: Path, out_path: Path, split: str = "train", limit: int | None = None) -> int: ...  # 기록한 샘플 수 반환
   ```
   - 원천은 `split_path`(`{source_id: "train"|"val"|"test"}`)의 해당 분할 중 `consulting_topic == TOPIC`인 항목이다.
   - **원본 필드 구조는 실제 데이터로 확인했다(2026-09-28, 은행 Training 라벨링).** 파일 하나가 상담 하나이고 `qa_data`에는 QA가 1건 들어 있다. 위치는 `source.source_id`, `consulting.consulting_topic`, `qa_data[0].qa_topic`(QA 단위 주제, `consulting_topic`과 값이 다를 수 있음), `qa_data[0].input.question`·`input.answer`·`input.follow_up_question`, `qa_data[0].output`이다. 필드 접근은 `_extract_turns(item)` 같은 **한 곳의 어댑터 함수로 모은다**. 주제 필터에 `consulting_topic`과 `qa_topic` 중 어느 것을 쓸지는 팀 합의 전이므로, 어느 필드를 쓸지 고르는 코드도 어댑터 한 곳에만 둔다.
   - 실제 원본에는 `●●●`·`★★`·`OO` 같은 익명화 기호가 이미 들어 있고 `mask()`는 이를 처리하지 않는다. 이 step에서 기호를 토큰으로 바꾸는 규칙을 만들지 마라(계약 4 합의 대상). 요약에 "익명화 기호 미처리"라고 적어라.
   - 추론 입력과 맞추기 위해(LN-006) **마지막 user 발화 뒤에 `prompt.build_messages`와 같은 형식의 "대출 정보"·"사용할 수 있는 슬롯" 줄을 붙인다**. 대출 종류·만기일은 합성 고정값(종류는 일반 명칭)을 쓰고, 원금 숫자는 넣지 않는다. **연장 가능 값은 고정하지 않고 아래 규칙으로 답변 내용에 맞춰 채운다.** 시스템 메시지는 `prompt.SYSTEM_PROMPT`를 그대로 쓴다.
   - **연장 가능 값 규칙** — `infer_extendable(output: str, rng: random.Random) -> bool | None`
     - 이유: 정보 줄이 "연장 가능=예"인데 답변이 "연장 불가"라고 하거나 그 반대이면 모델이 모순을 학습하고, 런타임 검증(LN-004 d)과도 어긋난다. 실제 데이터에서 숫자·서류명 정제를 통과한 대출 답변 6,225건 중 1,921건(31%)이 부정 표현 없이 "가능"이 든 문장을 포함해 `extendable=false` 검사에 걸린다(2026-09-28 측정). 그래서 값을 고정할 수 없다.
     - 문장은 `validate`와 같은 기준(`.`·`!`·`?`·줄바꿈)으로 나눈다. **긍정** = "가능"이 있고 부정 표현(불가·않·어렵·없)이 없는 문장이 있음. **부정** = "불가"·"어렵"이 있는 문장, 또는 "가능"과 "않"·"없"이 함께 있는 문장이 있음.
     - 긍정만 있으면 `True`(연장 가능=예), 부정만 있으면 `False`(연장 가능=아니오(사유는 알 수 없음)), 둘 다 있으면 `None`(모호하므로 **샘플에서 제외**), 둘 다 없으면 `rng`로 정한다. `rng`는 `source_id`로 시드를 고정해 같은 입력이면 항상 같은 값이 나오게 한다.
     - 정보 줄 형식은 `prompt.build_messages`와 같아야 한다("연장 가능=아니오(사유는 알 수 없음)" 포함).
     - 모호해서 제외한 샘플 수는 `build_dataset`이 알 수 있게 하고(로그 또는 반환 요약), 완료 요약에 적는다. 부정 표현 목록은 `validate`의 값과 같아야 하며, 어긋남은 아래 불변식 테스트가 잡는다.
   - 모든 user·assistant 발화에 `app.masking.mask()`를 적용한 `masked_text`를 쓴다. 원본 텍스트를 결과 파일에 남기지 마라.
   - `is_clean` 정제 규칙(`output` 기준, `input`에 없는 것이 있으면 **제외**):
     - 숫자(금액·퍼센트·기간)
     - `validate.DOCUMENT_KEYWORDS`의 구체적인 서류명 키워드("서류"라는 일반 단어는 제외 대상이 아니다 — LN-002)
     - 일반 명칭이 아닌 상품명으로 보이는 표현(예: `○○대출`, `○○통장`처럼 일반 명칭 허용 목록 `신용대출`·`주택담보대출`·`전세자금대출` 등에 없는 것). 휴리스틱이다. 규칙을 코드 상수로 두고 요약에 적는다.
   - 출력은 JSONL(`{"messages": [...]}` 한 줄 한 대화) — `backend/data/processed/loan_train.jsonl`이 기본 경로다. `backend/data/`는 gitignore 대상이다.
   - CLI 진입점(`python -m training.loan.prepare --raw ... --split ... --out ... [--limit N]`)을 둔다.

## 테스트로 고정할 핵심 규칙

- 분할 필터: `val`·`test` 항목이나 다른 `consulting_topic` 항목이 `train` 결과에 섞이지 않는다(누수 방지 — ADR-008)
- 마스킹: 합성 입력에 주민번호·계좌번호·금액 원본이 있으면 결과 JSONL 어디에도 그 원본 문자열이 없다
- 정제: `output`에 `input`에 없는 퍼센트("연 3.5%")·서류명 키워드("재직증명서")·일반 명칭 밖 상품명이 있으면 제외되고, `input`에도 같은 값이 있으면 유지된다
- 연장 가능 값: 답변이 "연장 가능 대상입니다"면 정보 줄이 "연장 가능=예", "연장은 불가합니다"면 "연장 가능=아니오(사유는 알 수 없음)"다. "연장은 불가합니다. 다른 조건은 가능합니다."처럼 긍정·부정이 함께 있으면 결과에서 제외된다. 판정 표현이 없는 답변은 같은 `source_id`로 여러 번 돌려도 값이 같다
- 연장 불변식: 숫자가 없는 합성 답변들로 만든 결과 JSONL에서 정보 줄이 "연장 가능=아니오"인 모든 샘플의 마지막 assistant 발화는 `validate.is_valid_output(..., extendable=False)`를 통과한다(부정 표현 목록이 `validate`와 어긋나면 이 테스트가 실패한다). 숫자가 있는 답변은 `is_clean`이 입력에도 있는 숫자를 허용하는 반면 `is_valid_output`은 숫자를 전부 막아 결과가 다르므로 이 불변식의 대상이 아니다
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
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"` (어댑터 함수명, 정제 규칙 상수, 기본 출력 경로 포함. 필드 구조는 실제 데이터로 확인했으나 주제 필드(`consulting_topic` vs `qa_topic`)와 익명화 기호 처리는 미정임을 명시. 연장 가능 값 규칙과 모호해서 제외한 샘플 수도 포함)
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- AI Hub 원본·가공본·합성이 아닌 실제 발화를 저장소에 커밋하거나 테스트 픽스처로 넣지 마라. 이유: 데이터셋 이용조건이 제3자 제공 금지이며 저장소는 공유된다(PRD 제약).
- `masking`을 재구현하지 마라. 이유: 학습과 추론의 마스킹 규칙이 어긋나면 분포가 달라진다(계약 4).
- train 학습 스크립트(`train.py`)를 이 step에서 만들지 마라. 이유: GPU가 필요하고 다음 human step에서 사람이 실제 데이터 구조를 확인한 뒤 진행한다.
- 다른 영역의 `backend/training/` 폴더나 `training/common`을 고치지 마라. 이유: 소유자가 다르다(팀원C).
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
