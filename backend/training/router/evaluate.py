"""cs-router 평가 (docs/PRD.md 인수 기준 1·7, docs/ADR.md ADR-005 벤치마크).

실행: cd backend && python -m training.router.evaluate [주제별 건수 제한] [model]
      예) python -m training.router.evaluate 100        → 주제별 100건, 실제 경로(키워드 규칙 + 모델)
          python -m training.router.evaluate 0 model    → 전량, 키워드 규칙 없이 모델만
필요: Ollama 실행 중 + cs-router 등록, data/processed/router/test.jsonl (prepare.py)

test.jsonl의 질문을 실제 추론 경로 classify()(RT-002 키워드 규칙 + 모델)로 돌려
전체·주제별 정확도, 혼동(정답 → 예측), 응답 시간을 출력하고 outputs/eval-<시각>.json에 남긴다.
- 엄격: 첫 코드 == 정답. 관대: 정답이 topics 안에 있음(되묻기 선택지에 정답이 있으면 클릭 한 번으로 맞는 에이전트로 간다).
"""
import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from app import llm, router
from app.router.classify import MODEL, RouteResult, parse_topic
from app.router.topics import SUPPORTED, SYSTEM_PROMPT, TOPIC_LABELS
from training.router.prepare import OUT_DIR as DATA_DIR

TEST_PATH = DATA_DIR / "test.jsonl"
OUTPUTS_DIR = Path(__file__).resolve().parent / "outputs"


def load_examples(path: Path, limit_per_topic: int | None = None) -> list[tuple[str, str]]:
    """jsonl → [(질문, 정답 코드)]. 제한이 있으면 주제별로 파일 순서상 앞 n건만(정렬돼 있어 결정적)."""
    examples, taken = [], Counter()
    for line in path.read_text(encoding="utf-8").splitlines():
        messages = json.loads(line)["messages"]
        question, gold = messages[1]["content"], messages[2]["content"]
        if limit_per_topic and taken[gold] >= limit_per_topic:
            continue
        taken[gold] += 1
        examples.append((question, gold))
    return examples


def classify_model_only(question: str) -> RouteResult:
    """키워드 규칙 없이 cs-router만 부른다. 모델 자체의 정확도를 보기 위한 경로."""
    raw = llm.generate(MODEL, [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": question}], temperature=0)
    code = parse_topic(raw)
    return RouteResult(topics=[code] if code else [])


def evaluate(examples: list[tuple[str, str]], classify=router.classify) -> dict:
    """엄격: 첫 코드 == 정답. 관대: 정답이 topics 안에 있음. 지원 주제 2개 이상(되묻기)은 따로 센다."""
    per_topic = {code: {"total": 0, "correct": 0, "lenient": 0} for code in TOPIC_LABELS}
    confusion: Counter = Counter()
    latency, clarify = [], 0
    for question, gold in examples:
        start = time.perf_counter()
        topics = classify(question).topics
        latency.append(time.perf_counter() - start)
        pred = topics[0] if topics else None
        clarify += len([t for t in topics if t in SUPPORTED]) >= 2
        per_topic[gold]["total"] += 1
        per_topic[gold]["correct"] += pred == gold
        per_topic[gold]["lenient"] += gold in topics
        if pred != gold:
            confusion[(gold, pred)] += 1
    return {
        "total": len(examples),
        "correct": sum(v["correct"] for v in per_topic.values()),
        "lenient": sum(v["lenient"] for v in per_topic.values()),
        "per_topic": per_topic,
        "confusion": confusion,
        "clarify": clarify,
        "latency": latency,
    }


def report(result: dict) -> None:
    total, correct = result["total"], result["correct"]
    lenient = result["lenient"]
    print(f"\n엄격 정확도 {correct}/{total} = {correct / total:.1%}   관대 {lenient}/{total} = {lenient / total:.1%}   (인수 기준 1: 90% 이상)")
    print(f"되묻기(지원 주제 2개 이상) {result['clarify']}건\n")
    print(f"{'주제':15s} {'건수':>5s} {'엄격':>7s} {'관대':>7s}")
    for code, v in result["per_topic"].items():
        if v["total"]:
            print(f"{code:15s} {v['total']:5d} {v['correct'] / v['total']:7.1%} {v['lenient'] / v['total']:7.1%}")
    print("\n혼동 상위 (정답 → 예측):")
    for (gold, pred), n in result["confusion"].most_common(10):
        print(f"  {gold} → {pred}: {n}")
    lat = sorted(result["latency"])
    warm = lat[1:] or lat
    print(f"\n응답 시간: 첫 호출 {result['latency'][0]:.2f}s (적재 포함), 이후 평균 {sum(warm) / len(warm):.2f}s, "
          f"p50 {warm[len(warm) // 2]:.2f}s, p95 {warm[int(len(warm) * 0.95) - 1]:.2f}s   (인수 기준 7: 전체 10초 이내)")


def main(limit_per_topic: int | None = None, model_only: bool = False) -> None:
    examples = load_examples(TEST_PATH, limit_per_topic)
    print(f"test {len(examples)}건 평가 중 ({'모델만' if model_only else '키워드 규칙 + 모델'}) ...")
    result = evaluate(examples, classify=classify_model_only if model_only else router.classify)
    report(result)

    OUTPUTS_DIR.mkdir(exist_ok=True)
    out = OUTPUTS_DIR / f"eval-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({
        **{k: result[k] for k in ("total", "correct", "lenient", "per_topic", "clarify")},
        "model_only": model_only,
        "confusion": {f"{g} → {p}": n for (g, p), n in result["confusion"].items()},
        "latency_mean": sum(result["latency"]) / len(result["latency"]),
        "limit_per_topic": limit_per_topic,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장 → {out}")


if __name__ == "__main__":
    main(int(sys.argv[1]) or None if len(sys.argv) > 1 else None, model_only="model" in sys.argv[2:])
