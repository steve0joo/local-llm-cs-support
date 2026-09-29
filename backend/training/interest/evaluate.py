"""cs-interest 답변 평가 (docs/agent-interest/EVALUATION.md).

같은 질문 셋으로 베이스와 파인튜닝 모델을 비교한다.
- golden: 데모 고객(C002 정상, C003 연체) 고정 질문 + 문항별 기대 조건. 학습 데이터·합성 템플릿과 겹치지 않는다.
- test: prepare.py가 만든 AI Hub test 분할(학습 미사용). 기대 조건 없음.

지표: 검증 통과(valid), 슬롯 사용(slot), 금지 표현(forbidden), 길이, 상담 톤(tone),
기대 조건(expect), 규칙 준수(rule = valid·금지 표현 없음·expect·tone 모두 충족, golden만).

실행(학습 장비, training/interest/.venv):
  cd backend
  training/interest/.venv/bin/python -m training.interest.evaluate --name base
  training/interest/.venv/bin/python -m training.interest.evaluate --name tuned --adapter training/interest/outputs/<run>/adapter
  training/interest/.venv/bin/python -m training.interest.evaluate --compare base tuned
  training/interest/.venv/bin/python -m training.interest.evaluate --blind base tuned   # 사람 블라인드 평가 시트
  --test-questions: test.jsonl(답 필터를 통과한 것만) 대신 test_questions.jsonl(test 분할 질문 전체, 약 119건)로 평가
출력: training/interest/outputs/eval/ (gitignore). --adapter로 평가하면 <run>/eval/에도 사본. 같은 이름은 덮어쓰지 않음
"""

import argparse
import csv
import json
import random
import re
import time
from pathlib import Path

from app.agents.interest.balance_source import enrich
from app.agents.interest.prompt import build_messages, build_slots
from app.agents.interest.validate import is_valid, phrase_problems, required_slots
from training.interest.prepare import _CLAIM, _PII_REQUEST, tone_ok  # tone_ok: 학습 데이터와 같은 기준
from training.interest.train import DATA_DIR, DEFAULT_BASE_MODEL, OUTPUT_DIR, load_tokenizer

BACKEND = Path(__file__).resolve().parents[2]
MOCK_FILE = BACKEND / "app/agents/interest/mock_data.json"
EVAL_DIR = OUTPUT_DIR / "eval"

