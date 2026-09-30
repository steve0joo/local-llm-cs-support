import importlib
import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from app import llm, router
from app.router.classify import parse_topic
from app.router.topics import SUPPORTED, SYSTEM_PROMPT, TOPIC_LABELS
from training.router.prepare import OUT_DIR as DATA_DIR

classify_module = importlib.import_module("app.router.classify")   # app.router.classify는 패키지가 export한 함수라 모듈은 이렇게 가져온다
TEST_PATH = DATA_DIR / "test.jsonl"
OUTPUTS_DIR = Path(__file__).resolve().parent / "outputs"


def load_examples(path: Path) -> list[tuple[str, str]]:
    """jsonl → [(질문, 정답 코드)]"""
    rows = [json.loads(line)["messages"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [(m[1]["content"], m[2]["content"]) for m in rows]


def predict_model(question: str) -> str | None:
    """모델만: 키워드 규칙·폴백 없이 cs-router 출력을 파싱한다."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": question}]
    return parse_topic(llm.generate(classify_module.MODEL, messages, temperature=0))


def predict_classify(question: str) -> str | None:
    """서비스 경로: classify()의 첫 코드."""
    topics = router.classify(question).topics
    return topics[0] if topics else None


def agent_of(code: str | None) -> str | None:
    return code if code in SUPPORTED else ("unsupported" if code in TOPIC_LABELS else None)


def score(pairs: list[tuple[str, str | None]]) -> dict:
    """(정답, 예측) 목록 → 지표. 예측 None은 형식 오류(코드가 아닌 출력)."""
    gold_n = Counter(gold for gold, _ in pairs)
    pred_n = Counter(pred for _, pred in pairs)
    hit_n = Counter(gold for gold, pred in pairs if gold == pred)

    per_topic = {}
    for topic in TOPIC_LABELS:
        if not gold_n[topic]:
            continue
        recall = hit_n[topic] / gold_n[topic]
        precision = hit_n[topic] / pred_n[topic] if pred_n[topic] else 0.0
        f1 = 2 * recall * precision / (recall + precision) if recall + precision else 0.0
        per_topic[topic] = {"n": gold_n[topic], "recall": recall, "precision": precision, "f1": f1}

    return {
        "total": len(pairs),
        "accuracy": sum(hit_n.values()) / len(pairs),
        "agent_accuracy": sum(agent_of(g) == agent_of(p) for g, p in pairs) / len(pairs),
        "macro_f1": sum(v["f1"] for v in per_topic.values()) / len(per_topic),
        "min_recall": min(((t, v["recall"]) for t, v in per_topic.items()), key=lambda x: x[1]),
        "format_error_rate": pred_n[None] / len(pairs),
        "per_topic": per_topic,
        "confusion": Counter((g, p) for g, p in pairs if g != p),
    }


def main(model_name: str = classify_module.MODEL, real: bool = False) -> None:
    classify_module.MODEL = model_name
    predict = predict_classify if real else predict_model
    examples = load_examples(TEST_PATH)
    print(f"test {len(examples)}건 평가 중 ({model_name}, {'classify() 경로' if real else '모델만'}) ...")

    pairs, latency = [], []
    for question, gold in examples:
        start = time.perf_counter()
        pairs.append((gold, predict(question)))
        latency.append(time.perf_counter() - start)
    s = score(pairs)
    warm = sorted(latency[1:])
    p95 = warm[int(len(warm) * 0.95) - 1]

    topic, recall = s["min_recall"]
    print(f"\n에이전트 단위 정확도 {s['agent_accuracy']:.1%}   (인수 기준 1: 90%)")
    print(f"9주제 정확도 {s['accuracy']:.1%}   macro-F1 {s['macro_f1']:.3f}   최저 재현율 {recall:.1%} ({topic})   형식 오류 {s['format_error_rate']:.1%}")
    print(f"응답 시간 첫 호출 {latency[0]:.2f}s, 평균 {sum(warm) / len(warm):.2f}s, p95 {p95:.2f}s   (인수 기준 7: 10초)\n")
    print(f"{'주제':15s} {'건수':>5s} {'재현율':>7s} {'정밀도':>7s} {'F1':>6s}")
    for t, v in s["per_topic"].items():
        print(f"{t:15s} {v['n']:5d} {v['recall']:7.1%} {v['precision']:7.1%} {v['f1']:6.3f}")
    print("\n혼동 상위 (정답 → 예측):")
    for (g, p), n in s["confusion"].most_common(10):
        print(f"  {g} → {p}: {n}")

    OUTPUTS_DIR.mkdir(exist_ok=True)
    out = OUTPUTS_DIR / f"eval-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({
        "model": model_name, "path": "classify" if real else "model_only",
        **{k: s[k] for k in ("total", "accuracy", "agent_accuracy", "macro_f1", "min_recall", "format_error_rate", "per_topic")},
        "confusion": {f"{g} → {p}": n for (g, p), n in s["confusion"].items()},
        "latency": {"first": latency[0], "mean": sum(warm) / len(warm), "p95": p95},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장 → {out}")


if __name__ == "__main__":
    main(*(a for a in sys.argv[1:] if a != "real"), real="real" in sys.argv)
