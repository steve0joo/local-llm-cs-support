import json
import zipfile
from collections import Counter

import pytest

from app.agents.balance.intent import classify_intent
from app.agents.balance.mock_api import get_accounts
from app.agents.balance.prompt import SLOT_NAMES, SYSTEM_PROMPT, build_messages
from app.agents.balance.resolve import ASK_TEXT, account_label
from app.agents.balance.validate import is_valid
from app.masking import mask
from training.balance import prepare
from training.balance.train import check_dataset

TOPIC = "거래내역/잔액조회"
OK_OUTPUT = "앱에서 계좌를 선택하시면 확인하실 수 있습니다."
ACCOUNTS = [a for customer_id in ("C001", "C002", "C003") for a in get_accounts(customer_id)]
# 재작성 캐시의 다시 쓴 답(BAL-010). 안전망 필터를 모두 통과한다
RW_ANSWER = "잔액과 최근 거래내역은 채팅으로 바로 보여 드릴 수 있습니다."
RW_OUTPUT = "앱에서 계좌를 선택하시면 거래내역을 확인하실 수 있습니다."
REWRITE = {"answer": RW_ANSWER, "output": RW_OUTPUT}


def _doc(source_id, question, *, topic=TOPIC, qa_topic=TOPIC, answer="네, 확인해 드리겠습니다.",
         follow_up="어떻게 확인하나요?", output=OK_OUTPUT):
    return {
        "source": {"source_id": source_id},
        "consulting": {"consulting_category": "은행", "consulting_topic": topic},
        "qa_data": [{
            "qa_id": f"{source_id}-1",
            "qa_topic": qa_topic,
            "input": {"question": question, "answer": answer, "follow_up_question": follow_up},
            "output": output,
        }],
    }


def _write_zip(path, docs):
    with zipfile.ZipFile(path, "w") as z:
        for i, doc in enumerate(docs):
            z.writestr(f"{i}.json", json.dumps(doc, ensure_ascii=False))
    return path


def _write_rewrites(path, zip_paths, rewrite=REWRITE, source_ids=None):
    """load_qas가 내는 QA마다 rewrite.py와 같은 모양의 캐시 한 줄을 쓴다."""
    lines = [
        json.dumps({"key": prepare.qa_key(qa), "source": prepare.mask_fields(qa), **rewrite}, ensure_ascii=False) + "\n"
        for zip_path in zip_paths for qa in prepare.load_qas(zip_path)
        if source_ids is None or qa["source_id"] in source_ids
    ]
    path.write_text("".join(lines), encoding="utf-8")
    return path


