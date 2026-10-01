"""cs-loan 모델 평가 (팀 공용틀 EVALUATION_공용틀.md, docs/agent-loan/EVALUATION.md).

Ollama에 등록한 모델(Base·v3·v4)을 같은 문항·같은 생성 설정(temperature=0)으로 돌려 자동 채점한다.
- compare(30): K01~K20(golden_set_v4_compare.jsonl) + 사용자 새 10문항 M01~M10(golden_set_v4_new.jsonl). 규칙 준수율 80% 판정, 버전 선택.
  기존 golden_set 비교용 30문항은 개발 중 노출돼 점수가 부풀어 compare_old로 내려 **참고만** 한다(판정 제외)
- regress(20): golden_set.jsonl 회귀. Base 대비 정답률 하락 5%p 이내(1문항까지). 그중 대출 없는 고객 2문항은 서비스가 고정 문장으로 답하고
  모델을 부르지 않으므로(bypass) 모든 모델이 같게 통과한다. 20문항(1문항=5%p)을 지키려고 남겨 둔다
- final(10): golden_set_final_v4.jsonl 최종 확인용. 사람 블라인드 10문항이 이 세트 전체
- k20(20), new10(10): compare를 나눠 보는 선택 세트(기본 실행에서 제외, 결과는 compare:K, compare:M으로도 집계된다)
지표: valid(검증기), slot, forbidden(지어냄·처리 약속 등), length, tone(존댓말), expect(기대 조건), rule(위 전부 충족).

실행(cd backend, 모델은 `ollama create`로 등록돼 있어야 한다):
  .venv/bin/python -m training.loan.evaluate --name base            # cs-loan-base
  .venv/bin/python -m training.loan.evaluate --name v3              # cs-loan-v3
  .venv/bin/python -m training.loan.evaluate --name v4 --model cs-loan-v4
  .venv/bin/python -m training.loan.evaluate --compare base v3 v4   # 첫 이름이 Base(기준). --flags <판정.json>으로 수동 판정 반영
  .venv/bin/python -m training.loan.evaluate --review-sheet base v3 v4   # 수동 판정용 익명 시트 + 키(docs MANUAL_REVIEW_CRITERIA.md)
  .venv/bin/python -m training.loan.evaluate --blind base v4        # 사람 블라인드 시트(final 10문항) + 키 파일
  .venv/bin/python -m training.loan.evaluate --judge base v4 [--judge-dry-run] [--judge-limit 2] [--yes]   # GPT Judge(OpenAI API, 확인 필요)
  .venv/bin/python -m training.loan.evaluate --agree base v4        # 사람 시트와 Judge 일치 수
출력: training/loan/outputs/eval/ (gitignore). 같은 이름은 덮어쓰지 않는다(--overwrite로만).
Judge는 --judge를 줄 때만 API를 부르고, 호출 횟수를 보여 준 뒤 확인을 받는다(--yes로 생략). 자동 채점은 API 없이 돈다.
"""
import argparse
import collections
import csv
import json
import os
import random
import re
import time
from pathlib import Path

from app import llm
from app.agents.loan import prompt, validate
from app.agents.loan.mock_api import get_loans

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]
EVAL_DIR = HERE / "outputs" / "eval"
ENV_FILE = BACKEND / ".env"

# Base와 모든 튜닝 버전에 같은 값을 쓴다(공용틀 7절). 나머지 옵션(top_p, repeat_penalty)은 Modelfile 값이고 세 모델이 같다.
GENERATION_OPTIONS = {"temperature": 0, "num_predict": 256}
# 서비스 설정(공용틀 7절: 최종 후보는 서비스 설정으로 한 번 더): temperature는 Modelfile 값(0.3)에 맡기고 나머지는 위와 같다
SERVICE_OPTIONS = {"num_predict": GENERATION_OPTIONS["num_predict"]}

# 세트 이름 → (파일, 행 선택). 문항은 사용자·작성자가 쓴 것이고 이 도구는 고치지 않는다.
SETS = {
    "compare": [("golden_set_v4_compare.jsonl", lambda r: True), ("golden_set_v4_new.jsonl", lambda r: True)],
    "compare_old": [("golden_set.jsonl", lambda r: r.get("set") == "compare")],
    "regress": [("golden_set.jsonl", lambda r: r.get("set") == "regress")],
    "final": [("golden_set_final_v4.jsonl", lambda r: True)],
    "k20": [("golden_set_v4_compare.jsonl", lambda r: True)],
    "new10": [("golden_set_v4_new.jsonl", lambda r: True)],
}
DEFAULT_SETS = ("compare", "compare_old", "regress", "final")
JUDGE_SETS = ("compare", "final")     # 공용틀 6-1: Golden Set(비교용 30 + 최종 확인용 10) 전체

RULE_PASS = 0.80          # 규칙 준수율 통과선(compare)
REGRESS_MAX_DROP_PP = 5.0  # Base 대비 회귀 정답률 허용 하락(%p)
AGREE_MIN = 8             # 사람 10문항과 Judge 일치 기준

# --- 채점 코드 (EVAL_CRITERIA_v3.md 정의 + v4 사후 조정에서 확인한 오탐 제거를 처음부터 반영) -----------------------------------
_DIR = re.compile(r"올라|오릅|오르|상승|높아|내려|내립|낮아|하락|인하됩|동일|그대로|변동 없|맞습니다|맞아요|(?<!범위가 )아닙니다|아니에요|틀립니다|사실입니다")
_CAUSE = re.compile(r"때문입니다|때문이에요|때문에 연장|때문에 불가|원인은|(사유|이유)는[^.]*입니다")
_CAUSE_OK = re.compile(r"조회되지|알 수 없|확인")
_COMMIT = re.compile(r"(접수|신청|처리)[^.]*(해 드리|해드리|했습니다|완료|진행)")
_REFUSED = re.compile(r"어렵|어려워|없|불가")   # "어려워"(연결형)도 거절 표현: 사후 조정, 2026-09-30
_AFFIRM = re.compile(r"^네(?:[,. ]|$)|맞습니다|맞아요|사실입니다|그렇습니다")
_ECHO = re.compile(r"\[[^\]]+_\d+\]")
_SENT = re.compile(r"[.!?\n]+")
_FEE_WORDS = ("수수료", "비용", "위약금", "페널티", "불이익", "금액")
FORBIDDEN_CODES = ("no_direction", "no_cause_claim", "no_commit", "no_echo_token")
_EXPECT_TO_CODE = {"date": "date", "slot_principal": "slot_principal", "slot_extend": "slot_extend", "refer": "refer"}  # off_topic·no_loan은 추가 조건 없음


