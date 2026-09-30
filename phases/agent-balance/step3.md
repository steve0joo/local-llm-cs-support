# Step 3: train-prepare

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/ARCHITECTURE.md` (계약 4 마스킹 토큰, 학습 파이프라인)
- `/docs/ADR.md` (ADR-005 정제 원칙, ADR-008 공통 분할)
- `/docs/router/ADR.md` (RT-005 학습 데이터 규칙 — 분할·라벨·금액 정규화)
- `/docs/agent-balance/ARCHITECTURE.md` ("학습 데이터" 절 전체와 "`prepare.py` 인터페이스 (3차)", "테스트로 고정할 핵심 규칙"의 `test_prepare.py`)
- `/docs/agent-balance/ADR.md` (BAL-006 마스킹 게이트, BAL-008)
- `/backend/training/balance/MAC_TRAINING.md` (선행 조건 1~5)
- `/backend/training/common/split.py` (**팀원C 소유** — `TL_ZIP`·`VL_ZIP`·`OUT_PATH`, `split.json` 형식 `{source_id: "train"|"val"|"test"}`)
- `/backend/training/balance/train.py` (`check_dataset` — 출력 형식 기준)
- `/backend/app/masking/` (**팀원C 소유** — `mask(text) -> MaskResult(masked_text, mask_map)`)
- `/backend/app/agents/balance/prompt.py`, `validate.py`, `intent.py`, `resolve.py`, `mock_api.py` (step 1·2 산출물 포함)

## 사전 점검 (가장 먼저)

`from app.masking import mask`가 실패하면 아무것도 만들지 말고 `blocked`로 표시한다. `blocked_reason`: "app.masking import 실패 — 학습 데이터는 게이트웨이와 같은 mask()로만 만든다(계약 4, BAL-006)".

## 작업

수정 가능한 범위는 `backend/training/balance/`, `backend/tests/balance/`, `docs/agent-balance/`, `backend/training/balance/MAC_TRAINING.md`뿐이다. **실제 AI Hub 데이터로 실행하지 않는다.** 실제 실행은 step 5(사람)가 한다.

**테스트를 먼저** 작성한다(TDD 가드).

1. `backend/tests/balance/test_prepare.py` — 픽스처는 `tmp_path`에 만든다: 실제 원본과 같은 구조의 JSON(`source.source_id`, `consulting.consulting_category="은행"`·`consulting_topic`, `qa_data[0].qa_topic`·`input.question`·`input.answer`·`input.follow_up_question`·`output`)을 담은 zip 두 개와 `split.json`. ARCHITECTURE `test_prepare.py` 항목을 모두 테스트로 만든다.
2. `backend/training/balance/prepare.py` — ARCHITECTURE "`prepare.py` 인터페이스 (3차)"의 상수·함수 시그니처를 그대로 따른다.
   ```python
   TOPIC = "거래내역/잔액조회"
   OUT_DIR: Path
   SPLIT_FILES = {"train": "train.jsonl", "val": "valid.jsonl", "test": "test.jsonl"}
   BALANCE_QUESTIONS: tuple[str, ...]; TRANSACTION_QUESTIONS: tuple[str, ...]   # 각 20개 이상
   BALANCE_ANSWERS: tuple[str, ...];   TRANSACTION_ANSWERS: tuple[str, ...]     # 각 5개 이상
   def load_qas(zip_path: Path) -> Iterator[dict]: ...
   def normalize_amounts(text: str) -> str: ...
   def build_sample(qa: dict) -> dict | None: ...
   def synth_samples() -> dict[str, list[dict]]: ...
   def build_dataset(split_path: Path, out_dir: Path, zip_paths: list[Path]) -> dict[str, int]: ...
   def main(argv: list[str] | None = None) -> None: ...   # python -m training.balance.prepare, 기본값은 split.py의 경로와 OUT_DIR
   ```
   핵심 규칙(어기면 안 된다):
   - 모든 발화는 `app.masking.mask()`를 거친 `masked_text`만 결과에 쓴다. 원본 텍스트를 결과 파일에 남기지 않는다.
   - 입력 메시지는 `prompt.build_messages`로 만든다(추론과 같은 system·슬롯 줄). 직접 문자열을 조립하지 않는다.
   - 제외 규칙은 ARCHITECTURE의 두 가지(`validate.is_valid(output, (), ())`, 상품명 휴리스틱)다. 원본 필드 접근은 `load_qas` 한 곳에만 둔다.
   - 결정적이어야 한다. `random`을 쓰지 않는다. 같은 입력이면 같은 파일이 나온다.
   - 원본 zip 경로와 `split.json` 경로는 `training.common.split`에서 import한다.
3. 문서: 구현이 ARCHITECTURE와 달라진 점이 있으면 `docs/agent-balance/ARCHITECTURE.md`를 고치고 summary에 `deviation:`으로 적는다. `MAC_TRAINING.md`의 "현재 `prepare.py`는 아직 구현되지 않았다"와 `docs/agent-balance/ARCHITECTURE.md`의 디렉토리 구조 `prepare.py(3차 예정, BAL-008)`·"`prepare.py` 인터페이스 (3차)" 제목의 "3차" 표시를 지운다. "학습 데이터" 절의 "`prepare.py`와 실제 가공 데이터는 아직 없으므로" 문장은 "실제 가공 데이터는 step 5에서 만든다"로 고친다.

## Acceptance Criteria

```bash
(cd backend && .venv/bin/python -m pytest tests/balance/test_prepare.py tests/balance/test_train.py -q)
test -z "$(git ls-files backend/data backend/training/balance/outputs)"
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `prepare.py`가 `backend/training/balance/` 안에 있고, 산출물 기본 경로가 `backend/data/processed/balance/`(gitignore)인가?
   - `app.masking.mask`를 그대로 import했는가(자체 정규식·fallback 마스킹 없음)?
   - 합성 질문이 모두 `classify_intent`로 자기 의도가 되고, 합성 응답이 모두 `is_valid`를 통과하는가(테스트로 확인)?
   - `git status --short`에 데이터·가공본이 없는가?
