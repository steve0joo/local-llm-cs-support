# 잔액조회 에이전트: Mac 학습·평가

범위는 `cs-balance`뿐이다. 라우터·대출·이자 학습은 공통 Windows 계획을 따른다. 현재 장비는 Apple M4 Pro, 통합 메모리 24GB, Python 3.11이다. Hugging Face는 **베이스 모델 다운로드**에, Ollama는 **학습 후 추론·평가**에 쓴다. AI Hub 원본·가공본과 어댑터·가중치는 로컬에만 보관한다.

## 선행 조건과 데이터

1. AI Hub 은행 라벨링 원본 `TL_은행.zip`·`VL_은행.zip`은 `backend/data/raw/` 아래에 있다. 공통 `training/common/split.py`는 `backend/data/raw/TL_은행.zip`·`VL_은행.zip` 경로를 그대로 읽는다. 이 Mac에는 zip이 `backend/data/raw/금융분야_고객상담_데이터/3.개방데이터/2.데이터(NIA)/{Training,Validation}/02.라벨링데이터/` 안에 있으므로 한 번 링크를 만든다: `ln -s "$PWD/backend/data/raw/금융분야_고객상담_데이터/3.개방데이터/2.데이터(NIA)/Training/02.라벨링데이터/TL_은행.zip" backend/data/raw/TL_은행.zip`(VL도 같은 방식, 저장소 루트에서 실행). 실제 JSON 구조는 `source.source_id`, `consulting.consulting_topic`, `qa_data[].input.question`·`input.answer`·`input.follow_up_question`·`output`이다. 잔액조회 라벨은 Training 4,017건, Validation 503건이다. 이용조건을 확인하고 원본·가공본을 저장소에 추가하지 않는다.
2. 팀원C의 `training/common`이 은행 데이터를 `source.source_id` 단위로 train/val/test 분할한다. 원천 Training/Validation 사이에도 겹치는 `source_id`가 2개 있으므로 원천 디렉터리를 그대로 분할로 쓰지 않는다(공통 분할은 이 2건을 train으로 보낸다, main `docs/router/ADR.md` RT-005). 같은 `source_id`의 QA가 분할을 넘나들면 안 된다.
3. `training/balance/prepare.py`는 공통 `split.json`에 따라 `consulting.consulting_topic == "거래내역/잔액조회"` 대화를 추출해야 한다. 모든 user·assistant 발화는 게이트웨이와 같은 `app.masking.mask()`로 마스킹한다(계약 4). import에 실패하면 전처리를 멈추며 임시 정규식이나 fallback 함수로 학습 데이터를 만들지 않는다. 입력에 없는 숫자·상품명을 출력에 덧붙인 샘플과 실제 금액·계좌번호가 남은 샘플은 제외한다. 인터페이스와 제외 규칙은 `docs/agent-balance/ARCHITECTURE.md` "`prepare.py` 인터페이스"가 기준이다. 실행: `cd backend && .venv/bin/python -m training.common.split && .venv/bin/python -m training.balance.prepare`.
4. 결과를 `backend/data/processed/balance/{train,valid,test}.jsonl`로 만든다. 한 줄에 `{"messages":[{"role":"system","content":"..."},{"role":"user","content":"..."},{"role":"assistant","content":"..."}]}` 한 대화를 쓴다. 마지막 메시지는 학습 목표 assistant 답변이다. 원천에는 `{{슬롯}}` 응답이 없으므로 잔액·거래내역 슬롯 응답은 템플릿 합성 샘플로 보강하고, 입력은 추론과 같은 `prompt.build_messages` 형식으로 만든다(`docs/agent-balance/ADR.md` BAL-008). 원본 필드와 정제 결과를 확인하기 전에는 학습을 시작하지 않는다.
5. `valid`에서 최소 20건을 사람이 읽고 마스킹·슬롯·사실성·존댓말을 점검한다. `test`는 최종 점검 때만 연다. 자동 평가는 MLX LM test loss/perplexity이며, 인수 판정은 Ollama의 PM 고정 10문항으로 한다.

이 브랜치에는 공통 `mask()` 원본 `6c61e00`과 `source_id` 분할 원본 `925c7da`를 수정 없이 가져왔다. main에서 둘 중 하나가 바뀌면 balance 가공 데이터를 다시 만든다.

## Mac 학습 환경과 Hugging Face 베이스

