"""prepare.py의 v2 교체 모드 (2026-09-29 결정, docs/agent-loan/ADR.md).

AI Hub 상담사 답변은 절차·채널·서류를 지어내므로 학습 정답으로 쓰지 않는다. AI Hub는 질문 공급원으로만 쓰고,
질문 유형(서류·조건 / 금리)에 맞는 정답을 우리가 정한 문장으로 붙인다. 픽스처는 합성 데이터만 쓴다.
"""
import json
import zipfile
from pathlib import Path

import pytest

from app.agents.loan.validate import is_valid_output
from training.loan import prepare
from training.loan.prepare import (
    CLOSINGS,
    REFUSAL_TEMPLATES,
    TOPIC,
    build_dataset_v2,
    classify_replace_type,
    josa,
    render_refusal,
)


def _entry(source_id, qa_id, question, answer="원본 상담사 답변입니다. 모바일 앱에서 신청하세요.", follow_up="그렇군요.", topic=TOPIC):
    return {
        "source": {"source_id": source_id, "source_institution": "테스트은행"},
        "consulting": {"consulting_category": "은행", "consulting_topic": topic},
        "qa_data": [{
            "qa_id": qa_id, "qa_topic": topic, "instruction": "안내하시오.",
            "input": {"question": question, "answer": answer, "follow_up_question": follow_up},
            "output": "상담사가 지어낸 최종 답변. 고객센터로 연락 주세요.",
        }],
    }


def _setup(tmp_path: Path, questions: list[str]):
    raw = tmp_path / "raw"
    raw.mkdir()
    entries = [_entry(f"s{i}", f"q{i}", q) for i, q in enumerate(questions)]
    with zipfile.ZipFile(raw / "TL_은행.zip", "w") as z:
        for i, e in enumerate(entries):
            z.writestr(f"01/{i:03d}.json", json.dumps(e, ensure_ascii=False))
    split = tmp_path / "split.json"
    split.write_text(json.dumps({f"s{i}": "train" for i in range(len(questions))}), encoding="utf-8")
    return raw, split


