# 잔액조회 에이전트: Mac 학습·평가

범위는 `cs-balance`뿐이다. 라우터·대출·이자 학습은 공통 Windows 계획을 따른다. 현재 장비는 Apple M4 Pro, 통합 메모리 24GB, Python 3.11이다. Hugging Face는 **베이스 모델 다운로드**에, Ollama는 **학습 후 추론·평가**에 쓴다. AI Hub 원본·가공본과 어댑터·가중치는 로컬에만 보관한다. 학습 데이터 재작성 때만 마스킹된 텍스트를 Claude Code 헤드리스 모드(`claude -p`, Claude Haiku 4.5)로 보낸다(BAL-010). 학습 자체는 로컬에서만 한다.

## 선행 조건과 데이터

1. AI Hub 은행 라벨링 원본 `TL_은행.zip`·`VL_은행.zip`은 `backend/data/raw/` 아래에 있다. 공통 `training/common/split.py`는 `backend/data/raw/TL_은행.zip`·`VL_은행.zip` 경로를 그대로 읽는다. 이 Mac에는 zip이 `backend/data/raw/금융분야_고객상담_데이터/3.개방데이터/2.데이터(NIA)/{Training,Validation}/02.라벨링데이터/` 안에 있으므로 한 번 링크를 만든다: `ln -s "$PWD/backend/data/raw/금융분야_고객상담_데이터/3.개방데이터/2.데이터(NIA)/Training/02.라벨링데이터/TL_은행.zip" backend/data/raw/TL_은행.zip`(VL도 같은 방식, 저장소 루트에서 실행). 실제 JSON 구조는 `source.source_id`, `consulting.consulting_topic`, `qa_data[].input.question`·`input.answer`·`input.follow_up_question`·`output`이다. 잔액조회 라벨은 Training 4,017건, Validation 503건이다. 이용조건을 확인하고 원본·가공본을 저장소에 추가하지 않는다.
2. 팀원C의 `training/common`이 은행 데이터를 `source.source_id` 단위로 train/val/test 분할한다. 원천 Training/Validation 사이에도 겹치는 `source_id`가 2개 있으므로 원천 디렉터리를 그대로 분할로 쓰지 않는다(공통 분할은 이 2건을 train으로 보낸다, main `docs/router/ADR.md` RT-005). 같은 `source_id`의 QA가 분할을 넘나들면 안 된다.
3. `training/balance/prepare.py`는 공통 `split.json`에 따라 `consulting.consulting_topic == "거래내역/잔액조회"` 대화를 추출해야 한다. 모든 user·assistant 발화는 게이트웨이와 같은 `app.masking.mask()`로 마스킹한다(계약 4). import에 실패하면 전처리를 멈추며 임시 정규식이나 fallback 함수로 학습 데이터를 만들지 않는다. 정답은 `training/balance/rewrite.py`가 챗봇 답변으로 다시 쓴 것만 쓴다. 다시 쓴 답에도 안전망 필터(숫자·상품명·콜센터식 정답·조회 결과 단정·비식별 표시·200자)를 적용한다(BAL-010). 인터페이스와 제외 규칙은 `docs/agent-balance/ARCHITECTURE.md` "학습 데이터"와 "`prepare.py`·`rewrite.py` 인터페이스"가 기준이다. 실행(`backend/`에서):

   ```bash
   claude --version                                       # Claude Code CLI가 설치되고 로그인돼 있어야 한다(API 키 불필요)
   .venv/bin/python -m training.common.split
   .venv/bin/python -m training.balance.rewrite --limit 30  # 시범 30건(묶음 2번). saved·missing·cost_usd를 출력한다
   # data/processed/balance/rewrites.jsonl의 30건을 원문(source)과 나란히 읽고, 규칙 위반이 적으면 나머지를 돌린다
   # 규칙(REWRITE_SYSTEM)이나 모델을 바꿨으면 캐시 키가 같으므로 기존 캐시를 옮기고 시범부터 다시 한다: mv data/processed/balance/rewrites.jsonl data/processed/balance/rewrites.v1.jsonl
   .venv/bin/python -m training.balance.rewrite --jobs 4    # 캐시에 없는 나머지 전부. 끊기면 같은 명령으로 이어서 돈다
   .venv/bin/python -m training.balance.prepare             # 재작성 캐시만 읽는다(결정적)
   ```
