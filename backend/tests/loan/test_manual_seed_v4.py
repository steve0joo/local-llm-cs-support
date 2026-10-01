"""manual_seed_v4.jsonl (2026-09-30). v3 평가(EVAL_CRITERIA_v3)에서 확인한 결함을 시드로 고친 버전.

v3 파일(manual_seed.jsonl, sha256 5773891820c3…)은 그대로 두고, 같은 생성기에 --version v4 를 주어 새 파일로 만든다.
결함: 연체·기한 초과·상환액·갈아타기 추측, 처리 요청에서 "직접 처리해 드린다", 조건 질문에 연장 슬롯 누락,
"손해/이득"의 근거 없는 인과, 수수료↔금리 혼동, 거절 문형 "~ㄹ 수 있/없"이 뒤집혀 사실·약속처럼 되는 문제.
"""
import collections
import difflib
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from app.agents.loan.validate import is_valid_output
from training.loan.prepare import is_clean

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND / "training" / "loan"
V3_SHA256 = "5773891820c3df4659bf928c32f0a4fa2804879ccc9010448a6fa5e97ebe8832"


def _load(name):
    return [json.loads(l) for l in (ROOT / name).read_text(encoding="utf-8").splitlines() if l.strip()]


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_v2 = _module("v2_golden_tests", Path(__file__).with_name("test_golden_set.py"))
_final = _module("final_v4_tests", Path(__file__).with_name("test_golden_set_final_v4.py"))
SEEDS = _load("manual_seed_v4.jsonl")
NEW = [s for s in SEEDS if s["source_id"].startswith("manual-v4")]
KEPT = [s for s in SEEDS if not s["source_id"].startswith("manual-v4")]


def _kind(s):
    return re.sub(r"-\d+$", "", s["source_id"])[7:]


def _norm(t):
    return re.sub(r"[\s?.!,]", "", t)


def _has_agent(s):  # 상담원 안내가 든 행 = 거절 행
    return "상담원" in s["output"]


def _is_pure_refusal(s):  # 조회 사실(슬롯·날짜) 없이 상담원 안내만 하는 행
    return _has_agent(s) and "{{" not in s["output"] and not re.search(r"\d{4}-\d{2}-\d{2}", s["output"])


def test_size_and_refusal_share_are_guarded_but_not_the_verdict():
    """과다 거절의 판정은 시드 비율이 아니라 "정상 질문 통과율이 v3보다 떨어지지 않는가"다(EVAL_CRITERIA_v4.md).
    연장 불가 정상 답변에도 v3처럼 "상담원 확인" 꼬리를 붙이므로 상담원 안내 행 비율은 45%를 조금 넘을 수 있다.
    여기서는 폭주만 막는다: 상담원 안내 행 ≤ 52%(v3 48%), 사실 없는 순수 거절 ≤ 20%."""
    assert 400 <= len(SEEDS) <= 470
    assert sum(_has_agent(s) for s in SEEDS) / len(SEEDS) <= 0.52
    assert sum(_is_pure_refusal(s) for s in SEEDS) / len(SEEDS) <= 0.20


def test_unextendable_normal_answers_keep_the_same_agent_tail_as_v3():
    """v3와 일관: 연장 불가 정상 답변(연장 슬롯을 주는 답)은 끝에 상담원 확인 꼬리를 붙인다."""
    tail = "자세한 사항은 상담원에게 확인해 주세요."
    rows = [s for s in NEW if _kind(s) in ("v4tone", "v4mask") and not s["extendable"] and s["output"].count("{{extendable_status}}")]
    assert rows and all(tail in s["output"] for s in rows), [s["output"] for s in rows if tail not in s["output"]]