def _rows(path: Path):
    return [json.loads(l)["messages"] for l in path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("question,expected", [
    ("연장하려면 어떤 서류가 필요한가요?", "서류·조건"),
    ("연장 조건이 어떻게 되나요?", "서류·조건"),
    ("대출 연장 자격 요건이 있나요?", "서류·조건"),
    ("연장할 때 제출해야 하는 자료가 있나요?", "서류·조건"),
    ("현재 금리가 몇 퍼센트인가요?", "금리"),
    ("연장하면 이율이 바뀌나요?", "금리"),
    ("이자율이 궁금합니다.", "금리"),
])
def test_classify_matches_supported_types(question, expected):
    assert classify_replace_type(question) == expected


@pytest.mark.parametrize("question", [
    "연장 서류와 금리가 둘 다 궁금합니다.",  # 복수 유형
    "중도상환 수수료가 있나요?",  # 수수료는 교체 대상 아님
    "금리와 수수료를 알려주세요.",  # 수수료 포함은 제외
    "이자 납부일을 바꾸고 싶어요.",  # 이자·상환은 다른 에이전트 담당
    "상환 방법이 궁금해요.",
    "전자서명이 끝나면 바로 연장이 적용되나요?",  # 서류·조건이 아님
    "서류가 필요한가요?",  # 연장 문맥이 없으면 대상 아님
    "★★은행 연장 서류가 필요한가요?",  # 익명화 기호
    "연장 서류가 필요한가요?" + "가" * 200,  # 너무 긴 질문
    "안녕하세요",
])
def test_classify_excludes_out_of_scope_questions(question):
    assert classify_replace_type(question) is None


def test_josa_follows_final_consonant():
    assert josa("서류·조건", ("은", "는")) == "서류·조건은"
    assert josa("금리", ("은", "는")) == "금리는"
    assert josa("서류·조건", ("을", "를")) == "서류·조건을"
    assert josa("금리", ("을", "를")) == "금리를"
    assert "(" not in josa("금리", ("을", "를"))


@pytest.mark.parametrize("topic", ["서류·조건", "금리", "연장 불가 사유"])
@pytest.mark.parametrize("closing", [False, True])
def test_every_refusal_sentence_passes_the_validator(topic, closing):
    for i in range(len(REFUSAL_TEMPLATES)):
        text = render_refusal(topic, i, closing=CLOSINGS[i % len(CLOSINGS)] if closing else None)
        assert "(를)" not in text and "(을)" not in text and "{t" not in text
        assert is_valid_output(text, maturity_date="2027-03-31", extendable=True), text
        assert is_valid_output(text, maturity_date="2027-03-31", extendable=False), text
        assert "상담원" in text


def test_closings_pass_the_validator():
    assert len(CLOSINGS) >= 4
    for c in CLOSINGS:
        assert is_valid_output(c, maturity_date="2027-03-31", extendable=True), c


def test_v2_never_uses_the_original_counselor_text(tmp_path):
    raw, split = _setup(tmp_path, ["연장하려면 어떤 서류가 필요한가요?", "현재 금리가 몇 퍼센트인가요?"])
    out = tmp_path / "out.jsonl"
    build_dataset_v2(raw, split, out, caps={"서류·조건": 10, "금리": 10})
    text = out.read_text(encoding="utf-8")
    assert "원본 상담사" not in text and "모바일" not in text and "고객센터" not in text and "그렇군요" not in text


def test_v2_builds_single_turn_samples_with_refusal_targets(tmp_path):
    raw, split = _setup(tmp_path, ["연장하려면 어떤 서류가 필요한가요?", "현재 금리가 몇 퍼센트인가요?"])
    out = tmp_path / "out.jsonl"
    n = build_dataset_v2(raw, split, out, caps={"서류·조건": 10, "금리": 10})
    rows = _rows(out)
    assert n == len(rows) == 2
    for msgs in rows:
        assert [m["role"] for m in msgs] == ["system", "user", "assistant"]  # 가짜 히스토리 없음
        assert "상담원" in msgs[-1]["content"]
        assert "대출 정보:" in msgs[1]["content"]
    targets = " ".join(m[-1]["content"] for m in rows)
    assert "서류·조건" in targets and "금리" in targets


def test_v2_respects_caps_and_is_deterministic(tmp_path):
    qs = [f"연장 서류가 필요한지 알려주세요 {i}번" for i in range(20)] + [f"금리가 어떻게 되나요 {i}번" for i in range(20)]
    raw, split = _setup(tmp_path, qs)
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    build_dataset_v2(raw, split, a, caps={"서류·조건": 5, "금리": 7})
    build_dataset_v2(raw, split, b, caps={"서류·조건": 5, "금리": 7})
    assert a.read_text(encoding="utf-8") == b.read_text(encoding="utf-8")
    rows = _rows(a)
    assert len(rows) == 12
    assert sum("서류" in m[1]["content"] for m in rows) == 5


def test_v2_skips_other_topics_and_unsplit_items(tmp_path):
    raw, split = _setup(tmp_path, ["연장하려면 어떤 서류가 필요한가요?"])
    with zipfile.ZipFile(raw / "VL_은행.zip", "w") as z:
        z.writestr("x.json", json.dumps(_entry("s9", "q9", "연장 서류가 필요한가요?", topic="이자/연체금액"), ensure_ascii=False))
    out = tmp_path / "out.jsonl"
    assert build_dataset_v2(raw, split, out) == 1


def test_v2_manual_seed_is_copied_and_targets_validate(tmp_path):
    raw, split = _setup(tmp_path, [])
    manual = tmp_path / "m.jsonl"
    manual.write_text(json.dumps({
        "question": "만기일 알려주세요.", "answer": "", "follow_up_question": "",
        "output": "고객님의 {{loan_label}} 만기일은 2027-03-31입니다.", "extendable": True, "maturity_date": "2027-03-31",
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    out = tmp_path / "out.jsonl"
    n = build_dataset_v2(raw, split, out, manual_path=manual)
    assert n == prepare.MANUAL_COPIES
