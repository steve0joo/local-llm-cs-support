"""training/loan/evaluate.py — 팀 공용틀(EVALUATION_공용틀.md) 규약의 대출문의 평가 도구.

모델(Ollama)과 Judge(OpenAI)는 가짜로 바꿔 API·모델 없이 돌린다.
"""
import json
from pathlib import Path

import pytest

from app.agents.loan import prompt
from training.loan import evaluate as ev

MATURITY = "2027-03-31"   # C002 신용대출(연장 가능)
LOAN_OK = {"product_type": "신용대출", "principal_remaining": 12000000, "maturity_date": MATURITY, "extendable": True}
LOAN_NO = {"product_type": "주택담보대출", "principal_remaining": 85000000, "maturity_date": "2035-06-30", "extendable": False}
GOOD = "고객님의 {{loan_label}} 만기일은 2027-03-31입니다."
REFUSAL = "정확한 처리 시간은 제가 확인해 드리기 어렵습니다. 상담원에게 확인해 주세요."


# --- 세트 -------------------------------------------------------------------------------


def test_sets_follow_the_common_frame_sizes():
    sizes = {name: len(ev.load_cases([name])) for name in ev.SETS}
    # compare = K20 + 새 10문항(M), compare_old = 기존 golden_set 비교용(참고만, 판정 제외)
    assert sizes == {"compare": 30, "compare_old": 30, "regress": 20, "final": 10, "k20": 20, "new10": 10}
    assert ev.DEFAULT_SETS == ("compare", "compare_old", "regress", "final")
    assert ev.JUDGE_SETS == ("compare", "final")


def test_compare_set_is_k20_plus_the_users_new_ten():
    ids = [c["id"] for c in ev.load_cases(["compare"])]
    assert ids == [f"K{i:02d}" for i in range(1, 21)] + [f"M{i:02d}" for i in range(1, 11)]


def test_case_ids_are_unique_across_default_sets():
    cases = ev.load_cases(list(ev.DEFAULT_SETS))
    keys = [(c["set"], c["id"]) for c in cases]
    assert len(keys) == len(set(keys))


def test_cases_use_the_service_prompt_and_never_carry_amounts():
    for c in (c for c in ev.load_cases(list(ev.SETS)) if not c["bypass"]):
        assert c["messages"][0] == {"role": "system", "content": prompt.SYSTEM_PROMPT}
        assert c["messages"][-1]["content"].startswith(c["question"] + "\n대출 정보: ")
        text = json.dumps(c["messages"], ensure_ascii=False)
        assert "12000000" not in text and "85000000" not in text and "12,000,000" not in text


def test_progress_line_does_not_reveal_the_automatic_verdict(capsys):
    ev._print_progress(1, 2, _row("compare", "K01", True, seconds=1.0))
    out = capsys.readouterr().out
    assert "K01" in out and "rule" not in out and "valid" not in out and "True" not in out and "False" not in out


def test_no_loan_cases_stay_in_the_set_but_never_call_the_model():
    # 공용틀 회귀 20문항(1문항 = 5%p)을 지키려고 대출 없는 고객(C001) 2문항을 남기되, 서비스처럼 고정 문장으로 답한다
    bypass = [c for c in ev.load_cases(list(ev.SETS)) if c["bypass"]]
    assert len(bypass) == 2 and {c["customer"] for c in bypass} == {"C001"} and {c["set"] for c in bypass} == {"regress"}
    calls = []
    rows = ev.generate_answers(bypass, "cs-loan-base", generate=lambda *a, **k: calls.append(a) or "x", progress=lambda *_: None)
    assert calls == []
    assert all(r["answer"] == prompt.NO_LOAN_TEXT and r["bypass"] and r["score"]["rule"] for r in rows)


def test_regular_cases_are_not_bypass():
    assert not any(c["bypass"] for c in ev.load_cases(["compare", "final", "k20"]))


# --- 채점 -------------------------------------------------------------------------------


def _case(**kw):
    base = {"set": "compare", "id": "X", "customer": "C002", "loan": LOAN_OK, "question": "q", "history": [],
            "expect": [], "must": None, "category": "만기", "bypass": False}
    return base | kw


def test_codes_date_and_slots():
    c = ev.codes(GOOD, LOAN_OK)
    assert c["date"] and c["slot_loan_label"] and not c["slot_extend"] and not c["slot_principal"]
    assert not ev.codes("만기일은 2027-04-01입니다.", LOAN_OK)["date"]
    assert ev.codes("만기일은 2027년 3월 31일입니다.", LOAN_OK)["date"]
    assert ev.codes("{{extendable_status}} {{principal_remaining}}", LOAN_OK)["slot_extend"]


@pytest.mark.parametrize(
    "text, code, expected",
    [
        ("네, 맞습니다. 만기일은 2027-03-31입니다.", "no_direction", False),
        ("금리가 올라서 그렇습니다.", "no_direction", False),
        ("이 문의는 제가 도와드리는 범위가 아닙니다. 상담원에게 확인해 주세요.", "no_direction", True),  # 거절 문형은 방향 표현이 아니다
        ("연장이 안 되는 이유는 신용 때문입니다.", "no_cause_claim", False),
        ("연장이 안 되는 사유는 조회되지 않습니다.", "no_cause_claim", True),
        ("연장 신청을 접수해 드리겠습니다.", "no_commit", False),
        ("연장 신청 처리는 제가 해 드리기 어렵습니다. 상담원에게 확인해 주세요.", "no_commit", True),  # 거절 문장은 약속이 아니다
        ("주민번호 [주민번호_1]을 확인했습니다.", "no_echo_token", False),
        ("고객님의 {{loan_label}} 정보입니다.", "no_echo_token", True),
        ("아니요, 고객님의 {{loan_label}} 만기일은 2027-03-31입니다.", "no_affirm", True),
        ("말씀하신 날짜와 다릅니다. 만기일은 2027-03-31입니다.", "no_affirm", True),
        ("네, 맞습니다. 만기일은 2027-03-31입니다.", "no_affirm", False),
        ("네 만기일은 2027-03-31입니다.", "no_affirm", False),
        ("만기일은 2027-03-31이 맞습니다.", "no_affirm", False),
        ("그렇습니다. 만기일은 2027-03-31입니다.", "no_affirm", False),
        ("아니요, 만기일은 2027-03-31입니다.", "explicit_no", True),
        ("만기일은 2027-03-31입니다.", "explicit_no", False),
        ("만기일을 알려 주세요", "polite", True),
        ("만기일 알려줘", "polite", False),
    ],
)
def test_forbidden_and_tone_codes(text, code, expected):
    assert ev.codes(text, LOAN_OK)[code] is expected


