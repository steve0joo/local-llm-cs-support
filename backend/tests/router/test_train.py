"""cs-router 학습 스크립트 중 GPU 없이 검사할 수 있는 부분 (docs/router/ADR.md RT-006).

- 레코드를 TRL prompt-completion 형식으로 바꾼다. 손실은 completion(코드)에만.
- Qwen3 템플릿이 assistant 앞에 빈 think 블록을 넣는지 확인한다. 추론 때 Ollama가 think:false로 같은 블록을 채운다.
"""
import json

import pytest

pytest.importorskip("trl")            # 학습 의존성이 없는 기기(Mac)에서는 건너뛴다
from training.router import train    # noqa: E402

RECORD = {"messages": [
    {"role": "system", "content": "분류하세요"},
    {"role": "user", "content": "[계좌번호_1] 잔액 알려줘"},
    {"role": "assistant", "content": "balance"},
]}


def test_load_rows_splits_prompt_and_completion(tmp_path):
    path = tmp_path / "train.jsonl"
    path.write_text(json.dumps(RECORD, ensure_ascii=False) + "\n", encoding="utf-8")
    assert train.load_rows(path) == [{
        "prompt": [{"role": "system", "content": "분류하세요"}, {"role": "user", "content": "[계좌번호_1] 잔액 알려줘"}],
        "completion": [{"role": "assistant", "content": "balance"}],
    }]


def test_base_model_follows_rt006():
    assert train.BASE_MODEL == "Qwen/Qwen3-1.7B"
    assert train.MAX_LENGTH == 256


def test_qwen3_template_puts_empty_think_block_before_the_code():
    from transformers import AutoTokenizer
    try:
        tokenizer = AutoTokenizer.from_pretrained(train.BASE_MODEL, local_files_only=True)
    except OSError:
        pytest.skip("Qwen3-1.7B 토크나이저가 HF 캐시에 없다 (학습 노트북에서만 검사)")
    completion = train.check_template(tokenizer, {"prompt": RECORD["messages"][:-1], "completion": RECORD["messages"][-1:]})
    assert completion.startswith(train.NO_THINK + "balance")
