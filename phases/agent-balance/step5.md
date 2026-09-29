# Step 5: train-export (human)

이 step은 사람이 직접 수행한다. executor는 여기서 멈춘다. 체크리스트를 끝낸 뒤 `phases/agent-balance/index.json`의 step 5 `status`를 `"completed"`로 바꾸면 이어서 실행된다.

사람이 하는 이유: 원본 데이터 접근, 약 8GB 베이스 다운로드, 수십 분 이상 걸리는 학습, llama.cpp 빌드·변환은 세션 타임아웃과 맞지 않고 결과를 사람이 읽어 판단해야 한다.

## 읽어야 할 파일

- `/backend/training/balance/MAC_TRAINING.md` (명령의 기준 — 여기 명령을 그대로 따른다)
- `/docs/agent-balance/ARCHITECTURE.md` ("학습 데이터", "`prepare.py` 인터페이스", "Modelfile")
- `/docs/agent-balance/ADR.md` (BAL-006, BAL-008)
- `/backend/training/balance/prepare.py`, `/backend/models/balance/Modelfile` (step 3·4 산출물)
- 참고: `git show origin/feat-agent-interest:backend/training/interest/export.md` (팀원B의 llama.cpp 설치·변환 기록)

## 체크리스트

데이터:

- [ ] `backend/data/raw/TL_은행.zip`·`VL_은행.zip` 링크를 만들었다(`MAC_TRAINING.md` 선행 조건 1)
- [ ] `cd backend && .venv/bin/python -m training.common.split` → `data/processed/split.json` 생성
- [ ] `cd backend && .venv/bin/python -m training.balance.prepare` → 분할별 기록 수를 적어 둔다(참고: AI Hub 통과분은 약 2,000건)
- [ ] `valid.jsonl`에서 20건 이상을 읽었다: 원본 개인정보 없음, 슬롯 응답은 `{{account_label}}` 등 허용 슬롯만, 지어낸 금리·상품명·서류 없음, 존댓말. 문제가 있으면 멈추고 `prepare.py` 수정 step을 추가한다

학습:

- [ ] `.venv-train` 생성, `requirements-mac.txt` 설치
- [ ] `mlx_lm convert`로 `Qwen/Qwen3-4B-Instruct-2507` 4bit MLX 베이스 생성, `config.json`에 `quantization` 확인
- [ ] `train check` 통과 → `train --iters 100` 소규모 학습에서 loss가 줄고 메모리가 24GB 안에서 도는지 확인
- [ ] 반복 수를 정해 본 학습 → `train test`로 test loss 기록

변환·등록:

- [ ] `mlx_lm fuse --dequantize` → llama.cpp `convert_hf_to_gguf.py` → `llama-quantize` Q4_K_M
- [ ] 결과를 `backend/models/balance/cs-balance.gguf`로 복사
- [ ] `ollama create cs-balance -f backend/models/balance/Modelfile` 성공, `ollama run cs-balance "잔액 알려줘"`가 한국어 존댓말로 답한다
- [ ] 변환이나 로딩이 실패하면 완료 처리하지 않고 원인을 `MAC_TRAINING.md`에 적는다(BAL-006)

기록·커밋 위생:

- [ ] 베이스 리비전, MLX LM 버전, 분할별 샘플 수(AI Hub·합성), 반복 수, test loss를 `docs/agent-balance/PRD.md` "구현 진행"에 한 줄로 적었다
- [ ] `git status --short`에 `.gguf`·`.safetensors`·`backend/data/`·`training/balance/outputs/`가 없다
- [ ] 문서만 `docs(agent-balance): cs-balance 첫 학습 기록` 형식으로 커밋했다