def test_score_rule_needs_valid_expect_tone_and_no_forbidden():
    case = _case(expect=["date"])
    ok = ev.score(case, GOOD)
    assert ok["valid"] and ok["expect"] and ok["tone"] and ok["forbidden"] == [] and ok["rule"] and ok["fail"] == []
    bad_date = ev.score(case, "고객님의 {{loan_label}} 만기일은 곧 도래합니다.")
    assert not bad_date["rule"] and bad_date["fail"] == ["date"]
    invalid = ev.score(case, "만기일은 2027-03-31이고 금리는 3%입니다.")  # 검증기가 숫자를 막는다
    assert not invalid["valid"] and not invalid["rule"] and "validator" in invalid["fail"]
    committed = ev.score(_case(expect=[]), "연장 신청을 접수해 드리겠습니다.")
    assert "no_commit" in committed["forbidden"] and not committed["rule"]


def test_japanese_output_is_invalid_for_every_model():
    assert not ev.score(_case(), "제가 확인できません. 상담원에게 문의해 주세요.")["valid"]


def test_must_based_rows_use_their_own_required_codes():
    case = _case(set="final", must=["slot_loan_label", "no_fabrication", "polite"], expect=[])
    assert ev.score(case, "고객님의 {{loan_label}}입니다.")["rule"]
    missed = ev.score(case, "고객님의 대출입니다.")
    assert not missed["rule"] and missed["fail"] == ["slot_loan_label"]


def test_m08_wrong_date_correction_passes_even_with_explicit_no():
    case = _case(set="compare", id="M08", must=["date", "no_affirm", "polite"], record=["explicit_no"])
    ok = ev.score(case, "아니요, 고객님의 {{loan_label}} 만기일은 2027-03-31입니다.")   # no_fabrication이 아니므로 "아니요"가 실패가 아니다
    assert ok["rule"] and ok["record"] == {"explicit_no": True}
    affirmed = ev.score(case, "네, 맞습니다. 만기일은 2027-03-31입니다.")
    assert not affirmed["rule"] and affirmed["fail"] == ["no_affirm"]
    repeated = ev.score(case, "2027-05-31이 아니라 2027-03-31입니다.")          # 틀린 날짜를 되풀이하면 검증기가 숫자로 막는다
    assert not repeated["valid"] and "validator" in repeated["fail"]
    implicit = ev.score(case, "말씀하신 날짜와 다릅니다. 만기일은 2027-03-31입니다.")
    assert implicit["rule"] and implicit["record"] == {"explicit_no": False}


def test_expect_codes_of_dev_rows_map_to_required_codes():
    assert ev.required_codes(_case(expect=["date", "slot_principal"])) == ["date", "slot_principal", "polite", "no_fabrication"]
    assert ev.required_codes(_case(expect=["off_topic"])) == ["polite", "no_fabrication"]
    assert ev.required_codes(_case(expect=["refer"], category="수수료"))[-1] == "topic_fee_word"
    assert ev.required_codes(_case(must=["date", "polite"])) == ["date", "polite"]


def test_fee_topic_row_needs_a_fee_word_and_no_rate():
    case = _case(expect=["refer"], category="수수료")
    assert ev.score(case, "수수료는 제가 알 수 없습니다. 상담원에게 확인해 주세요.")["rule"]
    assert not ev.score(case, "금리는 제가 알 수 없습니다. 상담원에게 확인해 주세요.")["rule"]


# --- 생성 -------------------------------------------------------------------------------


def test_generation_options_pin_temperature_zero():
    assert ev.GENERATION_OPTIONS["temperature"] == 0
    assert ev.GENERATION_OPTIONS["num_predict"] > 0


def test_generate_answers_uses_fixed_options_and_serves_fallback_when_invalid():
    calls = []

    def fake(model, messages, **options):
        calls.append((model, options))
        return "만기일은 2027-03-31이고 금리는 3%입니다." if len(calls) == 1 else GOOD

    cases = [_case(id="A", expect=["date"], messages=[{"role": "user", "content": "q"}]),
             _case(id="B", expect=["date"], messages=[{"role": "user", "content": "q"}])]
    rows = ev.generate_answers(cases, "cs-loan-base", generate=fake, progress=lambda *_: None)
    assert [o for _, o in calls] == [ev.GENERATION_OPTIONS] * 2 and {m for m, _ in calls} == {"cs-loan-base"}
    assert rows[0]["answer"].endswith("3%입니다.") and not rows[0]["score"]["valid"]
    assert rows[0]["served"] == prompt.fallback_text(LOAN_OK)     # 서비스와 같은 대체 문장
    assert rows[1]["served"] == GOOD and rows[1]["score"]["rule"]
    assert "messages" not in rows[0]
    # 서비스가 보여 주는 답(final)도 같은 기준으로 채점한다. 대체 문장은 검증기를 통과하는 고정 문장이다
    assert rows[0]["score_final"]["valid"] and rows[1]["score_final"]["rule"] == rows[1]["score"]["rule"]


