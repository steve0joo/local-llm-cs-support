# cs-interest 모델 내보내기: LoRA 병합 → GGUF → Ollama

> 학습한 LoRA 어댑터를 서비스에서 쓰는 Ollama 모델 `cs-interest`로 만드는 절차다(ADR-004, 계약 5).
> 채택 여부는 `docs/agent-interest/EVALUATION.md` 기준으로 먼저 정한다. **Base보다 나은 버전만** 내보낸다.
> 모든 산출물(병합 모델, .gguf)은 커밋하지 않는다(`.gitignore`: `*.gguf`, `*.safetensors`, `backend/training/**/outputs/`).

## 0. 준비 (처음 한 번)

| 항목 | 명령·위치 | 비고 |
|---|---|---|
| 16bit 원본 베이스 | `Qwen/Qwen3-4B-Instruct-2507` (약 8GB, `~/.cache/huggingface/`) | 학습에 쓴 4bit 버전(`unsloth/...-bnb-4bit`)에 병합하면 양자화 오차가 겹친다. 병합은 16bit 원본에 한다 |
| llama.cpp | `git clone --depth 1 https://github.com/ggml-org/llama.cpp ~/llama.cpp` 후 `cmake -B build -DGGML_CUDA=OFF -DLLAMA_CURL=OFF && cmake --build build --config Release -j 8 --target llama-quantize` | 변환 스크립트(`convert_hf_to_gguf.py`)와 양자화 도구. 변환·양자화만 하므로 CPU 빌드로 충분하다(학습 장비 설치 완료: 2026-09-28, 0c6a6a7) |
| 변환 전용 가상환경 | `cd ~/llama.cpp && uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements/requirements-convert_hf_to_gguf.txt --index-strategy unsafe-best-match` | **학습 환경에 설치하지 않는다.** 변환 requirements가 torch 2.11(CPU)·transformers 4.57을 고정해 학습 환경(torch 2.14·transformers 5.17)을 내려 버린다 |
| Ollama | `ollama --version` (학습 장비: WSL, 0.34 확인) | Mac에도 설치 |

## 1. 내보낼 버전 고르기

```bash
cat backend/training/interest/outputs/runs/index.jsonl          # 버전 목록
cat backend/training/interest/outputs/runs/<버전>/run_info.json  # 데이터·설정·git 커밋
```
- 평가 결과(`<버전>/eval/`)로 Base보다 나은지 확인한 버전만 쓴다.
- 이하 `RUN=backend/training/interest/outputs/runs/<버전>`.

## 2. LoRA 병합 (16bit)

`peft`로 16bit 원본에 어댑터를 합쳐 `$RUN/merged/`에 저장한다. 토크나이저는 **공식 채팅 템플릿**(`training/interest/chat_template.jinja`)을 입힌 것을 함께 저장한다.

```python
# cd backend && training/interest/.venv/bin/python
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM
from training.interest.train import load_tokenizer

RUN = "training/interest/outputs/runs/<버전>"
base = AutoModelForCausalLM.from_pretrained("Qwen/Qwen3-4B-Instruct-2507", dtype=torch.bfloat16, device_map="cpu")
merged = PeftModel.from_pretrained(base, f"{RUN}/adapter").merge_and_unload()
merged.save_pretrained(f"{RUN}/merged", safe_serialization=True)
load_tokenizer("Qwen/Qwen3-4B-Instruct-2507").save_pretrained(f"{RUN}/merged")
```
- CPU에서 병합한다(8GB VRAM에 16bit 4B 모델이 다 올라가지 않는다). RAM 약 10GB가 필요하다.
- 어댑터를 4bit 모델로 학습했어도 LoRA 가중치는 16bit라 16bit 원본에 병합할 수 있다.

## 3. GGUF 변환 + Q4_K_M 양자화

```bash
~/llama.cpp/.venv/bin/python ~/llama.cpp/convert_hf_to_gguf.py $RUN/merged --outtype f16 --outfile $RUN/cs-interest-f16.gguf
~/llama.cpp/build/bin/llama-quantize $RUN/cs-interest-f16.gguf $RUN/cs-interest.gguf Q4_K_M
```
- 결과 크기는 약 2.5GB. f16 파일(약 8GB)은 확인이 끝나면 지워도 된다.

## 4. Ollama 등록

```bash
cp $RUN/cs-interest.gguf backend/models/interest/cs-interest.gguf
basename $RUN > backend/models/interest/VERSION        # 어떤 학습 버전인지 기록
ollama create cs-interest -f backend/models/interest/Modelfile
```
- `Modelfile`은 공식 ChatML 템플릿, `SYSTEM`(= `prompt.SYSTEM_PROMPT`, 테스트로 일치 확인), 멈춤 토큰 `<|im_end|>`, `temperature 0.2`를 쓴다.
- 에이전트는 매 요청에 시스템 프롬프트를 messages로 보낸다(`prompt.build_messages`). 학습 데이터와 같은 형식이다.

## 5. 확인

1. **동작 확인:** Golden Set 질문 하나를 Ollama로 보내 답이 나오는지, 답 앞에 `<think>`·`<tool_call>` 같은 태그가 없는지 본다.
   ```bash
   curl -s localhost:11434/api/chat -d '{"model":"cs-interest","stream":false,"messages":[{"role":"user","content":"이번 달에 낼 이자가 얼마죠?\n이자 정보: 종류=신용대출, 상환 방식=만기일시, 금리 방식=변동, 납부 방법=자동이체, 다음 납부일=2026-10-15, 연체 여부=연체 없음\n사용할 수 있는 슬롯: {{loan_label}}, {{interest_due}}"}]}'
   ```
2. **변환 전후 품질 비교(ADR-004):** 같은 Golden Set으로 변환 전(transformers + 어댑터) 결과와 비교한다. 규칙 준수율이 3%p 넘게 떨어지면 원인을 찾는다(양자화 수준, 템플릿 불일치).
3. **응답 시간:** Golden Set 질문으로 첫 응답까지 시간을 잰다. 인수 기준 7(라우터 + 에이전트 합쳐 10초 이내) 중 이 모델의 몫을 기록한다.

## 6. Mac 등록 (인수 기준 8)

- 같은 `cs-interest.gguf`, `Modelfile`, `VERSION`을 Mac의 `backend/models/interest/`에 복사하고 `ollama create cs-interest -f backend/models/interest/Modelfile`.
- 복사는 USB 등 로컬 매체로 한다. 클라우드 드라이브는 쓰지 않는다(데이터 파생물, 제3자 제공 금지).
- Mac에서도 5-1·5-3을 확인한다.

## 기록

내보낸 뒤 `$RUN/run_info.json`과 같은 폴더에 `export.json`(gguf 크기·sha256, 양자화 방식, 변환 전후 규칙 준수율, 응답 시간)을 남긴다.
