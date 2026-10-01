# 대출문의 모델 배포 절차 (LoRA 병합 → GGUF → Ollama)

ADR-004(GGUF 통일)·ADR-005(QLoRA) 절차. `train.py`가 만든 어댑터(`backend/training/loan/outputs/adapter/`)를
병합·양자화해 `cs-loan`으로 등록한다. 아래는 실행 절차이고, 실제 실행은 사람이 한다(step 4).

이미 `~/qlora_ft_ex/llama.cpp`에 빌드된 llama.cpp가 있으면(`llama.cpp/build/bin/llama-quantize` 존재 확인)
그걸 그대로 써도 된다. 없거나 새로 받고 싶으면 0번부터 한다.

## 0. llama.cpp 준비(이미 있으면 건너뛴다)

```bash
sudo apt update && sudo apt install -y cmake git build-essential
git clone https://github.com/ggml-org/llama.cpp ~/llama.cpp   # 이미 ~/qlora_ft_ex/llama.cpp가 있으면 그 경로를 대신 쓴다
cd ~/llama.cpp
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
ls build/bin/llama-quantize   # 경로가 나오면 정상
```

## 1. LoRA 병합 (4bit가 아니라 bf16 베이스에 병합한다)

QLoRA는 4bit 베이스 위에서 학습했지만, 병합은 반드시 **양자화 전 원본(bf16/fp16) 베이스**에 한다.
4bit 위에 병합하면 오차가 누적된다.

`backend/training/loan/`에서 실행(가상환경은 `backend/.venv` 그대로 사용):

```bash
cd backend
.venv/bin/python - <<'EOF'
from pathlib import Path
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE_MODEL = "Qwen/Qwen3-4B-Instruct-2507"   # train.py --model과 같은 값으로 맞춘다
ADAPTER_DIR = "training/loan/outputs/adapter"
MERGED_DIR = "training/loan/outputs/merged"

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
base = AutoModelForCausalLM.from_pretrained(BASE_MODEL, torch_dtype=torch.bfloat16, device_map="cpu")
model = PeftModel.from_pretrained(base, ADAPTER_DIR)
model = model.merge_and_unload()

Path(MERGED_DIR).mkdir(parents=True, exist_ok=True)
model.save_pretrained(MERGED_DIR, safe_serialization=True)
tokenizer.save_pretrained(MERGED_DIR)
print("병합 완료:", MERGED_DIR)
EOF
```

- `training/loan/outputs/`는 gitignore 대상이다(`backend/training/**/outputs/`). 커밋하지 않는다.
- CPU에서 병합해도 된다(4B는 bf16로 약 8GB RAM 필요, 이 노트북은 RAM 32GB라 여유 있다). GPU가 비어 있으면 `device_map="cuda"`로 바꿔도 된다.

## 2. HF 병합 모델 → GGUF(F16) 변환

```bash
cd backend
LLAMA_CPP=~/qlora_ft_ex/llama.cpp   # 또는 0번에서 새로 받은 경로
python "$LLAMA_CPP/convert_hf_to_gguf.py" \
  training/loan/outputs/merged \
  --outfile training/loan/outputs/cs-loan-f16.gguf \
  --outtype f16
```

- `convert_hf_to_gguf.py`가 요구하는 `transformers`·`tokenizers` 버전이 학습 venv와 다를 수 있다(스크립트 자체 안내 참고).
  안 맞으면 `~/qlora_ft_ex/llama.cpp`의 자체 가상환경(`uv sync` 등)을 써도 된다 — 변환은 가중치 포맷 변환이라
  학습 결과(merged 모델 파일)만 있으면 되고, 어떤 파이썬 환경에서 돌리든 상관없다.

## 3. Q4_K_M 양자화

```bash
"$LLAMA_CPP/build/bin/llama-quantize" \
  training/loan/outputs/cs-loan-f16.gguf \
  training/loan/outputs/cs-loan-q4_k_m.gguf \
  Q4_K_M
```

## 4. `models/loan/Modelfile`로 Ollama 등록

`backend/models/loan/Modelfile`은 이미 커밋돼 있다(`.gguf`는 커밋 금지, 경로는 로컬 절대경로로 각자 맞춘다).

```bash
ollama create cs-loan -f backend/models/loan/Modelfile
ollama list   # cs-loan이 보이면 정상
```

## 5. 품질 확인 (ADR-004 트레이드오프 — 양자화 후 품질이 떨어지지 않았는지)

```bash
ollama run cs-loan
```

아래를 직접 물어보고 확인한다:
- 존댓말 상담 톤이 유지되는가
- `{{loan_label}}`·`{{principal_remaining}}`·`{{extendable_status}}` 슬롯을 실제로 쓰는가(직접 "가능합니다"라고 쓰지 않는가)
- 숫자·금리·서류 요건을 지어내지 않는가(LN-002, LN-004)
- C002(연장 가능)·C003(연장 불가) 두 시나리오를 다르게 답하는가

`backend/app/agents/loan/validate.py`의 `is_valid_output` 기준과 같은 눈으로 본다.

## 6. Mac(M4 Pro)에서 추론 확인 (인수 기준 8)

같은 `cs-loan-q4_k_m.gguf`와 `Modelfile`을 Mac에 복사한 뒤:

```bash
ollama create cs-loan -f Modelfile   # Modelfile의 FROM 경로를 Mac 쪽 절대경로로 바꾼다
ollama run cs-loan
```

## 7. 10초 벤치마크 (인수 기준 7)

라우터 → 대출 에이전트 실제 경로(비스트리밍)로 첫 응답까지 시간을 잰다. 게이트웨이(`/api/chat`)가
아직 없으면 `llm.generate("cs-loan", messages)` 직접 호출 + 라우터 분류 시간을 더해 근사치를 낸다.
4개 모델(`cs-router`·`cs-balance`·`cs-loan`·`cs-interest`)을 동시에 올려 둔 상태에서 재는 것이 실제에 가깝다.

## 커밋 대상

- `backend/training/loan/train.py`, `export.md`(이 파일), `backend/models/loan/Modelfile`
- `.gguf`·`.safetensors`·`training/loan/outputs/`는 커밋하지 않는다(gitignore로 이미 막혀 있다)