def test_generation_uses_llm_module_by_default(monkeypatch):
    seen = []
    monkeypatch.setattr(ev.llm, "generate", lambda model, messages, **o: seen.append(o) or GOOD)
    ev.generate_answers([_case(expect=["date"], messages=[{"role": "user", "content": "q"}])], "cs-loan-v4",
                        progress=lambda *_: None)
    assert seen == [ev.GENERATION_OPTIONS]


# --- 집계·저장·비교 ------------------------------------------------------------------------


def _row(set_, id_, rule, valid=True, **kw):
    score = {"valid": valid, "slot": True, "forbidden": [] if rule else ["no_commit"], "length": 10, "tone": True,
             "expect": rule, "rule": rule, "fail": []}
    return {"set": set_, "id": id_, "customer": "C002", "category": "만기", "question": "q", "answer": "a", "served": "a",
            "score": score} | kw


def test_summarize_rates_per_set_and_all():
    rows = [_row("compare", "1", True), _row("compare", "2", False), _row("regress", "3", True)]
    s = ev.summarize(rows)
    assert s["compare"]["n"] == 2 and s["compare"]["rule"] == 0.5 and s["compare"]["forbidden"] == 0.5
    assert s["regress"]["rule"] == 1.0
    assert s["all"]["n"] == 3


def test_summarize_reports_raw_final_model_only_and_groups():
    rows = [_row("compare", "K01", True), _row("compare", "M01", False), _row("regress", "R01", True),
            _row("regress", "R07", True, bypass=True)]
    rows[1]["score_final"] = dict(rows[1]["score"], rule=True)          # 검증기 대체로 final은 통과
    rows[0]["score_final"] = dict(rows[0]["score"]); rows[2]["score_final"] = dict(rows[2]["score"]); rows[3]["score_final"] = dict(rows[3]["score"])
    s = ev.summarize(rows)
    assert s["compare"]["rule"] == 0.5 and s["compare"]["rule_final"] == 1.0
    assert s["compare:K"]["n"] == 1 and s["compare:M"]["n"] == 1 and s["compare:M"]["rule"] == 0.0
    assert s["regress"]["n"] == 2 and s["regress"]["n_model"] == 1 and s["regress"]["rule_model"] == 1.0   # 20문항 중 모델 호출 18문항 병기


def test_type_groups_bundle_m05_with_k10():
    groups = ev.type_groups(ev.load_cases(["compare"]))
    assert {"K10", "M05"} <= set(groups["수수료"])


def test_save_results_never_overwrites_without_flag(tmp_path):
    rows = [_row("compare", "1", True)]
    ev.save_results(rows, ev.summarize(rows), "v4", tmp_path)
    assert (tmp_path / "v4.jsonl").exists() and (tmp_path / "v4.summary.json").exists()
    with pytest.raises(FileExistsError):
        ev.save_results(rows, ev.summarize(rows), "v4", tmp_path)
    ev.save_results(rows, ev.summarize(rows), "v4", tmp_path, overwrite=True)


def test_verdicts_apply_the_team_thresholds():
    base = {"compare": {"rule": 0.70}, "regress": {"rule": 0.90}}
    good = {"compare": {"rule": 0.87}, "regress": {"rule": 0.85}}     # 회귀 하락 5%p = 허용(1문항)
    worse = {"compare": {"rule": 0.77}, "regress": {"rule": 0.80}}
    v = ev.verdicts(base, good)
    assert v["rule_pass"] and v["regress_drop_pp"] == pytest.approx(5.0) and v["regress_pass"]
    w = ev.verdicts(base, worse)
    assert not w["rule_pass"] and not w["regress_pass"] and w["regress_drop_pp"] == pytest.approx(10.0)


# --- 사람 블라인드 ---------------------------------------------------------------------------


def _pair():
    a = [_row("final", f"F{i}", True, answer=f"a{i}", served=f"a{i}") for i in range(1, 11)] + [_row("compare", "C1", True)]
    b = [_row("final", f"F{i}", True, answer=f"b{i}", served=f"b{i}") for i in range(1, 11)] + [_row("compare", "C1", True)]
    return a, b


def test_blind_sheet_uses_only_final_set_and_hides_model_names():
    a, b = _pair()
    sheet, key = ev.make_blind_sheet(a, b, "base", "v4", seed=1)
    assert len(sheet) == 10 and len(key) == 10
    text = json.dumps(sheet, ensure_ascii=False)
    assert "base" not in text and "v4" not in text
    assert {k["1"] for k in key.values()} | {k["2"] for k in key.values()} == {"base", "v4"}
    assert any(k["1"] == "base" for k in key.values()) and any(k["1"] == "v4" for k in key.values())  # 위치가 섞인다
    assert sheet == ev.make_blind_sheet(a, b, "base", "v4", seed=1)[0]                                # 같은 시드는 같은 배치


def test_blind_sheet_shows_the_raw_model_answer_like_the_judge_does():
    a, b = _pair()
    a[0]["served"] = "대체 문장"
    sheet, key = ev.make_blind_sheet(a, b, "base", "v4", seed=0)
    shown = {s["answer_1"] for s in sheet} | {s["answer_2"] for s in sheet}
    assert "a1" in shown and "대체 문장" not in shown


# --- Judge ------------------------------------------------------------------------------------


def _judge_case(**kw):
    return _case(id="F01", set="final", question="만기가 언제예요?") | kw


def test_judge_prompt_has_no_model_names_or_amounts():
    msgs = ev.build_judge_messages(_judge_case(), "답변1 {{principal_remaining}}", "답변2")
    text = json.dumps(msgs, ensure_ascii=False)
    for banned in ("base", "Base", "cs-loan", "v3", "v4", "Qwen", "QLoRA", "12000000", "12,000,000"):
        assert banned not in text, banned
    assert "답변1 {{principal_remaining}}" in text and "답변2" in text and MATURITY in text     # 슬롯은 그대로 보낸다
    for key in ("accuracy", "relevance", "instruction", "rule", "fluency"):
        assert key in text


