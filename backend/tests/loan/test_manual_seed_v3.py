"""manual_seed.jsonl v3 확장 (2026-09-29).

v2 Golden Set에서 드러난 약점(복합 질문 누락, 수수료 주제 어긋남, 전반 조회 회피, 문형 반복)을 보강한 시드가
검증기·정제 규칙을 통과하고 유형별로 충분히 들어 있는지 본다. 질문 겹침은 test_golden_set*.py가 본다.
"""
import collections
import datetime
import json
import re
import statistics
from pathlib import Path

import pytest

from app.agents.loan.validate import DOCUMENT_KEYWORDS, is_valid_output
from training.loan.prepare import is_clean

SEED_PATH = Path(__file__).resolve().parents[2] / "training" / "loan" / "manual_seed.jsonl"
SEEDS = [json.loads(l) for l in SEED_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]


def _kind(seed: dict) -> str:
    return re.sub(r"-\d+$", "", seed["source_id"])


def test_seed_count_grew_to_v3_scale():
    # 상한 320은 추정이었다. 말투 변형·마스킹·구체 질문 61건을 더해 350이 됐다(train은 val로 뗀 질문을 뺀 만큼 적다).
    assert 260 <= len(SEEDS) <= 380


def test_weak_categories_are_covered():
    kinds = collections.Counter(_kind(s) for s in SEEDS)
    assert kinds["manual-combo"] >= 36  # v2: 4건. 두 가지 이상을 함께 묻는 질문
    assert kinds["manual-info"] >= 18   # v2: 2건. 전반 조회
    assert kinds["manual-fee"] >= 19    # v2: 5건. 비용·위약금·페널티 표현 포함
    assert kinds["manual-ctx"] >= 10    # v2: 0건. 이전 턴을 이어 묻는 질문


def test_answers_are_more_varied_than_v2():
    outputs = [s["output"] for s in SEEDS]
    # v2: 66, v3 초안: 175. 250을 목표로 잡았으나 실측 233에서 멈춘다: 사유·추측·요청 유형은 test_prepare가 문형 상한을 둔 기존 유형이다.
    assert len(set(outputs)) >= 230
    # v2: 57. 도입·맺음을 줄이면(문형 다양화와 맞바꿈) 길이가 줄어 v3 초안 73자에서 68자가 됐다.
    assert statistics.mean(len(o) for o in outputs) >= 65


def test_maturity_dates_are_varied_and_real():
    """mock 날짜 2개에 갇히면 모델이 날짜를 복사하지 않고 외운다. 실재하는 날짜만 쓴다."""
    dates = {s["maturity_date"] for s in SEEDS}
    assert len(dates) >= 20
    for d in dates:
        datetime.datetime.strptime(d, "%Y-%m-%d")
    assert {"2027-03-31", "2035-06-30"} <= dates  # mock 날짜는 계속 넣는다


_FRAME_MARKERS = (
    "더 궁금하신 점", "추가로 궁금하신 내용", "다른 문의사항",
    "조회해 보니 ", "확인 결과 ", "확인해 보니 ", "말씀하신 대출 기준으로", "문의해 주신 내용을 조회한 결과", "문의하신 내용은 다음과 같습니다",
)


def test_opening_and_closing_phrases_are_not_on_every_answer():
    framed = sum(any(m in s["output"] for m in _FRAME_MARKERS) for s in SEEDS)
    assert framed / len(SEEDS) <= 0.5


def test_unextendable_answers_do_not_double_refer_to_the_agent():
    """"상담원에게 확인해 주세요" 뒤에 "더 궁금하신 점이…"을 또 붙이면 안내가 두 번 나온다."""
    for s in SEEDS:
        if "상담원에게 확인해 주세요" in s["output"]:
            assert not any(m in s["output"] for m in _FRAME_MARKERS[:3]), s["output"]


@pytest.mark.parametrize("seed", SEEDS, ids=[s["source_id"] for s in SEEDS])
def test_every_seed_passes_validator_and_cleaning(seed):
    assert is_valid_output(seed["output"], maturity_date=seed["maturity_date"], extendable=seed["extendable"]), seed["output"]
    assert is_clean(seed), seed["output"]


def test_combo_and_info_answers_contain_every_asked_slot():
    """R06 방지: 함께 물은 항목이 답에서 빠지면 안 된다."""
    for s in SEEDS:
        if _kind(s) == "manual-info":
            assert all(t in s["output"] for t in ("{{principal_remaining}}", "{{extendable_status}}", s["maturity_date"])), s
        if _kind(s) == "manual-combo":
            asked = [
                slot for word, slot in (
                    ("원금", "{{principal_remaining}}"), ("잔액", "{{principal_remaining}}"),
                    ("연장", "{{extendable_status}}"), ("만기", s["maturity_date"]),
                )
                if word in s["question"]
            ]
            assert all(slot in s["output"] for slot in asked), s