4. 결과를 `backend/data/processed/balance/{train,valid,test}.jsonl`로 만든다. 한 줄에 `{"messages":[{"role":"system","content":"..."},{"role":"user","content":"..."},{"role":"assistant","content":"..."}]}` 한 대화를 쓴다. 마지막 메시지는 학습 목표 assistant 답변이다. AI Hub QA 하나에서 첫 턴·이어진 턴 샘플을 최대 2개 만든다. 원천에는 `{{슬롯}}` 응답이 없으므로 잔액·거래내역 슬롯 응답과 general 상담원 안내는 템플릿 합성 샘플로 보강하고, 입력은 추론과 같은 `prompt.build_messages` 형식으로 만든다(`docs/agent-balance/ADR.md` BAL-008). 원본 필드와 정제 결과를 확인하기 전에는 학습을 시작하지 않는다.
5. `valid`에서 최소 20건을 사람이 읽고 마스킹·슬롯·사실성·존댓말을 점검한다. `test`는 최종 점검 때만 연다. 자동 평가는 MLX LM test loss/perplexity이며, 인수 판정은 Ollama의 PM 고정 10문항으로 한다.

이 브랜치에는 공통 `mask()` 원본 `6c61e00`과 `source_id` 분할 원본 `925c7da`를 수정 없이 가져왔다. main에서 둘 중 하나가 바뀌면 balance 가공 데이터를 다시 만든다.

## Mac 학습 환경과 Hugging Face 베이스

저장소 루트에서 실행한다. 런타임 `.venv`와 학습 `.venv-train`을 분리한다. Mac의 Ollama에 있는 `qwen3:8b`는 추론용 파일이며 MLX 학습 베이스 파일로 재사용하지 않는다. 베이스는 팀원B(interest)와 같은 `Qwen/Qwen3-4B-Instruct-2507`이다(2026-09-29 결정, BAL-006). 팀원C 벤치마크로 팀 공통 베이스가 달라지면 그 모델로 다시 변환·학습한다.

```bash
backend/.venv/bin/python -m venv backend/.venv-train
backend/.venv-train/bin/python -m pip install -r backend/training/balance/requirements-mac.txt
backend/.venv-train/bin/python -m mlx_lm convert --hf-path Qwen/Qwen3-4B-Instruct-2507 --mlx-path backend/data/models/qwen3-4b-instruct-2507-4bit -q --q-bits 4
```

`huggingface_hub` 1.x에서는 변환이 저장 단계에서 `IncompleteSnapshotError`로 멈출 수 있다. `mlx_lm`이 받지 않는 `.gitattributes`·`LICENSE`·`README.md` 때문이다. 이 세 파일만 같은 리비전으로 받은 뒤(`hf_hub_download`) 같은 명령을 다시 실행한다(2026-09-30, 리비전 `cdbee75f17c01a7cc42f958dc650907174af0554`). 베이스 출처·리비전·MLX LM 버전을 실행 기록에 적는다. 공통 베이스가 결정되면 해당 Hugging Face 모델로 위 변환을 다시 수행한다. 학습 전에 `config.json`의 `quantization` 존재를 확인한다. 양자화 베이스가 아니면 일반 LoRA가 되어 이 계획의 QLoRA가 아니다.

학습 명령은 `backend/`에서 실행한다. 먼저 소규모 반복으로 메모리와 loss를 확인하고, 학습 반복 수·길이는 결과를 보고 정한다. 학습 결과는 `backend/training/balance/outputs/adapters/`에 저장한다.

```bash
cd backend
.venv-train/bin/python -m training.balance.train check --model data/models/qwen3-4b-instruct-2507-4bit --data data/processed/balance
.venv-train/bin/python -m training.balance.train train --model data/models/qwen3-4b-instruct-2507-4bit --data data/processed/balance --iters 100 --batch-size 1
```

## Ollama 내보내기·평가 게이트

MLX LM의 Qwen GGUF 직접 export는 지원되지 않는다. 그래서 어댑터를 **16bit 원본 베이스**(`Qwen/Qwen3-4B-Instruct-2507`, 같은 리비전, HF 캐시)에 병합한다. 4bit 베이스에 `--dequantize`로 병합하면 4bit 반올림 오차가 남은 채로 Q4_K_M을 한 번 더 거친다(BAL-006 보강). 병합 결과를 로컬 llama.cpp `convert_hf_to_gguf.py`로 변환한다. 아래 명령은 2026-09-30에 이 절차대로 검증했다.

llama.cpp는 팀원B 기록(`origin/feat-agent-interest:backend/training/interest/export.md`)처럼 `~/llama.cpp`에 둔다. 변환 전용 가상환경을 쓰고 학습 환경에는 설치하지 않는다. 변환 requirements가 transformers 4.x를 고정하기 때문이다. cmake가 없으면 같은 가상환경에 설치한다.