def _sents(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(text) if s.strip()]


def _date_ok(text: str, iso: str) -> bool:
    y, m, d = iso.split("-")
    others = [x for x in re.findall(r"\d{4}-\d{2}-\d{2}", text) if x != iso]
    return (iso in text or f"{y}년 {int(m)}월 {int(d)}일" in text) and not others


def _commit_hit(text: str) -> bool:
    sentences = _sents(text)
    if validate._PROMISE.search(text):   # 처리하겠다는 약속. 거절 문장("…해 드리기 어렵습니다")은 약속이 아니다
        return any(not _REFUSED.search(s) and validate._PROMISE.search(s) for s in sentences)
    return any(_COMMIT.search(s) and not _REFUSED.search(s) for s in sentences)


def codes(text: str, loan: dict) -> dict[str, bool]:
    ss = _sents(text)
    valid = validate.is_valid_output(text, maturity_date=loan["maturity_date"], extendable=loan["extendable"])
    c = {
        "polite": all(s.endswith("}}") or re.search(r"(니다|세요|요|죠|까요|시오)$", s) for s in ss),
        "slot_extend": "{{extendable_status}}" in text,
        "slot_principal": "{{principal_remaining}}" in text,
        "slot_loan_label": "{{loan_label}}" in text,
        "date": _date_ok(text, loan["maturity_date"]),
        "refer": "상담원" in text,
        "topic_fee": "수수료" in text and "금리" not in text,
        "topic_rate": "금리" in text and "수수료" not in text,
        "topic_fee_word": any(w in text for w in _FEE_WORDS) and "금리" not in text,
        "no_affirm": not any(_AFFIRM.search(x) for x in ss),   # 틀린 날짜를 맞다고 확인하지 않음(M08). "아니요"는 허용
        "explicit_no": any(x.startswith("아니요") for x in ss),
        "no_echo_token": not _ECHO.search(text),
        "no_direction": not _DIR.search(text) and not any(s.startswith(("네,", "네 ", "아니요")) for s in ss),
        "no_cause_claim": not any(_CAUSE.search(s) and not _CAUSE_OK.search(s) for s in ss),
        "no_commit": not _commit_hit(text),
    }
    c["no_fabrication"] = valid and all(c[k] for k in FORBIDDEN_CODES)
    return c


def required_codes(case: dict) -> list[str]:
    """이 문항이 '성공'이려면 충족해야 하는 코드. must가 있으면 그대로, 없으면 expect + 존댓말 + 지어내지 않음(+수수료 주제)."""
    if case.get("must") is not None:
        return list(case["must"])
    req = [_EXPECT_TO_CODE[e] for e in case.get("expect", []) if e in _EXPECT_TO_CODE] + ["polite", "no_fabrication"]
    if case.get("category") == "수수료":
        req.append("topic_fee_word")
    return req


def score(case: dict, answer: str) -> dict:
    loan = case["loan"]
    valid = validate.is_valid_output(answer, maturity_date=loan["maturity_date"], extendable=loan["extendable"])
    c = codes(answer, loan)
    required = required_codes(case)
    # no_affirm을 요구하는 문항(M08)에서는 틀린 날짜를 정정하는 "아니요"가 정답이므로 no_direction을 위반으로 세지 않는다
    forbidden = [k for k in FORBIDDEN_CODES if not c[k] and not (k == "no_direction" and "no_affirm" in required)]
    checks = [k for k in required if k not in ("polite", "no_fabrication")]
    fail = ([] if valid else ["validator"]) + [k for k in required if not c[k]]
    return {
        "valid": valid,
        "slot": "{{" in answer,
        "forbidden": forbidden,
        "length": len(answer),
        "tone": c["polite"],
        "expect": all(c[k] for k in checks),
        "rule": valid and all(c[k] for k in required),
        "fail": fail,
        "record": {k: c[k] for k in case.get("record", [])},
    }


# --- 문항 ------------------------------------------------------------------------------------------


def _read(name: str) -> list[dict]:
    return [json.loads(l) for l in (HERE / name).read_text(encoding="utf-8").splitlines() if l.strip()]


def load_cases(sets: list[str] | tuple[str, ...]) -> list[dict]:
    cases = []
    for name in sets:
        for r in (r for filename, pick in SETS[name] for r in filter(pick, _read(filename))):
            loans = get_loans(r["customer"])
            loan = r.get("loan") or (loans[0] if loans else None)   # 대출 없는 고객은 서비스가 고정 문장을 돌려주고 모델을 부르지 않는다
            cases.append({
                "set": name, "id": r["id"], "customer": r["customer"], "category": r.get("category") or r.get("type"),
                "question": r["question"], "history": r.get("history", []), "expect": r.get("expect", []),
                "must": r.get("must"), "record": r.get("record", []), "loan": loan, "bypass": loan is None,
                "messages": None if loan is None else prompt.build_messages(r.get("history", []), r["question"], loan),   # 서비스(agent.py)와 같은 입력
            })
    return cases


# --- 생성 ------------------------------------------------------------------------------------------


def _print_progress(i, n, row):
    print(f"[{i}/{n}] {row['set']}/{row['id']} {row['seconds']}s")   # 채점 결과는 보여 주지 않는다(요약을 미리 보지 않기)


def generate_answers(cases: list[dict], model: str, generate=None, progress=_print_progress, options=None, reps: int = 1) -> list[dict]:
    generate = generate or llm.generate   # 모델 호출은 llm.generate 한 곳만(입력 로그)
    options = GENERATION_OPTIONS if options is None else options
    rows = []
    plan = [(rep_no, c) for rep_no in range(1, reps + 1) for c in cases]
    for i, (rep_no, case) in enumerate(plan, 1):
        t0 = time.time()
        if case["bypass"]:   # 서비스(agent.py)가 모델 없이 돌려주는 고정 문장
            row = {k: case[k] for k in ("set", "id", "customer", "category", "question")}
            fixed = {"valid": True, "slot": False, "forbidden": [], "length": len(prompt.NO_LOAN_TEXT), "tone": True,
                     "expect": True, "rule": True, "fail": [], "record": {}}
            row |= {"model": model, "answer": prompt.NO_LOAN_TEXT, "served": prompt.NO_LOAN_TEXT, "seconds": 0.0, "bypass": True,
                    "score": fixed, "score_final": dict(fixed)}
            rows.append(row | ({"rep": rep_no} if reps > 1 else {}))
            progress(i, len(plan), row)
            continue
        for attempt in range(3):
            try:
                answer = generate(model, case["messages"], **options)
                break
            except Exception as e:   # Ollama 적재 지연 등
                if attempt == 2:
                    raise
                print(f"재시도 {attempt + 1}: {case['id']} {e}")
                time.sleep(3)
        loan = case["loan"]
        valid = validate.is_valid_output(answer, maturity_date=loan["maturity_date"], extendable=loan["extendable"])
        row = {k: case[k] for k in ("set", "id", "customer", "category", "question")}
        served = answer if valid else prompt.fallback_text(loan)
        row |= {"model": model, "answer": answer, "served": served, "seconds": round(time.time() - t0, 2),
                "score": score(case, answer), "score_final": score(case, served)}   # score = 모델 원문(raw), score_final = 서비스가 보여 주는 답(final)
        rows.append(row | ({"rep": rep_no} if reps > 1 else {}))
        progress(i, len(plan), row)
    return rows