def _reply(a, b):
    def one(s):
        return {k: {"score": s, "reason": "근거"} for k in ev.JUDGE_KEYS}
    return json.dumps({"A": one(a), "B": one(b)})


class FakeClient:
    """openai.OpenAI 흉내: chat.completions.create(**kw) → 미리 정한 응답."""

    def __init__(self, replies):
        self.replies, self.calls = list(replies), []
        self.chat = self
        self.completions = self

    def create(self, **kw):
        self.calls.append(kw)
        reply = self.replies.pop(0)
        return type("R", (), {"choices": [type("C", (), {"message": type("M", (), {"content": reply})()})()]})()


def test_judge_pair_scores_both_orders_and_maps_back_to_models():
    # 1회차: A=tuned(4점) B=base(2점). 2회차(순서 반대): A=base(2점) B=tuned(4점)
    client = FakeClient([_reply(4, 2), _reply(2, 4)])
    out = ev.judge_pair(client, _judge_case(), "tuned 답", "base 답", "v4", "base")
    assert set(out["scores"]) == {"v4", "base"}
    assert all(out["scores"]["v4"][k] == 4 and out["scores"]["base"][k] == 2 for k in ev.JUDGE_KEYS)
    assert out["winner"] == "v4" and len(client.calls) == 2
    firsts = [c["messages"][-1]["content"].index("tuned 답") < c["messages"][-1]["content"].index("base 답") for c in client.calls]
    assert firsts[0] != firsts[1]                                                                # 순서가 바뀐다
    assert all("temperature" not in c for c in client.calls)                                    # GPT-5 계열은 temperature 미지원


def test_judge_pair_retries_bad_json_once_then_fails_loudly():
    client = FakeClient(["not json", _reply(3, 3), _reply(3, 3)])
    out = ev.judge_pair(client, _judge_case(), "x", "y", "v4", "base")
    assert out["winner"] == "tie" and len(client.calls) == 3
    with pytest.raises(ValueError):
        ev.judge_pair(FakeClient(["bad", "bad", "bad"]), _judge_case(), "x", "y", "v4", "base")   # 최초 1회 + 재시도 2회


@pytest.mark.parametrize("bad", [{"A": {}, "B": {}}, json.loads(_reply(6, 3)), json.loads(_reply(0, 3))])
def test_parse_judge_reply_rejects_missing_keys_and_out_of_range_scores(bad):
    with pytest.raises(ValueError):
        ev.parse_judge_reply(json.dumps(bad))


def test_summarize_judge_reports_means_and_win_rates():
    def r(v4, base):
        return {"scores": {"v4": {k: v4 for k in ev.JUDGE_KEYS}, "base": {k: base for k in ev.JUDGE_KEYS}},
                "winner": "v4" if v4 > base else "base" if base > v4 else "tie"}
    s = ev.summarize_judge([r(4, 2), r(3, 3), r(2, 4), r(5, 1)], "v4", "base")
    assert s["n"] == 4 and s["wins"] == {"v4": 2, "base": 1, "tie": 1}
    assert s["mean"]["v4"]["accuracy"] == pytest.approx(3.5) and s["mean"]["base"]["accuracy"] == pytest.approx(2.5)
    assert s["win_rate"] == {"v4": 0.5, "base": 0.25, "tie": 0.25} and s["pass_vs_base"] is True


def test_agreement_counts_matching_judgements(tmp_path):
    a, b = _pair()
    sheet, key = ev.make_blind_sheet(a, b, "base", "v4", seed=3)
    # 사람: 모든 문항에서 v4 선호. Judge: 앞 8문항 v4, 뒤 2문항 base
    human = {no: ("1" if key[no]["1"] == "v4" else "2") for no in key}
    judge = {f"F{i}": ("v4" if i <= 8 else "base") for i in range(1, 11)}
    ids = {no: f"F{no}" for no in key}
    res = ev.agreement(human, key, judge, ids)
    assert res == {"matched": 8, "total": 10, "trust_judge": True}
    judge_worse = {f"F{i}": ("v4" if i <= 7 else "base") for i in range(1, 11)}
    assert ev.agreement(human, key, judge_worse, ids)["trust_judge"] is False


