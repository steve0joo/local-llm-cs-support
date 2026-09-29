"""라우터 학습 데이터 생성 (docs/router/ADR.md RT-005).

- 은행 상담만, consulting_topic == qa_topic 인 QA만, 계약 2에 있는 주제만, 상담의 첫 QA(_001)만. follow_up_question은 쓰지 않는다.
- 질문은 mask()를 거치고, 원본에서 가려진 금액(●●●원)도 이어지는 번호의 [금액_n]이 된다.
- split.json대로 나누고 train만 주제별 상한. 정렬 뒤 앞에서 잘라 결정적이다.
- 레코드는 Ollama messages 형식이고 system 프롬프트는 topics.SYSTEM_PROMPT 그대로다.
"""
import json
import zipfile

from app.router.topics import SYSTEM_PROMPT
from training.router import prepare

BAL, LOAN, FX = "거래내역/잔액조회", "대출문의(만기/연장/조회등)", "환전문의"


def _doc(source_id, topic, question, *, qa_topic=None, category="은행", qa_no=1):
    return {
        "source": {"source_id": source_id},
        "consulting": {"consulting_category": category, "consulting_topic": topic},
        "qa_data": [{"qa_id": f"{source_id}_{qa_no:03d}", "qa_topic": qa_topic or topic,
                     "input": {"question": question, "answer": "답변", "follow_up_question": "후속 질문입니다"}, "output": "목표"}],
    }


def _write_zip(path, docs):
    with zipfile.ZipFile(path, "w") as z:
        for i, doc in enumerate(docs):
            z.writestr(f"{i:02d}/{doc['qa_data'][0]['qa_id']}.json", json.dumps(doc, ensure_ascii=False))
    return path


def _codes(path):
    return [json.loads(l)["messages"][2]["content"] for l in path.read_text(encoding="utf-8").splitlines()]


# ---------- 마스킹 ----------

def test_mask_question_masks_pii_and_hidden_amounts_with_continuing_numbers():
    text = "제 계좌 110-1234-5678에서 5,000원 보내고 ●●●원 남았는데 ●●● ●원 더 빠졌어요"
    assert prepare.mask_question(text) == "제 계좌 [계좌번호_1]에서 [금액_1] 보내고 [금액_2] 남았는데 [금액_3] 더 빠졌어요"


def test_same_hidden_amount_string_gets_same_token():
    assert prepare.mask_question("●●●원 냈는데 ●●●원 또 나갔어요") == "[금액_1] 냈는데 [금액_1] 또 나갔어요"


# ---------- 추출·필터 ----------

def test_read_examples_keeps_only_bank_matching_label_known_topic_first_qa(tmp_path):
    z = _write_zip(tmp_path / "TL.zip", [
        _doc("s1", BAL, "잔액 알려줘"),
        _doc("s2", BAL, "적금 만기 재투자", qa_topic="만기,연장/해지,수신"),   # 라벨 불일치 → 제외
        _doc("s3", LOAN, "대출 만기", category="카드"),                     # 은행 아님 → 제외
        _doc("s4", "기타(은행)", "기타 문의"),                               # 계약 2에 없음 → 제외
        _doc("s5", FX, "환전 ●●●원 하고 싶어요"),
        _doc("s6", BAL, "그리고 절차는요?", qa_no=2),                          # 첫 QA가 아님 → 제외
    ])
    examples = list(prepare.read_examples(z))
    assert [(e["source_id"], e["code"], e["question"]) for e in examples] == [
        ("s1", "balance", "잔액 알려줘"),
        ("s5", "fx", "환전 [금액_1] 하고 싶어요"),
    ]
    assert all("후속" not in e["question"] for e in examples)              # follow_up은 쓰지 않는다


def test_record_is_ollama_messages_with_shared_system_prompt():
    example = {"source_id": "s1", "qa_id": "s1_001", "code": "balance", "question": "[계좌번호_1] 잔액"}
    assert prepare.to_record(example) == {"messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "[계좌번호_1] 잔액"},
        {"role": "assistant", "content": "balance"},
    ]}


# ---------- 분할·상한 ----------

def test_main_assigns_by_split_and_caps_train_only(tmp_path):
    docs = [_doc(f"b{i}", BAL, f"잔액 {i}") for i in range(4)] + [_doc(f"l{i}", LOAN, f"대출 {i}") for i in range(4)]
    z = _write_zip(tmp_path / "TL.zip", docs)
    split_path = tmp_path / "split.json"
    split_path.write_text(json.dumps({"b0": "train", "b1": "train", "b2": "train", "b3": "val",
                                      "l0": "train", "l1": "train", "l2": "test", "l9": "train"}), encoding="utf-8")
    out = tmp_path / "router"
    prepare.main(zips=[z], split_path=split_path, out_dir=out, cap=2)

    assert _codes(out / "train.jsonl") == ["balance", "balance", "loan", "loan"]   # 정렬 후 주제별 앞 2개
    assert _codes(out / "val.jsonl") == ["balance"]                                # val은 상한 없음
    assert _codes(out / "test.jsonl") == ["loan"]                                  # l3은 split.json에 없어 버려짐
