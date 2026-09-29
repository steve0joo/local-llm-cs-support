"""training/loan/prepare.py (docs/agent-loan/ARCHITECTURE.md 학습 데이터 절, phases/agent-loan/step3.md).

픽스처는 전부 이 파일 안에서 tmp_path에 합성 JSON/zip으로 만든다. 실제 AI Hub 데이터는 쓰지 않는다.
"""
import json
import re
import zipfile
from pathlib import Path

import pytest

from training.loan import prepare
from training.loan.prepare import (
    MANUAL_COPIES,
    NO_EXTEND_COPIES,
    TOPIC,
    build_dataset,
    infer_extendable,
    is_clean,
    iter_conversations,
    iter_manual_samples,
    to_messages,
)

from app.agents.loan.validate import is_valid_output


def _entry(
    source_id: str,
    qa_id: str,
    question: str,
    answer: str,
    follow_up_question: str,
    output: str,
    topic: str = TOPIC,
    qa_topic: str | None = None,
) -> dict:
    """실제 은행 라벨링 데이터와 같은 구조(2026-09-29 확인)의 합성 항목 하나."""
    return {
        "source": {"source_id": source_id, "source_institution": "테스트은행"},
        "consulting": {"consulting_category": "은행", "consulting_topic": topic},
        "qa_data": [
            {
                "qa_id": qa_id,
                "qa_topic": qa_topic if qa_topic is not None else topic,
                "instruction": "안내하시오.",
                "input": {
                    "question": question,
                    "answer": answer,
                    "follow_up_question": follow_up_question,
                },
                "output": output,
            }
        ],
    }


def _write_zip(path: Path, entries: list[dict]) -> None:
    with zipfile.ZipFile(path, "w") as z:
        for i, entry in enumerate(entries):
            z.writestr(f"01/{i:03d}.json", json.dumps(entry, ensure_ascii=False))


@pytest.fixture()
def raw_dir(tmp_path: Path) -> Path:
    d = tmp_path / "raw"
    d.mkdir()
    return d


def _split_path(tmp_path: Path, mapping: dict[str, str]) -> Path:
    p = tmp_path / "split.json"
    p.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 분할 필터
# ---------------------------------------------------------------------------


def test_iter_conversations_filters_by_split_and_topic(tmp_path, raw_dir):
    train_item = _entry("s-train", "q-train", "만기가 언제예요?", "안내드립니다.", "감사합니다.", "만기일을 확인해 드립니다.")
    val_item = _entry("s-val", "q-val", "만기가 언제예요?", "안내드립니다.", "감사합니다.", "만기일을 확인해 드립니다.")
    other_topic_item = _entry(
        "s-other", "q-other", "이자가 얼마예요?", "안내드립니다.", "감사합니다.", "이자를 확인해 드립니다.",
        topic="이자/연체금액",
    )
    _write_zip(raw_dir / "TL_은행.zip", [train_item, other_topic_item])
    _write_zip(raw_dir / "VL_은행.zip", [val_item])
    split_path = _split_path(tmp_path, {"s-train": "train", "s-val": "val", "s-other": "train"})

    train_ids = [item["source_id"] for item in iter_conversations(raw_dir, split_path, "train")]

    assert train_ids == ["s-train"]  # val 항목도, 다른 주제 항목도 섞이지 않는다


def test_iter_conversations_val_split(tmp_path, raw_dir):
    val_item = _entry("s-val", "q-val", "만기가 언제예요?", "안내드립니다.", "감사합니다.", "만기일을 확인해 드립니다.")
    _write_zip(raw_dir / "TL_은행.zip", [])
    _write_zip(raw_dir / "VL_은행.zip", [val_item])
    split_path = _split_path(tmp_path, {"s-val": "val"})

    val_ids = [item["source_id"] for item in iter_conversations(raw_dir, split_path, "val")]

    assert val_ids == ["s-val"]


# ---------------------------------------------------------------------------
# 마스킹
# ---------------------------------------------------------------------------