def test_normal_answers_avoid_the_awkward_lookup_phrasing():
    """"확인 결과 조회된 …", "…의 만기 조회 결과는 …입니다" 같은 어색한 문형(v4 정상 답변 문구 풀 개선)."""
    for s in SEEDS:
        for field in ("output", "answer"):
            assert not re.search(r"조회된 |조회 결과|조회한 결과|조회했습니다", s[field]), (s["source_id"], s[field])


def test_duplicate_refusals_were_trimmed_and_new_rows_added():
    assert 305 <= len(KEPT) <= 325  # v3 350건에서 중복성 높은 거절 약 30건 정리
    kinds = collections.Counter(_kind(s) for s in NEW)
    need = {"v4range": 16, "v4request": 10, "v4cond": 8, "v4loss": 8, "v4feerate": 10, "v4combo": 4,
            "v4tone": 20, "v4mask": 20, "v4ctx": 20, "v4wrong": 6, "v4right": 4}
    for k, n in need.items():
        assert kinds[k] >= n, (k, kinds[k])


def test_refusal_phrasing_has_no_able_unable_or_handle_for_you():
    """"~ㄹ 수 있/없"은 모델이 뒤집으면 처리 약속이나 사실 단정이 된다(v3: "안내드릴 수 있습니다")."""
    for s in SEEDS:
        for field in ("output", "answer"):
            if "상담원" in s[field]:
                assert not re.search(r"수 있|수 없|처리해 드", s[field]), (s["source_id"], s[field])


def test_new_rows_avoid_verify_for_you_and_not_looked_up_phrasing():
    for s in NEW:
        assert not re.search(r"확인해 드|조회되지 않아", s["output"]), (s["source_id"], s["output"])


def test_range_and_loss_answers_state_no_consequences_or_reasons():
    for s in NEW:
        if _kind(s) in ("v4range", "v4loss", "v4combo"):
            assert not re.search(r"이자|벌금|법규|처분|가산", s["output"]), s["output"]
            assert "안내드리기 어렵습니다" in s["output"], s["output"]
        if _kind(s) == "v4loss":
            assert not re.search(r"금리|상환 방식|상환 계획|따라 다르", s["output"]), s["output"]  # v3 N14: 근거 없는 인과


def test_request_answers_say_it_is_out_of_scope_and_do_not_claim_handling():
    for s in NEW:
        if _kind(s) == "v4request":
            assert "도와드리는 범위가 아닙니다" in s["output"] and "상담원에게 확인해 주세요" in s["output"], s["output"]
            assert not re.search(r"직접|저희가|처리해|접수해|완료", s["output"].replace("연장 신청과 처리는", "")), s["output"]


def test_condition_answers_give_the_extension_slot():
    for s in NEW:
        if _kind(s) == "v4cond":
            assert "{{extendable_status}}" in s["output"] and "연장 조건" in s["output"], s["output"]  # v3 U15


def test_combo_answers_give_the_principal_slot_and_refuse_the_payment_amount():
    for s in NEW:
        if _kind(s) == "v4combo":
            assert "{{principal_remaining}}" in s["output"] and "안내드리기 어렵습니다" in s["output"], s["output"]


def test_fee_and_rate_answers_name_the_asked_topic_only():
    """수수료 질문에 금리로, 금리 질문에 수수료로 답하지 않는다(v3 N15, U06)."""
    rows = [s for s in NEW if _kind(s) == "v4feerate"]
    assert sum("수수료" in s["question"] for s in rows) >= 5 and sum("금리" in s["question"] for s in rows) >= 5
    for s in rows:
        if "수수료" in s["question"]:
            assert "수수료" in s["output"] and "금리" not in s["output"], s
        else:
            assert "금리" in s["question"] and "금리" in s["output"] and "수수료" not in s["output"], s


def test_new_normal_answers_do_not_refuse_facts_they_can_give():
    for s in NEW:
        if _kind(s) in ("v4tone", "v4mask", "v4ctx"):
            assert ("{{" in s["output"]) or re.search(r"\d{4}-\d{2}-\d{2}", s["output"]), s["output"]  # 사실(슬롯·날짜)을 준다


