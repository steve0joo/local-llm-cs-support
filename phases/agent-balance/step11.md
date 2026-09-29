# Step 11: train-export (human)

이 step은 사람이 직접 수행한다. executor는 여기서 멈춘다. 체크리스트를 끝낸 뒤 `phases/agent-balance/index.json`의 step 11 `status`를 `"completed"`로 바꾸면 이어서 실행된다.

사람이 하는 이유: 원본 데이터 접근, 구독 사용량을 쓰는 재작성(Claude Code) 실행과 결과 판독, 약 8GB 베이스 다운로드, 수십 분 이상 걸리는 학습, llama.cpp 빌드·변환은 세션 타임아웃과 맞지 않고 결과를 사람이 읽어 판단해야 한다.

## 읽어야 할 파일

- `/backend/training/balance/MAC_TRAINING.md` (명령의 기준 — 여기 명령을 그대로 따른다)
- `/docs/agent-balance/ARCHITECTURE.md` ("학습 데이터", "`prepare.py` 인터페이스", "`rewrite.py` 인터페이스", "Modelfile")
- `/docs/agent-balance/ADR.md` (BAL-006, BAL-008, BAL-009, BAL-010과 그 보강)
- `/backend/training/balance/prepare.py`, `/backend/training/balance/rewrite.py`, `/backend/models/balance/Modelfile` (step 3~10 산출물)
- 참고: `git show origin/feat-agent-interest:backend/training/interest/export.md` (팀원B의 llama.cpp 설치·변환 기록)

## 체크리스트

데이터:

- [ ] `backend/data/raw/TL_은행.zip`·`VL_은행.zip` 링크를 만들었다(`MAC_TRAINING.md` 선행 조건 1)
- [ ] `cd backend && .venv/bin/python -m training.common.split` → `data/processed/split.json` 생성
- [ ] `claude --version`이 돌고 Claude Code에 로그인돼 있다(MAC_TRAINING 선행 조건 3, API 키 불필요)
- [ ] 1차 시범(규칙 1~10) 캐시를 옮겼다: `cd backend && mv data/processed/balance/rewrites.jsonl data/processed/balance/rewrites.v1.jsonl`. 캐시 키에 규칙이 들어가지 않아서 옮기지 않으면 같은 30건을 다시 보내지 않는다(MAC_TRAINING)
- [ ] 시범 재작성: `cd backend && .venv/bin/python -m training.balance.rewrite --limit 30` → `data/processed/balance/rewrites.jsonl` 30건을 원문(`source`)과 나란히 읽었다. 확인할 것: 존댓말 200자 이내, 조회 결과 단정 없음, 행동 약속·개인정보 요구 없음, 지어낸 메뉴·금리·수수료·상품명 없음, `★`·`OO`·숫자 없음, 원래 답의 일반 안내가 살아 있음(BAL-010). 보강 규칙도 본다: 원문 사실(수수료 유무·처리 기간·휴일 처리·자동 해제·규정 변경)과 한 고객의 조회 결과를 일반화한 설명 없음, 나중에 해 줄 일 약속 없음, 다른 item 내용 없음. 1차 시범(`rewrites.v1.jsonl`)과 같은 30건이므로 나란히 비교한다(BAL-010 보강). 위반이 많으면 멈추고 `REWRITE_SYSTEM`이나 모델을 바꾸는 step을 추가한다
- [ ] 전체 재작성: `rewrite --jobs 4`. `saved`·`missing`·`cost_usd`(참고값)를 적어 둔다. missing이 남으면 같은 명령을 다시 실행한다(캐시에 없는 것만 보낸다). 구독 사용량 한도에 걸리면 기다렸다가 다시 실행한다
- [ ] `cd backend && .venv/bin/python -m training.balance.prepare` → 분할별 기록 수와 재작성 없음으로 빠진 QA 수를 적어 둔다(참고: 대상 QA는 train 3,644·val 245·test 248, QA마다 샘플 최대 2개)
- [ ] `valid.jsonl`에서 20건 이상을 읽었다(첫 턴·이어진 턴·합성 general·가상 계좌번호 질문이 섞이게): 원본 개인정보 없음, 슬롯 응답은 `{{account_label}}` 등 허용 슬롯만, 지어낸 금리·상품명·서류·메뉴 없음, 존댓말, 개인정보 요구·할 수 없는 행동 약속·조회 결과 단정 없음(BAL-009·BAL-010). 문제가 있으면 멈추고 수정 step을 추가한다

학습:

- [ ] `.venv-train` 생성, `requirements-mac.txt` 설치
- [ ] `mlx_lm convert`로 `Qwen/Qwen3-4B-Instruct-2507` 4bit MLX 베이스 생성, `config.json`에 `quantization` 확인
- [ ] `train check` 통과 → `train --iters 100` 소규모 학습에서 loss가 줄고 메모리가 24GB 안에서 도는지 확인
- [ ] 가장 긴 목표 답이 베이스 토크나이저로 256토큰(Modelfile `num_predict`) 이하인지 확인했다: `.venv-train/bin/python -c "import json;from transformers import AutoTokenizer as A;t=A.from_pretrained('data/models/qwen3-4b-instruct-2507-4bit');print(max(len(t.encode(json.loads(l)['messages'][-1]['content'])) for l in open('data/processed/balance/train.jsonl')))"`. 넘으면 멈추고 `MAX_CHARS`나 `num_predict`를 조정하는 step을 추가한다
- [ ] 반복 수를 정해 본 학습 → `train test`로 test loss 기록

변환·등록:

- [ ] `mlx_lm fuse --dequantize` → llama.cpp `convert_hf_to_gguf.py` → `llama-quantize` Q4_K_M
- [ ] 결과를 `backend/models/balance/cs-balance.gguf`로 복사
- [ ] `ollama create cs-balance -f backend/models/balance/Modelfile` 성공, `ollama run cs-balance "잔액 알려줘"`가 한국어 존댓말로 답한다
- [ ] 변환이나 로딩이 실패하면 완료 처리하지 않고 원인을 `MAC_TRAINING.md`에 적는다(BAL-006)

기록·커밋 위생:

- [ ] 재작성 모델·Claude Code 버전·`cost_usd` 합, 베이스 리비전, MLX LM 버전, 분할별 샘플 수(AI Hub 첫 턴·이어진 턴·합성), 반복 수, test loss를 `docs/agent-balance/PRD.md` "구현 진행"에 한 줄로 적었다
- [ ] `git status --short`에 `.gguf`·`.safetensors`·`backend/data/`(`rewrites.jsonl` 포함)·`training/balance/outputs/`가 없다
- [ ] 문서만 `docs(agent-balance): cs-balance 첫 학습 기록` 형식으로 커밋했다
