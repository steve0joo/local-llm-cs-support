import json
import zipfile
from collections import Counter

import pytest

from app.agents.balance.intent import classify_intent
from app.agents.balance.mock_api import get_accounts
from app.agents.balance.prompt import SLOT_NAMES, SYSTEM_PROMPT
from app.agents.balance.resolve import ASK_TEXT, account_label
from app.agents.balance.validate import is_valid
from app.masking import mask
from training.balance import prepare
from training.balance.train import check_dataset

TOPIC = "거래내역/잔액조회"
OK_OUTPUT = "앱에서 계좌를 선택하시면 확인하실 수 있습니다."
ACCOUNTS = [a for customer_id in ("C001", "C002", "C003") for a in get_accounts(customer_id)]


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


def _read(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


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
    return split_path, [tl, vl]


def _synth_counts():
    counts = Counter()
    for questions, answers in ((prepare.BALANCE_QUESTIONS, prepare.BALANCE_ANSWERS),
                               (prepare.TRANSACTION_QUESTIONS, prepare.TRANSACTION_ANSWERS)):
        for i in range(len(questions)):
            counts["test" if i % 10 == 0 else "val" if i % 10 == 1 else "train"] += len(answers)
    return counts


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


def test_build_sample_uses_general_prompt_and_output_as_target():
    qa = {"source_id": "S1", "question": "잔액이 ●●●원 맞나요?", "answer": "네, 확인해 드리겠습니다.",
          "follow_up": "어떻게 확인하나요?", "output": OK_OUTPUT}
    assert prepare.build_sample(qa) == {"messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "잔액이 [금액_1] 맞나요?"},
        {"role": "assistant", "content": "네, 확인해 드리겠습니다."},
        {"role": "user", "content": "어떻게 확인하나요?"},
        {"role": "assistant", "content": OK_OUTPUT},
    ]}


def test_build_sample_masks_personal_info_in_inputs():
    qa = {"source_id": "S1", "question": "제 계좌 110-9876-5432 잔액이요",
          "answer": "주민번호 900101-1234567 확인했습니다.",
          "follow_up": "010-2222-3333으로 연락 주세요", "output": OK_OUTPUT}
    text = json.dumps(prepare.build_sample(qa), ensure_ascii=False)
    for original in ("110-9876-5432", "900101-1234567", "010-2222-3333"):
        assert original not in text
    for token in ("[계좌번호_1]", "[주민번호_1]", "[전화번호_1]"):
        assert token in text


@pytest.mark.parametrize("output", [
    "잔액은 ●●●원입니다.",                       # 금액 → 마스킹 토큰
    "영업일 기준 3일 뒤에 확인하세요.",            # 숫자
    "신분증과 서류를 지참해 주세요.",               # 서류 키워드
    "○○자유통장으로 바꾸시면 편리합니다.",         # 입력에 없는 상품명
])
def test_build_sample_excludes_bad_outputs(output):
    qa = {"source_id": "S1", "question": "잔액 알려주세요", "answer": "네.",
          "follow_up": "통장 바꾸면 좋은가요?", "output": output}
    assert prepare.build_sample(qa) is None


@pytest.mark.parametrize("follow_up, output", [
    ("카드로도 되나요?", "체크카드로 결제하신 내역도 앱에서 보실 수 있습니다."),           # 허용 목록 명칭
    ("자유통장도 조회되나요?", "자유통장도 앱에서 조회하실 수 있습니다."),                  # 입력에 있는 상품명
])
def test_build_sample_keeps_generic_or_mentioned_product_names(follow_up, output):
    qa = {"source_id": "S1", "question": "잔액 알려주세요", "answer": "네.",
          "follow_up": follow_up, "output": output}
    assert prepare.build_sample(qa)["messages"][-1]["content"] == output


@pytest.mark.parametrize("output", [
    # 개인정보 요구 (BAL-009)
    "성함과 생년월일 앞 여섯 자리를 알려주시기 바랍니다",
    "계좌 비밀번호 네 자리를 입력해 주십시오",
    "계좌 번호를 알려 주시면 확인해 드리겠습니다",
    # 행동 약속 (BAL-009)
    "문자로 상세 정보를 보내드리겠습니다",
    "필요하시면 영수증도 전송해 드리니 잠시만 기다려 주시기 바랍니다",
    "PDF 파일이나 우편으로 발급해 드리겠습니다",
    "신속히 확인하여 조치해 드리겠습니다",
])
def test_build_sample_excludes_call_center_outputs(output):
    qa = {"source_id": "S1", "question": "잔액 알려주세요", "answer": "네.",
          "follow_up": "어떻게 확인하나요?", "output": output}
    assert prepare.build_sample(qa) is None