```bash
git clone --depth 1 https://github.com/ggml-org/llama.cpp ~/llama.cpp   # 검증: 19e28a2
cd ~/llama.cpp && uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python cmake -r requirements/requirements-convert_hf_to_gguf.txt --index-strategy unsafe-best-match
PATH="$HOME/llama.cpp/.venv/bin:$PATH" cmake -B build -DLLAMA_CURL=OFF -DCMAKE_BUILD_TYPE=Release && PATH="$HOME/llama.cpp/.venv/bin:$PATH" cmake --build build --config Release -j 6 --target llama-quantize
```

`backend/`에서 실행한다. `mlx_lm fuse`는 학습 환경의 transformers 5로 토크나이저·`config.json`을 다시 저장한다. 그러면 llama.cpp 변환기(transformers 4.x)가 `extra_special_tokens` 목록을 읽지 못하고, `eos_token_id`·pre_tokenizer 표기도 원본과 달라진다. LoRA는 토크나이저를 바꾸지 않으므로 이 파일들을 원본 스냅샷 것으로 되돌린다. 가중치 파일은 그대로 둔다.

```bash
.venv-train/bin/python -m mlx_lm fuse --model Qwen/Qwen3-4B-Instruct-2507 --adapter-path training/balance/outputs/adapters --save-path training/balance/outputs/fused
B=$(ls -d ~/.cache/huggingface/hub/models--Qwen--Qwen3-4B-Instruct-2507/snapshots/cdbee75*)
for f in config.json tokenizer_config.json tokenizer.json vocab.json merges.txt; do cp -L "$B/$f" training/balance/outputs/fused/; done
rm training/balance/outputs/fused/chat_template.jinja   # 원본 tokenizer_config.json의 chat_template과 같다
~/llama.cpp/.venv/bin/python ~/llama.cpp/convert_hf_to_gguf.py training/balance/outputs/fused --outfile training/balance/outputs/balance-f16.gguf --outtype f16
~/llama.cpp/build/bin/llama-quantize training/balance/outputs/balance-f16.gguf training/balance/outputs/balance-q4_k_m.gguf Q4_K_M
```

변환이나 Ollama 로딩에 실패하면 GGUF 생성 절차를 확정하지 않는다. 성공하면 `balance-q4_k_m.gguf`를 `backend/models/balance/cs-balance.gguf`로 복사하고(`Modelfile`이 `FROM ./cs-balance.gguf`로 가리킨다) `ollama create cs-balance -f backend/models/balance/Modelfile`을 실행한다. GGUF와 모델 가중치는 커밋하지 않는다. 터미널이 아닌 곳(스크립트·에이전트)에서 `ollama run cs-balance "잔액 알려줘"`를 부르면 표준 입력을 기다리며 멈춘다. 그럴 때는 `</dev/null`을 붙인다.

`test` 분할은 최종 단계에서만 열어 MLX LM test loss/perplexity를 확인한다.

```bash
.venv-train/bin/python -m training.balance.train test --model data/models/qwen3-4b-instruct-2507-4bit --data data/processed/balance
```

`train test`는 `--mask-prompt` 없이 `mlx_lm lora --test`를 부른다. 그래서 system·user 토큰까지 loss에 들어가, 학습 중 valid loss와 비교할 수 없다(2026-09-30: 2.501). 학습과 같은 기준의 값은 `mlx_lm lora`를 직접 불러 잰다(같은 날 0.886).

```bash
.venv-train/bin/python -m mlx_lm lora --model data/models/qwen3-4b-instruct-2507-4bit --adapter-path training/balance/outputs/adapters --data data/processed/balance --test --test-batches -1 --batch-size 1 --max-seq-length 1024 --mask-prompt
```

Ollama의 실제 `/api/chat` 경로에서 PM 고정 질문 10건 중 9건 이상, 숫자·상품명 환각 0건, 모델 응답의 필수 슬롯, 마스킹 로그, 첫 응답 시간 기준을 검사한다. Mac 평가가 통과하면 동일 GGUF의 Windows 로컬 추론도 공통 인수 기준에 따라 확인한다.

참고: [Hugging Face Qwen 베이스](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507), [MLX LM LoRA/QLoRA와 JSONL 형식](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md), [MLX LM GGUF export 제한](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/fuse.py), [Ollama 모델 가져오기](https://github.com/ollama/ollama/blob/main/docs/import.mdx).
