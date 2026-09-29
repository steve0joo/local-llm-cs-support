"""models/interest/Modelfile이 학습·추론 형식과 어긋나지 않는지 확인한다(training/interest/export.md)."""

import re
from pathlib import Path

from app.agents.interest.prompt import SYSTEM_PROMPT

MODELFILE = Path(__file__).resolve().parents[2] / "models/interest/Modelfile"


def block(name: str) -> str:
    m = re.search(rf'^{name} """(.*?)"""', MODELFILE.read_text(encoding="utf-8"), re.S | re.M)
    assert m, f"{name} 블록이 없다"
    return m.group(1)


def test_from_local_gguf():
    # .gguf는 커밋하지 않는다(.gitignore *.gguf). 같은 폴더에 두고 ollama create 한다.
    assert re.search(r"^FROM \./cs-interest\.gguf$", MODELFILE.read_text(encoding="utf-8"), re.M)


def test_system_matches_prompt_module():
    # 학습 데이터·에이전트가 쓰는 시스템 프롬프트와 한 글자도 다르면 안 된다.
    assert block("SYSTEM") == SYSTEM_PROMPT


def test_template_is_chatml_without_think():
    # 공식 Qwen3-4B-Instruct-2507 템플릿과 같은 ChatML. 생각 블록을 넣지 않는다(unslothai/unsloth#3383).
    template = block("TEMPLATE")
    assert "<think>" not in template
    assert "<|im_start|>{{ .Role }}\n{{ .Content }}<|im_end|>\n" in template
    assert template.endswith("<|im_start|>assistant\n")


def test_stop_tokens_and_sampling():
    text = MODELFILE.read_text(encoding="utf-8")
    assert 'PARAMETER stop "<|im_end|>"' in text
    temperature = float(re.search(r"^PARAMETER temperature ([\d.]+)$", text, re.M).group(1))
    assert temperature <= 0.3  # 지어내기를 줄이려고 낮게 둔다
