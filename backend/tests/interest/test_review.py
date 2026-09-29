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


# --- AI Hub 답 수정(--fix): 표현 문제로 빠진 train 샘플을 고쳐서만 되살린다 ------------------------


def fix_record(rid, reason="invalid", answer="고객센터로 문의해 주세요."):
    return {**record(rid, answer=answer), "needs_fix": reason}


def test_edit_uses_training_checks_not_only_inference():
    # 학습 데이터 제외 규칙(약속·처리 주장 등)도 적용한다. 이자 정보의 날짜는 사실이라 허용한다.
    with pytest.raises(ValueError, match="promise"):
        decide(record("a1"), "e", text="확인 후 연락드리겠습니다.")
    with pytest.raises(ValueError, match="digit"):
        decide(record("a1"), "e", text="밤 11시까지 입금해 주세요.")
    assert decide(record("a1"), "e", text="다음 납부일은 2026-10-15입니다.")["output"] == "다음 납부일은 2026-10-15입니다."


def test_render_fix_shows_reason_and_problems():
    text = render(fix_record("a1"), position=(1, 2))
    assert "고칠 이유: invalid" in text and "지어낸 채널" in text


def test_run_fix_requires_edit_or_reject(tmp_path):
    path = tmp_path / "reviews.json"
    messages = []
    inputs = iter(["a", "e", "납부 관련 자세한 사항은 상담원에게 확인해 주세요.", "채널 삭제", "r", "주제 밖"])
    run([fix_record("a1"), fix_record("a2", reason="promise", answer="확인 후 연락드리겠습니다.")], path,
        ask=lambda _prompt: next(inputs), show=messages.append, fix=True)
    reviews = load_reviews(path)
    assert reviews["a1"] == {"ok": True, "note": "채널 삭제", "output": "납부 관련 자세한 사항은 상담원에게 확인해 주세요."}
    assert reviews["a2"] == {"ok": False, "note": "주제 밖"}
    assert any("고친 답" in m for m in messages)  # 승인만은 안 된다는 안내


def test_main_fix_reads_fix_queue(tmp_path):
    from training.interest.review import main

    (tmp_path / "fix_queue.jsonl").write_text(json.dumps(fix_record("a1"), ensure_ascii=False) + "\n", encoding="utf-8")
    (tmp_path / "candidates.jsonl").write_text("", encoding="utf-8")
    path = tmp_path / "reviews.json"
    import builtins

    answers = iter(["r", "주제 밖"])
    original = builtins.input
    builtins.input = lambda _prompt="": next(answers)
    try:
        main(["--fix", "--data-dir", str(tmp_path), "--reviews", str(path)])
    finally:
        builtins.input = original
    assert load_reviews(path) == {"a1": {"ok": False, "note": "주제 밖"}}


def test_main_fix_can_filter_reasons(tmp_path):
    # 고칠 양이 많아 사유별로 나눠 한다(예: 지어낸 표현·약속부터).
    from training.interest.review import main

    rows = [fix_record("a1", "document"), fix_record("a2", "promise", "확인 후 연락드리겠습니다."), fix_record("a3", "invalid")]
    (tmp_path / "fix_queue.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    path = tmp_path / "reviews.json"
    import builtins

    answers = iter(["r", "x", "r", "y"])
    original = builtins.input
    builtins.input = lambda _prompt="": next(answers)
    try:
        main(["--fix", "--reasons", "invalid,promise", "--data-dir", str(tmp_path), "--reviews", str(path)])
    finally:
        builtins.input = original
    assert set(load_reviews(path)) == {"a2", "a3"}