# (고객, 질문, 기대 조건 코드). 합성 템플릿(synth.py) 질문과 겹치지 않게 썼다(test_evaluate가 확인).
# C002 = 정상(신용대출·만기일시·변동·자동이체), C003 = 연체 12일(주택담보대출·원리금균등·고정·가상계좌 입금)
# C004 = 연체 65일·자동이체, C005 = 정상·가상계좌·원금균등, C006 = 연체 2일, C007 = 납부일 임박·만기일시
GOLDEN = [
    ("C002", "이번 달에 낼 이자가 얼마죠?", "interest_amount"),
    ("C002", "다음 달엔 얼마 내야 돼요?", "interest_amount"),
    ("C002", "이자 빠지는 날이 언제예요?", "due_date"),
    ("C002", "이자 며칠까지 넣으면 돼요?", "due_date"),
    ("C002", "혹시 제 대출 연체된 거 있나요?", "overdue_status"),
    ("C002", "제가 안 낸 이자가 남아 있나요?", "overdue_status"),
    ("C002", "지금 대출 금리 몇 퍼센트 적용돼 있어요?", "rate"),
    ("C002", "이번 이자가 좀 많이 나온 것 같은데 왜 그래요?", "reason"),
    ("C002", "이자 납부일을 다른 날로 옮길 수 있어요?", "staff"),
    ("C002", "원금은 언제 갚는 거예요?", "loan_terms_repay"),
    ("C002", "제 대출 금리는 시장 따라 바뀌나요?", "loan_terms_interest_type"),
    ("C002", "이자 낼 때 제가 따로 입금해야 하나요?", "loan_terms_payment"),
    ("C002", "연체 이자 붙었다는 문자가 왔는데 뭐죠?", "false_premise"),
    ("C002", "이자 조금만 깎아 주시면 안 될까요?", "guarantee"),
    ("C002", "제 카드 대금도 같이 봐 줄 수 있어요?", "missing_info"),
    ("C002", "중도상환하면 이자 얼마나 줄어요?", "calculation"),
    ("C002", "가산금리가 무슨 뜻이에요?", "term"),
    ("C003", "이번 달에 낼 이자가 얼마죠?", "interest_amount"),
    ("C003", "다음 납부일이 언제로 잡혀 있어요?", "due_date"),
    ("C003", "혹시 제 대출 연체된 거 있나요?", "overdue_status"),
    ("C003", "지금 연체 며칠째예요?", "overdue_status"),
    ("C003", "연체되면 이자 몇 % 더 붙어요?", "rate"),
    ("C003", "이번 이자가 좀 많이 나온 것 같은데 왜 그래요?", "reason"),
    ("C003", "밀린 돈은 어떻게 내면 돼요?", "overdue_action"),
    ("C003", "연체가 계속되면 어떻게 되나요?", "overdue_action"),
    ("C003", "연체된 기록 없애 주실 수 있어요?", "guarantee"),
    ("C003", "연체 이자 계산 방식 좀 알려 주세요", "calculation"),
    ("C003", "저 연체된 거 아니죠? 지난주에 냈는데요", "false_premise"),
    ("C003", "연체 금액 입금은 어디로 해요?", "loan_terms_payment"),
    ("C003", "제 대출은 원금이랑 이자를 같이 갚는 방식이에요?", "loan_terms_repay"),
    ("C003", "제 대출 금리는 고정이에요?", "loan_terms_interest_type"),
    ("C003", "부모님 명의 대출도 여기서 확인돼요?", "missing_info"),
    ("C003", "대출 기간 늘리려면 뭐 챙겨야 해요?", "staff"),
    ("C003", "변동금리랑 고정금리 중 뭐가 유리해요?", "term"),
    # 계약 6 확장 제안 고객(C004~C007). 기존 문항 번호가 바뀌지 않게 맨 뒤에 둔다.
    ("C004", "연체된 지 얼마나 됐어요?", "overdue_status"),
    ("C004", "자동이체 걸어 뒀는데 왜 연체예요?", "reason"),
    ("C005", "이자 낼 계좌가 따로 있나요?", "loan_terms_payment"),
    ("C005", "상환 방식이 뭐로 돼 있죠?", "loan_terms_repay"),
    ("C006", "연체됐다는데 며칠 된 거예요?", "overdue_status"),
    ("C006", "이번에 낼 이자 금액 알려 주실래요?", "interest_amount"),
    ("C007", "이자 내는 날 얼마나 남았어요?", "due_date"),
    ("C007", "제 대출 금리 방식 알려 주세요", "loan_terms_interest_type"),
]
EXPECT_CODES = [
    "interest_amount", "due_date", "overdue_status", "overdue_action", "reason", "term", "rate", "calculation",
    "false_premise", "guarantee", "missing_info", "staff",
    "loan_terms_repay", "loan_terms_interest_type", "loan_terms_payment",
]

# TRAINING_DATA.md 3절 "하지 말 것" 중 출력 검증(is_valid)이 보지 않는 것
FORBIDDEN = [
    ("%", re.compile(r"\d\s*(?:%|퍼센트|프로)")),
    ("서류·증빙", re.compile(r"서류|증명서|사본|등본|신분증")),
    ("은행·앱", re.compile(r"하나은행|하나원큐|은행 앱|앱에서|메뉴")),
    ("시각·기간", re.compile(r"\d+\s*(?:시|분|영업일|시간|개월)")),
    ("처리 주장", _CLAIM),
    ("개인정보 요구", _PII_REQUEST),
]

_NO_OVERDUE = re.compile(r"연체[^.]{0,15}(?:없|않)")