def _read(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _read_all(out_dir):
    return "".join((out_dir / file).read_text(encoding="utf-8") for file in prepare.SPLIT_FILES.values())


@pytest.fixture
def raw(tmp_path):
    tl = _write_zip(tmp_path / "TL.zip", [
        _doc("S1", "학습용 잔액 질문이에요"),
        _doc("S4", "다른 주제 질문이에요", topic="대출문의(만기/연장/조회등)", qa_topic="대출문의(만기/연장/조회등)"),
        _doc("S5", "라벨 어긋난 질문이에요", qa_topic="기타(은행)"),
    ])
    vl = _write_zip(tmp_path / "VL.zip", [
        _doc("S2", "검증용 잔액 질문이에요"),
        _doc("S3", "평가용 잔액 질문이에요"),
        _doc("S6", "분할에 없는 질문이에요"),
    ])
    split_path = tmp_path / "split.json"
    split_path.write_text(json.dumps(
        {"S1": "train", "S2": "val", "S3": "test", "S4": "train", "S5": "train"}
    ), encoding="utf-8")
    return split_path, [tl, vl], _write_rewrites(tmp_path / "rewrites.jsonl", [tl, vl])


# 분할별 합성 샘플 수: 슬롯 샘플, 가상 계좌번호 질문(의도마다), general "상담원 안내"(범주 1은 질문 5개)
SYNTH_COUNTS = {
    "train": {"slot": 192, "masked_balance": 18, "masked_transactions": 18, "general": 33},
    "val": {"slot": 24, "masked_balance": 6, "masked_transactions": 6, "general": 15},
    "test": {"slot": 24, "masked_balance": 6, "masked_transactions": 6, "general": 15},
}


def _synth_counts():
    return Counter({split: sum(kinds.values()) for split, kinds in SYNTH_COUNTS.items()})


def _synth_kind(sample):
    """슬롯 줄이 없으면 general, 첫 질문에 [계좌번호_1]이 있으면 가상 계좌번호 질문, 그 밖은 슬롯 샘플."""
    last_user = sample["messages"][-2]["content"]
    if "사용할 수 있는 슬롯" not in last_user:
        return "general"
    if "[계좌번호_1]" not in sample["messages"][1]["content"]:
        return "slot"
    return "masked_balance" if "{{balance}}" in last_user else "masked_transactions"


def _split_of(i):
    return "test" if i % 10 == 0 else "val" if i % 10 == 1 else "train"


def test_uses_gateway_mask_and_default_paths():
    from training.common.split import OUT_PATH

    assert prepare.mask is mask
    assert prepare.OUT_DIR == OUT_PATH.parent / "balance"
    assert prepare.SPLIT_FILES == {"train": "train.jsonl", "val": "valid.jsonl", "test": "test.jsonl"}


def test_load_qas_keeps_only_qas_labeled_with_topic_twice(tmp_path):
    path = _write_zip(tmp_path / "raw.zip", [
        _doc("S1", "잔액 질문", answer="답변", follow_up="후속 질문", output="정답"),
        _doc("S4", "대출 질문", topic="대출문의(만기/연장/조회등)"),
        _doc("S5", "라벨 어긋난 질문", qa_topic="기타(은행)"),
    ])
    assert list(prepare.load_qas(path)) == [{
        "source_id": "S1", "question": "잔액 질문", "answer": "답변",
        "follow_up": "후속 질문", "output": "정답",
    }]


def test_normalize_amounts_turns_hidden_amounts_into_numbered_tokens():
    assert prepare.normalize_amounts("잔액이 ●●●원이고 이체는 ●,●●●원입니다") == "잔액이 [금액_1]이고 이체는 [금액_2]입니다"
    assert prepare.normalize_amounts("●●만 원 남았어요") == "[금액_1] 남았어요"
    assert prepare.normalize_amounts("잔액 알려줘") == "잔액 알려줘"


RAW_QA = {"source_id": "S1", "question": "제 계좌 110-9876-5432 잔액이 ●●●원 맞나요?",
          "answer": "주민번호 900101-1234567 확인했습니다.", "follow_up": "010-2222-3333으로 연락 주세요",
          "output": OK_OUTPUT}


def test_rewrite_cache_constants():
    assert prepare.REWRITE_PATH == prepare.OUT_DIR / "rewrites.jsonl"
    assert prepare.MAX_CHARS == 200


def test_mask_fields_normalizes_amounts_and_masks_each_field():
    fields = prepare.mask_fields(RAW_QA)
    assert fields == {
        "question": "제 계좌 [계좌번호_1] 잔액이 [금액_1] 맞나요?",
        "answer": mask("주민번호 900101-1234567 확인했습니다.").masked_text,
        "follow_up": mask("010-2222-3333으로 연락 주세요").masked_text,
        "output": OK_OUTPUT,
    }
    text = json.dumps(fields, ensure_ascii=False)
    for original in ("110-9876-5432", "900101-1234567", "010-2222-3333", "●"):
        assert original not in text


def test_qa_key_is_stable_32_hex():
    key = prepare.qa_key(RAW_QA)
    assert key == prepare.qa_key(dict(RAW_QA))
    assert len(key) == 32 and all(c in "0123456789abcdef" for c in key)


@pytest.mark.parametrize("field", ["source_id", "question", "answer", "follow_up", "output"])
def test_qa_key_changes_when_any_field_changes(field):
    assert prepare.qa_key({**RAW_QA, field: RAW_QA[field] + "요"}) != prepare.qa_key(RAW_QA)


def test_qa_key_keeps_field_boundaries():
    assert (prepare.qa_key({**RAW_QA, "question": "잔액", "answer": "안내"})
            != prepare.qa_key({**RAW_QA, "question": "잔", "answer": "액안내"}))


def test_load_rewrites_returns_empty_for_missing_file(tmp_path):
    assert prepare.load_rewrites(tmp_path / "none.jsonl") == {}


def test_load_rewrites_keeps_last_line_per_key(tmp_path):
    path = tmp_path / "rewrites.jsonl"
    rows = [
        {"key": "k1", "source": {"question": "q"}, "answer": "첫 답", "output": "첫 출력"},
        {"key": "k2", "source": {"question": "q"}, "answer": "다른 답", "output": "다른 출력"},
        {"key": "k1", "source": {"question": "q"}, "answer": "새 답", "output": "새 출력"},
    ]
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    assert prepare.load_rewrites(path) == {
        "k1": {"answer": "새 답", "output": "새 출력"},
        "k2": {"answer": "다른 답", "output": "다른 출력"},
    }


def _qa(**fields):
    return {"source_id": "S1", "question": "잔액 알려주세요", "answer": "원문 답변입니다.",
            "follow_up": "어떻게 확인하나요?", "output": "원문 정답입니다.", **fields}


def _turns(samples):
    """첫 턴 샘플은 메시지 3개, 이어진 턴 샘플은 5개다."""
    return [{3: "first", 5: "follow_up"}[len(s["messages"])] for s in samples]


def test_build_samples_returns_nothing_without_rewrite():
    assert prepare.build_samples(_qa(), None) == []


def test_build_samples_makes_first_and_follow_up_turns_from_rewrite():
    qa = _qa(question="잔액이 ●●●원 맞나요?")
    assert prepare.build_samples(qa, REWRITE) == [
        {"messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "잔액이 [금액_1] 맞나요?"},
            {"role": "assistant", "content": RW_ANSWER},
        ]},
        {"messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "잔액이 [금액_1] 맞나요?"},
            {"role": "assistant", "content": RW_ANSWER},
            {"role": "user", "content": "어떻게 확인하나요?"},
            {"role": "assistant", "content": RW_OUTPUT},
        ]},
    ]


