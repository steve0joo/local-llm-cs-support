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


def _manual_row(question, split=None):
    row = {
        "question": question, "answer": "", "follow_up_question": "",
        "output": "고객님의 {{loan_label}} 만기일은 2027-03-31입니다.", "extendable": True, "maturity_date": "2027-03-31",
    }
    if split:
        row["split"] = split
    return row


def test_v2_val_uses_held_out_manual_seeds_once_and_train_never_sees_them(tmp_path):
    """val 손실이 슬롯 답변(만기·원금·연장)도 재도록, 질문 단위로 떼어 둔 수동 시드를 val에 1배로 넣는다."""
    raw, split = _setup(tmp_path, [])
    manual = tmp_path / "m.jsonl"
    manual.write_text(
        "\n".join(json.dumps(_manual_row(q, s), ensure_ascii=False) for q, s in (
            ("만기일 알려주세요.", None), ("만기가 언제인가요?", None), ("대출 끝나는 날이 언제예요?", "val"),
        )) + "\n",
        encoding="utf-8",
    )
    train_out, val_out = tmp_path / "train.jsonl", tmp_path / "val.jsonl"
    assert build_dataset_v2(raw, split, train_out, split="train", manual_path=manual) == 2 * prepare.MANUAL_COPIES
    assert build_dataset_v2(raw, split, val_out, split="val", manual_path=manual) == 1  # 복제 없이 1배
    train_text = train_out.read_text(encoding="utf-8")
    assert "대출 끝나는 날이 언제예요?" not in train_text
    assert "대출 끝나는 날이 언제예요?" in val_out.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# v4 거절 문형(2026-09-30): "~ㄹ 수 있/없"이 뒤집히면 처리 약속·사실 단정이 되므로 쓰지 않는다. v3는 그대로 재현한다.
# ---------------------------------------------------------------------------
import hashlib
import re

V3_TEMPLATES_SHA256 = "a706fd37b37cd331f77631e5de46afdbb79544cedff74549d1763026c5867bed"


def test_v3_refusal_templates_are_frozen_so_v3_data_stays_reproducible():
    assert hashlib.sha256("\n".join(REFUSAL_TEMPLATES).encode()).hexdigest() == V3_TEMPLATES_SHA256


def test_v4_refusal_templates_keep_the_same_slots_and_avoid_able_unable_phrasing():
    v4 = prepare.REFUSAL_TEMPLATES_V4
    assert len(v4) == len(REFUSAL_TEMPLATES)
    assert v4 != REFUSAL_TEMPLATES
    for t in v4:
        assert not re.search(r"수 있|수 없|처리해 드", t), t
    for topic in ("서류·조건", "금리"):
        for i in range(len(v4)):
            for closing in (None, CLOSINGS[0]):
                text = render_refusal(topic, i, closing, version="v4")
                assert is_valid_output(text, maturity_date="2027-03-31", extendable=True), text


def test_render_refusal_defaults_to_v3_and_the_flag_selects_v4():
    assert render_refusal("금리", 1) == render_refusal("금리", 1, version="v3")
    assert "안내드릴 수 없어" in render_refusal("금리", 1)  # v3 그대로
    assert "안내드리기 어렵습니다" in render_refusal("금리", 1, version="v4")
    with pytest.raises(ValueError):
        render_refusal("금리", 1, version="v9")


def test_dataset_builder_passes_the_refusal_version_through(tmp_path):
    raw, split = _setup(tmp_path, [f"연장하려면 서류가 뭐가 필요한가요 {i}?" for i in range(6)])
    out3, out4 = tmp_path / "v3.jsonl", tmp_path / "v4.jsonl"
    build_dataset_v2(raw, split, out3)
    build_dataset_v2(raw, split, out4, refusal_version="v4")
    assert re.search(r"수 없어|받아보실 수", out3.read_text(encoding="utf-8"))
    assert not re.search(r"수 있|수 없", "".join(m[-1]["content"] for m in _rows(out4)))
