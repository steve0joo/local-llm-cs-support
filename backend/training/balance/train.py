"""Mac MLX LM 학습 진입점. 실제 상담 데이터는 data/ 아래에만 둔다."""

from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import subprocess
import sys
from pathlib import Path


DEFAULT_ADAPTER = Path(__file__).resolve().parent / "outputs" / "adapters"
ROLES = {"system", "user", "assistant"}


def check_dataset(data_dir: Path, mode: str) -> dict[str, int]:
    names = ("train", "valid") if mode == "train" else ("test",)
    counts = {}
    for name in names:
        path = data_dir / f"{name}.jsonl"
        if not path.is_file():
            raise ValueError(f"필요한 데이터 파일이 없습니다: {path}")
        count = 0
        with path.open(encoding="utf-8") as source:
            for line_no, line in enumerate(source, 1):
                if not line.strip():
                    raise ValueError(f"빈 JSONL 줄: {path}:{line_no}")
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"JSON 형식 오류: {path}:{line_no}") from exc
                messages = item.get("messages") if isinstance(item, dict) else None
                if not isinstance(messages, list) or len(messages) < 2:
                    raise ValueError(f"messages 형식 오류: {path}:{line_no}")
                if any(
                    not isinstance(message, dict)
                    or message.get("role") not in ROLES
                    or not isinstance(message.get("content"), str)
                    or not message["content"].strip()
                    for message in messages
                ) or messages[-1]["role"] != "assistant" or not any(
                    message["role"] == "user" for message in messages
                ):
                    raise ValueError(f"대화 역할·내용 오류: {path}:{line_no}")
                count += 1
        if count == 0:
            raise ValueError(f"데이터 파일이 비었습니다: {path}")
        counts[name] = count
    return counts


def check_model(model_dir: Path) -> None:
    config_path = model_dir / "config.json"
    if not config_path.is_file():
        raise ValueError(f"로컬 MLX 모델 config.json이 없습니다: {config_path}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not (config.get("quantization") or config.get("quantization_config")):
        raise ValueError("양자화 베이스 모델이 아닙니다. QLoRA에는 양자화 MLX 모델이 필요합니다.")


def build_command(args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable, "-m", "mlx_lm", "lora", "--model", str(args.model),
        "--data", str(args.data), "--adapter-path", str(args.adapter_path),
        "--batch-size", str(args.batch_size), "--max-seq-length", str(args.max_seq_length),
    ]
    if args.mode == "train":
        command += ["--train", "--mask-prompt", "--iters", str(args.iters),
                    "--num-layers", str(args.num_layers)]
    else:
        command += ["--test"]
    return command


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="잔액조회 Mac MLX LM QLoRA 학습·평가")
    parser.add_argument("mode", choices=("check", "train", "test"))
    parser.add_argument("--model", type=Path, required=True, help="로컬 양자화 MLX 베이스")
    parser.add_argument("--data", type=Path, required=True, help="train/valid/test.jsonl 디렉터리")
    parser.add_argument("--adapter-path", type=Path, default=DEFAULT_ADAPTER)
    parser.add_argument("--iters", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--num-layers", type=int, default=8)
    parser.add_argument("--max-seq-length", type=int, default=1024)
    args = parser.parse_args(argv)

    if sys.platform != "darwin" or platform.machine() != "arm64":
        parser.error("Mac Apple Silicon에서만 실행할 수 있습니다")
    if min(args.iters, args.batch_size, args.num_layers, args.max_seq_length) < 1:
        parser.error("학습 수치는 양수여야 합니다")
    try:
        check_model(args.model)
        counts = check_dataset(args.data, "test" if args.mode == "test" else "train")
        if args.mode == "test" and not (args.adapter_path / "adapters.safetensors").is_file():
            raise ValueError(f"학습된 어댑터가 없습니다: {args.adapter_path}")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    print("데이터 점검 통과:", ", ".join(f"{name}={count}" for name, count in counts.items()))
    if args.mode == "check":
        return 0
    if importlib.util.find_spec("mlx_lm") is None:
        parser.error("MLX LM이 없습니다. requirements-mac.txt를 .venv-train에 설치하세요")
    return subprocess.run(build_command(args), check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