저장소 루트에서 실행한다. 런타임 `.venv`와 학습 `.venv-train`을 분리한다. Mac의 Ollama에 있는 `qwen3:8b`는 추론용 파일이며 MLX 학습 베이스 파일로 재사용하지 않는다. 베이스는 팀원B(interest)와 같은 `Qwen/Qwen3-4B-Instruct-2507`이다(2026-09-29 결정, BAL-006). 팀원C 벤치마크로 팀 공통 베이스가 달라지면 그 모델로 다시 변환·학습한다.

```bash
backend/.venv/bin/python -m venv backend/.venv-train
backend/.venv-train/bin/python -m pip install -r backend/training/balance/requirements-mac.txt
backend/.venv-train/bin/python -m mlx_lm convert --hf-path Qwen/Qwen3-4B-Instruct-2507 --mlx-path backend/data/models/qwen3-4b-instruct-2507-4bit -q --q-bits 4
```

베이스 출처·리비전·MLX LM 버전을 실행 기록에 적는다. 공통 베이스가 결정되면 해당 Hugging Face 모델로 위 변환을 다시 수행한다. 학습 전에 `config.json`의 `quantization` 존재를 확인한다. 양자화 베이스가 아니면 일반 LoRA가 되어 이 계획의 QLoRA가 아니다.

학습 명령은 `backend/`에서 실행한다. 먼저 소규모 반복으로 메모리와 loss를 확인하고, 학습 반복 수·길이는 결과를 보고 정한다. 학습 결과는 `backend/training/balance/outputs/adapters/`에 저장한다.

```bash
cd backend
.venv-train/bin/python -m training.balance.train check --model data/models/qwen3-4b-instruct-2507-4bit --data data/processed/balance
.venv-train/bin/python -m training.balance.train train --model data/models/qwen3-4b-instruct-2507-4bit --data data/processed/balance --iters 100 --batch-size 1
```

## Ollama 내보내기·평가 게이트

MLX LM의 Qwen GGUF 직접 export는 지원되지 않는다. 우선 어댑터를 양자화 베이스와 병합하고 비양자화한 모델을 만든다. 그 결과를 로컬 llama.cpp `convert_hf_to_gguf.py`로 변환하는 **호환성 시험**을 한다. 아래 명령은 변환 경로가 통과하는지 확인하는 절차이며, 아직 이 프로젝트의 산출물로 검증된 명령은 아니다.

```bash
.venv-train/bin/python -m mlx_lm fuse --model data/models/qwen3-4b-instruct-2507-4bit --adapter-path training/balance/outputs/adapters --save-path training/balance/outputs/fused --dequantize
.venv-train/bin/python /path/to/llama.cpp/convert_hf_to_gguf.py training/balance/outputs/fused --outfile training/balance/outputs/balance-f16.gguf --outtype f16
/path/to/llama.cpp/build/bin/llama-quantize training/balance/outputs/balance-f16.gguf training/balance/outputs/balance-q4_k_m.gguf Q4_K_M
```

변환이나 Ollama 로딩에 실패하면 GGUF 생성 절차를 확정하지 않는다. 성공하면 `balance-q4_k_m.gguf`를 `backend/models/balance/cs-balance.gguf`로 복사하고(`Modelfile`이 `FROM ./cs-balance.gguf`로 가리킨다) `ollama create cs-balance -f backend/models/balance/Modelfile`을 실행한다. GGUF와 모델 가중치는 커밋하지 않는다.

`test` 분할은 최종 단계에서만 열어 MLX LM test loss/perplexity를 확인한다.

```bash
.venv-train/bin/python -m training.balance.train test --model data/models/qwen3-4b-instruct-2507-4bit --data data/processed/balance
```

Ollama의 실제 `/api/chat` 경로에서 PM 고정 질문 10건 중 9건 이상, 숫자·상품명 환각 0건, 모델 응답의 필수 슬롯, 마스킹 로그, 첫 응답 시간 기준을 검사한다. Mac 평가가 통과하면 동일 GGUF의 Windows 로컬 추론도 공통 인수 기준에 따라 확인한다.

참고: [Hugging Face Qwen 베이스](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507), [MLX LM LoRA/QLoRA와 JSONL 형식](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md), [MLX LM GGUF export 제한](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/fuse.py), [Ollama 모델 가져오기](https://github.com/ollama/ollama/blob/main/docs/import.mdx).