def check_expect(expect: str, item: dict, answer: str) -> bool:
    """문항 유형별로 답에 반드시 있어야 할 내용(EVALUATION.md 질문 2 '질문에 맞는 내용')."""
    overdue = item["overdue_days"] > 0
    y, m, d = item["next_due_date"].split("-")
    has_date = item["next_due_date"] in answer or f"{int(m)}월 {int(d)}일" in answer
    states_overdue = f"{item['overdue_days']}일" in answer and "{{overdue_amount}}" in answer
    states_no_overdue = "{{overdue_amount}}" not in answer and bool(_NO_OVERDUE.search(answer))
    refers_staff = "상담원" in answer
    rules = {
        "interest_amount": lambda: "{{interest_due}}" in answer,
        "due_date": lambda: has_date,
        "overdue_status": lambda: states_overdue if overdue else states_no_overdue,
        "false_premise": lambda: states_overdue if overdue else states_no_overdue,
        "overdue_action": lambda: ("연체" in answer and "{{overdue_amount}}" in answer) if overdue else "연체" in answer,
        "reason": lambda: "연체" in answer if overdue else refers_staff,
        "loan_terms_repay": lambda: item["repayment_method"] in answer,
        "loan_terms_interest_type": lambda: item["interest_type"] in answer,
        "loan_terms_payment": lambda: item["payment_method"] in answer,
    }
    return bool(rules.get(expect, lambda: refers_staff)())


def build_golden_cases(mock: dict) -> list[dict]:
    cases = []
    for i, (customer, question, expect) in enumerate(GOLDEN):
        item = enrich(mock[customer][0], customer)  # 서비스(agent.py)와 같은 입력
        cases.append(
            {
                "set": "golden",
                "id": f"golden-{i:02d}",
                "customer": customer,
                "question": question,
                "expect": expect,
                "item": item,
                "messages": build_messages(question, [], item),
            }
        )
    return cases


def load_split_cases(data_dir: Path, split: str) -> list[dict]:
    cases = []
    for line in (Path(data_dir) / f"{split}.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        cases.append(
            {
                "set": split,
                "id": r["id"],
                "question": r["messages"][-2]["content"].split("\n")[0],
                "expect": None,
                "item": r["item"],
                "messages": r["messages"][:-1],
                "reference": r["messages"][-1]["content"],
            }
        )
    return cases


def load_question_cases(data_dir: Path) -> list[dict]:
    """prepare.py의 test_questions.jsonl: AI Hub test 분할 질문 전체(답 필터 없음, 참고 답 없음)."""
    cases = []
    for line in (Path(data_dir) / "test_questions.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            cases.append({"set": "test_q", "id": r["id"], "question": r["messages"][-1]["content"].split("\n")[0],
                          "expect": None, "item": r["item"], "messages": r["messages"]})
    return cases


def score(case: dict, answer: str) -> dict:
    item = case["item"]
    valid = is_valid(
        answer,
        allowed_slots=set(build_slots(item)),
        required_slots=required_slots(case["question"], item["overdue_days"] > 0),
    )
    forbidden = [name for name, pattern in FORBIDDEN if pattern.search(answer)]
    forbidden += [p for p in phrase_problems(answer) if p not in ("서류", "개인정보 요구")]  # 위 목록과 겹치는 이름은 한 번만
    expect = check_expect(case["expect"], item, answer) if case.get("expect") else None
    tone = tone_ok(answer)
    return {
        "valid": valid,
        "slot": "{{" in answer,
        "forbidden": forbidden,
        "length": len(answer),
        "tone": tone,
        "expect": expect,
        "rule": (valid and not forbidden and expect and tone) if expect is not None else None,
    }


def summarize(rows: list[dict]) -> dict:
    def rate(subset, key):
        vals = [r["score"].get(key) for r in subset if r["score"].get(key) is not None]
        return sum(bool(v) for v in vals) / len(vals) if vals else None

    def agg(subset):
        n = len(subset)
        return {
            "n": n,
            "valid": sum(r["score"]["valid"] for r in subset) / n,
            "slot": sum(r["score"]["slot"] for r in subset) / n,
            "forbidden": sum(bool(r["score"]["forbidden"]) for r in subset) / n,
            "avg_length": sum(r["score"]["length"] for r in subset) / n,
            "tone": rate(subset, "tone"),
            "expect": rate(subset, "expect"),
            "rule": rate(subset, "rule"),
        }

    out = {s: agg([r for r in rows if r["set"] == s]) for s in dict.fromkeys(r["set"] for r in rows)}
    out["all"] = agg(rows)
    return out