def test_fee_answers_name_the_asked_topic():
    """F09 방지: 수수료·비용 질문에 금리 얘기를 하면 안 된다."""
    for s in SEEDS:
        if _kind(s) == "manual-fee":
            assert "금리" not in s["output"], s
            assert any(t in s["output"] for t in ("수수료", "비용", "위약금", "페널티", "불이익", "금액")), s


def test_context_seeds_have_history_and_answer_the_follow_up():
    ctx = [s for s in SEEDS if _kind(s) == "manual-ctx"]
    for s in ctx:
        assert s["question"] and s["answer"] and s["follow_up_question"], s
        assert s["output"] != s["answer"]


def test_extendable_and_unextendable_both_present_per_kind():
    for kind in ("manual-combo", "manual-info", "manual-fee"):
        flags = {s["extendable"] for s in SEEDS if _kind(s) == kind}
        assert flags == {True, False}, kind


# ---------------------------------------------------------------------------
# 2026-09-29 사용자 요청 항목: 말투·마스킹·구체 질문·"네," 규칙·val 분리·"조회" 중복
# ---------------------------------------------------------------------------
_POLITE = re.compile(r"(요|니다|까|세요|죠)[?.!]*$")
_YES_NO = re.compile(r"(나요|가요|까요|죠|지요)\??$")
_WH = re.compile(r"언제|얼마|어떻게|무엇|뭐|왜|어디|몇|어떤|어느")
_MASK = re.compile(r"\[[^\]]+_\d+\]")


def _is_yes_no(question: str) -> bool:
    return bool(_YES_NO.search(question.strip())) and not _WH.search(question)


def test_casual_short_and_typo_questions_are_covered():
    casual = [s for s in SEEDS if _kind(s) == "manual-casual"]
    assert len(casual) >= 24
    assert sum(not _POLITE.search(s["question"]) for s in casual) >= 10  # 반말·명사형·오타
    assert sum(len(s["question"].replace(" ", "")) <= 8 for s in casual) >= 5  # 짧은 질문
    for s in casual:  # 질문이 반말이어도 답은 정중체
        assert re.search(r"(니다|세요|바랍니다|해요)[.]?$", s["output"].strip()) or "{{extendable_status}}" in s["output"], s


def test_masked_token_questions_are_covered_and_never_echoed():
    masked = [s for s in SEEDS if _kind(s) == "manual-mask"]
    assert len(masked) >= 16
    assert len({t for s in masked for t in _MASK.findall(s["question"])}) >= 5  # 토큰 종류
    for s in masked:
        assert _MASK.search(s["question"]), s
        assert not _MASK.search(s["output"]), s  # 원본이 아니어도 답에서 되풀이하지 않는다


def test_rate_document_and_condition_seeds_include_concrete_questions():
    concrete = [
        s for s in SEEDS
        if _kind(s) in ("manual-rate", "manual-doc", "manual-cond")
        and (re.search(r"\d", s["question"]) or any(k in s["question"] for k in DOCUMENT_KEYWORDS))
    ]
    assert len(concrete) >= 16
    for s in concrete:  # 질문의 숫자·서류명을 맞다/틀리다 하지 않고 되풀이하지도 않는다
        assert not re.search(r"\d", s["output"]) and not any(k in s["output"] for k in DOCUMENT_KEYWORDS), s


def test_yes_prefix_only_on_yes_no_questions_with_an_affirmative_answer():
    """"네,"는 예/아니오 질문에 긍정으로 답할 때만 쓴다. 연장 불가인데 "네,"로 시작하면 모순이다."""
    for s in SEEDS:
        if s["output"].startswith("네,"):
            assert _is_yes_no(s["question"]), s
            if "{{extendable_status}}" in s["output"]:
                assert s["extendable"], s


def test_held_out_seeds_are_split_by_question_not_by_row():
    val = [s for s in SEEDS if s.get("split") == "val"]
    train = [s for s in SEEDS if s.get("split", "train") == "train"]
    assert {s.get("split", "train") for s in SEEDS} <= {"train", "val"}
    assert not {s["question"] for s in val} & {s["question"] for s in train}  # 같은 질문의 변형이 양쪽에 걸치면 누출
    assert 0.08 <= len({s["question"] for s in val}) / len({s["question"] for s in SEEDS}) <= 0.2
    assert {"manual-maturity", "manual-principal", "manual-combo", "manual-info", "manual-fee", "manual-ctx"} <= {
        _kind(s) for s in val
    }


def test_each_combo_and_info_answer_says_lookup_at_most_once():
    """{{extendable_status}}는 화면에서 "…조회됩니다"로 바뀌므로 그 슬롯이 있으면 모델 문장에는 "조회"를 쓰지 않는다."""
    for s in SEEDS:
        if _kind(s) in ("manual-combo", "manual-info"):
            rendered = s["output"].count("조회") + ("{{extendable_status}}" in s["output"])
            assert rendered <= 1, s["output"]