def test_build_dataset_masks_pii(tmp_path, raw_dir):
    item = _entry(
        "s1", "q1",
        "제 번호는 010-1234-5678이고 계좌 잔액이 궁금해요.",
        "네 확인해 드리겠습니다.",
        "감사합니다.",
        "만기일을 확인해 드립니다.",
    )
    _write_zip(raw_dir / "TL_은행.zip", [item])
    _write_zip(raw_dir / "VL_은행.zip", [])
    split_path = _split_path(tmp_path, {"s1": "train"})
    out_path = tmp_path / "out.jsonl"

    build_dataset(raw_dir, split_path, out_path, split="train")

    dumped = out_path.read_text(encoding="utf-8")
    assert "010-1234-5678" not in dumped


# ---------------------------------------------------------------------------
# is_clean
# ---------------------------------------------------------------------------


def _clean_item(**overrides) -> dict:
    base = dict(
        source_id="s1",
        qa_id="q1",
        topic=TOPIC,
        question="만기 연장이 되나요?",
        answer="확인해 드리겠습니다.",
        follow_up_question="네 알겠습니다.",
        output="만기일을 확인해 드립니다. 연장 신청이 가능합니다.",
    )
    base.update(overrides)
    return base


def test_is_clean_rejects_percent_not_in_input():
    item = _clean_item(output="금리는 연 3.5%입니다.")
    assert is_clean(item) is False


def test_is_clean_rejects_percent_even_if_present_in_input():
    # 엄격 규칙(2026-09-29): 금리·수수료(%)는 input에 이미 있어도 output에 있으면 무조건 제외한다.
    item = _clean_item(question="금리가 연 3.5%인가요?", output="네, 금리는 연 3.5%입니다.")
    assert is_clean(item) is False


def test_is_clean_rejects_fee_percent_near_keyword():
    item = _clean_item(output="중도상환수수료는 1%입니다.")
    assert is_clean(item) is False


def test_is_clean_rejects_period_mention():
    item = _clean_item(output="심사는 영업일 기준 3일 정도 걸립니다.")
    assert is_clean(item) is False


def test_is_clean_accepts_number_present_in_input():
    item = _clean_item(
        question="2027-03-31에 만기인가요?",
        output="네, 2027-03-31에 만기입니다.",
    )
    assert is_clean(item) is True


def test_is_clean_rejects_document_keyword_not_in_input():
    item = _clean_item(output="재직증명서를 제출해 주세요.")
    assert is_clean(item) is False


def test_is_clean_rejects_document_keyword_even_if_in_input():
    # 엄격 규칙: 서류명은 input에 이미 있어도 output에 있으면 무조건 제외한다.
    item = _clean_item(question="재직증명서가 필요한가요?", output="네, 재직증명서를 제출해 주세요.")
    assert is_clean(item) is False


def test_is_clean_rejects_new_document_keywords():
    item_1 = _clean_item(output="급여명세서를 제출해 주세요.")
    item_2 = _clean_item(output="등기부 등본을 제출해 주세요.")
    assert is_clean(item_1) is False
    assert is_clean(item_2) is False


def test_is_clean_accepts_generic_document_word():
    item = _clean_item(output="필요한 서류는 상담원에게 확인해 주세요.")
    assert is_clean(item) is True


def test_is_clean_rejects_unattested_product_name():
    item = _clean_item(output="새싹대출로 전환하시면 유리합니다.")
    assert is_clean(item) is False


def test_is_clean_accepts_allowed_product_name():
    item = _clean_item(output="신용대출 상품 안내드립니다.")
    assert is_clean(item) is True


def test_is_clean_accepts_product_name_present_in_input():
    item = _clean_item(question="새싹대출 문의드립니다.", output="새싹대출은 만기 연장이 가능합니다.")
    assert is_clean(item) is True


# ---------------------------------------------------------------------------
# 연장 가능 값 추론
# ---------------------------------------------------------------------------


def test_infer_extendable_positive():
    assert infer_extendable("연장 신청이 가능합니다.") is True


def test_infer_extendable_negative_requires_extension_context():
    assert infer_extendable("연장은 불가합니다.") is False


def test_infer_extendable_unrelated_negation_is_not_negative_evidence():
    # "불가"가 있지만 "연장"과 무관하다 — 부정 근거로 세지 않는다(근거 없음 → None, 샘플 제외)
    assert infer_extendable("환불은 불가합니다.") is None


