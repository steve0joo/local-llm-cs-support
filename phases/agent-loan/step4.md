# Step 4: train-model (human)

이 step은 사람이 직접 수행한다. executor는 여기서 멈춘다. 체크리스트를 끝낸 뒤 `phases/agent-loan/index.json`의 step 4 `status`를 `"completed"`로 바꾸면 이어서 실행된다.

## 읽어야 할 파일

- `/docs/ADR.md` (ADR-004 GGUF, ADR-005 QLoRA·공통 베이스·벤치마크)
- `/docs/ARCHITECTURE.md` (학습 파이프라인)
- `/docs/agent-loan/ARCHITECTURE.md` (학습 데이터 절)
- `/backend/training/loan/prepare.py` (step 3 산출물)

## 체크리스트

시작 전 선행 조건 (하나라도 안 되면 진행하지 않는다):

- [x] 팀원C가 만든 `training/common`의 `split.json`이 나왔다(ADR-008) — 2026-09-29 생성 완료(train 26,577·val 1,792·test 1,787)
- [x] ~~베이스 모델 크기가 팀에서 확정됐다~~ **해당 없음(2026-09-29 정정)**: 공통 PRD·ADR-005는 "4개 영역이 공통 베이스 1종을 쓴다"고 가정했지만, 실제로는 팀원B는 Qwen3 4B급, 팀원C는 Qwen3 1.7B급으로 각자 다른 크기를 쓰고 있다. 영역별로 크기를 따로 정한다. 대출문의는 이 step에서 정한다.
- [x] ~~공용 Windows 노트북(RTX 4060 8GB) 학습 순서가 내 차례다~~ **해당 없음(2026-09-29 정정)**: 공통 PRD·ADR-005는 "공용 노트북 1대를 순서대로 쓴다"고 가정했지만, 실제로는 각자 자기 노트북에서 학습한다(이 브랜치는 RTX 4060 Laptop 8GB, WSL2). 순서 조율이 필요 없다.

데이터 확인:

- [x] 실제 원본 구조가 `prepare.py`의 가정 필드명과 같은지 확인했다. 다르면 `_extract_turns`만 고치고 `docs/ARCHITECTURE.md` 학습 파이프라인 절과 영역 문서를 갱신했다 — step 3에서 확인 완료(구조는 가정과 일치, 주제 필드는 `qa_topic`으로 정함)
- [x] `prepare.py`로 `backend/data/processed/loan_train.jsonl`을 만들었다(val 분할도 별도로 생성) — 2026-09-29: train 10,168행, val 542행(`loan_val.jsonl`)
- [ ] val에서 샘플 20건 이상을 사람이 읽어 확인했다: 금리·서류 요건·상품명이 지어낸 값으로 남은 것이 없다 — **사람이 직접(`loan_val.jsonl`), 진행 중**

학습·변환:

- [x] `backend/training/loan/train.py`(QLoRA)를 작성했다(Transformers + PEFT + TRL, ADR-005). 결과물은 `backend/training/loan/outputs/`(gitignore)에 둔다 — 2026-09-29 작성(베이스 `Qwen/Qwen3-4B-Instruct-2507`, 대안 `Qwen/Qwen3-1.7B`, `--model`만 바꿔 교체. `max_length=1024`(실측), `assistant_only_loss=True`, micro-batch=1+grad_accum=16, `paged_adamw_8bit`+gradient checkpointing으로 8GB 대응). **아직 실행 안 함 — 사람이 WSL2에서 직접 돌린다.**
- [x] LoRA 병합 → GGUF(Q4_K_M) 변환 절차를 `backend/training/loan/export.md`에 적었다 — 2026-09-29 작성(`~/qlora_ft_ex/llama.cpp` 재사용 가능하도록 안내)
- [x] `backend/models/loan/Modelfile`을 작성했다(`.gguf`는 커밋 금지) — 2026-09-29 작성(SYSTEM은 `prompt.SYSTEM_PROMPT`와 동일 문구, TEMPLATE은 GGUF 내장 chat_template에 맡김)
- [ ] `ollama create cs-loan -f backend/models/loan/Modelfile` 성공 — 학습·변환 후 진행
- [ ] Mac(M4 Pro)에 같은 `.gguf`를 복사해 `ollama create cs-loan`으로 추론이 되는지 확인했다(인수 기준 8)
- [ ] 첫 응답이 10초 안에 오는지 라우터 → 에이전트 실제 경로로 한 번 쟀다(인수 기준 7)

커밋 위생:

- [ ] `git status`에 `.gguf`·`.safetensors`·`backend/data/`·`backend/logs/`가 없다
- [ ] 위 파일 중 커밋 대상(`train.py`, `export.md`, `Modelfile`)만 `feat(agent-loan): ...` 형식으로 커밋했다