def test_build_samples_masks_inputs_and_rewritten_answers():
    qa = _qa(question="제 계좌 110-9876-5432 잔액이요", follow_up="010-2222-3333으로 연락 주세요")
    rewrite = {**REWRITE, "answer": "주민번호 900101-1234567 같은 정보는 채팅에 입력하지 마세요."}
    samples = prepare.build_samples(qa, rewrite)
    assert _turns(samples) == ["follow_up"]      # 마스킹 토큰이 든 answer는 첫 턴 목표에서 빠진다
    text = json.dumps(samples, ensure_ascii=False)
    for original in ("110-9876-5432", "900101-1234567", "010-2222-3333"):
        assert original not in text
    for token in ("[계좌번호_1]", "[주민번호_1]", "[전화번호_1]"):
        assert token in text


@pytest.mark.parametrize("output", [
    "잔액은 [금액_1]입니다.",                     # 마스킹 토큰
    "영업일 기준 3일 뒤에 확인하세요.",            # 숫자
    "신분증과 서류를 지참해 주세요.",               # 서류 키워드
    "○○자유통장으로 바꾸시면 편리합니다.",         # 입력에 없는 상품명
])
def test_build_samples_excludes_bad_outputs(output):
    qa = _qa(follow_up="통장 바꾸면 좋은가요?")
    assert _turns(prepare.build_samples(qa, {**REWRITE, "output": output})) == ["first"]


@pytest.mark.parametrize("follow_up, output", [
    ("카드로도 되나요?", "체크카드로 결제하신 내역도 앱에서 보실 수 있습니다."),           # 허용 목록 명칭
    ("자유통장도 조회되나요?", "자유통장도 앱에서 조회하실 수 있습니다."),                  # 입력에 있는 상품명
])
def test_build_samples_keeps_generic_or_mentioned_product_names(follow_up, output):
    samples = prepare.build_samples(_qa(follow_up=follow_up), {**REWRITE, "output": output})
    assert samples[-1]["messages"][-1]["content"] == output


def test_product_names_are_checked_against_each_turn_inputs():
    # 첫 턴의 입력은 question뿐이고, 이어진 턴의 입력은 question·answer·follow_up이다
    qa = _qa(follow_up="자유통장도 조회되나요?")
    rewrite = {"answer": "자유통장 잔액도 채팅으로 보실 수 있습니다.", "output": "자유통장도 앱에서 조회하실 수 있습니다."}
    assert _turns(prepare.build_samples(qa, rewrite)) == ["follow_up"]


