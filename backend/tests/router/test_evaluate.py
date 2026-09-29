"""라우터 평가 스크립트 중 Ollama 없이 검사할 수 있는 부분 (docs/PRD.md 인수 기준 1·7, docs/ADR.md ADR-005).

- test.jsonl에서 (질문, 정답 코드)를 읽고 주제별 건수를 제한할 수 있다(정렬 뒤 앞에서 → 결정적).
- classify() 결과의 첫 코드를 예측으로 본다. 전체·주제별 정확도, 혼동(정답 → 예측), 응답 시간을 계산한다.
"""
import json

from app.router import RouteResult
from training.router import evaluate

RECORDS = [
    {"messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "잔액 알려줘"}, {"role": "assistant", "content": "balance"}]},
    {"messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "잔고 얼마"}, {"role": "assistant", "content": "balance"}]},
    {"messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "대출 만기"}, {"role": "assistant", "content": "loan"}]},
    {"messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "환전"}, {"role": "assistant", "content": "fx"}]},
]


def _write(tmp_path, records):
    path = tmp_path / "test.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    return path


def test_load_examples_reads_question_and_gold(tmp_path):
    examples = evaluate.load_examples(_write(tmp_path, RECORDS))
    assert examples == [("잔액 알려줘", "balance"), ("잔고 얼마", "balance"), ("대출 만기", "loan"), ("환전", "fx")]


def test_limit_per_topic_keeps_first_n_of_each_topic(tmp_path):
    examples = evaluate.load_examples(_write(tmp_path, RECORDS), limit_per_topic=1)
    assert examples == [("잔액 알려줘", "balance"), ("대출 만기", "loan"), ("환전", "fx")]


def test_evaluate_counts_accuracy_per_topic_and_confusion():
    answers = {"잔액 알려줘": ["balance"], "잔고 얼마": ["loan"], "대출 만기": ["loan", "interest"], "환전": []}
    examples = [("잔액 알려줘", "balance"), ("잔고 얼마", "balance"), ("대출 만기", "loan"), ("환전", "fx")]
    result = evaluate.evaluate(examples, classify=lambda q: RouteResult(topics=answers[q]))
    assert result["total"] == 4
    assert result["correct"] == 2                                   # balance ✓, balance ✗(loan), loan ✓(첫 코드), fx ✗(빈 결과)
    assert result["lenient"] == 2                                   # 관대도 같음: 되묻기 [loan, interest]의 정답은 loan
    assert result["per_topic"]["balance"] == {"total": 2, "correct": 1, "lenient": 1}
    assert result["per_topic"]["loan"] == {"total": 1, "correct": 1, "lenient": 1}
    assert result["confusion"][("balance", "loan")] == 1
    assert result["confusion"][("fx", None)] == 1
    assert result["clarify"] == 1                                    # 지원 주제 2개 이상이 나온 건수
    assert len(result["latency"]) == 4