def test_infer_extendable_ambiguous_returns_none():
    assert infer_extendable("연장은 불가합니다. 다른 조건은 가능합니다.") is None


def test_infer_extendable_negation_word_inside_positive_is_not_negative():
    # "없"이 들어 있지만 부정 표현이 아니다(서류 "없이") — 긍정으로 판정
    assert infer_extendable("서류 없이 연장 신청이 가능합니다.") is True


def test_infer_extendable_no_evidence_returns_none():
    # 2026-09-29: 근거 없을 때 무작위 배정하던 분기를 제거했다 — 근거 없으면 무조건 제외(None)한다.
    assert infer_extendable("상담원에게 확인해 주세요.") is None


# ---------------------------------------------------------------------------
# 학습 대화 구성
# ---------------------------------------------------------------------------


def test_to_messages_structure_and_slots():
    item = _clean_item(question="질문", answer="답변", follow_up_question="재질문", output="만기일을 확인해 드립니다.")
    messages = to_messages(item, extendable=True, maturity_date="2027-03-31")

    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user", "assistant"]
    assert messages[1]["content"] == "질문"
    assert messages[2]["content"] == "답변"
    last_user = messages[3]["content"]
    assert "재질문" in last_user
    assert "만기일=2027-03-31" in last_user
    assert "연장 가능=예" in last_user
    assert "{{loan_label}}, {{principal_remaining}}, {{extendable_status}}" in last_user
    assert messages[4]["content"] == "만기일을 확인해 드립니다."


def test_to_messages_non_extendable_info_line():
    item = _clean_item()
    messages = to_messages(item, extendable=False, maturity_date="2035-06-30")
    assert "연장 가능=아니오(사유는 알 수 없음)" in messages[3]["content"]


# ---------------------------------------------------------------------------
# build_dataset 통합: 정제·복제·불변식
# ---------------------------------------------------------------------------


def test_build_dataset_excludes_dirty_and_ambiguous_samples(tmp_path, raw_dir):
    clean = _entry(
        "s-clean", "q-clean", "만기가 언제예요?", "안내드립니다.", "감사합니다.",
        "만기일을 확인해 드립니다. 연장 신청이 가능합니다.",
    )
    dirty = _entry("s-dirty", "q-dirty", "금리가 얼마예요?", "안내드립니다.", "감사합니다.", "금리는 연 3.5%입니다.")
    ambiguous = _entry(
        "s-ambiguous", "q-amb", "연장되나요?", "안내드립니다.", "감사합니다.",
        "연장은 불가합니다. 다른 조건은 가능합니다.",
    )
    _write_zip(raw_dir / "TL_은행.zip", [clean, dirty, ambiguous])
    _write_zip(raw_dir / "VL_은행.zip", [])
    split_path = _split_path(tmp_path, {"s-clean": "train", "s-dirty": "train", "s-ambiguous": "train"})
    out_path = tmp_path / "out.jsonl"

    written = build_dataset(raw_dir, split_path, out_path, split="train")

    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert written == len(lines) == 1  # dirty는 정제 제외, ambiguous는 연장 판정 모호로 제외


def test_build_dataset_duplicates_only_evidence_based_negative_in_train(tmp_path, raw_dir):
    negative = _entry(
        "s-neg", "q-neg", "연장되나요?", "안내드립니다.", "감사합니다.", "연장은 불가합니다.",
    )
    positive = _entry(
        "s-pos", "q-pos", "연장되나요?", "안내드립니다.", "감사합니다.", "연장 신청이 가능합니다.",
    )
    _write_zip(raw_dir / "TL_은행.zip", [negative, positive])
    _write_zip(raw_dir / "VL_은행.zip", [])
    split_path = _split_path(tmp_path, {"s-neg": "train", "s-pos": "train"})
    out_path = tmp_path / "out.jsonl"

    build_dataset(raw_dir, split_path, out_path, split="train")

    lines = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]
    neg_lines = [
        line for line in lines
        if "연장 가능=아니오" in line["messages"][3]["content"]
    ]
    pos_lines = [
        line for line in lines
        if "연장 가능=예" in line["messages"][3]["content"]
    ]
    assert len(neg_lines) == NO_EXTEND_COPIES == 2
    assert len(pos_lines) == 1
    # 복제본은 질문·답변은 같고 만기일만 다르다
    assert neg_lines[0]["messages"][4] == neg_lines[1]["messages"][4]
    date_pattern = re.compile(r"만기일=(\S+),")
    dates = {date_pattern.search(line["messages"][3]["content"]).group(1) for line in neg_lines}
    assert len(dates) == 2