@pytest.mark.parametrize("output", [
    # 개인정보 요구 (BAL-009)
    "성함과 생년월일 앞 여섯 자리를 알려주시기 바랍니다",
    "계좌 비밀번호 네 자리를 입력해 주십시오",
    "계좌 번호를 알려 주시면 확인해 드리겠습니다",
    "먼저 성함과 생년월일을 제공해 주셔야 본인 확인 절차를 진행할 수 있습니다",
    # 행동 약속 (BAL-009)
    "문자로 상세 정보를 보내드리겠습니다",
    "필요하시면 영수증도 전송해 드리니 잠시만 기다려 주시기 바랍니다",
    "PDF 파일이나 우편으로 발급해 드리겠습니다",
    "신속히 확인하여 조치해 드리겠습니다",
    "문자 발송을 바로 진행해 드리겠습니다",
    "요청해 주시면 해당 내용을 전달해 드리겠습니다",
    "입금 상세 내역을 추가로 제공해 드리겠습니다",
    "변경을 원하시는 내용을 알려 주시면 즉시 처리해 드립니다",
    "원하시는 신청 방법을 알려 주시면 즉시 진행하겠습니다",
    "변경 내역을 서면으로 발송해 드릴 수 있으니 요청해 주세요",
    "문자 메시지로도 정리해 드릴 수 있으니 문의해 주시기 바랍니다",
    "최근 자동이체 여부를 조회해 드리겠습니다",
])
def test_build_samples_excludes_call_center_outputs(output):
    assert _turns(prepare.build_samples(_qa(), {**REWRITE, "output": output})) == ["first"]


@pytest.mark.parametrize("output", [
    "카드사 상담원과 연결해 드리겠습니다",
    "담당 부서로 연결해 드리겠습니다",
    "고객센터로 문의해 주시기 바랍니다",
    "조회 방법을 안내해 드리겠습니다",
    "해당 내역은 조회해 드릴 수 없으니 상담원에게 확인해 주세요",
])
def test_build_samples_keeps_handoff_and_guide_outputs(output):
    assert prepare.build_samples(_qa(), {**REWRITE, "output": output})[-1]["messages"][-1]["content"] == output


@pytest.mark.parametrize("output", [
    "시스템 확인 결과 해당 일자에는 거래가 없습니다",
    "거래내역을 확인한 결과, 자동이체로 출금된 금액은 대출 상환입니다",
    "확인한 바에 따르면 변경 사항이 정상적으로 적용되어 있습니다",
    "입금이 정상적으로 확인되었습니다",
])
def test_build_samples_excludes_lookup_claims(output):
    assert _turns(prepare.build_samples(_qa(), {**REWRITE, "output": output})) == ["first"]


@pytest.mark.parametrize("output", [
    "조회 결과는 화면에 표시되며 캡처하실 수 있습니다",
    "조회 결과를 앱에서 확인하실 수 있습니다",
    "입금 여부는 앱에서 확인하실 수 있습니다",
])
def test_build_samples_keeps_lookup_guides(output):
    assert prepare.build_samples(_qa(), {**REWRITE, "output": output})[-1]["messages"][-1]["content"] == output


@pytest.mark.parametrize("output", [
    "★★은행 모바일 앱에서 확인해 주세요",
    "●월 ●일 기준으로 반영됩니다",
    "OOO 고객님 확인 부탁드립니다",
])
def test_build_samples_excludes_deidentified_marks(output):
    assert _turns(prepare.build_samples(_qa(), {**REWRITE, "output": output})) == ["first"]


@pytest.mark.parametrize("length, turns", [(200, ["first", "follow_up"]), (201, ["first"])])
def test_build_samples_excludes_targets_over_max_chars(length, turns):
    output = ("앱에서 확인하실 수 있습니다. " * 20)[:length]
    assert len(output) == length
    assert _turns(prepare.build_samples(_qa(), {**REWRITE, "output": output})) == turns


