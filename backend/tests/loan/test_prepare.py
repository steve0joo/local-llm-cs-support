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


def test_is_clean_accepts_number_present_in_input():
    item = _clean_item(
        question="2027-03-31에 만기인가요?",
        output="네, 2027-03-31에 만기입니다.",
    )
    assert is_clean(item) is True


def test_is_clean_rejects_document_keyword_not_in_input():
    item = _clean_item(output="재직증명서를 제출해 주세요.")
    assert is_clean(item) is False


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
    import random

    assert infer_extendable("연장 신청이 가능합니다.", random.Random(1)) is True


def test_infer_extendable_negative_requires_extension_context():
    import random

    assert infer_extendable("연장은 불가합니다.", random.Random(1)) is False


def test_infer_extendable_unrelated_negation_is_not_negative_evidence():
    import random

    # "불가"가 있지만 "연장"과 무관하다 — 부정 근거로 세지 않는다(무작위 배정 대상)
    result = infer_extendable("환불은 불가합니다.", random.Random(1))
    assert result in (True, False)  # 무작위 배정. 값 자체보다 "복제 대상이 아님"이 핵심(아래 복제 테스트에서 확인)


def test_infer_extendable_ambiguous_returns_none():
    import random

    assert infer_extendable("연장은 불가합니다. 다른 조건은 가능합니다.", random.Random(1)) is None


def test_infer_extendable_negation_word_inside_positive_is_not_negative():
    import random

    # "없"이 들어 있지만 부정 표현이 아니다(서류 "없이") — 긍정으로 판정
    assert infer_extendable("서류 없이 연장 신청이 가능합니다.", random.Random(1)) is True


def test_infer_extendable_is_deterministic_per_source_id():
    import random

    output = "상담원에게 확인해 주세요."  # 판정 근거 없음 → 무작위, 단 같은 시드면 같은 값
    first = infer_extendable(output, random.Random("s1"))
    second = infer_extendable(output, random.Random("s1"))
    assert first == second


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
    clean = _entry("s-clean", "q-clean", "만기가 언제예요?", "안내드립니다.", "감사합니다.", "만기일을 확인해 드립니다.")
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


def test_build_dataset_does_not_duplicate_random_negative(tmp_path, raw_dir):
    # 판정 근거가 없어 무작위로 "아니오"가 나온 경우는 복제 대상이 아니다(연장 언급 자체가 없음)
    neutral = _entry("s-neutral", "q-neutral", "다른 질문", "안내드립니다.", "감사합니다.", "상담원에게 확인해 주세요.")
    _write_zip(raw_dir / "TL_은행.zip", [neutral])
    _write_zip(raw_dir / "VL_은행.zip", [])
    split_path = _split_path(tmp_path, {"s-neutral": "train"})
    out_path = tmp_path / "out.jsonl"

    build_dataset(raw_dir, split_path, out_path, split="train")

    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1  # 무작위 배정은 예·아니오 어느 쪽이든 복제되지 않는다


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
        _entry(f"s{i}", f"q{i}", "만기가 언제예요?", "안내드립니다.", "감사합니다.", "만기일을 확인해 드립니다.")
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
    auto_item = _entry("s-auto", "q-auto", "만기가 언제예요?", "안내드립니다.", "감사합니다.", "만기일을 확인해 드립니다.")
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

    assert written == 2  # 자동 추출 1건 + 수동 1건
    lines = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]
    manual_line = next(line for line in lines if "연장 신청이 가능합니다." in line["messages"][4]["content"])
    assert "연장 가능=예" in manual_line["messages"][3]["content"]


def test_manual_samples_file_missing_or_none_does_not_break(tmp_path, raw_dir):
    auto_item = _entry("s-auto", "q-auto", "만기가 언제예요?", "안내드립니다.", "감사합니다.", "만기일을 확인해 드립니다.")
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
            "output": "만기일을 확인해 드립니다.", "split": "val",
        },
        {
            "question": "만기가 언제예요?", "answer": "안내드립니다.", "follow_up_question": "감사합니다.",
            "output": "만기일을 확인해 드립니다.",  # split 생략 → train
        },
    ])
    split_path = _split_path(tmp_path, {})
    out_train = tmp_path / "train.jsonl"
    out_val = tmp_path / "val.jsonl"

    written_train = build_dataset(raw_dir, split_path, out_train, split="train", manual_path=manual_path)
    written_val = build_dataset(raw_dir, split_path, out_val, split="val", manual_path=manual_path)

    assert written_train == 1
    assert written_val == 1


def test_manual_samples_go_through_same_cleaning_and_duplication(tmp_path, raw_dir):
    manual_path = tmp_path / "manual.jsonl"
    _write_manual(manual_path, [
        {
            "question": "연장되나요?", "answer": "확인해 드리겠습니다.", "follow_up_question": "감사합니다.",
            "output": "연장은 불가합니다.",  # 정제는 통과, 연장 불가 근거 있음 → 2배 복제 대상
        },
        {
            "question": "금리가 얼마예요?", "answer": "확인해 드리겠습니다.", "follow_up_question": "감사합니다.",
            "output": "금리는 연 3.5%입니다.",  # input에 없는 숫자 → 정제 제외
        },
    ])
    split_path = _split_path(tmp_path, {})
    out_path = tmp_path / "out.jsonl"

    written = build_dataset(raw_dir, split_path, out_path, split="train", manual_path=manual_path)

    assert written == 2  # 연장불가 샘플 2배 복제, 금리 샘플은 제외


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