def test_build_dataset_does_not_duplicate_in_val_or_test(tmp_path, raw_dir):
    negative = _entry("s-neg", "q-neg", "연장되나요?", "안내드립니다.", "감사합니다.", "연장은 불가합니다.")
    _write_zip(raw_dir / "TL_은행.zip", [])
    _write_zip(raw_dir / "VL_은행.zip", [negative])
    split_path = _split_path(tmp_path, {"s-neg": "val"})
    out_path = tmp_path / "out.jsonl"

    build_dataset(raw_dir, split_path, out_path, split="val")

    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_build_dataset_excludes_samples_with_no_extension_evidence(tmp_path, raw_dir):
    # 2026-09-29: 연장 근거가 없으면 무작위 배정하지 않고 제외한다(연장 언급 자체가 없는 대화)
    neutral = _entry("s-neutral", "q-neutral", "다른 질문", "안내드립니다.", "감사합니다.", "상담원에게 확인해 주세요.")
    _write_zip(raw_dir / "TL_은행.zip", [neutral])
    _write_zip(raw_dir / "VL_은행.zip", [])
    split_path = _split_path(tmp_path, {"s-neutral": "train"})
    out_path = tmp_path / "out.jsonl"

    written = build_dataset(raw_dir, split_path, out_path, split="train")

    assert written == 0
    assert out_path.read_text(encoding="utf-8") == ""


def test_no_extend_samples_pass_own_validation(tmp_path, raw_dir):
    negative = _entry(
        "s-neg", "q-neg", "연장되나요?", "안내드립니다.", "감사합니다.",
        "연장은 불가합니다. 상담원에게 확인해 주세요.",
    )
    _write_zip(raw_dir / "TL_은행.zip", [negative])
    _write_zip(raw_dir / "VL_은행.zip", [])
    split_path = _split_path(tmp_path, {"s-neg": "train"})
    out_path = tmp_path / "out.jsonl"

    build_dataset(raw_dir, split_path, out_path, split="train")

    date_pattern = re.compile(r"만기일=(\S+),")
    for line in out_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        last_user = record["messages"][3]["content"]
        if "연장 가능=아니오" not in last_user:
            continue
        maturity_date = date_pattern.search(last_user).group(1)
        target = record["messages"][4]["content"]
        assert is_valid_output(target, maturity_date=maturity_date, extendable=False)


def test_limit_caps_written_count(tmp_path, raw_dir):
    items = [
        _entry(f"s{i}", f"q{i}", "만기가 언제예요?", "안내드립니다.", "감사합니다.", "만기일을 확인해 드립니다. 연장 신청이 가능합니다.")
        for i in range(3)
    ]
    _write_zip(raw_dir / "TL_은행.zip", items)
    _write_zip(raw_dir / "VL_은행.zip", [])
    split_path = _split_path(tmp_path, {f"s{i}": "train" for i in range(3)})
    out_path = tmp_path / "out.jsonl"

    written = build_dataset(raw_dir, split_path, out_path, split="train", limit=1)

    assert written == 1
    assert len(out_path.read_text(encoding="utf-8").splitlines()) == 1


# ---------------------------------------------------------------------------
# 어댑터 격리
# ---------------------------------------------------------------------------