def make_blind_sheet(rows_a: list[dict], rows_b: list[dict], name_a: str, name_b: str, seed: int = 0):
    """사람 블라인드 평가 시트와 정답 키. 모델 이름을 숨기고 A/B 순서를 섞는다(EVALUATION.md 질문 4)."""
    rng = random.Random(seed)
    b_by_id = {r["id"]: r for r in rows_b}
    sheet, key = [], {}
    for no, a in enumerate((r for r in rows_a if r["set"] in ("golden", "demo")), 1):
        b = b_by_id[a["id"]]
        first, second = ((name_a, a), (name_b, b)) if rng.random() < 0.5 else ((name_b, b), (name_a, a))
        sheet.append(
            {
                "no": no,
                "customer": a.get("customer", ""),
                "question": a["question"],
                "answer_1": first[1]["answer"],
                "answer_2": second[1]["answer"],
                "prefer(1/2/tie)": "",
                "주제적합(O/X)": "",
                "지어내지않음(O/X)": "",
                "존댓말톤(O/X)": "",
                "note": "",
            }
        )
        key[no] = {"1": first[0], "2": second[0]}
    return sheet, key


def save_results(rows: list[dict], summary: dict, name: str, eval_dir: Path, adapter: Path | None, overwrite: bool = False) -> None:
    """평가 결과를 eval_dir에 저장하고, 어댑터로 평가했으면 그 버전 폴더(<run>/eval/)에도 사본을 남긴다.
    같은 이름 결과는 덮어쓰지 않는다(overwrite=True일 때만)."""
    targets = [Path(eval_dir)] + ([Path(adapter).parent / "eval"] if adapter is not None else [])
    if not overwrite:
        for d in targets:
            if (d / f"{name}.jsonl").exists():
                raise FileExistsError(f"{d / name}.jsonl이 이미 있다. 다른 --name을 쓰거나 --overwrite를 준다.")
    for d in targets:
        d.mkdir(parents=True, exist_ok=True)
        with (d / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        (d / f"{name}.summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def generate_answers(cases: list[dict], base_model: str, adapter: Path | None, max_new_tokens: int = 256) -> list[dict]:
    import torch
    from transformers import AutoModelForCausalLM

    tokenizer = load_tokenizer(base_model)  # 학습과 같은 공식 채팅 템플릿
    model = AutoModelForCausalLM.from_pretrained(base_model, dtype=torch.bfloat16, device_map={"": 0})
    if adapter is not None:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, str(adapter))
    model.eval()

    rows = []
    for i, case in enumerate(cases, 1):
        enc = tokenizer.apply_chat_template(
            case["messages"], add_generation_prompt=True, return_dict=True, return_tensors="pt"
        ).to(model.device)
        t0 = time.time()
        with torch.no_grad():
            out = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False)
        answer = tokenizer.decode(out[0, enc["input_ids"].shape[1] :], skip_special_tokens=True).strip()
        row = {k: v for k, v in case.items() if k != "messages"}
        row |= {"answer": answer, "seconds": round(time.time() - t0, 2), "score": score(case, answer)}
        rows.append(row)
        print(f"[{i}/{len(cases)}] {case['id']} valid={row['score']['valid']} rule={row['score']['rule']} {row['seconds']}s")
    return rows


def _pct(v) -> str:
    return "-" if v is None else f"{v:.0%}"


def compare(names: list[str]) -> None:
    summaries = {n: json.loads((EVAL_DIR / f"{n}.summary.json").read_text(encoding="utf-8")) for n in names}
    print("| 모델 | 셋 | n | 규칙 준수 | 기대 조건 | 검증 통과 | 슬롯 사용 | 금지 표현 | 상담 톤 | 평균 길이 |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for n, s in summaries.items():
        for split, m in s.items():
            print(
                f"| {n} | {split} | {m['n']} | {_pct(m.get('rule'))} | {_pct(m.get('expect'))} | {_pct(m['valid'])} "
                f"| {_pct(m['slot'])} | {_pct(m['forbidden'])} | {_pct(m.get('tone'))} | {m['avg_length']:.0f} |"
            )

    # 문항 수가 다른 결과끼리도 어긋나지 않게 id로 맞춘다.
    answers = {
        n: {r["id"]: r for r in map(json.loads, (EVAL_DIR / f"{n}.jsonl").read_text(encoding="utf-8").splitlines())}
        for n in names
    }
    for rid, row in answers[names[0]].items():
        if row["set"] not in ("golden", "demo") or not all(rid in answers[n] for n in names):
            continue
        print(f"\n### {row.get('customer', '')} {row['question']} ({row.get('expect', '')})")
        for n in names:
            r = answers[n][rid]
            ok = r["score"].get("rule")
            flag = "✅" if ok else "❌" if ok is False else ("✅" if r["score"]["valid"] and not r["score"]["forbidden"] else "❌")
            print(f"- {n} {flag} {r['answer']}")


def write_blind(name_a: str, name_b: str) -> Path:
    load = lambda n: [json.loads(l) for l in (EVAL_DIR / f"{n}.jsonl").read_text(encoding="utf-8").splitlines()]  # noqa: E731
    sheet, key = make_blind_sheet(load(name_a), load(name_b), name_a, name_b)
    path = EVAL_DIR / f"blind_{name_a}_vs_{name_b}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as f:  # 엑셀에서 한글이 깨지지 않게 BOM
        writer = csv.DictWriter(f, fieldnames=list(sheet[0]))
        writer.writeheader()
        writer.writerows(sheet)
    (EVAL_DIR / f"blind_{name_a}_vs_{name_b}.key.json").write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"시트: {path}\n키(채점 끝난 뒤 열기): {path.with_suffix('.key.json')}")
    return path