@pytest.mark.parametrize("output", [
    "카드사 상담원과 연결해 드리겠습니다",
    "담당 부서로 연결해 드리겠습니다",
    "고객센터로 문의해 주시기 바랍니다",
    "조회 방법을 안내해 드리겠습니다",
])
def test_build_sample_keeps_handoff_and_guide_outputs(output):
    qa = {"source_id": "S1", "question": "잔액 알려주세요", "answer": "네.",
          "follow_up": "어떻게 확인하나요?", "output": output}
    assert prepare.build_sample(qa)["messages"][-1]["content"] == output


def test_call_center_rule_applies_to_output_only():
    qa = {"source_id": "S1", "question": "잔액 알려주세요", "answer": "문자로 상세 정보를 보내드리겠습니다",
          "follow_up": "계좌 번호를 알려드릴게요", "output": OK_OUTPUT}
    messages = prepare.build_sample(qa)["messages"]
    assert [m["content"] for m in messages[2:]] == ["문자로 상세 정보를 보내드리겠습니다", "계좌 번호를 알려드릴게요", OK_OUTPUT]


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


def test_synth_samples_have_no_mock_account_numbers_or_balances():
    text = json.dumps(prepare.synth_samples(), ensure_ascii=False)
    for account in ACCOUNTS:
        for value in (account["account_no"], account["account_no"].replace("-", ""),
                      str(account["balance"]), f"{account['balance']:,}"):
            assert value not in text


def test_build_dataset_splits_by_source_id_and_adds_synth(raw, tmp_path):
    split_path, zip_paths = raw
    out_dir = tmp_path / "out"
    counts = prepare.build_dataset(split_path, out_dir, zip_paths)

    synth = _synth_counts()
    assert counts == {"train": synth["train"] + 1, "val": synth["val"] + 1, "test": synth["test"] + 1}
    files = {name: (out_dir / file).read_text(encoding="utf-8") for name, file in prepare.SPLIT_FILES.items()}
    assert {name: len(_read(out_dir / file)) for name, file in prepare.SPLIT_FILES.items()} == counts
    assert "학습용" in files["train"] and "학습용" not in files["val"] + files["test"]
    assert "검증용" in files["val"] and "검증용" not in files["train"] + files["test"]
    assert "평가용" in files["test"] and "평가용" not in files["train"] + files["val"]
    for excluded in ("다른 주제", "라벨 어긋난", "분할에 없는"):
        assert excluded not in "".join(files.values())


def test_build_dataset_leaves_no_personal_info_in_files(tmp_path):
    zip_path = _write_zip(tmp_path / "TL.zip", [
        _doc("S1", "제 계좌 110-9876-5432 잔액이요", answer="주민번호 900101-1234567 확인했습니다.",
             follow_up="010-2222-3333으로 연락 주세요"),
        _doc("S2", "잔액 알려주세요", output="110-9876-5432 계좌는 010-2222-3333 번호로 등록되어 있습니다."),
    ])
    split_path = tmp_path / "split.json"
    split_path.write_text(json.dumps({"S1": "train", "S2": "train"}), encoding="utf-8")
    out_dir = tmp_path / "out"
    prepare.build_dataset(split_path, out_dir, [zip_path])

    text = "".join((out_dir / file).read_text(encoding="utf-8") for file in prepare.SPLIT_FILES.values())
    for original in ("110-9876-5432", "900101-1234567", "010-2222-3333"):
        assert original not in text


def test_build_dataset_output_passes_train_check_and_is_deterministic(raw, tmp_path):
    split_path, zip_paths = raw
    first, second = tmp_path / "first", tmp_path / "second"
    counts = prepare.build_dataset(split_path, first, zip_paths)
    prepare.build_dataset(split_path, second, zip_paths)

    assert check_dataset(first, "train") == {"train": counts["train"], "valid": counts["val"]}
    assert check_dataset(first, "test") == {"test": counts["test"]}
    for file in prepare.SPLIT_FILES.values():
        assert (first / file).read_bytes() == (second / file).read_bytes()


def test_main_takes_paths_as_arguments(raw, tmp_path):
    split_path, zip_paths = raw
    out_dir = tmp_path / "cli"
    prepare.main(["--split", str(split_path), "--out-dir", str(out_dir), "--zip", *map(str, zip_paths)])
    assert check_dataset(out_dir, "train")