def _write_manual(path: Path, samples: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")


def test_manual_samples_merge_when_present(tmp_path, raw_dir):
    auto_item = _entry(
        "s-auto", "q-auto", "만기가 언제예요?", "안내드립니다.", "감사합니다.",
        "만기일을 확인해 드립니다. 연장 신청이 가능합니다.",
    )
    _write_zip(raw_dir / "TL_은행.zip", [auto_item])
    _write_zip(raw_dir / "VL_은행.zip", [])
    split_path = _split_path(tmp_path, {"s-auto": "train"})
    manual_path = tmp_path / "manual.jsonl"
    _write_manual(manual_path, [
        {
            "question": "연장되나요?",
            "answer": "확인해 드리겠습니다.",
            "follow_up_question": "네 감사합니다.",
            "output": "연장 신청이 가능합니다.",
        },
    ])
    out_path = tmp_path / "out.jsonl"

    written = build_dataset(raw_dir, split_path, out_path, split="train", manual_path=manual_path)

    assert written == 1 + MANUAL_COPIES  # 자동 추출 1건 + 수동 1건(train은 MANUAL_COPIES배)
    lines = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]
    manual_line = next(line for line in lines if "연장 신청이 가능합니다." in line["messages"][4]["content"])
    assert "연장 가능=예" in manual_line["messages"][3]["content"]


def test_manual_samples_explicit_extendable_field_bypasses_inference(tmp_path, raw_dir):
    # 슬롯({{extendable_status}})만 쓰는 수동 샘플은 output에 "가능"/"불가" 문구가 없어
    # infer_extendable로는 판정할 수 없다 — extendable 필드를 직접 지정하면 그 값을 그대로 쓴다.
    manual_path = tmp_path / "manual.jsonl"
    _write_manual(manual_path, [
        {
            "question": "연장되나요?", "answer": "확인해 드리겠습니다.", "follow_up_question": "네.",
            "output": "고객님의 {{loan_label}}은 {{extendable_status}}.",
            "extendable": False,
        },
    ])
    _write_zip(raw_dir / "TL_은행.zip", [])
    _write_zip(raw_dir / "VL_은행.zip", [])
    split_path = _split_path(tmp_path, {})
    out_path = tmp_path / "out.jsonl"

    written = build_dataset(raw_dir, split_path, out_path, split="train", manual_path=manual_path)

    assert written == MANUAL_COPIES  # extendable=False가 명시돼 있어 근거 없음(None)으로 제외되지 않는다
    line = json.loads(out_path.read_text(encoding="utf-8").splitlines()[0])
    assert "연장 가능=아니오" in line["messages"][3]["content"]
    assert "{{extendable_status}}" in line["messages"][4]["content"]


def test_manual_samples_without_extendable_field_still_infers_from_text(tmp_path, raw_dir):
    manual_path = tmp_path / "manual.jsonl"
    _write_manual(manual_path, [
        {
            "question": "다른 질문", "answer": "안내드립니다.", "follow_up_question": "감사합니다.",
            "output": "상담원에게 확인해 주세요.",  # extendable 필드 없음 + 근거 없음 → 제외
        },
    ])
    _write_zip(raw_dir / "TL_은행.zip", [])
    _write_zip(raw_dir / "VL_은행.zip", [])
    split_path = _split_path(tmp_path, {})
    out_path = tmp_path / "out.jsonl"

    written = build_dataset(raw_dir, split_path, out_path, split="train", manual_path=manual_path)

    assert written == 0


def test_manual_samples_file_missing_or_none_does_not_break(tmp_path, raw_dir):
    auto_item = _entry(
        "s-auto", "q-auto", "만기가 언제예요?", "안내드립니다.", "감사합니다.",
        "만기일을 확인해 드립니다. 연장 신청이 가능합니다.",
    )
    _write_zip(raw_dir / "TL_은행.zip", [auto_item])
    _write_zip(raw_dir / "VL_은행.zip", [])
    split_path = _split_path(tmp_path, {"s-auto": "train"})
    out_path = tmp_path / "out.jsonl"

    written_without_arg = build_dataset(raw_dir, split_path, out_path, split="train")
    assert written_without_arg == 1

    written_missing_file = build_dataset(
        raw_dir, split_path, out_path, split="train", manual_path=tmp_path / "없는파일.jsonl"
    )
    assert written_missing_file == 1

    assert list(iter_manual_samples(None, "train")) == []
    assert list(iter_manual_samples(tmp_path / "없는파일.jsonl", "train")) == []


