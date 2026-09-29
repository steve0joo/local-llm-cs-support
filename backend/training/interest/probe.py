"""새 질문 40개로 모델을 분석하고 결과 숫자를 wandb에 올린다(개인 개발용).

- 질문은 Golden Set·수동 테스트(ask.py)·학습 템플릿·수동 학습 샘플과 겹치지 않는다(test_probe가 확인).
- 채점은 evaluate.py와 같다(검증 통과·금지 표현·기대 조건·상담 톤 → 규칙 준수).
- wandb에는 **숫자만** 올린다: 전체 지표, 유형별 규칙 준수율, 문항별 점수표(원문 제외).
  질문·답변 원문은 이 장비의 training/interest/outputs/eval/probe-<name>.jsonl에만 저장한다.
- wandb는 --wandb를 줄 때만 import한다(팀 공통 환경에는 설치하지 않는다).

실행(학습 장비):
  cd backend
  training/interest/.venv/bin/python -m training.interest.probe --name base --wandb
  training/interest/.venv/bin/python -m training.interest.probe --name v03 --adapter training/interest/outputs/runs/<버전>/adapter --wandb
"""

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from app.agents.interest.balance_source import enrich
from app.agents.interest.prompt import build_messages
from training.interest.evaluate import EVAL_DIR, MOCK_FILE, generate_answers, summarize
from training.interest.train import DEFAULT_BASE_MODEL, OUTPUT_DIR

WANDB_PROJECT = "cs-interest"

# (고객, 질문, 기대 조건 코드). C002 정상·만기일시·변동·자동이체 / C003 연체 12일·원리금균등·고정·가상계좌
# C004 연체 65일·자동이체 / C005 정상·원금균등·가상계좌 / C006 연체 2일·자동이체 / C007 정상·납부일 임박·만기일시
PROBE_QUESTIONS = [
    ("C002", "이번 달 대출이자 금액 좀 알려줄래요?", "interest_amount"),
    ("C002", "이자 빠져나가는 날짜가 며칠이에요?", "due_date"),
    ("C002", "혹시 이자 밀린 거 있나 확인 좀요", "overdue_status"),
    ("C002", "제 대출은 원금을 언제 갚는 구조예요?", "loan_terms_repay"),
    ("C002", "금리가 고정인지 궁금해요", "loan_terms_interest_type"),
    ("C002", "이자는 어떤 방식으로 내고 있어요?", "loan_terms_payment"),
    ("C002", "요즘 대출 금리 몇 퍼센트쯤 해요?", "rate"),
    ("C002", "이자가 지난달보다 늘었는데 이유가 뭘까요?", "reason"),
    ("C002", "대출 이자 좀 할인받을 수 있나요?", "guarantee"),
    ("C002", "제 명의 카드론도 조회돼요?", "missing_info"),
    ("C003", "연체된 금액 정확히 얼마예요?", "overdue_status"),
    ("C003", "며칠째 연체 중인 거예요?", "overdue_status"),
    ("C003", "밀린 이자 입금은 어디에 하면 되나요?", "loan_terms_payment"),
    ("C003", "이번에 낼 이자는 따로 얼마예요?", "interest_amount"),
    ("C003", "연체되면 가산 이자가 몇 퍼센트예요?", "rate"),
    ("C003", "연체 계속되면 어떤 불이익이 있어요?", "overdue_action"),
    ("C003", "연체 기록 지울 방법 있어요?", "guarantee"),
    ("C003", "저 연체 없는 걸로 아는데요?", "false_premise"),
    ("C003", "다음 달 납부일은 언제예요?", "due_date"),
    ("C003", "연체 이자 계산해 주실 수 있어요?", "calculation"),
    ("C004", "연체 금액 얼마나 쌓였어요?", "overdue_status"),
    ("C004", "자동이체인데 왜 연체가 났죠?", "reason"),
    ("C004", "연체 해결하려면 뭘 먼저 해야 돼요?", "overdue_action"),
    ("C004", "금리 방식이 어떻게 돼요?", "loan_terms_interest_type"),
    ("C004", "연체 이자율 좀 낮춰 주세요", "guarantee"),
    ("C005", "이번 이자 얼마 내면 돼요?", "interest_amount"),
    ("C005", "이자 입금은 어디로 해요?", "loan_terms_payment"),
    ("C005", "원금은 어떻게 갚아 나가는 방식이에요?", "loan_terms_repay"),
    ("C005", "납부일이 언제로 돼 있어요?", "due_date"),
    ("C005", "연체된 건 없죠?", "overdue_status"),
    ("C006", "연체가 생겼다는데 며칠 된 거예요?", "overdue_status"),
    ("C006", "연체 금액 알려 주세요", "overdue_status"),
    ("C006", "지금 바로 내면 연체 해결되나요?", "overdue_action"),
    ("C006", "이번 회차 이자는 얼마예요?", "interest_amount"),
    ("C007", "이자 납부일이 언제죠?", "due_date"),
    ("C007", "이자 얼마 준비해 두면 돼요?", "interest_amount"),
    ("C007", "원금은 매달 나가나요?", "loan_terms_repay"),
    ("C007", "금리는 바뀌는 방식이에요?", "loan_terms_interest_type"),
    ("C007", "만기 연장 가능해요?", "staff"),
    ("C007", "변동금리라는 게 무슨 뜻이에요?", "term"),
]

