"""AI Hub 학습 후보 사람 검수 도구 (docs/agent-interest/TRAINING_DATA_PLAN.md 5절).

candidates.jsonl의 AI Hub 샘플을 한 건씩 보여 주고 승인·반려·수정을 reviews.json에 저장한다.
원문은 이 장비 터미널에만 표시한다(데이터 제3자 제공 금지). 판정마다 저장하므로 중간에 멈춰도 이어서 할 수 있다.

실행: cd backend && python -m training.interest.review [--data-dir data/raw/04_interest_finetune]
      이후 prepare.py를 다시 실행하면 판정이 학습 데이터에 반영된다.
"""

import argparse
import json
from pathlib import Path

from app.agents.interest.prompt import build_slots
from app.agents.interest.validate import is_valid, required_slots
from training.interest.prepare import OUT_DIR, REVIEWS_FILE

HELP = "[a] 승인  [r] 반려  [e] 답 고쳐서 승인  [s] 건너뜀  [q] 종료"


def review_queue(candidates: list[dict], reviews: dict) -> list[dict]:
    """아직 판정하지 않은 AI Hub 샘플. 합성 샘플은 템플릿 단위로 검수하므로 뺀다."""
    return [r for r in candidates if r["origin"] == "aihub" and r["id"] not in reviews]


def render(record: dict, position: tuple[int, int]) -> str:
    turns = record["messages"][1:]  # 시스템 프롬프트는 모든 샘플이 같다
    lines = [f"[{position[0]}/{position[1]}] {record['id']}  ({record['category']}, {record['scenario']})", "-" * 60]
    for m in turns[:-2]:
        lines.append(f"{'고객' if m['role'] == 'user' else '상담'} (이전): {m['content']}")
    question, *context = turns[-2]["content"].split("\n")
    lines += [f"고객 질문: {question}", *context, "", f"▶ 학습할 답: {turns[-1]['content']}", "-" * 60]
    return "\n".join(lines)


def decide(record: dict, action: str, text: str | None = None, note: str = "") -> dict:
    if action == "a":
        return {"ok": True, "note": note}
    if action == "r":
        return {"ok": False, "note": note}
    if action == "e":
        item = record["item"]
        question = record["messages"][-2]["content"].split("\n")[0]
        required = required_slots(question, item["overdue_days"] > 0)
        if not text or not is_valid(text, allowed_slots=set(build_slots(item)), required_slots=required):
            raise ValueError("고친 답이 출력 검증을 통과하지 못한다(금액·금리 숫자, 허용 밖 슬롯, 필수 슬롯 누락 등)")
        return {"ok": True, "note": note, "output": text}
    raise ValueError(f"알 수 없는 선택: {action}")


def load_reviews(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else {}


def save_reviews(path: Path, reviews: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(reviews, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)  # 쓰는 도중 멈춰도 기존 판정이 깨지지 않게


def run(candidates: list[dict], path: Path, ask=input, show=print) -> None:
    reviews = load_reviews(path)
    queue = review_queue(candidates, reviews)
    show(f"검수 대기 {len(queue)}건 (이미 판정 {len(reviews)}건)\n{HELP}")
    for i, record in enumerate(queue, 1):
        show(render(record, (i, len(queue))))
        while True:
            action = ask("선택> ").strip().lower()
            if action == "q":
                show(f"종료. 저장된 판정 {len(reviews)}건")
                return
            if action == "s":
                break
            try:
                if action == "r":
                    entry = decide(record, "r", note=ask("반려 이유> ").strip())
                elif action == "e":
                    text = ask("고친 답> ").strip()
                    decide(record, "e", text=text)  # 메모를 묻기 전에 먼저 검증한다
                    entry = decide(record, "e", text=text, note=ask("메모> ").strip())
                else:
                    entry = decide(record, action)
            except ValueError as e:
                show(f"다시 입력: {e}\n{HELP}")
                continue
            reviews[record["id"]] = entry
            save_reviews(path, reviews)
            break
    show(f"끝. 저장된 판정 {len(reviews)}건. prepare.py를 다시 실행하면 반영된다.")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="AI Hub 학습 후보 사람 검수")
    p.add_argument("--data-dir", type=Path, default=OUT_DIR, help="candidates.jsonl이 있는 폴더")
    p.add_argument("--reviews", type=Path, default=REVIEWS_FILE)
    args = p.parse_args(argv)
    lines = (args.data_dir / "candidates.jsonl").read_text(encoding="utf-8").splitlines()
    run([json.loads(line) for line in lines if line.strip()], args.reviews)


if __name__ == "__main__":
    main()