def test_manual_samples_respect_own_split_field(tmp_path, raw_dir):
    manual_path = tmp_path / "manual.jsonl"
    _write_manual(manual_path, [
        {
            "question": "만기가 언제예요?", "answer": "안내드립니다.", "follow_up_question": "감사합니다.",
            "output": "만기일을 확인해 드립니다.", "split": "val", "extendable": True,
        },
        {
            "question": "만기가 언제예요?", "answer": "안내드립니다.", "follow_up_question": "감사합니다.",
            "output": "만기일을 확인해 드립니다.", "extendable": True,  # split 생략 → train
        },
    ])
    split_path = _split_path(tmp_path, {})
    out_train = tmp_path / "train.jsonl"
    out_val = tmp_path / "val.jsonl"

    written_train = build_dataset(raw_dir, split_path, out_train, split="train", manual_path=manual_path)
    written_val = build_dataset(raw_dir, split_path, out_val, split="val", manual_path=manual_path)

    assert written_train == MANUAL_COPIES
    assert written_val == 1  # 복제는 train에서만


def test_manual_samples_go_through_same_cleaning_and_duplication(tmp_path, raw_dir):
    manual_path = tmp_path / "manual.jsonl"
    _write_manual(manual_path, [
        {
            "question": "연장되나요?", "answer": "확인해 드리겠습니다.", "follow_up_question": "감사합니다.",
            "output": "연장은 불가합니다.",  # 정제는 통과
        },
        {
            "question": "금리가 얼마예요?", "answer": "확인해 드리겠습니다.", "follow_up_question": "감사합니다.",
            "output": "금리는 연 3.5%입니다.",  # input에 없는 숫자 → 정제 제외
        },
    ])
    split_path = _split_path(tmp_path, {})
    out_path = tmp_path / "out.jsonl"

    written = build_dataset(raw_dir, split_path, out_path, split="train", manual_path=manual_path)

    assert written == MANUAL_COPIES  # 수동 샘플은 MANUAL_COPIES배(NO_EXTEND 복제와 겹치지 않는다), 금리 샘플은 제외


def test_field_name_change_only_requires_extract_turns_patch(tmp_path, raw_dir, monkeypatch):
    """필드명이 다른 가상의 스키마도 _extract_turns만 바꾸면 나머지 함수는 그대로 동작한다."""
    alt_entry = {
        "sid": "s-alt",
        "qid": "q-alt",
        "topic_alt": TOPIC,
        "q": "만기가 언제예요?",
        "a": "안내드립니다.",
        "f": "감사합니다.",
        "out": "만기일을 확인해 드립니다.",
    }
    _write_zip(raw_dir / "TL_은행.zip", [alt_entry])
    _write_zip(raw_dir / "VL_은행.zip", [])
    split_path = _split_path(tmp_path, {"s-alt": "train"})

    def fake_extract_turns(raw: dict) -> dict:
        return {
            "source_id": raw["sid"],
            "qa_id": raw["qid"],
            "topic": raw["topic_alt"],
            "question": raw["q"],
            "answer": raw["a"],
            "follow_up_question": raw["f"],
            "output": raw["out"],
        }

    monkeypatch.setattr(prepare, "_extract_turns", fake_extract_turns)

    items = list(iter_conversations(raw_dir, split_path, "train"))

    assert [item["source_id"] for item in items] == ["s-alt"]


# ---------------------------------------------------------------------------
# 수동 샘플: maturity_date, 히스토리 없는 to_messages, MANUAL_COPIES, limit
# ---------------------------------------------------------------------------

_MANUAL_ROW = {
    "question": "제 대출 만기가 언제예요?", "answer": "", "follow_up_question": "",
    "output": "고객님의 {{loan_label}} 만기일은 2030-12-31입니다.",
    "extendable": True, "maturity_date": "2030-12-31",
}


def test_iter_manual_samples_reads_maturity_date(tmp_path):
    path = tmp_path / "manual.jsonl"
    _write_manual(path, [_MANUAL_ROW, {k: v for k, v in _MANUAL_ROW.items() if k != "maturity_date"}])

    items = list(iter_manual_samples(path))

    assert items[0]["maturity_date"] == "2030-12-31"
    assert "maturity_date" not in items[1]


def test_is_clean_accepts_answer_date_from_maturity_date_field():
    item = _clean_item(question="만기가 언제예요?", output="만기일은 2030-12-31입니다.")
    assert is_clean(item) is False  # maturity_date 없이는 input에 없는 숫자
    assert is_clean({**item, "maturity_date": "2030-12-31"}) is True
    assert is_clean({**item, "maturity_date": "2031-01-01"}) is False  # 다른 날짜는 여전히 걸린다


