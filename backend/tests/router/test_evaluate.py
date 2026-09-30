"""라우터 평가 지표 (docs/PRD.md 인수 기준 1·7). 채점은 score() 순수 함수라 Ollama 없이 검사한다.

- 에이전트 단위 정확도: balance/loan/interest/미지원 4갈래. 미지원끼리 혼동은 정답 (인수 기준 1의 정의).
- 9주제 정확도, 주제별 재현율·정밀도·F1, macro-F1, 최저 재현율, 형식 오류율(코드가 아닌 출력).
"""
import json

import pytest

from training.router import evaluate

RECORDS = [
    {"messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "잔액 알려줘"}, {"role": "assistant", "content": "balance"}]},
    {"messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "환전"}, {"role": "assistant", "content": "fx"}]},
]


def test_load_examples_reads_question_and_gold(tmp_path):
    path = tmp_path / "test.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in RECORDS), encoding="utf-8")
    assert evaluate.load_examples(path) == [("잔액 알려줘", "balance"), ("환전", "fx")]


# (정답, 예측) — balance 2건 중 1건 loan으로, fx 1건은 limit으로(미지원끼리), loan 1건은 None(형식 오류)
PAIRS = [("balance", "balance"), ("balance", "loan"), ("fx", "limit"), ("loan", None)]


def test_topic_accuracy_and_agent_accuracy():
    s = evaluate.score(PAIRS)
    assert s["accuracy"] == 1 / 4                  # 9주제: balance 하나만 정확
    assert s["agent_accuracy"] == 2 / 4            # fx→limit은 둘 다 미지원이라 정답


def test_per_topic_recall_precision_f1():
    s = evaluate.score(PAIRS)
    assert s["per_topic"]["balance"] == {"n": 2, "recall": 0.5, "precision": 1.0, "f1": 2 / 3}
    assert s["per_topic"]["loan"]["recall"] == 0.0                       # 정답 loan 1건을 None으로
    assert s["per_topic"]["loan"]["precision"] == 0.0                    # loan으로 예측한 1건(balance)이 오답
    assert s["per_topic"]["fx"]["recall"] == 0.0
    assert "limit" not in s["per_topic"]                                  # 정답에 없는 주제는 표에 넣지 않는다


def test_macro_f1_min_recall_and_format_error_rate():
    s = evaluate.score(PAIRS)
    assert s["macro_f1"] == pytest.approx((2 / 3) / 3)   # 정답에 등장한 주제(balance, loan, fx)만 평균
    assert s["min_recall"] == ("loan", 0.0)                # 0인 주제가 둘이면 TOPIC_LABELS 순서상 앞의 것
    assert s["format_error_rate"] == 1 / 4


def test_confusion_keeps_only_mistakes():
    s = evaluate.score(PAIRS)
    assert s["confusion"] == {("balance", "loan"): 1, ("fx", "limit"): 1, ("loan", None): 1}