# --- 집계·저장·비교 ---------------------------------------------------------------------------------


def summarize(rows: list[dict], reviewed: bool | None = None) -> dict:
    reviewed = any("manual" in r for r in rows) if reviewed is None else reviewed

    def agg(subset):
        n = len(subset)
        rate = lambda f: sum(bool(f(r["score"])) for r in subset) / n  # noqa: E731
        real = [r for r in subset if not r.get("bypass")]   # 서비스가 모델 없이 답한 문항(대출 없는 고객)은 모델 호출 문항에서 뺀다
        out = {"n": n, "rule": rate(lambda s: s["rule"]), "expect": rate(lambda s: s["expect"]), "valid": rate(lambda s: s["valid"]),
               "slot": rate(lambda s: s["slot"]), "forbidden": rate(lambda s: s["forbidden"]), "tone": rate(lambda s: s["tone"]),
               "avg_length": sum(r["score"]["length"] for r in subset) / n,
               "rule_final": sum(bool(r.get("score_final", r["score"])["rule"]) for r in subset) / n,
               "n_model": len(real), "rule_model": sum(bool(r["score"]["rule"]) for r in real) / len(real) if real else None}
        if reviewed:
            out["rule_reviewed"] = sum(bool(r["score"]["rule"]) and r.get("manual") != "fabricated" for r in subset) / n
            out["rule_reviewed_strict"] = sum(bool(r["score"]["rule"]) and r.get("manual") not in ("fabricated", "borderline") for r in subset) / n
            out["rule_literal"] = sum(bool(r["score"]["rule"]) and r.get("manual") not in ("fabricated", "borderline")
                                      and not r.get("manual_literal") for r in subset) / n   # 글자 기준: 기준 단어가 글자로 있으면 실패
            out["n_borderline"] = sum(r.get("manual") == "borderline" for r in subset)
        return out

    out = {s: agg([r for r in rows if r["set"] == s]) for s in dict.fromkeys(r["set"] for r in rows)}
    for part in ("K", "M"):   # compare 안의 K20 / 사용자 새 10문항을 나눠 본다
        sub = [r for r in rows if r["set"] == "compare" and r["id"].startswith(part)]
        if sub:
            out[f"compare:{part}"] = agg(sub)
    out["all"] = agg(rows)
    return out


def type_groups(items: list[dict]) -> dict[str, list[str]]:
    """문항을 유형별로 묶는다(같은 유형은 결과 표에서 나란히: 수수료 = K10 + M05)."""
    groups: dict[str, list[str]] = {}
    for c in items:
        ids = groups.setdefault(c["category"], [])
        if c["id"] not in ids:
            ids.append(c["id"])
    return groups