@pytest.mark.parametrize("answer", [
    "문자로 상세 정보를 보내드리겠습니다",            # 행동 약속
    "확인 결과 입금이 정상적으로 확인되었습니다",      # 조회 결과 단정
])
def test_rejected_answer_drops_only_first_turn_and_stays_in_history(answer):
    samples = prepare.build_samples(_qa(), {**REWRITE, "answer": answer})
    assert _turns(samples) == ["follow_up"]
    assert [m["content"] for m in samples[0]["messages"][2:]] == [answer, "어떻게 확인하나요?", RW_OUTPUT]


def test_safety_filter_does_not_judge_inputs():
    qa = _qa(question="★★은행 OO 계좌 잔액 알려주세요", follow_up="계좌 번호를 알려드릴게요. ●월 ●일에 들어온 거 맞나요?")
    assert _turns(prepare.build_samples(qa, REWRITE)) == ["first", "follow_up"]


def test_generic_product_names_constant():
    assert prepare.GENERIC_PRODUCT_NAMES == {
        "입출금통장", "정기예금", "정기적금", "신용카드", "체크카드", "신용대출", "주택담보대출", "전세자금대출",
    }


def test_synth_questions_classify_to_their_own_intent():
    assert len(prepare.BALANCE_QUESTIONS) >= 20
    assert len(prepare.TRANSACTION_QUESTIONS) >= 20
    assert [q for q in prepare.BALANCE_QUESTIONS if classify_intent(q) != "balance"] == []
    assert [q for q in prepare.TRANSACTION_QUESTIONS if classify_intent(q) != "transactions"] == []


def test_synth_answers_pass_output_validation():
    assert len(prepare.BALANCE_ANSWERS) >= 5
    assert len(prepare.TRANSACTION_ANSWERS) >= 5
    for intent, answers in (("balance", prepare.BALANCE_ANSWERS), ("transactions", prepare.TRANSACTION_ANSWERS)):
        slots = SLOT_NAMES[intent]
        assert [a for a in answers if not is_valid(a, slots, slots)] == []


def test_synth_samples_follow_question_index_rules():
    samples = prepare.synth_samples()
    assert {name: len(rows) for name, rows in samples.items()} == dict(_synth_counts())

    labels = [account_label(a) for a in ACCOUNTS]
    used_labels = set()
    for intent, questions, answers in (
        ("balance", prepare.BALANCE_QUESTIONS, prepare.BALANCE_ANSWERS),
        ("transactions", prepare.TRANSACTION_QUESTIONS, prepare.TRANSACTION_ANSWERS),
    ):
        slot_line = "\n사용할 수 있는 슬롯: " + ", ".join(f"{{{{{name}}}}}" for name in SLOT_NAMES[intent])
        for i, question in enumerate(questions):
            split = "test" if i % 10 == 0 else "val" if i % 10 == 1 else "train"
            if i % 2 == 0:
                expected_inputs = [[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": question + slot_line},
                ]]
            else:
                expected_inputs = [[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": ASK_TEXT},
                    {"role": "user", "content": label + slot_line},
                ] for label in labels]
            found = [s["messages"] for s in samples[split] if s["messages"][:-1] in expected_inputs]
            assert sorted(m[-1]["content"] for m in found) == sorted(answers)
            used_labels |= {m[-2]["content"].split("\n")[0] for m in found if i % 2 == 1}
    assert used_labels == set(labels)


MASKED_QUESTIONS = (("balance", "MASKED_BALANCE_QUESTIONS", "BALANCE_ANSWERS"),
                    ("transactions", "MASKED_TRANSACTION_QUESTIONS", "TRANSACTION_ANSWERS"))


def _masked(template, i):
    """템플릿 인덱스 i에 mock 계좌(C001~C003 순서)의 계좌번호를 차례로 넣고 런타임과 같은 mask()를 거친다."""
    return mask(template.format(account_no=ACCOUNTS[i % len(ACCOUNTS)]["account_no"])).masked_text


@pytest.mark.parametrize("intent, questions_name, _", MASKED_QUESTIONS)
def test_masked_account_questions_become_token_and_own_intent(intent, questions_name, _):
    templates = getattr(prepare, questions_name)
    assert len(templates) >= 5
    for template in templates:
        assert "{account_no}" in template
        for account in ACCOUNTS:
            question = mask(template.format(account_no=account["account_no"])).masked_text
            assert "[계좌번호_1]" in question and account["account_no"] not in question
            assert classify_intent(question) == intent


