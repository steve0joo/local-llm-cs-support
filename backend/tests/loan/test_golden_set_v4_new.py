"""training/loan/golden_set_v4_new.jsonl — 비교용 새 10문항 M01~M10 (2026-09-30, 사용자 작성, 모델 응답을 보기 전에 저장·고정).

사용자가 외부 Claude 대화의 초안을 참고해 다듬은 문항이다(시드 작성과는 독립적). 문항·필수·기록만은 고치지 않는다(해시 고정).
시드·기존 세트와 유사도 0.75 미만이어야 하지만, **근접 사례는 기각하지 않고 보고한다**: 아래 KNOWN_NEAR에 최고 유사도를 고정했다.
"""
import collections
import difflib
import hashlib
import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "training" / "loan"
NEW_SHA256 = "d1008b3d38bcdc9ce2b17a3b920d24aef995fd96615d2db1d0b1a05bf1a8a286"
CODES = {"no_fabrication", "no_direction", "no_cause_claim", "no_commit", "no_echo_token", "polite", "slot_extend", "slot_principal",
         "date", "refer", "topic_fee", "topic_rate", "no_affirm", "explicit_no"}
# 0.75 이상이거나 같은 세트 안에서 같은 유형인 근접 사례(보고용, 기각하지 않음). 값은 최고 유사도 상한
KNOWN_NEAR = {
    "M08": 0.83,  # 시드 "제 대출 만기가 2027-03-31 맞나요?"(정답이 반대: 시드는 맞는 날짜 확인, M08은 틀린 날짜 정정)
}


def _load(name):
    return [json.loads(l) for l in (ROOT / name).read_text(encoding="utf-8").splitlines() if l.strip()]


def _module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_v2 = _module("v2_golden_new", "test_golden_set.py")
ROWS = _load("golden_set_v4_new.jsonl")


def _norm(t):
    return re.sub(r"[\s?.!,]", "", t)


def test_file_is_frozen_by_hash():
    assert hashlib.sha256((ROOT / "golden_set_v4_new.jsonl").read_bytes()).hexdigest() == NEW_SHA256


def test_rows_are_the_users_and_well_formed():
    assert [r["id"] for r in ROWS] == [f"M{i:02d}" for i in range(1, 11)]
    for r in ROWS:
        assert r["source"] == "user" and r["tag"] == "compare-v4-new" and r["model_eval"] is True
        assert r["customer"] in {"C002", "C003"} and r["question"].strip() and r["history"] == []
        assert r["must"] and "polite" in r["must"] and set(r["must"]) | set(r["record"]) <= CODES, r


def test_customer_split_makes_k20_plus_new_fifteen_fifteen():
    new = collections.Counter(r["customer"] for r in ROWS)
    k = collections.Counter(r["customer"] for r in _load("golden_set_v4_compare.jsonl"))
    assert new == {"C002": 4, "C003": 6}
    assert k + new == {"C002": 15, "C003": 15}


def test_required_codes_follow_the_users_table():
    by_id = {r["id"]: r for r in ROWS}
    assert by_id["M02"]["must"] == ["date", "polite"]
    assert by_id["M05"]["must"] == ["no_fabrication", "topic_fee", "polite"]
    assert by_id["M08"]["must"] == ["date", "no_affirm", "polite"] and by_id["M08"]["record"] == ["explicit_no"]
    assert by_id["M09"]["must"] == ["slot_principal", "no_echo_token", "polite"]
    assert by_id["M10"]["must"] == ["slot_principal", "slot_extend", "polite"]
    assert all(by_id[i]["record"] == ["refer"] for i in ("M01", "M03", "M04", "M05", "M06", "M07"))
    assert by_id["M03"]["must"] == ["no_fabrication", "slot_extend", "polite"]


def test_questions_do_not_overlap_seeds_or_other_sets_beyond_the_known_near_cases():
    seeds = _load("manual_seed.jsonl") + _load("manual_seed_v4.jsonl")
    pool = ([_norm(s["question"]) for s in seeds] + [_norm(s["follow_up_question"]) for s in seeds if s["follow_up_question"]]
            + [_norm(r["question"]) for f in ("golden_set_risk.jsonl", "golden_set.jsonl", "golden_set_v3.jsonl",
                                               "golden_set_final_v4.jsonl", "golden_set_v4_compare.jsonl") for r in _load(f)]
            + [_norm(d) for d in _v2.DEV_QUESTIONS])
    for row in ROWS:
        q = _norm(row["question"])
        assert q not in pool, row["question"]
        best = max(difflib.SequenceMatcher(None, q, o).ratio() for o in pool)
        assert best < KNOWN_NEAR.get(row["id"], 0.75), (row["question"], round(best, 2))
    assert max(difflib.SequenceMatcher(None, _norm(next(r for r in ROWS if r["id"] == "M08")["question"]), o).ratio() for o in pool) >= 0.75


def test_composition_matches_the_planned_types():
    types = {r["id"]: r["type"] for r in ROWS}
    assert types["M01"] == "서류" and types["M03"] == "사유" and types["M04"] == "금리" and types["M07"] == "기간"
    assert types["M05"] == "수수료"        # K10과 같은 유형 — 결과 표에서 묶어 보여 준다
    assert types["M06"] == types["M08"] == "사실확인"
    assert {r["register"] for r in ROWS} == {"존댓말", "반말"}


def test_manual_review_criteria_file_is_frozen():
    path = ROOT.parents[2] / "docs" / "agent-loan" / "MANUAL_REVIEW_CRITERIA.md"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == "0a0b3ffff6ae878583fa1366a09ec9177eeb630e2534e4155c59ba47e9b1bf46"