def test_to_messages_without_history_is_three_turns_with_info_line():
    item = _clean_item(question="만기가 언제예요?", output="만기일은 2030-12-31입니다.")
    item = {**item, "answer": "", "follow_up_question": ""}

    messages = to_messages(item, True, "2030-12-31")

    assert [m["role"] for m in messages] == ["system", "user", "assistant"]
    assert messages[1]["content"].startswith("만기가 언제예요?\n대출 정보:")
    assert "만기일=2030-12-31" in messages[1]["content"]
    assert "연장 가능=예" in messages[1]["content"]
    assert messages[2]["content"] == "만기일은 2030-12-31입니다."


def test_to_messages_without_history_matches_runtime_prompt():
    from app.agents.loan.prompt import build_messages

    item = {**_clean_item(question="만기가 언제예요?"), "answer": "", "follow_up_question": ""}
    loan = {"product_type": "신용대출", "maturity_date": "2030-12-31", "extendable": False}

    assert to_messages(item, False, "2030-12-31")[:2] == build_messages([], "만기가 언제예요?", loan)


def _empty_split(tmp_path, raw_dir):
    _write_zip(raw_dir / "TL_은행.zip", [])
    _write_zip(raw_dir / "VL_은행.zip", [])
    return _split_path(tmp_path, {})


def test_manual_copies_keep_original_maturity_date(tmp_path, raw_dir):
    assert MANUAL_COPIES >= 2
    manual_path = tmp_path / "manual.jsonl"
    _write_manual(manual_path, [_MANUAL_ROW])
    out_path = tmp_path / "out.jsonl"

    written = build_dataset(raw_dir, _empty_split(tmp_path, raw_dir), out_path, manual_path=manual_path)

    assert written == MANUAL_COPIES
    for line in out_path.read_text(encoding="utf-8").splitlines():
        messages = json.loads(line)["messages"]
        assert "만기일=2030-12-31" in messages[1]["content"]
        assert is_valid_output(messages[2]["content"], maturity_date="2030-12-31", extendable=True)


def test_manual_copies_keep_maturity_date_even_with_negative_evidence(tmp_path, raw_dir):
    # 예전에는 연장 불가 근거가 있으면 복제본이 _ALT_MATURITY로 바뀌어 답 날짜와 어긋났다
    row = {**_MANUAL_ROW, "output": "연장은 불가합니다. 만기일은 2030-12-31입니다.", "extendable": False}
    manual_path = tmp_path / "manual.jsonl"
    _write_manual(manual_path, [row])
    out_path = tmp_path / "out.jsonl"

    build_dataset(raw_dir, _empty_split(tmp_path, raw_dir), out_path, manual_path=manual_path)

    for line in out_path.read_text(encoding="utf-8").splitlines():
        assert "만기일=2030-12-31" in json.loads(line)["messages"][1]["content"]


def test_auto_negative_copy_still_uses_alt_maturity(tmp_path, raw_dir):
    entry = _entry("s-no", "q-no", "연장되나요?", "확인합니다.", "네.", "연장은 불가합니다.")
    _write_zip(raw_dir / "TL_은행.zip", [entry])
    _write_zip(raw_dir / "VL_은행.zip", [])
    split_path = _split_path(tmp_path, {"s-no": "train"})
    out_path = tmp_path / "out.jsonl"

    build_dataset(raw_dir, split_path, out_path, split="train")

    infos = [json.loads(line)["messages"][3]["content"] for line in out_path.read_text(encoding="utf-8").splitlines()]
    assert len(infos) == NO_EXTEND_COPIES
    assert "만기일=2027-03-31" in infos[0]
    assert "만기일=2029-11-30" in infos[1]


