#!/usr/bin/env bash
# v4 야간 학습 (WSL). 실행: cd ~/local-llm-cs-support/backend && nohup bash training/loan/night_v4.sh > training/loan/outputs_v4_night.log 2>&1 &
# 학습 설정은 v3와 같다(train.py 기본값: lr 2e-4, epoch 3, LoRA r16/alpha32/dropout0.05, 실효 배치 16, seed 42). 에폭마다 체크포인트를 남긴다.
# 뒷단계(병합·변환·등록·스모크)가 실패해도 어댑터·체크포인트·로그는 지우지 않는다. 미리 확인만: DRY=1 bash training/loan/night_v4.sh
set -u -o pipefail
cd "$(dirname "$0")/../.." || exit 1        # backend/
PY=.venv/bin/python
OUT=training/loan/outputs_v4
LLAMA_CPP="${LLAMA_CPP:-$HOME/.unsloth/llama.cpp}"
BASE="Qwen/Qwen3-4B-Instruct-2507"
TRAIN=data/processed/loan_train_v4.jsonl; VAL=data/processed/loan_val_v4.jsonl; SEED=training/loan/manual_seed_v4.jsonl
mkdir -p "$OUT"; STATUS="$OUT/STATUS.txt"; : > "$STATUS"
say() { echo "[$(date '+%m-%d %H:%M:%S')] $*"; }
mark() { echo "$1 $2" | tee -a "$STATUS"; }        # 단계 이름과 OK/FAIL/SKIP을 STATUS.txt에 남긴다

# ---- 0. 실행 전 점검: 확정된 파일 해시(2026-09-30)와 다르면 학습하지 않는다 ------------------------------------------
check_sha() { local got; got=$(sha256sum "$1" | cut -c1-64); if [ "$got" != "$2" ]; then say "해시 불일치: $1 ($got)"; return 1; fi; say "해시 일치: $1"; }
check_sha "$SEED"  3e586ec1bf98f89dce96ff3d51de60c049bcc9c111c2f3a8986241279316d448 || { mark hash FAIL; exit 1; }
check_sha "$TRAIN" 780c9ba5da7e106bb2564dba1f8bf73c53b8b50d22f1eadeaf7ae6c11a45e850 || { mark hash FAIL; exit 1; }
check_sha "$VAL"   5965cfdb6df0de646ea5adb3644065a39104dfb6134a123efa11669886f2a119 || { mark hash FAIL; exit 1; }
mark hash OK
say "여유 디스크: $(df -h . | awk 'NR==2{print $4}') (병합·변환 중 최대 약 20GB 필요)"; nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader || true
for f in "$LLAMA_CPP/convert_hf_to_gguf.py" "$LLAMA_CPP/llama-quantize" "$PY"; do [ -e "$f" ] || say "경고: $f 없음(뒷단계가 실패할 수 있음, 학습은 진행)"; done
if [ "${DRY:-0}" = "1" ]; then say "DRY=1: 점검만 하고 종료합니다."; exit 0; fi
# Ollama가 GPU에 올려 둔 모델이 있으면 내린다(8GB GPU에서 학습 메모리를 확보). 실패해도 계속한다.
ollama ps 2>/dev/null | awk 'NR>1{print $1}' | while read -r m; do ollama stop "$m" >/dev/null 2>&1; done

