"""export.py 중 실행 없이 검사할 수 있는 부분. 병합·변환·양자화는 GPU와 llama.cpp가 필요해 여기서 돌리지 않는다."""
import pytest

pytest.importorskip("peft")            # 학습 의존성이 없는 기기(Mac)에서는 건너뛴다
from training.router import export     # noqa: E402


def test_modelfile_loads_gguf_and_is_deterministic_without_overriding_template():
    text = export.MODELFILE
    assert text.startswith("FROM ./cs-router.gguf\n")
    assert "PARAMETER temperature 0" in text
    assert "TEMPLATE" not in text        # GGUF에 든 Qwen3 템플릿을 그대로 쓴다 (think:false 처리 포함)


def test_model_name_matches_contract_5():
    assert export.MODEL_NAME == "cs-router"