def test_masked_and_context_seeds_are_well_formed():
    masked = [s for s in NEW if _kind(s) == "v4mask"]
    assert len({t for s in masked for t in re.findall(r"\[[^\]]+_\d+\]", s["question"])}) >= 5
    for s in masked:
        assert re.search(r"\[[^\]]+_\d+\]", s["question"]) and not re.search(r"\[[^\]]+_\d+\]", s["output"]), s
    ctx = [s for s in NEW if _kind(s) == "v4ctx"]
    assert len({(s["question"], s["follow_up_question"]) for s in ctx}) == len(ctx)
    for s in ctx:
        assert s["answer"] and s["follow_up_question"] and s["output"] != s["answer"], s


@pytest.mark.parametrize("seed", SEEDS, ids=[s["source_id"] for s in SEEDS])
def test_every_seed_passes_validator_and_cleaning(seed):
    assert is_valid_output(seed["output"], maturity_date=seed["maturity_date"], extendable=seed["extendable"]), seed["output"]
    assert is_clean(seed), seed["output"]


def test_masking_is_stable_on_all_seed_text():
    from app.masking import mask

    for s in SEEDS:
        for field in ("question", "answer", "follow_up_question", "output"):
            assert mask(s[field]).masked_text == s[field], (s["source_id"], field)


def test_val_split_is_by_question_and_covers_new_kinds():
    val = [s for s in SEEDS if s.get("split") == "val"]
    train = [s for s in SEEDS if s.get("split", "train") == "train"]
    assert not {s["question"] for s in val} & {s["question"] for s in train}
    assert 0.08 <= len({s["question"] for s in val}) / len({s["question"] for s in SEEDS}) <= 0.2
    assert {"v4range", "v4tone", "v4mask", "v4ctx"} <= {_kind(s) for s in val}


def test_new_questions_stay_below_075_against_every_eval_set_except_short_common_ones():
    """0.75 기준: S/N/U/D, 기존 Golden Set(dev), 개발 질문, 최종 확인용 10문항(F, 겹침 검사에만 사용).
    짧고 흔한 질문(공백 뺀 8자 이하)이 넘는 경우는 기각하지 않고 보고한다."""
    risk = _load("golden_set_risk.jsonl")
    pool = (
        [_norm(r["question"]) for r in risk] + [_norm(g["question"]) for g in _v2.GOLDEN]
        + [_norm(g["question"]) for g in _load("golden_set_v3.jsonl")] + [_norm(d) for d in _v2.DEV_QUESTIONS]
        + [_norm(q) for q in _final.FINAL_QUESTIONS]
    )
    for s in NEW:
        q = _norm(s["question"])
        if len(q) <= 8:
            continue
        for other in pool:
            ratio = difflib.SequenceMatcher(None, q, other).ratio()
            assert q != other and ratio < 0.75, (s["question"], other, round(ratio, 2))


def test_v3_seed_file_is_reproduced_byte_for_byte_by_the_default_version(tmp_path):
    out = tmp_path / "v3.jsonl"
    subprocess.run([sys.executable, str(ROOT / "make_manual_seed.py"), "--out", str(out)], check=True, cwd=BACKEND,
                   capture_output=True)
    assert hashlib.sha256(out.read_bytes()).hexdigest() == V3_SHA256
    assert hashlib.sha256((ROOT / "manual_seed.jsonl").read_bytes()).hexdigest() == V3_SHA256


def test_v4_generation_is_deterministic(tmp_path):
    outs = []
    for i in range(2):
        out = tmp_path / f"v4_{i}.jsonl"
        subprocess.run([sys.executable, str(ROOT / "make_manual_seed.py"), "--version", "v4", "--out", str(out)],
                       check=True, cwd=BACKEND, capture_output=True)
        outs.append(out.read_bytes())
    assert outs[0] == outs[1] == (ROOT / "manual_seed_v4.jsonl").read_bytes()