3. 결과에 따라 `phases/agent-balance/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"` (합성 질문·응답 개수, 분할별 합성 샘플 수, 상품명 허용 목록 상수 이름 포함)
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 실제 AI Hub 데이터나 가공본을 테스트·저장소에 넣지 마라. 이유: 데이터셋 이용조건상 제3자 제공 금지이고(CLAUDE.md CRITICAL), 다른 기기에는 데이터가 없다.
- 마스킹 import 실패 시 임시 정규식이나 fallback 마스킹으로 진행하지 마라. 이유: 학습 입력과 추론 입력의 토큰이 달라진다(계약 4, BAL-006).
- 합성 응답에 금리·수수료·기간·메뉴 이름·상품명·서류를 넣지 마라. 이유: 지어낸 사실 1건이 즉시 불합격이고, 모델이 템플릿의 사실을 그대로 배운다(BAL-008).
- 합성 샘플에 mock 잔액·계좌번호 값을 넣지 마라. 이유: 모델은 `{{슬롯}}`만 써야 한다(CLAUDE.md CRITICAL — mock 금액은 프롬프트 금지).
- `training/common/split.py`, `app/masking/`, `app/agents/balance/`의 코드를 고치지 마라. 이유: 앞의 둘은 팀원C 소유이고, 에이전트 코드는 이 step 범위가 아니다(`SYSTEM_PROMPT`가 바뀌면 학습·추론 입력이 어긋난다).
- MLX LM·Ollama를 호출하지 마라. 이유: 학습은 step 5(사람) 범위다.
- 기존 테스트를 깨뜨리지 마라
- git commit을 하지 마라. 이유: 커밋은 execute.py가 AC 재검증 후 수행한다