TABLE_COLUMNS = ["id", "customer", "expect", "rule", "expect_ok", "valid", "slot", "forbidden_count", "tone", "length", "seconds"]


def build_probe_cases(mock: dict) -> list[dict]:
    return [
        {"set": "probe", "id": f"probe-{i:02d}", "customer": c, "question": q, "expect": e, "item": enrich(mock[c][0], c),
         "messages": build_messages(q, [], enrich(mock[c][0], c))}
        for i, (c, q, e) in enumerate(PROBE_QUESTIONS, 1)
    ]


def wandb_payload(rows: list[dict]):
    """wandb에 올릴 숫자만 만든다. 질문·답변 원문은 넣지 않는다."""
    s = summarize(rows)["all"]
    summary = {**s, "avg_seconds": sum(r["seconds"] for r in rows) / len(rows)}
    by_cat = defaultdict(list)
    for r in rows:
        by_cat[r["expect"]].append(bool(r["score"]["rule"]))
    per_category = {f"category/{k}": sum(v) / len(v) for k, v in sorted(by_cat.items())}
    table_rows = [
        [r["id"], r["customer"], r["expect"], bool(r["score"]["rule"]), bool(r["score"]["expect"]), r["score"]["valid"],
         r["score"]["slot"], len(r["score"]["forbidden"]), r["score"]["tone"], r["score"]["length"], r["seconds"]]
        for r in rows
    ]
    return summary, per_category, table_rows, TABLE_COLUMNS


def _question_set_hash() -> str:
    return hashlib.sha256(json.dumps(PROBE_QUESTIONS, ensure_ascii=False).encode()).hexdigest()[:10]


def log_to_wandb(rows: list[dict], name: str, base_model: str, adapter: Path | None) -> str:
    import wandb  # 개인 개발 환경에만 설치

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    summary, per_category, table_rows, columns = wandb_payload(rows)
    version = adapter.parent.name if adapter else "base"
    run = wandb.init(
        project=WANDB_PROJECT,
        name=f"probe40-{name}",
        group="probe40",
        job_type="eval",
        dir=str(OUTPUT_DIR),  # 로컬 실행 기록을 gitignore 폴더(outputs/wandb/)에 남긴다
        config={"model": version, "base_model": base_model, "question_set": "probe40",
                "question_set_sha": _question_set_hash(), "generation": "greedy, max_new_tokens=256", "n": len(rows)},
    )
    run.summary.update({**summary, **per_category})
    run.log({**{f"metrics/{k}": v for k, v in summary.items() if isinstance(v, (int, float))}, **per_category,
             "per_question": wandb.Table(columns=columns, data=table_rows)})
    url = run.url
    run.finish()
    return url


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="새 질문 40개 분석 (+wandb)")
    p.add_argument("--name", required=True)
    p.add_argument("--base-model", default=DEFAULT_BASE_MODEL)
    p.add_argument("--adapter", type=Path)
    p.add_argument("--wandb", action="store_true", help="숫자 결과를 wandb에 올린다(개인 개발용)")
    args = p.parse_args(argv)

    mock = json.loads(MOCK_FILE.read_text(encoding="utf-8"))
    rows = generate_answers(build_probe_cases(mock), args.base_model, args.adapter)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    with (EVAL_DIR / f"probe-{args.name}.jsonl").open("w", encoding="utf-8") as f:  # 원문은 로컬에만
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary, per_category, _, _ = wandb_payload(rows)
    print(json.dumps({**summary, **per_category}, ensure_ascii=False, indent=2))
    if args.wandb:
        print("wandb:", log_to_wandb(rows, args.name, args.base_model, args.adapter))


if __name__ == "__main__":
    main()