@pytest.mark.parametrize("intent, questions_name, answers_name", MASKED_QUESTIONS)
def test_synth_masked_account_questions_follow_index_rules(intent, questions_name, answers_name):
    samples = prepare.synth_samples()
    answers = getattr(prepare, answers_name)
    for i, template in enumerate(getattr(prepare, questions_name)):
        expected = build_messages([], _masked(template, i), intent)
        found = [s["messages"][-1]["content"] for s in samples[_split_of(i)] if s["messages"][:-1] == expected]
        assert sorted(found) == sorted(answers)


def test_general_synth_questions_are_general_and_answers_pass_safety_filter():
    assert len(prepare.GENERAL_SYNTH) == 5
    for questions, answers in prepare.GENERAL_SYNTH:
        assert len(questions) >= 4 and len(answers) >= 3
        assert [q for q in questions if classify_intent(q) != "general"] == []
        for question in questions:
            # _rejected: is_valid(답, (), ())·상품명·콜센터식 정답·조회 결과 단정·비식별 표시·MAX_CHARS
            assert [a for a in answers if prepare._rejected(a, (question,))] == []


def test_synth_general_samples_follow_index_rules():
    samples = prepare.synth_samples()
    for questions, answers in prepare.GENERAL_SYNTH:
        for i, question in enumerate(questions):
            expected = build_messages([], question, "general")
            found = [s["messages"][-1]["content"] for s in samples[_split_of(i)] if s["messages"][:-1] == expected]
            assert sorted(found) == sorted(answers)


def test_synth_sample_counts_per_kind_and_split_are_deterministic():
    samples = prepare.synth_samples()
    assert {split: Counter(map(_synth_kind, rows)) for split, rows in samples.items()} == SYNTH_COUNTS
    assert prepare.synth_samples() == samples


def test_synth_samples_have_no_mock_account_numbers_or_balances():
    text = json.dumps(prepare.synth_samples(), ensure_ascii=False)
    assert "[계좌번호_1]" in text      # 가상 계좌번호 질문 샘플까지 덮는다
    for account in ACCOUNTS:
        for value in (account["account_no"], account["account_no"].replace("-", ""),
                      str(account["balance"]), f"{account['balance']:,}"):
            assert value not in text


def test_build_dataset_splits_by_source_id_and_adds_synth(raw, tmp_path):
    split_path, zip_paths, rewrites = raw
    out_dir = tmp_path / "out"
    counts = prepare.build_dataset(split_path, out_dir, zip_paths, rewrites)

    synth = _synth_counts()      # AI Hub QA 하나에서 첫 턴·이어진 턴 2개
    assert counts == {"train": synth["train"] + 2, "val": synth["val"] + 2, "test": synth["test"] + 2}
    files = {name: (out_dir / file).read_text(encoding="utf-8") for name, file in prepare.SPLIT_FILES.items()}
    assert {name: len(_read(out_dir / file)) for name, file in prepare.SPLIT_FILES.items()} == counts
    assert "학습용" in files["train"] and "학습용" not in files["val"] + files["test"]
    assert "검증용" in files["val"] and "검증용" not in files["train"] + files["test"]
    assert "평가용" in files["test"] and "평가용" not in files["train"] + files["val"]
    for excluded in ("다른 주제", "라벨 어긋난", "분할에 없는"):
        assert excluded not in "".join(files.values())


def test_build_dataset_skips_qas_missing_from_rewrite_cache(raw, tmp_path):
    split_path, zip_paths, _ = raw
    partial = _write_rewrites(tmp_path / "partial.jsonl", zip_paths, source_ids={"S1", "S2"})
    counts = prepare.build_dataset(split_path, tmp_path / "out", zip_paths, partial)

    synth = _synth_counts()
    assert counts == {"train": synth["train"] + 2, "val": synth["val"] + 2, "test": synth["test"]}
    assert "평가용" not in _read_all(tmp_path / "out")


