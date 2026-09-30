import re
from pathlib import Path

from app.agents.balance.prompt import SYSTEM_PROMPT

MODELFILE = Path(__file__).resolve().parents[2] / "models" / "balance" / "Modelfile"


def _text() -> str:
    return MODELFILE.read_text(encoding="utf-8")


def _block(name: str) -> str:
    match = re.search(rf'^{name} """(.*?)"""', _text(), re.M | re.S)
    assert match, f"{name} 블록이 없다"
    return match.group(1)


def test_system_matches_prompt_system_prompt():
    # 학습 데이터(prepare.py)와 추론 입력의 system 메시지가 prompt.SYSTEM_PROMPT다
    assert _block("SYSTEM") == SYSTEM_PROMPT


def test_from_local_gguf():
    assert re.search(r"^FROM \./cs-balance\.gguf$", _text(), re.M)


def test_stop_im_end():
    assert re.search(r'^PARAMETER stop "<\|im_end\|>"$', _text(), re.M)


def test_template_is_chatml_without_think():
    template = _block("TEMPLATE")
    assert "<|im_start|>" in template and "<|im_end|>" in template
    assert "<think>" not in template