def eval_wandb_metrics(summary: dict) -> dict:
    """wandb용 숫자 요약: '<분할>/<지표>' → 값. 질문·답 원문은 넣지 않는다."""
    return {f"{split}/{key}": value for split, metrics in summary.items() if split != "all"
            for key, value in metrics.items() if isinstance(value, (int, float)) and not isinstance(value, bool)}


def log_eval_to_wandb(summary: dict, name: str, adapter: Path | None) -> str:
    import wandb  # 개인 개발 환경에만 설치

    run = wandb.init(project="cs-interest", name=f"eval-{name}", group="eval", job_type="eval",
                     dir=str(OUTPUT_DIR),  # 로컬 실행 기록을 gitignore 폴더(outputs/wandb/)에 남긴다
                     config={"model": adapter.parent.name if adapter else "base"})
    metrics = eval_wandb_metrics(summary)
    run.summary.update(metrics)
    run.log(metrics)
    url = run.url
    run.finish()
    return url


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="cs-interest 답변 평가")
    p.add_argument("--name", help="결과 이름(예: base, tuned)")
    p.add_argument("--base-model", default=DEFAULT_BASE_MODEL)
    p.add_argument("--adapter", type=Path, help="LoRA 어댑터 경로(없으면 베이스 모델)")
    p.add_argument("--data-dir", type=Path, default=DATA_DIR)
    p.add_argument("--compare", nargs="+", metavar="NAME", help="저장된 결과 비교")
    p.add_argument("--blind", nargs=2, metavar=("A", "B"), help="사람 블라인드 평가 시트 생성")
    p.add_argument("--overwrite", action="store_true", help="같은 이름 결과를 덮어쓴다")
    p.add_argument("--test-questions", action="store_true",
                   help="test.jsonl 대신 test_questions.jsonl(test 분할 질문 전체)로 회귀 평가")
    p.add_argument("--wandb", action="store_true", help="분할별 숫자 요약을 wandb(cs-interest)에 올린다(개인 개발용)")
    args = p.parse_args(argv)

    if args.compare:
        compare(args.compare)
        return
    if args.blind:
        write_blind(*args.blind)
        return

    mock = json.loads(MOCK_FILE.read_text(encoding="utf-8"))
    test_cases = load_question_cases(args.data_dir) if args.test_questions else load_split_cases(args.data_dir, "test")
    cases = build_golden_cases(mock) + test_cases
    for target in [EVAL_DIR] + ([args.adapter.parent / "eval"] if args.adapter else []):
        if (target / f"{args.name}.jsonl").exists() and not args.overwrite:  # 생성 전에 먼저 막는다
            raise FileExistsError(f"{target / args.name}.jsonl이 이미 있다. 다른 --name이나 --overwrite를 쓴다.")
    rows = generate_answers(cases, args.base_model, args.adapter)
    summary = summarize(rows)
    save_results(rows, summary, args.name, EVAL_DIR, args.adapter, overwrite=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.wandb:
        print("wandb:", log_eval_to_wandb(summary, args.name, args.adapter))


if __name__ == "__main__":
    main()
