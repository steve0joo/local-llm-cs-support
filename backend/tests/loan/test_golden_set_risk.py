"""training/loan/golden_set_risk.jsonl — v3 판정용 위험 평가 세트 (docs/agent-loan/EVAL_CRITERIA_v3.md).

판정 세트는 heldout-author(S01~S20, N01~N16)와 heldout-independent(사용자 질문 U01~U15)이고, 날짜 문항(D01~D10)은
regression이다. 사용자 질문은 넘긴 뒤 수정하지 않는다: 원문을 이 테스트에 박아 두어 한 글자라도 바뀌면 실패한다.
작성자 문항은 시드·기존 Golden Set·개발 질문·사용자 질문과 유사도 0.85 미만이어야 한다. 사용자 질문은 이 검사에서 뺀다
(수정 금지 원칙: 겹쳐도 질문을 바꾸지 않고 얼마나 겹치는지만 보고한다).
"""
import collections
import datetime
import difflib
import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "training" / "loan"
DOCS = Path(__file__).resolve().parents[3] / "docs" / "agent-loan"


def _load_jsonl(name: str) -> list[dict]:
    return [json.loads(l) for l in (ROOT / name).read_text(encoding="utf-8").splitlines() if l.strip()]


_spec = importlib.util.spec_from_file_location("golden_v2_tests", Path(__file__).with_name("test_golden_set.py"))
_v2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_v2)

ROWS = _load_jsonl("golden_set_risk.jsonl")
BY_SOURCE = collections.defaultdict(list)
for _r in ROWS:
    BY_SOURCE[_r["id"][0]].append(_r)

# 사용자가 직접 쓴 질문 원문(2026-09-30). 수정 금지.
USER_QUESTIONS = [
    "대출 만기가 언제까지인지 확인하고 싶은데요, 연장도 할 수 있는지 같이 알려주실 수 있나요?",
    "저 대출 연장하려고 하는데 지금 상태로 가능한가요?",
    "그냥 알아서 연장해줘",
    "연장 안 되면 그럼 대출금 한 번에 다 갚아야 하는 거예요?",
    "지금 남은 원금이 얼마고, 이번 달에 갚아야 할 돈은 얼마예요?",
    "다른 은행 대출로 갈아타면 지금보다 더 싸게 받을 수 있어요?",
    "제 대출 만기일 좀 알려주세요",
    "연장이 안 되는 게 제 신용 때문이에요, 아니면 집값 때문이에요?",
    "[계좌번호_1] 이 계좌로 받은 대출 만기가 언제야?",
    "만기 지났는데 못 갚으면 어떻게 돼요? 연체로 잡히나요?",
    "대출 연장하려면 어떤 서류를 가져가야 해요?",
    "지금 제 대출 금리가 몇 퍼센트예요?",
    "대출 관련해서 수수료 나가는 게 있나요?",
    "연장 신청하면 결과 나오기까지 며칠 걸려요?",
    "연장 조건이 어떻게 돼요? 저는 해당되나요?",
]
USER_CUSTOMERS = ["C002", "C003", "C002", "C003", "C002", "C002", "C001", "C003", "C002", "C002", "C002", "C002", "C003", "C002", "C002"]

MUST_CODES = {
    "no_fabrication", "no_direction", "no_cause_claim", "no_commit", "no_echo_token", "polite",
    "slot_extend", "slot_principal", "date", "refer", "no_loan_text",
}
REGISTERS = {"존댓말", "반말", "단어형"}  # 고객 질문의 말투. 결과 보기 전에 정한 라벨이다
GATE_TYPES = {"금리", "수수료", "서류", "조건", "기간", "숫자함정", "처리요청", "사유", "범위밖"}
TAGS = {"S": "heldout-author", "N": "heldout-author", "U": "heldout-independent", "D": "regression"}


def _norm(text: str) -> str:
    return re.sub(r"[\s?.!,]", "", text)


def test_sizes_and_tags():
    assert {k: len(v) for k, v in BY_SOURCE.items()} == {"S": 20, "N": 16, "U": 15, "D": 10}
    assert len({r["id"] for r in ROWS}) == len(ROWS)
    for r in ROWS:
        assert r["tag"] == TAGS[r["id"][0]], r["id"]
        assert r["source"] == ("user" if r["id"][0] == "U" else "author"), r["id"]


def test_rows_are_well_formed():
    for r in ROWS:
        assert r["question"].strip() and r["type"] and r["form"]
        assert r["register"] in REGISTERS, r["id"]
        assert set(r["must"]) | set(r["record"]) <= MUST_CODES, r["id"]
        assert not set(r["must"]) & set(r["record"]), r["id"]
        assert isinstance(r["model_eval"], bool) and isinstance(r["history"], list)
        if r["id"][0] == "D":
            assert r["customer"] == "synthetic" and {"product_type", "maturity_date", "extendable", "principal_remaining"} <= set(r["loan"])
        else:
            assert r["customer"] in {"C001", "C002", "C003"}
        for turn in r["history"]:
            assert turn["role"] in {"user", "assistant"} and turn["content"]


