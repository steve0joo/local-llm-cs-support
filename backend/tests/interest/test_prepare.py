import json

import pytest

from app.agents.interest.prompt import SYSTEM_PROMPT
from training.interest.prepare import (
    assign_split,
    categorize,
    build_dataset,
    build_sample,
    convert_amounts,
    load_qas,
    normalize_input,
)

TOPIC = "이자/연체금액"


def qa(output, question="이번 달 이자 얼마예요?", answer="확인해 드리겠습니다.", follow_up="얼마인가요?", **kw):
    return {
        "source_id": kw.get("source_id", "S1"),
        "qa_id": kw.get("qa_id", "S1_001"),
        "qa_topic": kw.get("qa_topic", TOPIC),
        "question": question,
        "answer": answer,
        "follow_up": follow_up,
        "output": output,
    }


def identity(text):
    return text


# --- 로드 ---------------------------------------------------------------


def test_load_qas_reads_topic_folder(tmp_path):
    doc = {
        "source": {"source_id": "21-1_bk_06_000001"},
        "consulting": {"consulting_topic": TOPIC},
        "qa_data": [
            {
                "qa_id": "21-1_bk_06_000001_001",
                "qa_topic": TOPIC,
                "input": {"question": "q", "answer": "a", "follow_up_question": "f"},
                "output": "o",
            }
        ],
    }
    (tmp_path / "a.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    [row] = load_qas(tmp_path)
    assert row == {
        "source_id": "21-1_bk_06_000001",
        "qa_id": "21-1_bk_06_000001_001",
        "qa_topic": TOPIC,
        "question": "q",
        "answer": "a",
        "follow_up": "f",
        "output": "o",
    }


def test_load_qas_skips_underscore_files(tmp_path):
    # 03_interest/_manifest.json 같은 설명 파일은 학습 원천이 아니다.
    (tmp_path / "_manifest.json").write_text('{"files": 1}', encoding="utf-8")
    assert load_qas(tmp_path) == []


def test_raw_dir_is_interest_folder():
    from training.interest.prepare import RAW_DIR

    assert RAW_DIR.parts[-2:] == ("raw", "03_interest")


# --- 입력 정규화 -----------------------------------------------------------


def test_normalize_input_replaces_bank_and_amounts():
    text = normalize_input("★★은행 대출 이자가 ●●● ●●원 나왔고 ●● ●원 더 냈어요. ■■■입니다.")
    assert text == "은행 대출 이자가 [금액_1] 나왔고 [금액_2] 더 냈어요. ○○입니다."


# --- 금액 → 슬롯 ------------------------------------------------------------


@pytest.mark.parametrize(
    ("output", "expected", "slots"),
    [
        ("연체 금액은 ●●●● ●● 원으로 확인됩니다.", "연체 금액은 {{overdue_amount}}으로 확인됩니다.", {"overdue_amount"}),
        ("현재 연체금액은 ○○○원입니다.", "현재 연체금액은 {{overdue_amount}}입니다.", {"overdue_amount"}),
        ("미납된 금액은 1,200,000원입니다.", "미납된 금액은 {{overdue_amount}}입니다.", {"overdue_amount"}),
        ("이번 달 이자 금액은 약 ●●●원입니다.", "이번 달 이자 금액은 {{interest_due}}입니다.", {"interest_due"}),
        ("대출 이자는 ○○원이며 납부일에 출금됩니다.", "대출 이자는 {{interest_due}}이며 납부일에 출금됩니다.", {"interest_due"}),
        ("금액 없이 안내합니다.", "금액 없이 안내합니다.", set()),
    ],
)
def test_convert_amounts(output, expected, slots):
    assert convert_amounts(output) == (expected, slots)


@pytest.mark.parametrize(
    "output",
    [
        "현재 남은 원금은 ●●●원입니다.",  # 원금은 이 에이전트 슬롯이 아니다
        "원금과 이자를 합한 금액은 ●●●● ●● 원입니다.",  # 이자만의 금액이 아니다
        "총 납부 금액은 ○○○원입니다.",
        "연체 이자는 ○○○원입니다.",  # 연체 금액이 아니라 연체 이자
    ],
)
def test_convert_amounts_rejects_ambiguous(output):
    assert convert_amounts(output) is None


# --- 샘플 생성과 제외 규칙 ----------------------------------------------------


def test_sample_follows_inference_format():
    sample, reason = build_sample(qa("고객님의 연체 금액은 ●●● ●● 원이며, 빠른 납부를 부탁드립니다."), identity)
    assert reason is None
    messages = sample["messages"]

    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user", "assistant"]
    assert messages[0]["content"] == SYSTEM_PROMPT
    last_user = messages[3]["content"]
    assert last_user.startswith("얼마인가요?\n이자 정보: 종류=")
    assert "연체 여부=연체 중" in last_user  # 출력이 연체 금액을 말하므로 연체 상태여야 모순이 없다
    assert last_user.endswith("{{overdue_amount}}")
    assert messages[4]["content"] == "고객님의 연체 금액은 {{overdue_amount}}이며, 빠른 납부를 부탁드립니다."
    assert sample["source_id"] == "S1"


def test_sample_without_overdue_mention_is_not_overdue():
    sample, _ = build_sample(qa("납부일에 맞춰 자동이체 계좌에 잔액을 준비해 주세요."), identity)
    assert "연체 여부=연체 없음" in sample["messages"][3]["content"]


def test_sample_item_is_deterministic():
    a, _ = build_sample(qa("안내해 드렸습니다."), identity)
    b, _ = build_sample(qa("안내해 드렸습니다."), identity)
    assert a == b


def test_masking_applied_to_user_side_only():
    calls = []

    def fake_mask(text):
        calls.append(text)
        return text.replace("010-1234-5678", "[전화번호_1]")

    sample, _ = build_sample(qa("안내해 드렸습니다.", question="제 번호 010-1234-5678이에요"), fake_mask)
    assert sample["messages"][1]["content"] == "제 번호 [전화번호_1]이에요"
    assert "010-1234-5678" not in json.dumps(sample, ensure_ascii=False)


@pytest.mark.parametrize(
    ("output", "reason"),
    [
        ("연체 시 일일 0.03%가 가산됩니다.", "rate"),
        ("현재 남은 원금은 ●●●원입니다.", "amount"),
        ("밤 11시까지 입금해 주세요.", "digit"),
        ("●월 ●●일에 출금됩니다.", "deid"),
        ("신분증 사본과 거래내역서가 필요합니다.", "document"),
        ("앱의 '대출 관리' 메뉴에서 확인하실 수 있습니다.", "menu"),
        ("하나은행 앱에서 확인해 주세요.", "bank"),
        ("", "empty"),
    ],
)
def test_excluded_outputs(output, reason):
    sample, got = build_sample(qa(output), identity)
    assert sample is None
    assert got == reason


def test_other_qa_topic_is_excluded():
    assert build_sample(qa("안내해 드렸습니다.", qa_topic="거래내역/잔액조회"), identity) == (None, "topic")


def test_bank_placeholder_in_output_is_normalized():
    sample, _ = build_sample(qa("★★은행 상담원에게 문의해 주세요."), identity)
    assert sample["messages"][4]["content"] == "은행 상담원에게 문의해 주세요."


@pytest.mark.parametrize(
    ("output", "reason"),
    [
        ("현재 청약 담보 대출에 대해 납부일에 맞춰 출금됩니다.", "product"),
        ("소상공인 대출 이자는 매월 출금됩니다.", "product"),
        ("지금 바로 신청 절차를 모두 완료해 드렸습니다.", "claim"),
        ("서비스가 정상적으로 적용되었습니다.", "claim"),
        ("고객님께서는 내일 납부하실 이자를 확인하고자 하셨습니다. 확인해 드렸습니다.", "summary"),
        # 챗봇이 고객에게 개인정보·인증정보를 요구하면 안 된다(마스킹 원칙, 인수 기준 5).
        ("성함과 주민등록번호 앞 네 자리, 계좌 비밀번호를 알려 주시면 확인해 드리겠습니다.", "pii_request"),
        ("본인 확인을 위해 생년월일을 말씀해 주세요.", "pii_request"),
        ("휴대폰으로 받으신 인증번호를 입력해 주세요.", "pii_request"),
        # 챗봇이 나중에 할 수 없는 일을 약속하면 지어낸 사실이 된다(문자 발송·연락·연결·확인).
        ("확인 후 문자로 발송해 드리겠습니다.", "promise"),
        ("담당자가 확인 후 연락드리겠습니다.", "promise"),
        ("상담원에게 연결해 드리겠습니다.", "promise"),
        # 통화 상담의 대기 표현은 챗봇 답에 맞지 않는다.
        ("잠시만 기다려 주시면 확인 결과를 알려드립니다.", "call_context"),
        # 상담 톤: 마크다운·반말·6문장 이상(evaluate.tone_ok와 같은 기준).
        ("**연체 금액**은 상담원에게 확인해 주세요.", "tone"),
        ("이자는 다음 납부일에 나가.", "tone"),
    ],
)
def test_more_excluded_outputs(output, reason):
    assert build_sample(qa(output), identity) == (None, reason)


def test_generic_product_in_output_sets_item_product():
    # 정답이 말하는 대출 종류와 이자 정보 줄의 종류가 모순되지 않게 한다.
    sample, _ = build_sample(qa("신용대출 이자는 납부일에 자동으로 출금됩니다.", qa_id="X_1"), identity)
    assert "종류=신용대출" in sample["messages"][3]["content"]


@pytest.mark.parametrize(
    ("output", "field", "value"),
    [
        ("안내해 드린 가상계좌로 납부일에 입금해 주세요.", "payment_method", "가상계좌 입금"),
        ("납부일에 자동이체로 출금됩니다.", "payment_method", "자동이체"),
        ("원리금균등 방식이라 매달 같은 금액이 나갑니다.", "repayment_method", "원리금균등"),
        ("변동금리 상품이라 금리가 바뀔 수 있습니다.", "interest_type", "변동"),
    ],
)
def test_output_terms_set_item_values(output, field, value):
    # 정답이 말하는 방식과 이자 정보 줄이 모순되지 않게 한다.
    sample, _ = build_sample(qa(output), identity)
    assert sample["item"][field] == value


def test_record_fields():
    sample, _ = build_sample(qa("금리는 상담원에게 확인해 주세요.", question="금리 몇 %예요?"), identity)
    assert sample["id"] == "S1_001" and sample["origin"] == "aihub"
    assert sample["group_id"] == sample["source_id"] == "S1"
    assert sample["category"] == "rate" and sample["scenario"] == "normal"
    assert sample["reviewed"] is False and sample["review_note"] == ""


@pytest.mark.parametrize(
    ("text", "category"),
    [
        ("금리가 몇 %예요?", "rate"),
        ("연체된 거 있어요?", "overdue_status"),
        ("이자 언제 빠져나가요?", "due_date"),
        ("이번 달 이자 얼마예요?", "interest_amount"),
        ("가상계좌 번호 알려 주세요", "general"),
    ],
)
def test_categorize(text, category):
    assert categorize(text) == category


def test_overdue_question_without_amount_slot_is_invalid():
    # 연체 상태를 묻는 질문(follow_up)에 연체 금액 없이 답하면 추론 때 대체되므로 제외한다.
    sample, reason = build_sample(qa("현재 연체 중이시니 빠른 납부 부탁드립니다.", follow_up="연체된 거 있어요?"), identity)
    assert (sample, reason) == (None, "invalid")


# --- 분할 ------------------------------------------------------------------


def test_split_is_by_source_id_and_deterministic():
    assert assign_split("21-1_bk_06_000001") == assign_split("21-1_bk_06_000001")
    splits = {assign_split(f"S{i}") for i in range(200)}
    assert splits == {"train", "val", "test"}


def test_split_map_takes_priority():
    assert assign_split("S1", {"S1": "test"}) == "test"
    assert assign_split("S2", {"S1": "test"}) is None  # 공통 분할에 없는 상담은 쓰지 않는다


# --- 전체 ------------------------------------------------------------------


def test_build_dataset_counts():
    rows = [
        qa("이자 금액은 ●●●원입니다.", source_id="A", qa_id="A_1"),
        qa("연 5%가 적용됩니다.", source_id="B", qa_id="B_1"),
        qa("밤 11시까지 입금해 주세요.", source_id="C", qa_id="C_1"),
    ]
    splits, candidates, stats = build_dataset(
        rows, identity, split_map={"A": "train", "B": "train", "C": "val"}, include_unreviewed=True
    )
    assert len(splits["train"]) == 1 and splits["val"] == [] and splits["test"] == []
    assert [c["id"] for c in candidates] == ["A_1"]
    assert stats["aihub_total"] == 3
    assert stats["excluded"] == {"rate": 1, "digit": 1}
    assert stats["used"] == {"train": 1, "val": 0, "test": 0}


def test_unreviewed_records_are_not_used_by_default():
    rows = [qa("이자 금액은 ●●●원입니다.", source_id="A", qa_id="A_1")]
    splits, candidates, stats = build_dataset(rows, identity, split_map={"A": "train"})
    assert splits["train"] == [] and len(candidates) == 1
    assert stats["skipped_unreviewed"] == 1


def test_reviews_approve_reject_and_correct():
    rows = [
        qa("안내해 드렸습니다.", source_id="A", qa_id="A_1"),
        qa("안내해 드렸습니다.", source_id="B", qa_id="B_1"),
        qa("안내해 드렸습니다.", source_id="C", qa_id="C_1"),
    ]
    reviews = {
        "A_1": {"ok": True},
        "B_1": {"ok": False, "note": "주제 밖"},
        "C_1": {"ok": True, "output": "다음 납부일에 맞춰 납부해 주세요.", "note": "말투 수정"},
    }
    splits, _, stats = build_dataset(rows, identity, split_map={"A": "train", "B": "train", "C": "train"}, reviews=reviews)
    used = {r["id"]: r for r in splits["train"]}
    assert set(used) == {"A_1", "C_1"}
    assert used["C_1"]["messages"][-1]["content"] == "다음 납부일에 맞춰 납부해 주세요."
    assert used["C_1"]["review_note"] == "말투 수정" and used["C_1"]["reviewed"] is True
    assert stats["rejected"] == 1


def test_invalid_correction_is_refused():
    rows = [qa("안내해 드렸습니다.", source_id="A", qa_id="A_1")]
    with pytest.raises(ValueError, match="A_1"):
        build_dataset(rows, identity, split_map={"A": "train"}, reviews={"A_1": {"ok": True, "output": "이자는 5,000원입니다."}})


def test_synth_goes_to_train_only():
    # 합성은 템플릿 문장이 반복되므로 평가(val·test)에 넣지 않는다. 평가는 AI Hub 분할과 자체 점검 셋으로 한다.
    synth = [
        {"id": f"s{i}", "origin": "synth", "group_id": f"tpl-{i}", "category": "rate", "scenario": "normal",
         "reviewed": True, "review_note": "", "messages": [{"role": "assistant", "content": "x"}]}
        for i in range(30)
    ]
    splits, _, stats = build_dataset([], identity, synth=synth)
    assert len(splits["train"]) == 30 and splits["val"] == [] and splits["test"] == []
    assert stats["by_origin"] == {"synth": 30}


# --- 임시 마스킹(app.masking 머지 전) -------------------------------------------


def test_fallback_mask_uses_contract_tokens():
    from training.interest.prepare import fallback_mask

    text = fallback_mask("010-1234-5678로 연락 주시고 50만원, 50만원, 3,000원 냈어요")
    assert text == "[전화번호_1]로 연락 주시고 [금액_1], [금액_1], [금액_2] 냈어요"


# --- 출력 폴더 지정(04 폴더 등) -------------------------------------------------


def test_main_writes_to_out_dir(tmp_path, monkeypatch):
    import training.interest.prepare as prepare

    raw = tmp_path / "raw"
    raw.mkdir()
    doc = {
        "source": {"source_id": "S9"},
        "consulting": {"consulting_topic": TOPIC},
        "qa_data": [{"qa_id": "S9_001", "qa_topic": TOPIC,
                     "input": {"question": "이자 얼마예요?", "answer": "확인해 드리겠습니다.", "follow_up_question": "네"},
                     "output": "다음 납부일에 맞춰 납부해 주세요."}],
    }
    (raw / "a.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(prepare, "RAW_DIR", raw)
    monkeypatch.setattr(prepare, "SPLIT_FILE", tmp_path / "none.json")
    monkeypatch.setattr(prepare, "REVIEWS_FILE", tmp_path / "none2.json")
    out = tmp_path / "04"

    prepare.main(["--include-unreviewed", "--allow-fallback-mask", "--out-dir", str(out)])

    names = {p.name for p in out.iterdir()}
    assert {"train.jsonl", "val.jsonl", "test.jsonl", "candidates.jsonl", "stats.json"} <= names
    stats = json.loads((out / "stats.json").read_text(encoding="utf-8"))
    assert stats["aihub_total"] == 1 and stats["out_dir"] == str(out)


# --- 임시 마스킹 차단: 공통 app.masking이 없으면 명시적으로 허용할 때만 임시 함수 ---------------


def test_resolve_mask_refuses_fallback_by_default(monkeypatch):
    import sys

    from training.interest.prepare import resolve_mask

    monkeypatch.setitem(sys.modules, "app.masking", None)  # 공통 마스킹이 없는 상태를 재현
    with pytest.raises(SystemExit, match="allow-fallback-mask"):
        resolve_mask(allow_fallback=False)
    fn, source = resolve_mask(allow_fallback=True)
    assert source == "fallback" and fn("010-1234-5678") == "[전화번호_1]"


def test_main_without_masking_and_flag_stops(tmp_path, monkeypatch):
    import sys

    import training.interest.prepare as prepare

    monkeypatch.setitem(sys.modules, "app.masking", None)
    with pytest.raises(SystemExit):
        prepare.main(["--out-dir", str(tmp_path / "x")])
    assert not (tmp_path / "x").exists()


def test_guidance_phrase_is_not_a_promise():
    # "안내해 드리겠습니다" 뒤에 안내 내용이 바로 이어지면 괜찮다.
    sample, reason = build_sample(qa("납부 방법을 안내해 드리겠습니다. 납부일에 맞춰 입금해 주세요."), identity)
    assert reason is None


def test_tone_ok_shared_with_evaluate():
    from training.interest import evaluate, prepare

    assert evaluate.tone_ok is prepare.tone_ok


# --- 수동 샘플(manual/qNN.json) 병합 ----------------------------------------------------


def test_main_with_manual_adds_train_only_records(tmp_path, monkeypatch):
    import training.interest.manual_data as manual_data
    import training.interest.prepare as prepare

    raw = tmp_path / "raw"
    raw.mkdir()
    manual = tmp_path / "manual"
    manual.mkdir()
    row = {"no": 1, "customer": "C002", "question": "이번 달 이자 얼마야?", "check": "", "v03_answer": "", "note": "",
           "source": "ok", "answer": "{{loan_label}}의 다음 납부일은 {due}이고, 납부하실 이자는 {{interest_due}}입니다.", "train": True}
    (manual / "q01.json").write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(prepare, "RAW_DIR", raw)
    monkeypatch.setattr(prepare, "SPLIT_FILE", tmp_path / "none.json")
    monkeypatch.setattr(prepare, "REVIEWS_FILE", tmp_path / "none2.json")
    monkeypatch.setattr(manual_data, "MANUAL_DIR", manual)
    out = tmp_path / "05"

    prepare.main(["--with-manual", "--allow-fallback-mask", "--out-dir", str(out)])

    train = [json.loads(line) for line in (out / "train.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(train) == 3 and {r["origin"] for r in train} == {"manual"}
    assert (out / "val.jsonl").read_text(encoding="utf-8") == ""
    stats = json.loads((out / "stats.json").read_text(encoding="utf-8"))
    assert stats["with_manual"] is True and stats["by_origin"] == {"manual": 3}


# --- 평가용 질문(test_questions.jsonl): 답 필터 없이 test 분할의 질문을 모두 쓴다 ------------------


def test_test_questions_use_all_test_split_questions_regardless_of_answer():
    from training.interest.prepare import build_test_questions

    rows = [
        qa("고객센터로 문의해 주세요.", source_id="T", qa_id="T_1", follow_up="연체된 거 있나요?"),  # 답이 필터에 걸려도 질문은 쓴다
        qa("이자는 5,000원입니다.", source_id="T", qa_id="T_2"),
        qa("다음 납부일에 납부해 주세요.", source_id="A", qa_id="A_1"),  # train 분할은 넣지 않는다
        qa("안내해 드립니다.", source_id="T", qa_id="T_3", qa_topic="거래내역/잔액조회"),
        qa("안내해 드립니다.", source_id="T", qa_id="T_4", follow_up="  "),
    ]
    cases = build_test_questions(rows, identity, split_map={"T": "test", "A": "train"})
    assert [c["id"] for c in cases] == ["T_1", "T_2"]
    first = cases[0]
    assert first["messages"][-1]["role"] == "user" and first["messages"][-1]["content"].startswith("연체된 거 있나요?\n이자 정보: ")
    assert first["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert first["item"]["overdue_days"] > 0 and first["scenario"] == "overdue"  # 연체를 묻는 질문은 연체 고객으로
    assert cases[1]["item"]["overdue_days"] == 0
    assert all("5,000" not in m["content"] for c in cases for m in c["messages"])  # 답은 쓰지 않는다


# --- AI Hub 답 수정: 표현 문제로 빠진 train 샘플을 사람이 고쳐 되살린다 ---------------------------


def test_answer_problems_uses_training_checks():
    from training.interest.prepare import answer_problems

    item = {"loan_id": "L000", "product_type": "신용대출", "repayment_method": "만기일시", "interest_type": "변동",
            "payment_method": "자동이체", "next_due_date": "2026-10-15", "interest_due": 58000,
            "overdue_amount": 0, "overdue_days": 0}
    assert answer_problems("다음 납부일에 맞춰 납부해 주세요.", item, "이자 언제 내요?") == []
    assert "promise" in answer_problems("확인 후 연락드리겠습니다.", item, "이자 언제 내요?")
    assert "invalid" in answer_problems("고객센터로 문의해 주세요.", item, "이자 언제 내요?")
    assert "digit" in answer_problems("밤 11시까지 입금해 주세요.", item, "이자 언제 내요?")


def test_fix_queue_has_only_fixable_train_samples():
    from training.interest.prepare import FIXABLE, build_fix_queue

    rows = [
        qa("고객센터로 문의해 주세요.", source_id="A", qa_id="A_1"),  # invalid(지어낸 채널) → 고칠 수 있음
        qa("확인 후 연락드리겠습니다.", source_id="A", qa_id="A_2"),  # promise
        qa("이자는 5,000원입니다.", source_id="A", qa_id="A_3"),  # 금액 숫자: 표현만 고쳐서는 안 됨
        qa("주민등록번호를 알려 주세요.", source_id="A", qa_id="A_4"),  # 개인정보 요구: 되살리지 않음
        qa("다음 납부일에 맞춰 납부해 주세요.", source_id="A", qa_id="A_5"),  # 이미 통과
        qa("고객센터로 문의해 주세요.", source_id="V", qa_id="V_1"),  # val은 고치지 않는다
    ]
    queue = build_fix_queue(rows, identity, split_map={"A": "train", "V": "val"})
    assert {r["id"]: r["needs_fix"] for r in queue} == {"A_1": "invalid", "A_2": "promise"}
    assert {"invalid", "promise", "claim", "call_context"} <= FIXABLE and "pii_request" not in FIXABLE
    assert queue[0]["messages"][-1]["role"] == "assistant"  # 고칠 원래 답을 보여 준다
    # 이미 판정한 것은 대기열에서 빠진다
    assert [r["id"] for r in build_fix_queue(rows, identity, {"A": "train", "V": "val"}, reviews={"A_1": {"ok": False}})] == ["A_2"]


def test_fixed_answer_enters_train_and_rejected_stays_excluded():
    rows = [
        qa("고객센터로 문의해 주세요.", source_id="A", qa_id="A_1"),
        qa("확인 후 연락드리겠습니다.", source_id="B", qa_id="B_1"),
    ]
    reviews = {
        "A_1": {"ok": True, "output": "납부 관련 자세한 사항은 상담원에게 확인해 주세요.", "note": "채널 삭제"},
        "B_1": {"ok": False, "note": "주제 밖"},
    }
    splits, candidates, stats = build_dataset(rows, identity, split_map={"A": "train", "B": "train"}, reviews=reviews)
    [fixed] = splits["train"]
    assert fixed["id"] == "A_1" and fixed["reviewed"] is True and fixed["needs_fix"] == "invalid"
    assert fixed["messages"][-1]["content"] == "납부 관련 자세한 사항은 상담원에게 확인해 주세요."
    assert stats["fixed"] == 1 and stats["excluded"] == {"promise": 1}


def test_fix_must_pass_training_checks():
    rows = [qa("고객센터로 문의해 주세요.", source_id="A", qa_id="A_1")]
    with pytest.raises(ValueError, match="A_1"):
        build_dataset(rows, identity, split_map={"A": "train"}, reviews={"A_1": {"ok": True, "output": "확인 후 연락드리겠습니다."}})


def test_fix_without_output_is_not_used():
    # 표현 문제로 빠진 답은 승인만으로는 쓸 수 없다. 고친 답이 있어야 한다.
    rows = [qa("고객센터로 문의해 주세요.", source_id="A", qa_id="A_1")]
    splits, _, stats = build_dataset(rows, identity, split_map={"A": "train"}, reviews={"A_1": {"ok": True}})
    assert splits["train"] == [] and stats["excluded"] == {"invalid": 1}


def test_main_writes_test_questions_and_fix_queue(tmp_path, monkeypatch):
    import training.interest.prepare as prepare

    raw = tmp_path / "raw"
    raw.mkdir()
    doc = {
        "source": {"source_id": "S9"},
        "consulting": {"consulting_topic": TOPIC},
        "qa_data": [{"qa_id": "S9_001", "qa_topic": TOPIC,
                     "input": {"question": "이자 얼마예요?", "answer": "확인해 드리겠습니다.", "follow_up_question": "네"},
                     "output": "고객센터로 문의해 주세요."}],
    }
    (raw / "a.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(prepare, "RAW_DIR", raw)
    monkeypatch.setattr(prepare, "SPLIT_FILE", tmp_path / "split.json")
    (tmp_path / "split.json").write_text(json.dumps({"S9": "train"}), encoding="utf-8")
    monkeypatch.setattr(prepare, "REVIEWS_FILE", tmp_path / "none2.json")
    out = tmp_path / "07"

    prepare.main(["--include-unreviewed", "--allow-fallback-mask", "--out-dir", str(out)])

    assert (out / "test_questions.jsonl").exists()
    queue = [json.loads(line) for line in (out / "fix_queue.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["id"] for r in queue] == ["S9_001"]
    stats = json.loads((out / "stats.json").read_text(encoding="utf-8"))
    assert stats["test_questions"] == 0 and stats["fix_queue"] == 1 and stats["fixed"] == 0


def test_exclude_aihub_train_keeps_val_and_test():
    # 검수 전 AI Hub 답(필터가 놓친 수수료·약속 등)을 학습하지 않고, 평가 분할에는 남긴다.
    rows = [
        qa("다음 납부일에 맞춰 납부해 주세요.", source_id="A", qa_id="A_1"),
        qa("다음 납부일에 맞춰 납부해 주세요.", source_id="V", qa_id="V_1"),
        qa("다음 납부일에 맞춰 납부해 주세요.", source_id="T", qa_id="T_1"),
    ]
    synth = [{"id": "s1", "origin": "synth", "group_id": "tpl", "category": "rate", "scenario": "normal",
              "reviewed": True, "review_note": "", "messages": [{"role": "assistant", "content": "x"}]}]
    splits, _, stats = build_dataset(rows, identity, split_map={"A": "train", "V": "val", "T": "test"}, synth=synth,
                                     include_unreviewed=True, exclude_aihub_train=True)
    assert [r["id"] for r in splits["train"]] == ["s1"]
    assert [r["id"] for r in splits["val"]] == ["V_1"] and [r["id"] for r in splits["test"]] == ["T_1"]
    assert stats["aihub_train_excluded"] == 1


def test_main_exclude_aihub_train_flag(tmp_path, monkeypatch):
    import training.interest.prepare as prepare

    raw = tmp_path / "raw"
    raw.mkdir()
    doc = {
        "source": {"source_id": "S9"},
        "consulting": {"consulting_topic": TOPIC},
        "qa_data": [{"qa_id": "S9_001", "qa_topic": TOPIC,
                     "input": {"question": "이자 얼마예요?", "answer": "확인해 드리겠습니다.", "follow_up_question": "네"},
                     "output": "다음 납부일에 맞춰 납부해 주세요."}],
    }
    (raw / "a.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(prepare, "RAW_DIR", raw)
    monkeypatch.setattr(prepare, "SPLIT_FILE", tmp_path / "split.json")
    (tmp_path / "split.json").write_text(json.dumps({"S9": "train"}), encoding="utf-8")
    monkeypatch.setattr(prepare, "REVIEWS_FILE", tmp_path / "none2.json")
    out = tmp_path / "07"

    prepare.main(["--include-unreviewed", "--allow-fallback-mask", "--exclude-aihub-train", "--out-dir", str(out)])

    assert (out / "train.jsonl").read_text(encoding="utf-8") == ""
    stats = json.loads((out / "stats.json").read_text(encoding="utf-8"))
    assert stats["exclude_aihub_train"] is True and stats["aihub_train_excluded"] == 1