# ---- 1. 학습 (실패하면 뒷단계는 건너뛴다. 로그와 이미 저장된 체크포인트는 남는다) ------------------------------------
say "학습 시작 → $OUT (로그: training/loan/outputs_v4_train.log)"
$PY -m training.loan.train --train-data "$TRAIN" --val-data "$VAL" --out "$OUT" --save-total-limit 3 --report-to wandb --wandb-online > training/loan/outputs_v4_train.log 2>&1
if [ $? -ne 0 ] || [ ! -f "$OUT/adapter/adapter_model.safetensors" ]; then mark train FAIL; say "학습 실패. 로그와 체크포인트는 남겨 둡니다."; exit 1; fi
mark train OK; say "학습 완료: $OUT/adapter"
$PY - <<'PY' > "$OUT/summary.txt" 2>&1 || true
import glob, json
f = sorted(glob.glob("training/loan/outputs_v4/checkpoint-*/trainer_state.json"), key=lambda p: int(p.split("checkpoint-")[1].split("/")[0]))[-1]
for e in json.load(open(f))["log_history"]:
    if "eval_loss" in e: print(f"epoch {e['epoch']:.0f} eval_loss {e['eval_loss']:.4f} acc {e.get('eval_mean_token_accuracy',0):.4f}")
PY
say "val 추이: $(tr '\n' ' ' < "$OUT/summary.txt")"

# ---- 2. 병합 (bf16 베이스 위에. 실패해도 어댑터는 그대로) ---------------------------------------------------------------
say "병합"
OUT="$OUT" BASE="$BASE" $PY - <<'PY' > "$OUT/merge.log" 2>&1
import os, torch
from pathlib import Path
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
out, base = os.environ["OUT"], os.environ["BASE"]
tok = AutoTokenizer.from_pretrained(base)
m = PeftModel.from_pretrained(AutoModelForCausalLM.from_pretrained(base, dtype=torch.bfloat16, device_map="cpu"), f"{out}/adapter").merge_and_unload()
Path(f"{out}/merged").mkdir(exist_ok=True); m.save_pretrained(f"{out}/merged", safe_serialization=True); tok.save_pretrained(f"{out}/merged"); print("병합 완료")
PY
if [ $? -eq 0 ]; then mark merge OK; else mark merge FAIL; fi

# ---- 3. GGUF 변환 + Q4_K_M 양자화 (성공했을 때만 f16 중간 파일을 지운다) ---------------------------------------------
if grep -q "^merge OK" "$STATUS"; then
  say "GGUF 변환"
  $PY "$LLAMA_CPP/convert_hf_to_gguf.py" "$OUT/merged" --outfile "$OUT/cs-loan-v4-f16.gguf" --outtype f16 > "$OUT/convert.log" 2>&1 \
    && "$LLAMA_CPP/llama-quantize" "$OUT/cs-loan-v4-f16.gguf" "$OUT/cs-loan-v4-q4_k_m.gguf" Q4_K_M >> "$OUT/convert.log" 2>&1
  if [ $? -eq 0 ] && [ -s "$OUT/cs-loan-v4-q4_k_m.gguf" ]; then mark gguf OK; rm -f "$OUT/cs-loan-v4-f16.gguf"; else mark gguf FAIL; fi
else mark gguf SKIP; fi

# ---- 4. Ollama 등록 (기존 cs-loan-v3, cs-loan-test는 건드리지 않는다) ----------------------------------------------------
if grep -q "^gguf OK" "$STATUS"; then
  sed "s#^FROM .*#FROM $PWD/$OUT/cs-loan-v4-q4_k_m.gguf#" models/loan/Modelfile > "$OUT/Modelfile.v4"
  if ollama create cs-loan-v4 -f "$OUT/Modelfile.v4" > "$OUT/ollama_create.log" 2>&1; then mark ollama OK; else mark ollama FAIL; fi
else mark ollama SKIP; fi

# ---- 5. 스모크 테스트 (F01~F10 제외, 판정 아님) ------------------------------------------------------------------------
if grep -q "^ollama OK" "$STATUS"; then
  if $PY training/loan/smoke_v4.py cs-loan-v4 > "$OUT/smoke.txt" 2>&1; then mark smoke OK; else mark smoke FAIL; fi
else mark smoke SKIP; fi

say "종료. 단계 결과:"; cat "$STATUS"
say "산출물: $OUT/adapter, checkpoint-*, summary.txt, smoke.txt / 로그: training/loan/outputs_v4_train.log"