def test_limit_applies_to_auto_samples_only(tmp_path, raw_dir):
    items = [
        _entry(f"s{i}", f"q{i}", "만기가 언제예요?", "안내드립니다.", "감사합니다.", "연장 신청이 가능합니다.")
        for i in range(3)
    ]
    _write_zip(raw_dir / "TL_은행.zip", items)
    _write_zip(raw_dir / "VL_은행.zip", [])
    split_path = _split_path(tmp_path, {f"s{i}": "train" for i in range(3)})
    manual_path = tmp_path / "manual.jsonl"
    _write_manual(manual_path, [_MANUAL_ROW])
    out_path = tmp_path / "out.jsonl"

    written = build_dataset(raw_dir, split_path, out_path, split="train", limit=1, manual_path=manual_path)

    assert written == 1 + MANUAL_COPIES  # 자동 1건(limit) + 수동 전부(복제 포함)
    lines = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]
    assert sum(1 for m in lines if len(m["messages"]) == 3) == MANUAL_COPIES


# ---------------------------------------------------------------------------
# manual_seed.jsonl 내용 검증 (make_manual_seed.py가 만든 파일)
# ---------------------------------------------------------------------------

_SEED_PATH = Path(__file__).resolve().parents[2] / "training" / "loan" / "manual_seed.jsonl"
_D_YES, _D_NO = "2027-03-31", "2035-06-30"  # mock 고객의 만기일(C002 연장 가능, C003 연장 불가)


@pytest.fixture(scope="module")
def seed_rows() -> list[dict]:
    return [json.loads(line) for line in _SEED_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def _seed_category(row: dict) -> str:
    return row["source_id"].rsplit("-", 1)[0]


def test_seed_rows_pass_cleaning_and_runtime_validation(seed_rows):
    from app.masking import mask

    assert seed_rows
    for row in seed_rows:
        assert row["answer"] == "" and row["follow_up_question"] == ""
        assert is_clean(row), row["source_id"]
        assert is_valid_output(row["output"], maturity_date=row["maturity_date"], extendable=row["extendable"]), (
            row["source_id"]
        )
        assert mask(row["question"]).masked_text == row["question"], row["source_id"]
        assert mask(row["output"]).masked_text == row["output"], row["source_id"]
        dates = re.findall(r"\d{4}-\d{2}-\d{2}", row["output"])
        assert all(d == row["maturity_date"] for d in dates), row["source_id"]


def test_seed_mock_dates_appear_with_both_extendable_values(seed_rows):
    # 날짜만 보고 연장 여부를 맞히는 지름길을 막는다: 만기·연장·원금 질문마다 mock 날짜와 반대 연장 여부 조합이 3건 이상
    cross = ((_D_YES, False), (_D_NO, True))
    for category_prefix in ("manual-maturity", "manual-extend", "manual-principal"):
        rows = [r for r in seed_rows if r["source_id"].startswith(category_prefix)]
        for date, extendable in cross:
            count = sum(1 for r in rows if r["maturity_date"] == date and r["extendable"] is extendable)
            assert count >= 3, (category_prefix, date, extendable, count)


def test_seed_mock_dates_are_not_skewed_toward_one_extendable_value(seed_rows):
    for date in (_D_YES, _D_NO):
        flags = [r["extendable"] for r in seed_rows if r["maturity_date"] == date]
        assert 0.35 <= sum(flags) / len(flags) <= 0.65, (date, sum(flags), len(flags))


def test_seed_slot_sentences_have_variety(seed_rows):
    def outputs(prefix):
        return {r["output"] for r in seed_rows if r["source_id"].startswith(prefix)}

    def questions(prefix):
        return {r["question"] for r in seed_rows if r["source_id"].startswith(prefix)}

    assert 3 <= len(outputs("manual-extend-yes")) <= 4
    assert 3 <= len(outputs("manual-extend-no")) <= 4
    assert 3 <= len(outputs("manual-why")) <= 8
    assert len(questions("manual-extend-yes")) >= 14
    assert len(questions("manual-maturity")) >= 10
    counts = {}
    for r in seed_rows:
        counts[r["output"]] = counts.get(r["output"], 0) + 1
    assert max(counts.values()) <= 6


def test_seed_request_samples_use_same_tail_for_both_cases(seed_rows):
    rows = [r for r in seed_rows if r["source_id"].startswith("manual-request")]
    assert {r["extendable"] for r in rows} == {True, False}
    for r in rows:
        assert r["output"].endswith("자세한 사항은 상담원에게 확인해 주세요."), r["source_id"]
        assert "신청은 상담원" not in r["output"]