def test_load_api_key_reads_env_and_never_echoes_it(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(ev, "ENV_FILE", Path("/nonexistent/.env"))
    with pytest.raises(RuntimeError) as e:
        ev.load_api_key()
    assert "OPENAI_API_KEY" in str(e.value) and ".env" in str(e.value)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
    assert ev.load_api_key() == "sk-secret-value"


def test_judge_cli_does_not_call_the_api_without_confirmation(tmp_path, monkeypatch, capsys):
    rows = [_row("final", f"F{i:02d}", True, answer=f"a{i}", served=f"a{i}") for i in range(1, 3)]
    for name in ("base", "v4"):
        ev.save_results(rows, ev.summarize(rows), name, tmp_path)
    monkeypatch.setattr(ev, "EVAL_DIR", tmp_path)
    monkeypatch.setattr(ev, "make_client", lambda: pytest.fail("확인 없이 API 클라이언트를 만들었다"))
    monkeypatch.setattr("builtins.input", lambda *_: "n")
    ev.main(["--judge", "base", "v4", "--judge-sets", "final"])
    assert "호출 4회" in capsys.readouterr().out                                                   # 2문항 x 2순서


def test_judge_dry_run_writes_prompts_without_client(tmp_path, monkeypatch):
    rows = [_row("final", "F01", True, answer="a", served="a")]
    for name in ("base", "v4"):
        ev.save_results(rows, ev.summarize(rows), name, tmp_path)
    monkeypatch.setattr(ev, "EVAL_DIR", tmp_path)
    monkeypatch.setattr(ev, "make_client", lambda: pytest.fail("dry-run은 API를 부르지 않는다"))
    ev.main(["--judge", "base", "v4", "--judge-sets", "final", "--judge-dry-run"])
    dumped = [json.loads(l) for l in (tmp_path / "judge_base_vs_v4.dryrun.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(dumped) == 2 and all("messages" in d for d in dumped)


def test_judge_cli_fails_clearly_when_results_share_no_cases(tmp_path, monkeypatch):
    for name, id_ in (("base", "F01"), ("v4", "F02")):
        rows = [_row("final", id_, True)]
        ev.save_results(rows, ev.summarize(rows), name, tmp_path)
    monkeypatch.setattr(ev, "EVAL_DIR", tmp_path)
    with pytest.raises(SystemExit):
        ev.main(["--judge", "base", "v4", "--judge-sets", "final", "--yes"])


# --- 수동 판정(자동 코드의 빈틈) ----------------------------------------------------------------------


def _model_rows(model, answers):
    return [_row("compare", i, True, answer=a, model=model) for i, a in answers.items()]


def test_review_sheet_mixes_models_dedupes_and_hides_names():
    by_model = {"base": _model_rows("base", {"M03": "사유는 신용 때문입니다.", "M05": "수수료는 없습니다."}),
                "v3": _model_rows("v3", {"M03": "사유는 조회되지 않습니다.", "M05": "수수료는 없습니다."}),
                "v4": _model_rows("v4", {"M03": "사유는 조회되지 않습니다.", "M05": "상담원에게 확인해 주세요."})}
    sheet, key = ev.make_review_sheet(by_model, ["M03", "M05"], sets=("compare",), seed=1)
    assert len(sheet) == 4                                            # 같은 답은 합친다: M03 2개, M05 2개
    text = json.dumps(sheet, ensure_ascii=False)
    assert "base" not in text and "v3" not in text and "v4" not in text
    shared = next(s for s in sheet if s["answer"] == "수수료는 없습니다.")
    assert sorted(key[shared["no"]]["who"]) == [["base", "compare", "M05"], ["v3", "compare", "M05"]]
    assert sheet == ev.make_review_sheet(by_model, ["M03", "M05"], sets=("compare",), seed=1)[0]


def test_apply_manual_flags_counts_fabricated_as_failure_and_reports_borderline_both_ways():
    rows = [_row("compare", "M03", True, model="v4"), _row("compare", "M05", True, model="v4"), _row("compare", "M07", True, model="v4")]
    flags = {("v4", "compare", "M03"): "fabricated", ("v4", "compare", "M05"): "borderline", ("v4", "compare", "M07"): "ok"}
    ev.apply_manual_flags(rows, flags)
    s = ev.summarize(rows)
    assert s["compare"]["rule"] == 1.0                                   # 자동 채점은 그대로
    assert s["compare"]["rule_reviewed"] == pytest.approx(2 / 3)          # 경계선은 통과로 본 값
    assert s["compare"]["rule_reviewed_strict"] == pytest.approx(1 / 3)   # 경계선을 실패로 본 값
    assert s["compare"]["n_borderline"] == 1


def test_main_prints_no_summary_by_default_and_saves(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ev, "EVAL_DIR", tmp_path)
    monkeypatch.setattr(ev.llm, "generate", lambda model, messages, **o: GOOD)
    ev.main(["--name", "x", "--sets", "final", "--limit", "2"])
    out = capsys.readouterr().out
    assert (tmp_path / "x.jsonl").exists() and '"rule"' not in out                   # 요약표를 미리 보지 않는다(공용틀 12-2)
    ev.main(["--name", "y", "--sets", "final", "--limit", "1", "--show-summary"])
    assert '"rule"' in capsys.readouterr().out


def test_judge_limit_restricts_the_number_of_cases(tmp_path, monkeypatch):
    rows = [_row("final", f"F{i:02d}", True, answer="a", served="a") for i in range(1, 4)]
    for name in ("base", "v4"):
        ev.save_results(rows, ev.summarize(rows), name, tmp_path)
    monkeypatch.setattr(ev, "EVAL_DIR", tmp_path)
    monkeypatch.setattr(ev, "make_client", lambda: pytest.fail("dry-run은 API를 부르지 않는다"))
    ev.main(["--judge", "base", "v4", "--judge-sets", "final", "--judge-dry-run", "--judge-limit", "2"])
    dumped = (tmp_path / "judge_base_vs_v4.dryrun.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(dumped) == 4


def test_compare_applies_flags_by_result_name_not_ollama_model_name(tmp_path, monkeypatch, capsys):
    # 결과 행의 model은 Ollama 모델명(cs-loan-v3)이지만 판정 키는 결과 이름(v3)을 쓴다 — 이름이 어긋나면 판정이 조용히 무시된다
    for name in ("base", "v3"):
        rows = [_row("compare", "M07", True, model=f"cs-loan-{name}", answer="정확한 처리 시간은 제가 바로 안내해 드리기 어렵습니다.")]
        ev.save_results(rows, ev.summarize(rows), name, tmp_path)
    key = {"1": {"who": [["v3", "compare", "M07"]]}}
    (tmp_path / "review_key.json").write_text(json.dumps(key), encoding="utf-8")
    flags = tmp_path / "flags.json"
    flags.write_text(json.dumps({"1": {"verdict": "borderline", "note": "x"}}), encoding="utf-8")
    monkeypatch.setattr(ev, "EVAL_DIR", tmp_path)
    ev.compare(["base", "v3"], flags)
    out = capsys.readouterr().out
    v3_line = next(l for l in out.splitlines() if l.startswith("| v3 | compare |"))
    assert v3_line.rstrip().endswith("| 100% | 0% | 1 |")          # 경계선을 통과로 보면 100%, 실패로 보면 0%, 경계선 1건
    assert next(l for l in out.splitlines() if l.startswith("| base | compare |")).rstrip().endswith("| - | - | - |")   # 판정 파일에 없는 모델은 '-'



def test_apply_manual_flags_prefers_the_given_name():
    rows = [_row("compare", "M07", True, model="cs-loan-v3")]
    ev.apply_manual_flags(rows, {("v3", "compare", "M07"): "fabricated"}, name="v3")
    assert rows[0]["manual"] == "fabricated"


# --- 결정 반영·서비스 설정 반복·결함 비교 --------------------------------------------------------------


def test_decided_borderline_is_ok_but_the_literal_reading_is_reported_alongside():
    rows = [_row("compare", "M07", True, model="v3"), _row("compare", "M03", True, model="v3")]
    flags = {("v3", "compare", "M07"): ("ok", True), ("v3", "compare", "M03"): ("ok", False)}   # (판정, 글자 기준으로는 hit)
    ev.apply_manual_flags(rows, flags)
    s = ev.summarize(rows)["compare"]
    assert s["rule_reviewed"] == 1.0 and s["rule_literal"] == 0.5 and s["n_borderline"] == 0


def test_load_flags_reads_the_literal_marker(tmp_path):
    (tmp_path / "k.json").write_text(json.dumps({"1": {"who": [["v3", "compare", "M07"]]}}), encoding="utf-8")
    (tmp_path / "f.json").write_text(json.dumps({"1": {"verdict": "ok", "literal": "hit", "note": "n"}}), encoding="utf-8")
    assert ev.load_flags(tmp_path / "f.json", tmp_path / "k.json") == {("v3", "compare", "M07"): ("ok", True)}


def test_compare_shows_dash_for_models_without_manual_review(tmp_path, monkeypatch, capsys):
    for name in ("v1", "v3"):
        rows = [_row("compare", "M07", True, model=f"cs-loan-{name}", answer=REFUSAL, served=REFUSAL)]
        ev.save_results(rows, ev.summarize(rows), name, tmp_path)
    (tmp_path / "review_key.json").write_text(json.dumps({"1": {"who": [["v3", "compare", "M07"]]}}), encoding="utf-8")
    (tmp_path / "flags.json").write_text(json.dumps({"1": {"verdict": "ok", "note": ""}}), encoding="utf-8")
    monkeypatch.setattr(ev, "EVAL_DIR", tmp_path)
    ev.compare(["v1", "v3"], tmp_path / "flags.json")
    out = capsys.readouterr().out
    assert next(l for l in out.splitlines() if l.startswith("| v1 | compare |")).rstrip().endswith("| - | - | - |")
    assert next(l for l in out.splitlines() if l.startswith("| v3 | compare |")).rstrip().endswith("| 100% | 100% | 0 |")


def test_service_options_leave_temperature_to_the_modelfile():
    assert "temperature" not in ev.SERVICE_OPTIONS and ev.SERVICE_OPTIONS["num_predict"] == ev.GENERATION_OPTIONS["num_predict"]


def test_generate_answers_repeats_and_numbers_reps():
    seen = []
    cases = [_case(id="A", expect=["date"], messages=[{"role": "user", "content": "q"}])]
    rows = ev.generate_answers(cases, "cs-loan-v3", generate=lambda m, msgs, **o: seen.append(o) or GOOD,
                               progress=lambda *_: None, options=ev.SERVICE_OPTIONS, reps=3)
    assert [r["rep"] for r in rows] == [1, 2, 3] and seen == [ev.SERVICE_OPTIONS] * 3
    assert "rep" not in ev.generate_answers(cases, "cs-loan-v3", generate=lambda *a, **k: GOOD, progress=lambda *_: None)[0]


def test_review_key_and_flags_follow_the_rep_of_each_sample():
    rows = [_row("compare", "M07", True, model="cs-loan-v3", rep=1, answer="a"), _row("compare", "M07", True, model="cs-loan-v3", rep=2, answer="b")]
    sheet, key = ev.make_review_sheet({"v3": rows}, ["M07"], sets=("compare",), seed=0)
    assert sorted(w[3] for k in key.values() for w in k["who"]) == [1, 2]
    by_answer = {s["answer"]: s["no"] for s in sheet}
    flags = {("v3", "compare", "M07", 2): ("fabricated", False), ("v3", "compare", "M07", 1): ("ok", False)}
    ev.apply_manual_flags(rows, flags, name="v3")
    assert [r["manual"] for r in rows] == ["ok", "fabricated"] and by_answer["a"] != by_answer["b"]


@pytest.mark.parametrize("text, expected", [
    ("제가 확인できません. 상담원에게 문의해 주세요.", True), ("판단은 어렵습니다. 判断은 상담원에게.", True), ("확인해 주세요.", False),
])
def test_cjk_mix_detector(text, expected):
    assert ev.has_cjk_mix(text) is expected


@pytest.mark.parametrize("text, loose, strict", [
    ("금리 관련 내용은 제가 안내드릴 수 있습니다. 상담원에게 문의해 주세요.", True, True),      # 뒤집힌 거절
    ("수수료 관련 내용은 제가 확인해 드릴 수 없습니다. 상담원에게 문의해 주세요.", True, False),    # 정상 거절("수 없")은 넓은 정의에만 걸린다
    ("연장은 제가 처리해 드리겠습니다. 상담원에게 확인해 주세요.", True, True),
    ("이 부분은 제가 안내드리기 어렵습니다. 상담원에게 확인해 주세요.", False, False),
    ("고객님의 {{loan_label}}은 처리해 드릴 수 있습니다.", False, False),                           # 상담원 안내가 없으면 거절문이 아니다
])
def test_flipped_refusal_definitions(text, loose, strict):
    assert ev.flipped_refusal(text) is loose and ev.flipped_refusal(text, strict=True) is strict


def test_refusal_only_means_agent_referral_without_any_fact():
    assert ev.refusal_only("이 부분은 제가 안내드리기 어렵습니다. 상담원에게 확인해 주세요.")
    assert not ev.refusal_only("{{extendable_status}} 자세한 사항은 상담원에게 확인해 주세요.")
    assert not ev.refusal_only("만기일은 2027-03-31입니다. 상담원에게 확인해 주세요.")
    assert not ev.refusal_only("고객님의 {{loan_label}} 남은 원금은 {{principal_remaining}}입니다.")


def test_normal_questions_are_basic_and_combined_types():
    ids = {c["id"] for c in ev.load_cases(["compare", "final"]) if ev.is_normal(c)}
    assert {"K14", "K15", "K12", "M02", "M09", "M10", "F01", "F02", "F03"} <= ids
    assert not ids & {"K01", "K06", "M03", "M05", "F05"}


def test_defect_table_counts_per_model():
    def r(id_, answer, rule=True, valid=True, forb=(), manual=None, cat="기본"):
        row = _row("compare", id_, rule, answer=answer, category=cat, valid=valid)
        row["score"]["valid"] = valid
        row["score"]["forbidden"] = list(forb)
        if manual:
            row["manual"] = manual
        return row
    rows = {"v3": [r("K14", "금리는 제가 안내드릴 수 있습니다. 상담원에게 확인해 주세요.", rule=False),        # 뒤집힌 거절 + 과다 거절(정상 질문)
                   r("M07", "확인できません 상담원에게", rule=False, valid=False, cat="기간"),                  # 일본어 혼입
                   r("M03", "사유는 신용 때문입니다.", cat="사유", manual="fabricated")],                       # 수동으로 지어냄
            "v4": [r("K14", "고객님의 {{loan_label}} 남은 원금은 {{principal_remaining}}입니다.")]}
    t = ev.defect_table(rows, normal_ids={"K14"})
    assert t["v3"] == {"n": 3, "fabricated": 1, "blocked": 1, "cjk": 1, "flipped_loose": 1, "flipped_strict": 1,
                       "normal_n": 1, "over_refusal": 1}
    assert t["v4"]["n"] == 1 and t["v4"]["fabricated"] == t["v4"]["cjk"] == t["v4"]["over_refusal"] == 0


# --- 반복 결과 보고·재채점·M08 오탐 -------------------------------------------------------------------


def test_no_affirm_rows_do_not_count_the_no_direction_of_a_correction_as_forbidden():
    case = _case(must=["date", "no_affirm", "polite"], record=["explicit_no"])
    s = ev.score(case, "아니요, 고객님의 {{loan_label}} 만기일은 2027-03-31입니다.")
    assert s["forbidden"] == [] and s["rule"]                                    # 정정의 "아니요"는 위반이 아니다
    other = ev.score(_case(expect=[]), "아니요, 고객님의 {{loan_label}} 만기일은 2027-03-31입니다.")
    assert other["forbidden"] == ["no_direction"]                                # 다른 문항에서는 그대로 위반
    committed = ev.score(case, "연장 신청을 접수해 드리겠습니다. 만기일은 2027-03-31입니다.")
    assert "no_commit" in committed["forbidden"]                                 # 처리 약속은 M08에서도 위반


def test_saved_rows_are_rescored_with_the_current_rules_on_load(tmp_path, monkeypatch):
    stale = _row("compare", "M08", False, answer="아니요, 고객님의 {{loan_label}} 만기일은 2027-03-31입니다.", model="cs-loan-v4")
    stale["score"]["forbidden"] = ["no_direction"]
    stale["served"] = stale["answer"]
    ev.save_results([stale], ev.summarize([stale]), "old", tmp_path)
    monkeypatch.setattr(ev, "EVAL_DIR", tmp_path)
    [row] = ev._load_rows("old")
    assert row["score"]["forbidden"] == [] and row["score"]["rule"] and row["score_final"]["rule"]
    assert row["model"] == "cs-loan-v4"


def test_type_groups_dedupe_ids_and_compare_counts_repeats(tmp_path, monkeypatch, capsys):
    assert ev.type_groups([{"category": "수수료", "id": "K10"}, {"category": "수수료", "id": "M05"}, {"category": "수수료", "id": "K10"}]) == {"수수료": ["K10", "M05"]}
    answers = {1: "수수료에 대한 자세한 안내는 상담원을 통해 확인해 주세요.", 2: "금리는 상담원을 통해 확인해 주세요.", 3: "수수료 관련 내용은 제가 확인해 드릴 수 없습니다. 상담원에게 문의해 주세요."}
    rows = [_row("compare", "K10", ok, rep=i, category="수수료", answer=answers[i], served=answers[i]) for i, ok in ((1, True), (2, False), (3, True))]
    ev.save_results(rows, ev.summarize(rows), "svc", tmp_path)
    monkeypatch.setattr(ev, "EVAL_DIR", tmp_path)
    ev.compare(["svc"])
    out = capsys.readouterr().out
    assert "| 수수료 | K10 | 2/3 |" in out                                      # 문항은 한 번만, 통과는 샘플 수로
    assert out.count("### compare/K10") == 1


def test_refusal_in_the_form_eoryeowo_is_not_a_commitment():
    # "…바로 안내해 드리기 어려워, 상담원에게 확인해 주시기 바랍니다"는 거절이다. "어려워"가 거절 표현으로 안 잡혀 처리 약속으로 오탐됐었다(사후 조정)
    text = "정확한 처리 시간 내용은 제가 바로 안내해 드리기 어려워, 상담원에게 확인해 주시기 바랍니다."
    assert ev.codes(text, LOAN_OK)["no_commit"] is True
    assert ev.codes("연장은 제가 직접 처리해 드리기 때문에 걱정하지 않으셔도 됩니다.", LOAN_OK)["no_commit"] is False   # 진짜 약속은 그대로 잡는다


def test_judge_limit_summarizes_only_the_cases_already_judged(tmp_path, monkeypatch, capsys):
    rows = [_row("final", f"F{i:02d}", True, answer=f"a{i}", served=f"a{i}") for i in range(1, 4)]
    for name in ("base", "v4"):
        ev.save_results(rows, ev.summarize(rows), name, tmp_path)
    monkeypatch.setattr(ev, "EVAL_DIR", tmp_path)
    client = FakeClient([_reply(4, 2), _reply(2, 4)])                # 시험 호출: 1문항 x 2순서
    monkeypatch.setattr(ev, "make_client", lambda: client)
    ev.main(["--judge", "base", "v4", "--judge-sets", "final", "--judge-limit", "1", "--yes"])   # 예전에는 KeyError로 죽었다
    summary = json.loads((tmp_path / "judge_base_vs_v4.summary.json").read_text(encoding="utf-8"))
    assert summary["n"] == 1 and len(client.calls) == 2
    assert len((tmp_path / "judge_base_vs_v4.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_judge_limit_is_a_total_cap_that_counts_cases_already_judged(tmp_path, monkeypatch):
    rows = [_row("final", f"F{i:02d}", True, answer=f"a{i}", served=f"a{i}") for i in range(1, 5)]
    for name in ("base", "v4"):
        ev.save_results(rows, ev.summarize(rows), name, tmp_path)
    monkeypatch.setattr(ev, "EVAL_DIR", tmp_path)
    client = FakeClient([_reply(4, 2), _reply(2, 4)] * 3)
    monkeypatch.setattr(ev, "make_client", lambda: client)
    ev.main(["--judge", "base", "v4", "--judge-sets", "final", "--judge-limit", "2", "--yes"])
    assert len(client.calls) == 4                                       # 2문항 x 2순서
    ev.main(["--judge", "base", "v4", "--judge-sets", "final", "--judge-limit", "2", "--yes"])
    assert len(client.calls) == 4                                       # 같은 상한으로 다시 실행해도 API를 더 부르지 않는다
    ev.main(["--judge", "base", "v4", "--judge-sets", "final", "--judge-limit", "3", "--yes"])
    assert len(client.calls) == 6                                       # 상한을 올렸을 때만 1문항(2회) 추가


# --- Judge 오류·재시도 제어 -------------------------------------------------------------------------


class FlakyClient(FakeClient):
    """create()가 지정한 횟수만큼 예외를 던진 뒤 정상 응답을 준다."""

    def __init__(self, fail_times, replies):
        super().__init__(replies)
        self.fail_times = fail_times

    def create(self, **kw):
        if self.fail_times > 0:
            self.fail_times -= 1
            self.calls.append(kw)
            raise RuntimeError("일시 오류")
        return super().create(**kw)


def test_api_error_is_retried_at_most_twice_per_call(monkeypatch):
    monkeypatch.setattr(ev, "_sleep", lambda *_: None)
    ev.reset_judge_stats()
    ok = FlakyClient(2, [_reply(3, 3), _reply(3, 3)])
    ev.judge_pair(ok, _judge_case(), "x", "y", "v4", "base")
    assert ev.JUDGE_STATS["retries"] == 2 and len(ok.calls) == 4               # 첫 호출은 2번 실패 후 3번째에 성공(재시도 2회)
    with pytest.raises(ValueError):
        ev.judge_pair(FlakyClient(3, []), _judge_case(), "x", "y", "v4", "base")
    assert ev.JUDGE_STATS["retries"] == 4                                        # 실패한 호출도 재시도는 2회까지만


def test_openai_client_is_built_without_hidden_sdk_retries(monkeypatch):
    seen = {}
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    import openai
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: seen.update(kw) or object())
    ev.make_client()
    assert seen["max_retries"] == 0 and seen["timeout"] > 0                      # SDK가 몰래 재시도하지 않게 한다


def test_judge_stops_after_three_consecutive_case_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ev, "_sleep", lambda *_: None)
    rows = [_row("final", f"F{i:02d}", True, answer=f"a{i}", served=f"a{i}") for i in range(1, 8)]
    for name in ("base", "v4"):
        ev.save_results(rows, ev.summarize(rows), name, tmp_path)
    monkeypatch.setattr(ev, "EVAL_DIR", tmp_path)
    client = FlakyClient(10_000, [])
    monkeypatch.setattr(ev, "make_client", lambda: client)
    ev.main(["--judge", "base", "v4", "--judge-sets", "final", "--yes"])
    assert len(client.calls) == 3 * 3                                            # 3문항 x (최초 1 + 재시도 2)에서 멈춘다
    assert "연속 오류 3회" in capsys.readouterr().out


def test_judge_continues_after_a_single_failed_case_and_saves_each_case_at_once(tmp_path, monkeypatch):
    monkeypatch.setattr(ev, "_sleep", lambda *_: None)
    rows = [_row("final", f"F{i:02d}", True, answer=f"a{i}", served=f"a{i}") for i in range(1, 4)]
    for name in ("base", "v4"):
        ev.save_results(rows, ev.summarize(rows), name, tmp_path)
    monkeypatch.setattr(ev, "EVAL_DIR", tmp_path)

    class FirstCaseFails(FakeClient):                                            # 첫 문항(F01)의 답변 a1이 든 호출만 실패
        def create(self, **kw):
            self.calls.append(kw)
            if "a1" in kw["messages"][-1]["content"]:
                raise RuntimeError("오류")
            return type("R", (), {"choices": [type("C", (), {"message": type("M", (), {"content": _reply(4, 2)})()})()]})()

    monkeypatch.setattr(ev, "make_client", lambda: FirstCaseFails([]))
    ev.main(["--judge", "base", "v4", "--judge-sets", "final", "--yes"])
    saved = [json.loads(l) for l in (tmp_path / "judge_base_vs_v4.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [d["id"] for d in saved] == ["F02", "F03"]                            # 실패한 문항 뒤에도 계속 진행, 성공분은 즉시 저장
    summary = json.loads((tmp_path / "judge_base_vs_v4.summary.json").read_text(encoding="utf-8"))
    assert summary["api"]["case_errors"] == 1 and summary["api"]["retries"] == 2  # 실패 문항 1개(재시도 2회)