def test_v4_criteria_file_states_the_over_refusal_rule_before_results():
    text = (BACKEND.parent / "docs" / "agent-loan" / "EVAL_CRITERIA_v4.md").read_text(encoding="utf-8")
    for must_have in ("과다 거절", "정상 질문", "100%", "320/320", "final-v4", "떨어지면 안 된다", "9문항 이상", "시드 비율", "5773891820c3", "지어낸 사실", "고정 해시", "알려진 한계", "꼬리", "a0fd1c43955c", "44a968ce08d5", "0c9a34895a52"):
        assert must_have in text, must_have


# 2026-09-30 사용자가 확정한 v4 시드·학습 데이터의 sha256. 시드를 바꾸면 이 테스트가 실패한다(새 이름으로 만들 것).
V4_FROZEN = {
    "training/loan/manual_seed_v4.jsonl": "3e586ec1bf98f89dce96ff3d51de60c049bcc9c111c2f3a8986241279316d448",
}


def test_v4_seed_file_matches_the_frozen_hash():
    for rel, sha in V4_FROZEN.items():
        assert hashlib.sha256((BACKEND / rel).read_bytes()).hexdigest() == sha, rel


def test_wrong_date_confirmations_are_corrected_with_an_explicit_no():
    """고객이 말한 만기일이 실제와 다르면 "아니요,"로 부정하고 실제 만기일로 정정한다(맞다고 확인하지 않는다)."""
    rows = [s for s in NEW if _kind(s) == "v4wrong"]
    assert len(rows) >= 6
    assert len({r["question"] for r in rows}) == len(rows)
    for s in rows:
        said = re.findall(r"\d{4}-\d{2}-\d{2}", s["question"])
        assert said and said[0] != s["maturity_date"], s  # 고객이 말한 날짜는 실제와 다르다
        assert re.search(r"맞|확인", s["question"]), s  # 날짜를 확인하는 질문
        assert s["output"].startswith("아니요,"), s["output"]
        assert s["maturity_date"] in s["output"] and said[0] not in s["output"], s["output"]  # 실제 날짜로 정정, 틀린 날짜는 되풀이하지 않는다
        assert "맞습니다" not in s["output"] and "네," not in s["output"], s["output"]


def test_right_date_confirmations_say_yes_with_the_actual_date():
    rows = [s for s in NEW if _kind(s) == "v4right"]
    assert len(rows) == 4 and len({r["question"] for r in rows}) == 4
    for s in rows:
        said = re.findall(r"\d{4}-\d{2}-\d{2}", s["question"])
        assert said == [s["maturity_date"]], s  # 고객이 말한 날짜 = 실제 만기일
        assert s["output"].startswith("네, 맞습니다.") and s["maturity_date"] in s["output"], s["output"]
        assert "조회" not in s["output"] and "아니요" not in s["output"], s["output"]


def test_yes_and_no_confirmations_are_both_present_for_date_questions():
    """맞는 날짜 확인 6건(v3 2건 + v4 4건) : 틀린 날짜 확인 8건(v3 암시적 2건 + v4 명시적 6건)."""
    rows = [s for s in SEEDS if re.search(r"\d{4}-\d{2}-\d{2}", s["question"]) and re.search(r"맞|확인", s["question"]) and not s["follow_up_question"]]
    right = [s for s in rows if re.findall(r"\d{4}-\d{2}-\d{2}", s["question"])[0] == s["maturity_date"]]
    wrong = [s for s in rows if s not in right]
    assert len(right) == 6 and len(wrong) == 8, (len(right), len(wrong))
    assert sum(s["output"].startswith("아니요,") for s in wrong) == 6


def test_no_prefix_is_only_used_for_wrong_date_confirmations():
    for s in SEEDS:
        if s["output"].startswith("아니요"):
            assert _kind(s) == "v4wrong", s
