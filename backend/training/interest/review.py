"""AI Hub 학습 후보 사람 검수 도구 (docs/agent-interest/TRAINING_DATA_PLAN.md 5절).

candidates.jsonl의 AI Hub 샘플을 한 건씩 보여 주고 승인·반려·수정을 reviews.json에 저장한다.
원문은 이 장비 터미널에만 표시한다(데이터 제3자 제공 금지). 판정마다 저장하므로 중간에 멈춰도 이어서 할 수 있다.

실행: cd backend && python -m training.interest.review [--data-dir data/raw/04_interest_finetune]
      이후 prepare.py를 다시 실행하면 판정이 학습 데이터에 반영된다.

--fix: fix_queue.jsonl(표현 문제로 빠진 AI Hub train 샘플)을 고친다. 승인만은 안 되고, 고친 답을 쓰거나 반려한다.
      --reasons invalid,promise처럼 사유별로 나눠 할 수 있다.
      고친 답은 학습 데이터 제외 규칙과 추론 출력 검증을 모두 통과해야 저장된다(prepare.answer_problems).
"""

import argparse
import json
from pathlib import Path

from app.agents.interest.validate import phrase_problems
from training.interest.prepare import OUT_DIR, REVIEWS_FILE, answer_problems

HELP = "[a] 승인  [r] 반려  [e] 답 고쳐서 승인  [s] 건너뜀  [q] 종료"
HELP_FIX = "[e] 답 고쳐서 사용  [r] 반려  [s] 건너뜀  [q] 종료"


def review_queue(candidates: list[dict], reviews: dict) -> list[dict]:
    """아직 판정하지 않은 AI Hub 샘플. 합성 샘플은 템플릿 단위로 검수하므로 뺀다."""
    return [r for r in candidates if r["origin"] == "aihub" and r["id"] not in reviews]


def render(record: dict, position: tuple[int, int]) -> str:
    turns = record["messages"][1:]  # 시스템 프롬프트는 모든 샘플이 같다
    lines = [f"[{position[0]}/{position[1]}] {record['id']}  ({record['category']}, {record['scenario']})", "-" * 60]
    for m in turns[:-2]:
        lines.append(f"{'고객' if m['role'] == 'user' else '상담'} (이전): {m['content']}")
    question, *context = turns[-2]["content"].split("\n")
    lines += [f"고객 질문: {question}", *context, ""]
    if record.get("needs_fix"):
        detail = phrase_problems(turns[-1]["content"])
        lines.append(f"고칠 이유: {record['needs_fix']}" + (f" ({', '.join(detail)})" if detail else ""))
        lines.append(f"▶ 원래 답: {turns[-1]['content']}")
    else:
        lines.append(f"▶ 학습할 답: {turns[-1]['content']}")
    lines.append("-" * 60)
    return "\n".join(lines)


def decide(record: dict, action: str, text: str | None = None, note: str = "") -> dict:
    if action == "a":
        return {"ok": True, "note": note}
    if action == "r":
        return {"ok": False, "note": note}
    if action == "e":
        question = record["messages"][-2]["content"].split("\n")[0]
        problems = answer_problems(text or "", record["item"], question) if text else ["빈 답"]
        if problems:
            raise ValueError(f"고친 답이 검증을 통과하지 못한다: {', '.join(problems)}")
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


def run(candidates: list[dict], path: Path, ask=None, show=print, fix: bool = False) -> None:
    ask = ask or input  # 실행 시점의 input(테스트에서 바꿀 수 있게)
    reviews = load_reviews(path)
    queue = [r for r in candidates if r["id"] not in reviews] if fix else review_queue(candidates, reviews)
    help_text = HELP_FIX if fix else HELP
    show(f"{'수정' if fix else '검수'} 대기 {len(queue)}건 (이미 판정 {len(reviews)}건)\n{help_text}")
    for i, record in enumerate(queue, 1):
        show(render(record, (i, len(queue))))
        while True:
            action = ask("선택> ").strip().lower()
            if action == "q":
                show(f"종료. 저장된 판정 {len(reviews)}건")
                return
            if action == "s":
                break
            if fix and action == "a":
                show(f"표현 문제로 빠진 답이라 승인만으로는 쓸 수 없다. 고친 답을 쓰거나(e) 반려(r)한다.\n{help_text}")
                continue
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
                show(f"다시 입력: {e}\n{help_text}")
                continue
            reviews[record["id"]] = entry
            save_reviews(path, reviews)
            break
    show(f"끝. 저장된 판정 {len(reviews)}건. prepare.py를 다시 실행하면 반영된다.")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="AI Hub 학습 후보 사람 검수")
    p.add_argument("--data-dir", type=Path, default=OUT_DIR, help="candidates.jsonl이 있는 폴더")
    p.add_argument("--reviews", type=Path, default=REVIEWS_FILE)
    p.add_argument("--fix", action="store_true", help="fix_queue.jsonl의 AI Hub 답을 고친다")
    p.add_argument("--reasons", help="--fix에서 이 사유만(쉼표로 구분, 예: invalid,promise,claim,call_context)")
    args = p.parse_args(argv)
    lines = (args.data_dir / ("fix_queue.jsonl" if args.fix else "candidates.jsonl")).read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines if line.strip()]
    if args.fix and args.reasons:
        wanted = {r.strip() for r in args.reasons.split(",")}
        records = [r for r in records if r.get("needs_fix") in wanted]
    run(records, args.reviews, fix=args.fix)


if __name__ == "__main__":
    main()
