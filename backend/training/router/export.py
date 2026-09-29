import json
import os
import subprocess
import sys
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_NAME = "cs-router"                                                          # 계약 5 이름
MODELS_DIR = Path(__file__).resolve().parents[2] / "models" / "router"
LLAMA_CPP = Path(os.environ.get("LLAMA_CPP_DIR", "~/qlora_ft_ex/llama.cpp")).expanduser()

# Ollama Modelfile. 채팅 템플릿은 GGUF 안에 든 Qwen3 템플릿(학습 때 쓴 것과 동일, think:false 처리 포함)을 Ollama가 자동으로 쓴다.
MODELFILE = """FROM ./cs-router.gguf
PARAMETER temperature 0
PARAMETER num_predict 16
"""


def merge(adapter: Path, merged: Path) -> None:
    """LoRA 어댑터를 베이스에 합쳐 safetensors로 저장한다 (CPU, RAM 약 4GB)."""
    base = json.loads((adapter / "adapter_config.json").read_text())["base_model_name_or_path"]
    model = PeftModel.from_pretrained(AutoModelForCausalLM.from_pretrained(base, dtype=torch.float16), adapter)
    model.merge_and_unload().save_pretrained(merged, safe_serialization=True)
    AutoTokenizer.from_pretrained(adapter).save_pretrained(merged)


def convert(merged: Path, f16: Path) -> None:
    env = {**os.environ, "PYTHONPATH": str(LLAMA_CPP / "gguf-py")}                 # 변환 스크립트가 쓰는 gguf 패키지
    subprocess.run([sys.executable, LLAMA_CPP / "convert_hf_to_gguf.py", merged, "--outfile", f16, "--outtype", "f16"],
                   check=True, env=env)


def quantize(f16: Path, gguf: Path) -> None:
    subprocess.run([LLAMA_CPP / "build" / "bin" / "llama-quantize", f16, gguf, "Q4_K_M"], check=True)


def main(adapter: Path) -> None:
    run_dir = adapter.parent
    merged, f16, gguf = run_dir / "merged", run_dir / f"{MODEL_NAME}-f16.gguf", MODELS_DIR / f"{MODEL_NAME}.gguf"
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    if not (merged / "config.json").exists():
        print("1/4 병합");     merge(adapter, merged)
    print("2/4 GGUF f16");  convert(merged, f16)
    print("3/4 Q4_K_M");    quantize(f16, gguf)
    print("4/4 Modelfile"); (MODELS_DIR / "Modelfile").write_text(MODELFILE, encoding="utf-8")
    subprocess.run(["ollama", "create", MODEL_NAME, "-f", MODELS_DIR / "Modelfile"], check=True)
    print(f"등록 완료: ollama run {MODEL_NAME}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