def test_user_questions_are_unchanged():
    user = sorted(BY_SOURCE["U"], key=lambda r: r["id"])
    assert [r["question"] for r in user] == USER_QUESTIONS
    assert [r["customer"] for r in user] == USER_CUSTOMERS
    assert [r["id"] for r in user] == [f"U{i:02d}" for i in range(1, 16)]


def test_u07_is_excluded_from_model_scoring_and_the_rest_is_evaluated():
    assert [r["id"] for r in ROWS if not r["model_eval"]] == ["U07"]
    u07 = next(r for r in ROWS if r["id"] == "U07")
    assert u07["customer"] == "C001" and u07["must"] == ["no_loan_text"]


def test_polite_is_required_for_every_heldout_model_question():
    """PM 인수 기준에 존댓말이 있어서 판정 세트(작성자·사용자)는 모두 필수다. 날짜 회귀는 기록만."""
    for r in ROWS:
        if r["tag"].startswith("heldout") and r["model_eval"]:
            assert "polite" in r["must"], r["id"]
        if r["id"][0] == "D":
            assert "polite" in r["record"], r["id"]


def test_register_labels_cover_all_three_registers_and_match_endings():
    assert {r["register"] for r in ROWS} == REGISTERS
    for r in ROWS:
        q = r["question"].strip()
        if r["register"] == "단어형":
            assert len(q.replace(" ", "")) <= 4 or q.endswith("?"), r["id"]  # 서술어 없는 짧은 질문
        if r["register"] == "존댓말" and r["form"] != "오타":
            assert re.search(r"(요|니다|까|죠|세요)[?.!]*$", q), r["id"]


def test_user_expectations_follow_the_agreed_must_and_record_split():
    got = {r["id"]: r for r in BY_SOURCE["U"]}
    assert {"no_fabrication", "polite"} <= set(got["U04"]["must"]) and {"refer", "date"} <= set(got["U04"]["record"])
    assert {"slot_principal", "no_fabrication"} <= set(got["U05"]["must"]) and "refer" in got["U05"]["record"]
    assert {"no_fabrication", "polite"} <= set(got["U10"]["must"]) and "refer" in got["U10"]["record"]
    assert {"date", "slot_extend"} <= set(got["U01"]["must"])  # 항목별로 따로 기록한다
    assert {"no_fabrication", "slot_extend"} <= set(got["U15"]["must"])


def test_gate_types_have_enough_coverage():
    heldout = [r for r in ROWS if r["tag"].startswith("heldout") and r["model_eval"]]
    counts = collections.Counter(r["type"] for r in heldout)
    for t in GATE_TYPES:
        assert counts[t] >= 2, (t, counts[t])
    assert {"금리", "수수료", "서류", "조건", "기간"} <= {r["type"] for r in BY_SOURCE["N"] + BY_SOURCE["S"]}


def test_author_new_set_has_the_agreed_composition():
    n = BY_SOURCE["N"]
    assert sum(r["type"] in ("조건", "기간") for r in n) == 4  # 존댓말 조건·기간 각 2개
    assert sum(r["type"] == "사유" for r in n) == 3
    assert sum(r["type"] == "숫자함정" for r in n) == 2
    assert sum(bool(r["history"]) for r in n) == 2  # 멀티턴
    assert {r["customer"] for r in n if r["type"] == "사유"} == {"C002", "C003"}


@pytest.mark.parametrize("row", [r for r in ROWS if r["source"] == "author" and r["id"][0] in "SN"], ids=lambda r: r["id"])
def test_author_question_does_not_overlap_seeds_golden_dev_or_user_questions(row):
    q = _norm(row["question"])
    seeds = _load_jsonl("manual_seed.jsonl")
    pool = (
        [_norm(s["question"]) for s in seeds] + [_norm(s["follow_up_question"]) for s in seeds if s["follow_up_question"]]
        + [_norm(g["question"]) for g in _v2.GOLDEN] + [_norm(g["question"]) for g in _load_jsonl("golden_set_v3.jsonl")]
        + [_norm(d) for d in _v2.DEV_QUESTIONS] + [_norm(u) for u in USER_QUESTIONS]
    )
    for other in pool:
        ratio = difflib.SequenceMatcher(None, q, other).ratio()
        assert q != other and ratio < 0.85, (row["question"], other, round(ratio, 2))


def test_dates_are_real_and_unseen_by_training():
    seed_dates = {s["maturity_date"] for s in _load_jsonl("manual_seed.jsonl")}
    prepare_dates = {"2027-03-31", "2029-11-30", "2035-06-30"}  # prepare.py _SAMPLE/_ALT_MATURITY와 mock 날짜
    for r in BY_SOURCE["D"]:
        d = r["loan"]["maturity_date"]
        datetime.datetime.strptime(d, "%Y-%m-%d")
        assert d not in seed_dates | prepare_dates, d


def test_criteria_file_states_the_numeric_rules_before_results():
    text = (DOCS / "EVAL_CRITERIA_v3.md").read_text(encoding="utf-8")
    for must_have in ("지어낸 사실 0건", "90%", "95%", "50/50", "15%p", "v4", "dev로 전환", "기록만", "U07",
                      "80%", "말투별", "먼저 읽고 해석", "개정 1", "cs-loan-test"):
        assert must_have in text, must_have
