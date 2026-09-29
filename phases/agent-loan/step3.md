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
   NO_EXTEND_COPIES = 2                                   # "아니오" 판정 샘플을 train에 넣는 횟수
   def build_dataset(raw_dir: Path, split_path: Path, out_path: Path, split: str = "train", limit: int | None = None) -> int: ...  # 기록한 샘플 수 반환
   ```
   - 원천은 `split_path`(`{source_id: "train"|"val"|"test"}`)의 해당 분할 중 `consulting_topic == TOPIC`인 항목이다.
   - **원본 필드 구조는 실제 데이터로 확인했다(2026-09-28, 은행 Training 라벨링).** 파일 하나가 상담 하나이고 `qa_data`에는 QA가 1건 들어 있다. 위치는 `source.source_id`, `consulting.consulting_topic`, `qa_data[0].qa_topic`(QA 단위 주제, `consulting_topic`과 값이 다를 수 있음), `qa_data[0].input.question`·`input.answer`·`input.follow_up_question`, `qa_data[0].output`이다. 필드 접근은 `_extract_turns(item)` 같은 **한 곳의 어댑터 함수로 모은다**. 주제 필터에 `consulting_topic`과 `qa_topic` 중 어느 것을 쓸지는 팀 합의 전이므로, 어느 필드를 쓸지 고르는 코드도 어댑터 한 곳에만 둔다.
   - 실제 원본에는 `●●●`·`★★`·`OO` 같은 익명화 기호가 이미 들어 있고 `mask()`는 이를 처리하지 않는다. 이 step에서 기호를 토큰으로 바꾸는 규칙을 만들지 마라(계약 4 합의 대상). 요약에 "익명화 기호 미처리"라고 적어라.
   - 추론 입력과 맞추기 위해(LN-006) **마지막 user 발화 뒤에 `prompt.build_messages`와 같은 형식의 "대출 정보"·"사용할 수 있는 슬롯" 줄을 붙인다**("사용할 수 있는 슬롯" 줄에는 `{{extendable_status}}`도 포함한다 — 2026-09-29, step 2에서 `build_messages`에 추가된 슬롯과 맞춘다). 대출 종류·만기일은 합성 고정값(종류는 일반 명칭)을 쓰고, 원금 숫자는 넣지 않는다. **연장 가능 값은 고정하지 않고 아래 규칙으로 답변 내용에 맞춰 채운다.** 시스템 메시지는 `prompt.SYSTEM_PROMPT`를 그대로 쓴다.
   - **연장 가능 값 규칙(2026-09-29 목적 재정의)** — `infer_extendable(output: str, rng: random.Random) -> bool | None`
     - **더는 "연장 가능 여부 사실을 모델에게 가르치는" 용도가 아니다.** 그 사실은 이제 `{{extendable_status}}` 슬롯으로 코드가 항상 정확히 채운다(`docs/agent-loan/ARCHITECTURE.md` handle() 4~6단계). 정보 줄이 "연장 가능=예"인데 학습 답변이 "연장 불가"라고 말하는 모순은 여전히 피해야 하지만, 그 이유는 이제 "모델이 슬롯을 무시하고 직접 반대되는 말을 지어내는 버릇을 학습하지 않게 하기 위해서"다. 즉 목적은 사실 전달이 아니라 **모델이 정보 줄과 어긋나는 사실을 지어내지 않는 습관을 가볍게 보강**하는 것이다.
     - 실제 데이터에서 숫자·서류명 정제를 통과한 대출 답변 6,225건 중 1,921건(31%)이 부정 표현 없이 "가능"이 든 문장을 포함해 `extendable=false` 검사에 걸린다(2026-09-28 측정). 그래서 정보 줄 값을 고정하면 이 비율만큼 모순 샘플이 섞인다.
     - 문장은 `validate`와 같은 기준(`.`·`!`·`?`·줄바꿈)으로 나눈다.
       - **긍정 문장** = "가능"이 있고 `불가`·`어렵`·`가능하지 않`·`가능하지 못`이 없는 문장. "서류 없이 신청이 가능"처럼 "없"·"않"이 다른 뜻으로 들어간 문장은 긍정이다(`validate`처럼 "없"·"않"만으로 부정 처리하면 이런 문장이 부정으로 잘못 분류된다).
       - **연장 불가 문장** = 같은 문장 안에서 "연장" 뒤 15자 이내에 `불가`·`어렵`·`가능하지 않`·`가능하지 못`이 나오는 문장. "불가"만 보면 "환불 불가"·"자동이체 발급 불가"처럼 연장과 무관한 문장이 걸러진다(실측: "불가"·"어렵" 키워드만으로는 419건이 잡혔지만 연장 문맥으로 좁히면 57건이다).
     - 긍정 문장만 있으면 `True`(연장 가능=예), 연장 불가 문장만 있으면 `False`(연장 가능=아니오(사유는 알 수 없음)), 둘 다 있으면 `None`(모호하므로 **샘플에서 제외**), 둘 다 없으면 `rng`로 정한다. `rng`는 `source_id`로 시드를 고정해 같은 입력이면 항상 같은 값이 나오게 한다.
     - 정보 줄 형식은 `prompt.build_messages`와 같아야 한다("연장 가능=아니오(사유는 알 수 없음)" 포함).
     - 긍정 판정이 `validate`의 "부정 표현 없는 가능"보다 넓으므로, "아니오"로 정해진 샘플은 항상 `validate.is_valid_output(..., extendable=False)`를 통과한다(2026-09-28 실측 57건 모두 통과). 이 관계가 깨지면 아래 불변식 테스트가 잡는다.
     - 실측 분포(2026-09-28, 대출 정제 통과 6,225건): 판정 없음 3,932 · 예 2,181 · **아니오 57** · 모호(제외) 55. 판정 없음의 "아니오"는 무작위로 배정된 값이므로 아래 복제 대상이 아니다.
     - 모호해서 제외한 샘플 수는 `build_dataset`이 알 수 있게 하고(로그 또는 반환 요약), 완료 요약에 적는다.
   - **"아니오" 샘플 2배 복제** — `NO_EXTEND_COPIES = 2`
     - **목적(2026-09-29 재정의): 가벼운 보강일 뿐이다.** 연장 가능 여부의 정확성은 이제 `{{extendable_status}}` 슬롯이 구조적으로 보장하므로, 이 복제로 그 사실을 가르치려는 게 아니다. 목적은 "연장이 안 되는 상황을 모델이 어떤 어투·구조로 말하는지"에 대한 노출을 조금 늘려서, 모델이 근거 없는 이유(서류 요건 등)를 지어내는 쪽으로 빠지지 않게 하는 정도다. 연장 불가를 실제로 말하는 답변이 57건(약 0.9%)뿐이라 이 노출 자체가 거의 없다.
     - 방법: 위 규칙으로 "아니오"가 나온 샘플(연장 불가 문장이 근거인 것만, 무작위로 배정된 "아니오"는 제외)을 결과에 **총 2번** 넣는다. 복제본의 대화(질문·답변)는 원본과 글자 그대로 같고 정보 줄의 만기일 합성값만 다르다. 만기일은 답변에 들어가지 않으므로 사실이 바뀌지 않는다. 대출 종류는 바꾸지 마라(질문 내용과 어긋날 수 있다).
     - 2배인 이유: 새 문장을 만들지 않으므로 사실 왜곡 위험이 없다. 3배 이상이면 학습 2~3에폭에 같은 답변을 6~9번 보게 되어 외울 위험이 커진다. 가벼운 보강이 목적이므로 그 이상 늘릴 이유도 없다.
     - **복제는 분할 후 `train`에서만 한다.** 분할 전에 하면 같은 답변이 `val`·`test`에 들어가 누수된다(ADR-008). `val`·`test`용 출력에는 복제를 넣지 마라.
     - **하지 말 것**: 문장 바꿔 쓰기(패러프레이즈), 템플릿 조합 생성, 그 밖에 실제 데이터에 없는 문장·조합을 만드는 방식. 이유: 사실 왜곡 위험이 커지고 데이터 이용조건 범위도 벗어날 수 있다. 바꿔 쓰기는 "불가"가 "어렵다"로 약해지는 등 의미가 바뀔 수 있다.
     - 한계: 이 보강은 작아서 말투 이상의 효과를 기대하지 않는다. 실제 연장 가능 여부가 화면에 맞게 나오는지는 학습이 아니라 `{{extendable_status}}` 슬롯 치환(구조적 보장)과 LN-004 d(텍스트 이중 검증)가 책임진다. 모델이 슬롯을 실제로 쓰는지는 C003 시나리오로 step 4·5에서 사람이 확인한다.
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
- 연장 가능 값: 답변이 "연장 가능 대상입니다"면 정보 줄이 "연장 가능=예", "연장은 불가합니다"면 "연장 가능=아니오(사유는 알 수 없음)"다. "연장은 불가합니다. 다른 조건은 가능합니다."처럼 긍정·연장 불가 문장이 함께 있으면 결과에서 제외된다. "서류 없이 연장 신청이 가능합니다"는 긍정이고, "환불은 불가합니다"처럼 연장과 무관한 "불가"는 연장 불가로 세지 않는다(판정 없음 → 무작위). 판정 표현이 없는 답변은 같은 `source_id`로 여러 번 돌려도 값이 같다
- 연장 불변식: 숫자가 없는 합성 답변들로 만든 결과 JSONL에서 정보 줄이 "연장 가능=아니오"인 모든 샘플의 마지막 assistant 발화는 `validate.is_valid_output(..., extendable=False)`를 통과한다. 숫자가 있는 답변은 `is_clean`이 입력에도 있는 숫자를 허용하는 반면 `is_valid_output`은 숫자를 전부 막아 결과가 다르므로 이 불변식의 대상이 아니다
- 복제: 연장 불가 문장이 근거인 "아니오" 샘플은 `train` 결과에 정확히 2번 나오고(질문·답변은 같고 만기일만 다름), "예"·판정 없음·무작위 "아니오" 샘플은 1번만 나온다. `val`·`test` 출력에는 복제가 없다. 복제본의 assistant 발화는 원본과 같다
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
