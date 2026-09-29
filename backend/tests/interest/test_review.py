import json

import pytest

from training.interest.review import decide, load_reviews, render, review_queue, run, save_reviews

ITEM = {"loan_id": "L000", "product_type": "신용대출", "repayment_method": "만기일시", "interest_type": "변동",
        "payment_method": "자동이체", "next_due_date": "2026-10-15", "interest_due": 58000,
        "overdue_amount": 0, "overdue_days": 0}


def record(rid, origin="aihub", answer="다음 납부일에 맞춰 납부해 주세요."):
    return {
        "id": rid, "origin": origin, "item": ITEM, "category": "general", "scenario": "normal",
        "messages": [
            {"role": "system", "content": "시스템"},
            {"role": "user", "content": "이전 질문"},
            {"role": "assistant", "content": "이전 답변"},
            {"role": "user", "content": "이자 언제 내요?\n이자 정보: 종류=신용대출, 다음 납부일=2026-10-15\n사용할 수 있는 슬롯: {{loan_label}}, {{interest_due}}"},
            {"role": "assistant", "content": answer},
        ],
    }


def test_queue_only_unreviewed_aihub():
    candidates = [record("a1"), record("s1", origin="synth"), record("a2"), record("a3")]
    queue = review_queue(candidates, reviews={"a2": {"ok": True}})
    assert [r["id"] for r in queue] == ["a1", "a3"]


def test_render_shows_context_question_info_and_answer():
    text = render(record("a1"), position=(1, 3))
    for part in ("[1/3] a1", "이전 질문", "이전 답변", "이자 언제 내요?", "이자 정보: 종류=신용대출", "다음 납부일에 맞춰 납부해 주세요."):
        assert part in text
    assert "시스템" not in text  # 시스템 프롬프트는 모든 샘플이 같아 보여 주지 않는다


def test_decide_approve_reject_edit():
    r = record("a1")
    assert decide(r, "a") == {"ok": True, "note": ""}
    assert decide(r, "r", note="주제 밖") == {"ok": False, "note": "주제 밖"}
    assert decide(r, "e", text="다음 납부일은 2026-10-15입니다.", note="말투") == {
        "ok": True, "note": "말투", "output": "다음 납부일은 2026-10-15입니다."}


def test_decide_edit_must_pass_inference_validation():
    # 고친 정답도 추론 검증을 통과해야 한다(INT-004). prepare.apply_review와 같은 기준.
    with pytest.raises(ValueError):
        decide(record("a1"), "e", text="이자는 58,000원입니다.")


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "reviews.json"
    assert load_reviews(path) == {}
    save_reviews(path, {"a1": {"ok": True, "note": ""}})
    assert load_reviews(path) == {"a1": {"ok": True, "note": ""}}


def test_run_saves_after_each_decision_and_can_resume(tmp_path):
    path = tmp_path / "reviews.json"
    candidates = [record("a1"), record("a2"), record("a3")]
    inputs = iter(["a", "r", "주제 밖", "q"])
    run(candidates, path, ask=lambda _prompt: next(inputs), show=lambda _text: None)
    assert load_reviews(path) == {"a1": {"ok": True, "note": ""}, "a2": {"ok": False, "note": "주제 밖"}}

    inputs = iter(["e", "다음 납부일은 2026-10-15입니다.", ""])  # 이어서 a3만 남는다
    run(candidates, path, ask=lambda _prompt: next(inputs), show=lambda _text: None)
    assert load_reviews(path)["a3"]["output"] == "다음 납부일은 2026-10-15입니다."
    assert json.loads(path.read_text(encoding="utf-8"))["a1"]["ok"] is True


def test_run_retries_invalid_edit(tmp_path):
    path = tmp_path / "reviews.json"
    inputs = iter(["e", "이자는 58,000원입니다.", "e", "다음 납부일에 납부해 주세요.", "", "q"])
    messages = []
    run([record("a1")], path, ask=lambda _prompt: next(inputs), show=messages.append)
    assert load_reviews(path)["a1"]["output"] == "다음 납부일에 납부해 주세요."
    assert any("검증" in m for m in messages)
