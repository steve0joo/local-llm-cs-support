import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt

OUTPUTS_DIR = Path(__file__).resolve().parent / "outputs"
METRICS = {"agent_accuracy": "에이전트 단위 정확도", "accuracy": "9주제 정확도", "macro_f1": "macro-F1"}


def load_results(outputs_dir: Path, models: list[str] | None = None) -> list[dict]:
    latest = {}
    for path in sorted(outputs_dir.glob("eval-*.json")):          # 파일명이 시각순 → 나중 결과가 덮어쓴다
        r = json.loads(path.read_text(encoding="utf-8"))
        if r.get("path") == "model_only" and (not models or r["model"] in models):
            latest[r["model"]] = r
    return [latest[m] for m in sorted(latest)]


def main(models: list[str]) -> None:
    rows = load_results(OUTPUTS_DIR, models)
    for r in rows:
        print(f"{r['model']:26s} " + "  ".join(f"{label} {r[key]:.3f}" if key == "macro_f1" else f"{label} {r[key]:.1%}" for key, label in METRICS.items()))

    plt.rcParams["font.family"] = ["NanumGothic", "NanumSquare", "DejaVu Sans"]   # 한글
    fig, ax = plt.subplots(figsize=(2 + 2 * len(rows), 4))
    width = 0.25
    for i, (key, label) in enumerate(METRICS.items()):
        bars = ax.bar([x + i * width for x in range(len(rows))], [r[key] for r in rows], width, label=label)
        ax.bar_label(bars, fmt="{:.3f}" if key == "macro_f1" else "{:.1%}", fontsize=8)
    ax.axhline(0.9, linestyle="--", color="gray", label="인수 기준 90%")
    ax.set_xticks([x + width for x in range(len(rows))], [r["model"] for r in rows])
    ax.set_ylim(0, 1.05)
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncols=4)   # 축 아래: 막대·기준선을 가리지 않게
    fig.tight_layout()
    fig.savefig(OUTPUTS_DIR / "compare.png", dpi=150)
    print(f"저장 → {OUTPUTS_DIR / 'compare.png'}")


if __name__ == "__main__":
    main(sys.argv[1:])
