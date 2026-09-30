"""v4 자체 평가 실행(EVAL_CRITERIA_v4.md). 서비스(agent.py)와 같은 프롬프트 빌더·검증기·대체 문장을 쓴다.
세트: base = 위험 세트+dev(v3 평가와 같은 137문항 x5, 정상 질문 통과율·결함 보고에 쓴다)
      final0 = 최종 확인용 F01~F10 온도 0 x1(판정), final5 = F01~F10 서비스 설정(온도 0.3) x5(안정성 보고), compare = K01~K20 x5.
결과는 (모델, 세트, 문항, 회차) 단위로 data/derived/eval_v4/raw_<모델>.jsonl에 쌓고 중단 후 다시 실행하면 이어서 돈다(gitignored).
사용: .venv/bin/python training/loan/eval_v4_run.py cs-loan-v4 [cs-loan-v3 ...]   (v3는 base 세트를 이미 eval_v3에서 가져오므로 final·compare만 돈다)"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, ".")
from app import llm
from app.agents.loan import prompt, validate
from app.agents.loan.mock_api import get_loans

OUT = Path("data/derived/eval_v4"); OUT.mkdir(parents=True, exist_ok=True)
read = lambda p: [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
G = "training/loan/"
base = read(G + "golden_set_risk.jsonl") + [dict(r, tag="dev") for f in ("golden_set.jsonl", "golden_set_v3.jsonl") for r in read(G + f)]
final, compare = read(G + "golden_set_final_v4.jsonl"), read(G + "golden_set_v4_compare.jsonl")
# (세트 이름, 문항, 반복, 생성 옵션)  옵션 {}이면 Modelfile 값(온도 0.3)이 적용된다
PLAN = [("base", [r for r in base if r.get("model_eval", True)], 5, {}), ("final0", final, 1, {"temperature": 0}),
        ("final5", final, 5, {}), ("compare", compare, 5, {})]
def loan_of(r):
    if r.get("loan"): return r["loan"]
    loans = get_loans(r["customer"]); return loans[0] if loans else None
def log(m): open(OUT / "eval.log", "a", encoding="utf-8").write(time.strftime("%H:%M:%S ") + m + "\n")

for model in sys.argv[1:]:
    path = OUT / f"raw_{model}.jsonl"
    done = {(d["set"], d["id"], d["rep"]) for d in read(path)} if path.exists() else set()
    n = 0
    for name, rows, reps, opts in PLAN:
        if name == "base" and model == "cs-loan-v3": continue
        for rep in range(1, reps + 1):
            for r in rows:
                loan = loan_of(r)
                if loan is None or (name, r["id"], rep) in done: continue
                msgs = prompt.build_messages(r.get("history", []), r["question"], loan)
                t = time.time()
                for attempt in range(3):
                    try: raw = llm.generate(model, msgs, **opts); break
                    except Exception as e: log(f"{model} {name} {r['id']} rep{rep} 재시도 {attempt}: {e}"); time.sleep(3)
                else: continue
                valid = validate.is_valid_output(raw, maturity_date=loan["maturity_date"], extendable=loan["extendable"])
                with path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"model": model, "set": name, "id": r["id"], "rep": rep, "raw": raw, "valid": valid,
                                        "final": raw if valid else prompt.fallback_text(loan), "sec": round(time.time() - t, 2)}, ensure_ascii=False) + "\n")
                n += 1
                if n % 50 == 0: log(f"{model} 누적 {n}건 ({name})")
    log(f"{model} 완료 (이번 실행 {n}건)")
log("전체 완료")