def save_results(rows: list[dict], summary: dict, name: str, eval_dir: Path, overwrite: bool = False) -> None:
    eval_dir = Path(eval_dir)
    if (eval_dir / f"{name}.jsonl").exists() and not overwrite:
        raise FileExistsError(f"{eval_dir / name}.jsonl이 이미 있다. 다른 --name이나 --overwrite를 쓴다.")
    eval_dir.mkdir(parents=True, exist_ok=True)
    with (eval_dir / f"{name}.jsonl").open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    (eval_dir / f"{name}.summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def verdicts(base: dict, other: dict) -> dict:
    """팀 통과선 적용: compare 규칙 준수율 80% 이상, regress 정답률이 Base보다 5%p 넘게 떨어지지 않음."""
    drop = (base["regress"]["rule"] - other["regress"]["rule"]) * 100
    return {"rule": other["compare"]["rule"], "rule_pass": other["compare"]["rule"] >= RULE_PASS - 1e-9,
            "regress_drop_pp": drop, "regress_pass": drop <= REGRESS_MAX_DROP_PP + 1e-9}


def _pct(v) -> str:
    return "-" if v is None else f"{v:.0%}"


def _load_rows(name: str) -> list[dict]:
    """저장된 결과를 읽고 **현재 채점 규칙으로 다시 채점**한다(원문 답변이 기준이고 점수는 파생값이라 규칙을 고치면 재생성 없이 반영된다)."""
    rows = [json.loads(l) for l in (EVAL_DIR / f"{name}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    cases = {(c["set"], c["id"]): c for c in load_cases(list(SETS)) if not c["bypass"]}
    for r in rows:
        case = cases.get((r["set"], r["id"]))
        if case and not r.get("bypass"):
            r["score"], r["score_final"] = score(case, r["answer"]), score(case, r["served"])
    return rows


def compare(names: list[str], flags_path: Path | None = None, review_tag: str = "") -> None:
    """저장된 결과 비교. rule = 모델 원문(raw), final = 검증기 적용 후 서비스 표시문, 모델 = 모델 호출 문항만(회귀 20 중 18)."""
    rows_by = {n: _load_rows(n) for n in names}
    reviewed_names: set[str] = set()
    if flags_path:
        flags = load_flags(flags_path, EVAL_DIR / f"review_key{'_' + review_tag if review_tag else ''}.json")
        reviewed_names = {k[0] for k in flags}
        for n, rows in rows_by.items():
            apply_manual_flags(rows, flags, name=n)
    reviewed = bool(flags_path)
    summaries = {n: summarize(rows, reviewed) for n, rows in rows_by.items()}
    head = "| 모델 | 셋 | n | 규칙 준수(raw) | 규칙 준수(final) | 모델 호출 문항 | 기대 조건 | 검증 통과 | 금지 표현 | 상담 톤 |"
    print(head + (" 수동 판정 | 글자 기준 | 경계선(미결정) |" if reviewed else ""))
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|" + ("---:|---:|---:|" if reviewed else ""))
    for n, sm in summaries.items():
        for split, m in sm.items():
            model_part = f"{m['n_model']}문항 {_pct(m['rule_model'])}" if m["n_model"] != m["n"] else "-"
            line = (f"| {n} | {split} | {m['n']} | {_pct(m['rule'])} | {_pct(m['rule_final'])} | {model_part} | {_pct(m['expect'])} "
                    f"| {_pct(m['valid'])} | {_pct(m['forbidden'])} | {_pct(m['tone'])} |")
            if reviewed:   # 판정 파일에 없는 모델(수동 판정을 하지 않은 버전)은 '-'
                line += (f" {_pct(m['rule_reviewed'])} | {_pct(m['rule_literal'])} | {m['n_borderline']} |" if n in reviewed_names
                         else " - | - | - |")
            print(line)
    base = summaries[names[0]]
    if "compare" in base and "regress" in base:
        print(f"\n판정 (기준 = {names[0]}): 규칙 준수율(compare) {RULE_PASS:.0%} 이상, 회귀(regress) 하락 {REGRESS_MAX_DROP_PP:g}%p 이내")
        for n in names[1:]:
            if "compare" in summaries[n] and "regress" in summaries[n]:
                v = verdicts(base, summaries[n])
                print(f"- {n}: 규칙 준수 {_pct(v['rule'])} {'통과' if v['rule_pass'] else '미달'} | "
                      f"회귀 하락 {v['regress_drop_pp']:+.1f}%p {'통과' if v['regress_pass'] else '미달'}")
    answers: dict = {n: {} for n in rows_by}   # 모델 -> (세트, 문항) -> 회차별 행 목록
    for n, rows in rows_by.items():
        for r in rows:
            answers[n].setdefault((r["set"], r["id"]), []).append(r)
    cmp_rows = [r for r in rows_by[names[0]] if r["set"] == "compare"]
    if cmp_rows:   # 유형별 통과 수(같은 유형은 묶어서: 수수료 = K10 + M05). 반복 실행이면 샘플 수 기준
        groups = type_groups(cmp_rows)
        print("\n### compare 유형별 통과(rule, raw, 통과 샘플/전체 샘플)")
        print("| 유형 | 문항 | " + " | ".join(names) + " |")
        print("|---|---|" + "---:|" * len(names))
        for typ, ids in groups.items():
            cells = []
            for n in names:
                samples = [r for i in ids for r in answers[n][("compare", i)]]
                cells.append(f"{sum(r['score']['rule'] for r in samples)}/{len(samples)}")
            print(f"| {typ} | {'+'.join(ids)} | " + " | ".join(cells) + " |")
        order = [("compare", i) for ids in groups.values() for i in ids] + [k for k in answers[names[0]] if k[0] == "final"]
    else:
        order = [k for k in answers[names[0]] if k[0] == "final"]
    for key in order:
        if not all(key in answers[n] for n in names):
            continue
        row = answers[names[0]][key][0]
        print(f"\n### {row['set']}/{row['id']} [{row['category']}] {row['question']}")
        for n in names:
            group = answers[n][key]
            if len(group) == 1:
                r = group[0]
                note = "" if r["score"]["rule"] else f" (실패: {', '.join(r['score']['fail']) or '-'})"
                if r.get("manual") in ("fabricated", "borderline") or r.get("manual_literal"):
                    note += f" [수동: {r['manual']}{', 글자 기준 hit' if r.get('manual_literal') else ''}]"
                print(f"- {n} {'✅' if r['score']['rule'] else '❌'}{note} raw: {r['answer']}" + ("" if r['served'] == r['answer'] else f" → final: {r['served']}"))
                continue
            print(f"- {n} 통과 {sum(r['score']['rule'] for r in group)}/{len(group)}")
            for answer, same in collections.Counter(r["answer"] for r in group).most_common():
                r = next(x for x in group if x["answer"] == answer)
                note = "" if r["score"]["rule"] else f" (실패: {', '.join(r['score']['fail']) or '-'})"
                print(f"  - ×{same} {'✅' if r['score']['rule'] else '❌'}{note} {answer}")


# --- 수동 판정(자동 코드의 빈틈, docs/agent-loan/MANUAL_REVIEW_CRITERIA.md) -----------------------------

REVIEW_IDS = ("M03", "M05", "M06", "M07", "K10")   # K10은 M05와 같은 유형이라 M05 기준을 적용한다


def make_review_sheet(rows_by_model: dict, ids, sets=("compare",), seed: int = 0):
    """모델 이름 없이 섞은 고유 답변 시트와 키. 검증기가 이미 막은 응답은 자동 실패라 제외하고, 같은 답은 하나로 합친다."""
    rng = random.Random(seed)
    sheet, key = [], {}
    for id_ in ids:
        for set_ in sets:
            groups: dict[str, dict] = {}
            for model, rows in rows_by_model.items():
                for r in rows:
                    if r["id"] == id_ and r["set"] == set_ and not r.get("bypass") and r["score"]["valid"]:
                        g = groups.setdefault(r["answer"], {"question": r["question"], "who": []})
                        g["who"].append([model, set_, id_] + ([r["rep"]] if "rep" in r else []))
            items = list(groups.items())
            rng.shuffle(items)
            for answer, g in items:
                no = len(sheet) + 1
                sheet.append({"no": no, "id": id_, "question": g["question"], "answer": answer, "n": len(g["who"]),
                              "verdict(fabricated/ok/borderline)": "", "note": ""})
                key[no] = {"who": g["who"]}
    return sheet, key


def write_review(names: list[str], ids=REVIEW_IDS, sets=("compare",), seed: int = 0, tag: str = "") -> Path:
    sheet, key = make_review_sheet({n: _load_rows(n) for n in names}, ids, sets, seed)
    suffix = f"_{tag}" if tag else ""
    path, key_path = EVAL_DIR / f"review_sheet{suffix}.json", EVAL_DIR / f"review_key{suffix}.json"
    if path.exists() or key_path.exists():
        raise FileExistsError(f"{path}가 이미 있다(판정이 끝난 시트를 덮어쓰지 않는다). 지우고 다시 만들려면 직접 지운다.")
    path.write_text(json.dumps(sheet, ensure_ascii=False, indent=2), encoding="utf-8")
    key_path.write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"판정 시트: {path} ({len(sheet)}개 고유 답변)\n키(판정이 끝난 뒤에 열기): {key_path}")
    return path


def load_flags(flags_path: Path, key_path: Path) -> dict:
    """판정 파일 {"1": {"verdict": "fabricated|ok|borderline", "literal": "hit"(선택), "note": ...}} + 키
    → {(모델, 세트, 문항[, 회차]): (판정, 글자 기준으로 hit)}. literal은 경계선을 통과로 결정했더라도 기준 단어가 글자로 있었음을 표시한다."""
    key = json.loads(Path(key_path).read_text(encoding="utf-8"))
    flags = {}
    for no, item in json.loads(Path(flags_path).read_text(encoding="utf-8")).items():
        if item["verdict"] not in ("fabricated", "ok", "borderline"):
            raise ValueError(f"판정값 오류: {no} {item['verdict']}")
        for who in key[str(no)]["who"]:
            flags[tuple(who)] = (item["verdict"], item.get("literal") == "hit")
    return flags


def apply_manual_flags(rows: list[dict], flags: dict, name: str | None = None) -> None:
    """name = 결과 이름(v3). 행의 model은 Ollama 모델명(cs-loan-v3)이라 판정 키(결과 이름)와 다르므로 이름을 넘긴다."""
    for r in rows:
        who = (name or r.get("model"), r["set"], r["id"])
        v = flags.get(who + (r["rep"],)) if "rep" in r else None
        v = v or flags.get(who)
        if v:
            verdict, literal = v if isinstance(v, tuple) else (v, False)
            r["manual"], r["manual_literal"] = verdict, literal


# --- 결함 비교(지어낸 사실, 검증기 차단, 일본어·한자 혼입, 뒤집힌 거절 문형, 과다 거절) --------------------------------------

_FLIP_LOOSE = re.compile(r"수 있|수 없|처리해 드")   # v4 자체 평가(eval_v4_score.py)와 같은 정의
_FLIP_STRICT = re.compile(r"수 있|처리해 드")


def has_cjk_mix(text: str) -> bool:
    return bool(validate._NON_KOREAN_CJK.search(text))


def flipped_refusal(text: str, strict: bool = False) -> bool:
    """상담원 안내 답변에 "~ㄹ 수 있/처리해 드"가 들어 있음(거절이 처리 약속으로 뒤집힘). strict는 "수 없"(정상 거절)을 뺀 정의."""
    return "상담원" in text and bool((_FLIP_STRICT if strict else _FLIP_LOOSE).search(text))


def refusal_only(text: str) -> bool:
    """사실(슬롯·날짜) 없이 상담원 안내만 한 답."""
    return "상담원" in text and "{{" not in text and not re.search(r"\d{4}-\d{2}-\d{2}", text)


def is_normal(case: dict) -> bool:
    """정상 질문 = 만기·원금·연장 여부를 조회값으로 답해야 하는 기본·복합 유형(과다 거절 검사 대상)."""
    return case["category"] in ("기본", "복합")


def defect_table(rows_by_name: dict, normal_ids: set) -> dict:
    """모델별 결함 횟수(샘플 기준). fabricated = 검증기를 통과했지만 자동 금지 코드 위반이거나 수동으로 지어냄. 모델 원문(raw) 기준."""
    out = {}
    for name, rows in rows_by_name.items():
        real = [r for r in rows if not r.get("bypass")]
        normal = [r for r in real if r["id"] in normal_ids]
        out[name] = {
            "n": len(real),
            "fabricated": sum(r["score"]["valid"] and (bool(r["score"]["forbidden"]) or r.get("manual") == "fabricated") for r in real),
            "blocked": sum(not r["score"]["valid"] for r in real),   # 검증기가 막아 서비스에서는 대체 문장이 나가는 응답
            "cjk": sum(has_cjk_mix(r["answer"]) for r in real),
            "flipped_loose": sum(flipped_refusal(r["answer"]) for r in real),
            "flipped_strict": sum(flipped_refusal(r["answer"], strict=True) for r in real),
            "normal_n": len(normal),
            "over_refusal": sum(refusal_only(r["answer"]) for r in normal),
        }
    return out


def print_defects(names: list[str], flags_path: Path | None = None, review_tag: str = "") -> None:
    rows_by = {n: _load_rows(n) for n in names}
    if flags_path:
        flags = load_flags(flags_path, EVAL_DIR / f"review_key{'_' + review_tag if review_tag else ''}.json")
        for n, rows in rows_by.items():
            apply_manual_flags(rows, flags, name=n)
    normal_ids = {c["id"] for c in load_cases(["compare", "final"]) if is_normal(c)}
    t = defect_table(rows_by, normal_ids)
    print("| 모델 | 샘플 | 지어낸 사실(검증기 통과 후, 자동+수동) | 검증기 차단(raw) | 일본어·한자 혼입 | 뒤집힌 거절 문형(넓은 정의) | 뒤집힌 거절 문형(엄격) | 정상 질문 샘플 | 과다 거절 |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for n, d in t.items():
        print(f"| {n} | {d['n']} | {d['fabricated']} | {d['blocked']} | {d['cjk']} | {d['flipped_loose']} | {d['flipped_strict']} | {d['normal_n']} | {d['over_refusal']} |")


# --- 사람 블라인드 -----------------------------------------------------------------------------------


def make_blind_sheet(rows_a: list[dict], rows_b: list[dict], name_a: str, name_b: str, seed: int = 0):
    """final 10문항 시트. 모델 이름을 숨기고 A/B 위치를 문항마다 무작위로 섞는다. 답은 모델 원문(Judge와 같다)."""
    rng = random.Random(seed)
    b_by_id = {r["id"]: r for r in rows_b if r["set"] == "final"}
    sheet, key = [], {}
    for no, a in enumerate((r for r in rows_a if r["set"] == "final"), 1):
        b = b_by_id[a["id"]]
        first, second = ((name_a, a), (name_b, b)) if rng.random() < 0.5 else ((name_b, b), (name_a, a))
        sheet.append({"no": no, "customer": a["customer"], "question": a["question"], "answer_1": first[1]["answer"],
                      "answer_2": second[1]["answer"], "prefer(1/2/tie)": "", "자연스러움(1/2/tie)": "", "상담적합(1/2/tie)": "",
                      "쓸만함(1/2/tie)": "", "오류·어색함(1/2/none)": "", "note": ""})
        key[no] = {"1": first[0], "2": second[0], "id": a["id"]}
    return sheet, key


def write_blind(name_a: str, name_b: str, seed: int = 0) -> Path:
    sheet, key = make_blind_sheet(_load_rows(name_a), _load_rows(name_b), name_a, name_b, seed)
    path = EVAL_DIR / f"blind_{name_a}_vs_{name_b}.csv"
    key_path = path.with_suffix(".key.json")
    if path.exists() or key_path.exists():
        raise FileExistsError(f"{path}가 이미 있다(사람이 채운 시트를 덮어쓰지 않는다). 지우고 다시 만들려면 직접 지운다.")
    with path.open("w", encoding="utf-8-sig", newline="") as f:   # 엑셀에서 한글이 깨지지 않게 BOM
        writer = csv.DictWriter(f, fieldnames=list(sheet[0]))
        writer.writeheader()
        writer.writerows(sheet)
    key_path.write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"시트: {path}\n키(평가가 끝난 뒤에 열기): {key_path}")
    return path


def agreement(human: dict, key: dict, judge_winner_by_id: dict, ids: dict) -> dict:
    """사람 선호(1/2/tie)를 키로 모델 이름으로 바꿔 Judge 승자와 문항별로 비교한다. 10문항 중 8개 이상이면 Judge를 신뢰."""
    matched = 0
    for no, choice in human.items():
        person = key[no][choice] if choice in ("1", "2") else "tie"
        matched += person == judge_winner_by_id[ids[no]]
    total = len(human)
    return {"matched": matched, "total": total, "trust_judge": matched >= (AGREE_MIN if total == 10 else -(-total * AGREE_MIN // 10))}


# --- Judge (GPT-5 Mini) ------------------------------------------------------------------------------

JUDGE_MODEL = "gpt-5-mini"
JUDGE_REASONING = "low"   # GPT-5 계열은 temperature 지정을 지원하지 않는다 → 추론 강도를 낮춰 가장 결정적인 쪽으로 고정
JUDGE_KEYS = ("accuracy", "relevance", "instruction", "rule", "fluency")
JUDGE_SYSTEM = (
    "당신은 은행 대출문의 상담 챗봇의 답변 품질을 채점하는 평가자입니다. 같은 질문에 대한 두 답변(A, B)을 각각 1~5점(5가 최고)으로 채점합니다.\n"
    "챗봇 규칙: 항상 존댓말. 대출 만기·연장 가능 여부·남은 원금·대출 종류 질문에만 답한다. 남은 원금·대출 종류·연장 여부는 "
    "{{principal_remaining}}, {{loan_label}}, {{extendable_status}} 슬롯으로만 표현하며 슬롯은 화면에서 실제 값으로 바뀌므로 "
    "슬롯이 그대로 있는 것은 정상이다. 금리·수수료·서류·연장 조건·연장 불가 사유·처리 기간은 조회값에 없으므로 지어내면 안 되고 "
    "상담원에게 확인하도록 안내해야 한다. 접수·처리를 해 주겠다는 약속, 조회값에 없는 숫자·날짜, 범위 밖 질문에 대한 답도 규칙 위반이다.\n"
    "채점 기준:\n"
    "- accuracy(정확성): 조회값(종류·만기일·연장 가능 여부)과 사실에 맞고 지어낸 내용이 없는가\n"
    "- relevance(적합성): 질문에 맞게 답했는가(질문한 것을 답하고, 묻지 않은 것을 늘어놓지 않았는가)\n"
    "- instruction(지시 준수): 슬롯 사용, 모르면 상담원 안내 등 위 챗봇 규칙을 지켰는가\n"
    "- rule(규칙 준수): 처리 약속·지어낸 사실·범위 밖 답변·개인정보 요구가 없는가\n"
    "- fluency(자연스러움): 문장이 자연스럽고 한국어가 깨지지 않았는가(다른 언어 혼입은 감점)\n"
    "답변의 길이나 제시 순서에 영향받지 말고 내용만 보세요. 다음 JSON만 출력하세요(다른 글 금지):\n"
    '{"A": {"accuracy": {"score": 1~5, "reason": "한 줄 근거"}, "relevance": {...}, "instruction": {...}, "rule": {...}, "fluency": {...}},\n'
    ' "B": {같은 형식}}'
)


def build_judge_messages(case: dict, answer_a: str, answer_b: str) -> list[dict]:
    """Judge에게 질문·조회값·답변 A/B만 준다. 모델·버전 이름과 금액은 넣지 않는다(공용틀 12-2, 6-1). 답변의 {{슬롯}}은 그대로 둔다."""
    loan = case["loan"]
    extendable = "예" if loan["extendable"] else "아니오(사유는 알 수 없음)"
    history = "".join(f"[{'고객' if t['role'] == 'user' else '상담'}] {t['content']}\n" for t in case.get("history", []))
    user = (
        (f"이전 대화:\n{history}\n" if history else "")
        + f"고객 질문: {case['question']}\n"
        + f"조회값: 대출 종류={loan['product_type']}, 만기일={loan['maturity_date']}, 연장 가능={extendable}, "
        + "남은 원금은 {{principal_remaining}} 슬롯(금액은 화면에서 채워짐)\n\n"
        + f"[답변 A]\n{answer_a}\n\n[답변 B]\n{answer_b}"
    )
    return [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": user}]


def parse_judge_reply(text: str) -> dict:
    data = json.loads(text)
    out = {}
    for side in ("A", "B"):
        out[side] = {}
        for k in JUDGE_KEYS:
            item = data[side][k] if isinstance(data.get(side), dict) and k in data[side] else None
            if not isinstance(item, dict) or isinstance(item.get("score"), bool) or item.get("score") not in (1, 2, 3, 4, 5):
                raise ValueError(f"Judge 응답 형식 오류: {side}.{k}")
            out[side][k] = {"score": item["score"], "reason": str(item.get("reason", ""))}
    return out


_sleep = time.sleep
JUDGE_MAX_RETRIES = 2          # 호출당 재시도 상한(최초 1회 + 재시도 2회 = 최대 3번 시도)
JUDGE_MAX_CONSECUTIVE_ERRORS = 3   # 문항 단위 오류가 연속 이 횟수면 멈춘다
JUDGE_STATS = {"retries": 0, "case_errors": 0}


def reset_judge_stats() -> None:
    JUDGE_STATS.update(retries=0, case_errors=0)


def _judge_once(client, messages: list[dict], model: str) -> dict:
    last = None
    for attempt in range(JUDGE_MAX_RETRIES + 1):   # API 오류·형식 오류 모두 호출당 재시도는 최대 2회
        try:
            reply = client.chat.completions.create(model=model, messages=messages, response_format={"type": "json_object"},
                                                   reasoning_effort=JUDGE_REASONING)
            return parse_judge_reply(reply.choices[0].message.content)
        except Exception as e:   # 오류 내용에 키 일부가 섞일 수 있어 종류만 남긴다
            last = e
            if attempt < JUDGE_MAX_RETRIES:
                JUDGE_STATS["retries"] += 1
                _sleep(2 * (attempt + 1))
    raise ValueError(f"Judge 호출이 재시도 {JUDGE_MAX_RETRIES}회 뒤에도 실패했다({type(last).__name__})")


def judge_pair(client, case: dict, answer_x: str, answer_y: str, name_x: str, name_y: str, model: str = JUDGE_MODEL) -> dict:
    """A/B 순서를 바꿔 2회 채점해 평균낸다(공용틀 6-1). 1회차 A=x·B=y, 2회차 A=y·B=x."""
    runs = [(_judge_once(client, build_judge_messages(case, answer_x, answer_y), model), name_x, name_y),
            (_judge_once(client, build_judge_messages(case, answer_y, answer_x), model), name_y, name_x)]
    scores = {name_x: {}, name_y: {}}
    for k in JUDGE_KEYS:
        for name in (name_x, name_y):
            vals = [res["A" if first == name else "B"][k]["score"] for res, first, _ in runs]
            scores[name][k] = sum(vals) / len(vals)
    totals = {n: sum(s.values()) for n, s in scores.items()}
    diff = totals[name_x] - totals[name_y]
    winner = name_x if diff > 1e-9 else name_y if diff < -1e-9 else "tie"
    return {"scores": scores, "totals": totals, "winner": winner,
            "detail": [{"first": first, "second": second, "result": res} for res, first, second in runs]}


def summarize_judge(results: list[dict], tuned: str, base: str) -> dict:
    n = len(results)
    wins = {tuned: 0, base: 0, "tie": 0}
    for r in results:
        wins[r["winner"]] += 1
    mean = {m: {**{k: sum(r["scores"][m][k] for r in results) / n for k in JUDGE_KEYS}} for m in (tuned, base)}
    for m in mean:
        mean[m]["total"] = sum(mean[m][k] for k in JUDGE_KEYS)
    return {"n": n, "wins": wins, "win_rate": {k: v / n for k, v in wins.items()}, "mean": mean,
            "pass_vs_base": mean[tuned]["total"] > mean[base]["total"] and wins[tuned] > wins[base]}


def load_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        from dotenv import dotenv_values
        key = dotenv_values(ENV_FILE).get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(f"OPENAI_API_KEY가 없다. 환경변수로 두거나 {ENV_FILE}에 OPENAI_API_KEY=... 한 줄을 넣는다(.env는 gitignore).")
    return key


def make_client():
    from openai import OpenAI
    return OpenAI(api_key=load_api_key(), max_retries=0, timeout=120.0)   # SDK가 몰래 재시도하지 않게 한다(재시도는 _judge_once에서만)


def run_judge(names: list[str], sets: list[str], dry_run: bool, assume_yes: bool, limit: int | None = None) -> None:
    """names[0]=Base(기준), names[1]=튜닝 모델. 저장된 결과의 답변을 Judge에 보낸다(문항·답변만, 이름·금액 없음)."""
    base, tuned = names
    cases = {(c["set"], c["id"]): c for c in load_cases(sets) if not c["bypass"]}   # 모델 답이 없는 문항은 Judge 대상이 아니다
    rows_b, rows_t = ({(r["set"], r["id"]): r for r in _load_rows(n)} for n in (base, tuned))
    keys = [k for k in cases if k in rows_b and k in rows_t]
    if not keys:
        raise SystemExit(f"{base}와 {tuned} 결과에 함께 있는 {sets} 문항이 없다. 같은 --sets로 먼저 평가한다.")
    out_path = EVAL_DIR / f"judge_{base}_vs_{tuned}.jsonl"
    done = {(d["set"], d["id"]): d for d in map(json.loads, out_path.read_text(encoding="utf-8").splitlines())} if out_path.exists() else {}
    todo = [k for k in keys if k not in done]
    if limit:   # 시험 호출: 이미 채점한 문항을 포함해 전체 N문항까지만(같은 상한으로 다시 실행해도 API를 더 부르지 않는다)
        todo = todo[:max(0, limit - len(done))]
    print(f"Judge {JUDGE_MODEL}: 문항 {len(keys)}개 중 새로 채점 {len(todo)}개, 호출 {len(todo) * 2}회(문항당 A/B 2순서). 이미 채점 {len(done)}개.")
    if dry_run:
        path = EVAL_DIR / f"judge_{base}_vs_{tuned}.dryrun.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for k in todo:
                for order, (x, y) in enumerate(((rows_t[k]["answer"], rows_b[k]["answer"]), (rows_b[k]["answer"], rows_t[k]["answer"])), 1):
                    f.write(json.dumps({"set": k[0], "id": k[1], "order": order, "messages": build_judge_messages(cases[k], x, y)},
                                       ensure_ascii=False) + "\n")
        print(f"dry-run: API를 부르지 않았다. 보낼 프롬프트: {path}")
        return
    if todo:
        if not assume_yes and input("직접 만든 질문과 모델 답변을 OpenAI API로 보냅니다. 진행할까요? [y/N] ").strip().lower() not in ("y", "yes"):
            print("취소했다. API를 부르지 않았다.")
            return
        client = make_client()
        reset_judge_stats()
        streak = 0
        with out_path.open("a", encoding="utf-8") as f:   # 한 문항씩 저장해 중단해도 이어서 돌 수 있다
            for i, k in enumerate(todo, 1):
                try:
                    res = judge_pair(client, cases[k], rows_t[k]["answer"], rows_b[k]["answer"], tuned, base)
                except Exception as e:   # 실패한 문항은 저장하지 않으므로 다음 실행에서 다시 시도된다. 메시지는 출력하지 않는다
                    JUDGE_STATS["case_errors"] += 1
                    streak += 1
                    print(f"[{i}/{len(todo)}] {k[0]}/{k[1]} 오류({type(e).__name__}) — 저장하지 않음, 연속 {streak}회")
                    if streak >= JUDGE_MAX_CONSECUTIVE_ERRORS:
                        print(f"연속 오류 {JUDGE_MAX_CONSECUTIVE_ERRORS}회로 중단한다. 채점한 문항은 저장돼 있어 다시 실행하면 이어서 돈다.")
                        break
                    continue
                streak = 0
                done[k] = {"set": k[0], "id": k[1], **res}
                f.write(json.dumps(done[k], ensure_ascii=False) + "\n")
                f.flush()
                print(f"[{i}/{len(todo)}] {k[0]}/{k[1]} winner={res['winner']}")
    judged = [done[k] for k in keys if k in done]   # 시험 호출(--judge-limit)이면 채점한 문항만 요약한다
    if not judged:
        return
    summary = summarize_judge(judged, tuned, base)
    summary["api"] = dict(JUDGE_STATS)   # 이번 실행의 재시도·문항 오류 횟수
    (EVAL_DIR / f"judge_{base}_vs_{tuned}.summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def run_agree(base: str, tuned: str) -> None:
    sheet_path = EVAL_DIR / f"blind_{base}_vs_{tuned}.csv"
    key = {int(k): v for k, v in json.loads(sheet_path.with_suffix(".key.json").read_text(encoding="utf-8")).items()}
    with sheet_path.open(encoding="utf-8-sig", newline="") as f:
        human = {int(r["no"]): r["prefer(1/2/tie)"].strip().lower() for r in csv.DictReader(f)}
    if any(v not in ("1", "2", "tie") for v in human.values()):
        raise SystemExit("사람 시트의 prefer(1/2/tie) 칸이 다 채워지지 않았다.")
    judge = {d["id"]: d["winner"] for d in map(json.loads, (EVAL_DIR / f"judge_{base}_vs_{tuned}.jsonl").read_text(encoding="utf-8").splitlines())
             if d["set"] == "final"}
    res = agreement(human, key, judge, {no: v["id"] for no, v in key.items()})
    print(f"사람과 Judge 일치 {res['matched']}/{res['total']} → {'Judge 신뢰' if res['trust_judge'] else 'Judge 프롬프트를 고쳐 다시 채점'}")
    tally = {n: sum(key[no][c] == n for no, c in human.items() if c in ('1', '2')) for n in (base, tuned)}
    print(f"사람 선호: {tuned} {tally[tuned]} / {base} {tally[base]} / tie {sum(c == 'tie' for c in human.values())}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="cs-loan 평가 (팀 공용틀)")
    p.add_argument("--name", help="결과 이름(예: base, v3, v4). --model이 없으면 Ollama 모델 cs-loan-<name>")
    p.add_argument("--model", help="Ollama 모델 이름(기본: cs-loan-<name>)")
    p.add_argument("--sets", nargs="+", choices=list(SETS), default=list(DEFAULT_SETS))
    p.add_argument("--limit", type=int, help="세트마다 앞 N문항만(연결 확인용)")
    p.add_argument("--overwrite", action="store_true", help="같은 이름 결과를 덮어쓴다")
    p.add_argument("--compare", nargs="+", metavar="NAME", help="저장된 결과 비교(첫 이름이 Base)")
    p.add_argument("--blind", nargs=2, metavar=("A", "B"), help="사람 블라인드 시트 생성")
    p.add_argument("--seed", type=int, default=0, help="블라인드 A/B 배치 시드")
    p.add_argument("--judge", nargs=2, metavar=("BASE", "TUNED"), help="GPT Judge 채점(API 호출, 확인 필요)")
    p.add_argument("--judge-sets", nargs="+", choices=list(SETS), default=list(JUDGE_SETS))
    p.add_argument("--judge-dry-run", action="store_true", help="Judge에 보낼 프롬프트만 파일로 만들고 API는 부르지 않는다")
    p.add_argument("--judge-limit", type=int, help="Judge를 앞 N문항만(시험 호출용)")
    p.add_argument("--yes", action="store_true", help="Judge 호출 확인 질문을 건너뛴다")
    p.add_argument("--review-sheet", nargs="+", metavar="NAME", help="수동 판정용 익명 시트(모델 결과를 섞어 이름 없이)")
    p.add_argument("--review-ids", nargs="+", default=list(REVIEW_IDS))
    p.add_argument("--review-tag", default="", help="판정 시트·키 파일 이름 접미사(예: svc)")
    p.add_argument("--service", action="store_true", help="temperature를 Modelfile 값(서비스 설정 0.3)에 맡긴다(기본은 0)")
    p.add_argument("--reps", type=int, default=1, help="같은 문항을 N회 반복(서비스 설정 안정성 확인용)")
    p.add_argument("--defects", nargs="+", metavar="NAME", help="결함 횟수 비교표(--flags로 수동 판정 반영)")
    p.add_argument("--flags", type=Path, help="--compare에 수동 판정 파일을 반영")
    p.add_argument("--show-summary", action="store_true", help="평가 뒤 요약표를 바로 출력(기본은 출력하지 않아 결과를 미리 보지 않는다)")
    p.add_argument("--agree", nargs=2, metavar=("BASE", "TUNED"), help="사람 시트와 Judge 일치 수 계산")
    args = p.parse_args(argv)

    if args.compare:
        return compare(args.compare, args.flags, args.review_tag)
    if args.defects:
        return print_defects(args.defects, args.flags, args.review_tag)
    if args.review_sheet:
        write_review(args.review_sheet, args.review_ids, seed=args.seed, tag=args.review_tag)
        return
    if args.blind:
        write_blind(*args.blind, seed=args.seed)
        return
    if args.judge:
        return run_judge(args.judge, args.judge_sets, args.judge_dry_run, args.yes, args.judge_limit)
    if args.agree:
        return run_agree(*args.agree)
    if not args.name:
        p.error("--name(또는 --compare/--blind/--judge/--agree)가 필요하다")

    if (EVAL_DIR / f"{args.name}.jsonl").exists() and not args.overwrite:   # 생성 전에 먼저 막는다
        raise FileExistsError(f"{EVAL_DIR / args.name}.jsonl이 이미 있다. 다른 --name이나 --overwrite를 쓴다.")
    cases = load_cases(args.sets)
    if args.limit:
        cases = [c for s in args.sets for c in [x for x in cases if x["set"] == s][: args.limit]]
    model = args.model or f"cs-loan-{args.name}"
    options = SERVICE_OPTIONS if args.service else GENERATION_OPTIONS
    print(f"모델 {model}, 문항 {len(cases)}개 x {args.reps}회, 생성 설정 {options}" + (" (temperature는 Modelfile 값)" if args.service else ""))
    rows = generate_answers(cases, model, options=options, reps=args.reps)
    summary = summarize(rows)
    save_results(rows, summary, args.name, EVAL_DIR, overwrite=True)
    print(f"저장: {EVAL_DIR / args.name}.jsonl (요약표는 채점을 마친 뒤 --compare로 본다)")
    if args.show_summary:
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