def test_build_dataset_without_rewrite_cache_writes_only_synth(raw, tmp_path):
    split_path, zip_paths, _ = raw
    counts = prepare.build_dataset(split_path, tmp_path / "out", zip_paths, tmp_path / "none.jsonl")
    assert counts == dict(_synth_counts())


def test_build_dataset_writes_rewritten_answers_not_originals(tmp_path):
    zip_path = _write_zip(tmp_path / "TL.zip", [
        _doc("S1", "잔액 알려주세요", answer="원문답변에만있는문구입니다.", output="원문정답에만있는문구입니다."),
    ])
    split_path = tmp_path / "split.json"
    split_path.write_text(json.dumps({"S1": "train"}), encoding="utf-8")
    out_dir = tmp_path / "out"
    prepare.build_dataset(split_path, out_dir, [zip_path], _write_rewrites(tmp_path / "rewrites.jsonl", [zip_path]))

    text = _read_all(out_dir)
    assert "원문답변에만있는문구" not in text and "원문정답에만있는문구" not in text
    assert RW_ANSWER in text and RW_OUTPUT in text


def test_build_dataset_leaves_no_personal_info_in_files(tmp_path):
    zip_path = _write_zip(tmp_path / "TL.zip", [
        _doc("S1", "제 계좌 110-9876-5432 잔액이요", answer="주민번호 900101-1234567 확인했습니다.",
             follow_up="010-2222-3333으로 연락 주세요"),
        _doc("S2", "잔액 알려주세요", output="110-9876-5432 계좌는 010-2222-3333 번호로 등록되어 있습니다."),
    ])
    split_path = tmp_path / "split.json"
    split_path.write_text(json.dumps({"S1": "train", "S2": "train"}), encoding="utf-8")
    rewrites = _write_rewrites(tmp_path / "rewrites.jsonl", [zip_path], rewrite={
        **REWRITE, "answer": "010-4444-5555 번호로는 연락드리지 않으니 채팅으로 문의해 주세요."})
    out_dir = tmp_path / "out"
    prepare.build_dataset(split_path, out_dir, [zip_path], rewrites)

    text = _read_all(out_dir)
    for original in ("110-9876-5432", "900101-1234567", "010-2222-3333", "010-4444-5555"):
        assert original not in text
    assert "[전화번호_1] 번호로는" in text     # 다시 쓴 answer도 mask()를 거쳐 이어진 턴 history에 남는다


def test_build_dataset_output_passes_train_check_and_is_deterministic(raw, tmp_path):
    split_path, zip_paths, rewrites = raw
    first, second = tmp_path / "first", tmp_path / "second"
    counts = prepare.build_dataset(split_path, first, zip_paths, rewrites)
    prepare.build_dataset(split_path, second, zip_paths, rewrites)

    assert check_dataset(first, "train") == {"train": counts["train"], "valid": counts["val"]}
    assert check_dataset(first, "test") == {"test": counts["test"]}
    for file in prepare.SPLIT_FILES.values():
        assert (first / file).read_bytes() == (second / file).read_bytes()


def test_main_takes_paths_as_arguments(raw, tmp_path, capsys):
    split_path, zip_paths, _ = raw
    partial = _write_rewrites(tmp_path / "partial.jsonl", zip_paths, source_ids={"S1"})
    out_dir = tmp_path / "cli"
    prepare.main(["--split", str(split_path), "--out-dir", str(out_dir), "--zip", *map(str, zip_paths),
                  "--rewrites", str(partial)])
    assert check_dataset(out_dir, "train")
    assert RW_OUTPUT in (out_dir / "train.jsonl").read_text(encoding="utf-8")
    assert "재작성 없음으로 빠진 QA 2건" in capsys.readouterr().out    # S2·S3. S6은 분할에 없어 세지 않는다


def test_main_reads_default_rewrite_cache(raw, tmp_path, monkeypatch):
    split_path, zip_paths, rewrites = raw
    monkeypatch.setattr(prepare, "REWRITE_PATH", rewrites)
    out_dir = tmp_path / "cli"
    prepare.main(["--split", str(split_path), "--out-dir", str(out_dir), "--zip", *map(str, zip_paths)])
    assert RW_OUTPUT in (out_dir / "train.jsonl").read_text(encoding="utf-8")
