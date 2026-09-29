"""공통 데이터 분할 (docs/ADR.md ADR-008, docs/router/ARCHITECTURE.md 제공 인터페이스 split.json).

- 은행 상담만 쓴다. 파일 여러 개가 같은 source_id(상담 1건)를 가리키므로 source_id 단위로 나눈다.
- TL 상담은 전부 train. VL 상담은 주제별로 source_id 정렬 뒤 번갈아 val/test. 양쪽에 있는 상담은 train.
- 결정적이어야 한다: 팀원들이 각자 실행해도 같은 split.json이 나와야 한다(파일은 gitignore).
"""
import json
import zipfile

from training.common import split as split_mod
from training.common.split import read_consultations, split

BAL, LOAN = "거래내역/잔액조회", "대출문의(만기/연장/조회등)"


def test_tl_consultations_are_all_train():
    result = split(tl={"t1": BAL, "t2": LOAN}, vl={})
    assert result == {"t1": "train", "t2": "train"}


def test_vl_alternates_val_test_per_topic_in_sorted_order():
    vl = {"c": BAL, "a": BAL, "b": BAL, "x": LOAN, "y": LOAN}
    result = split(tl={}, vl=vl)
    assert result == {"a": "val", "b": "test", "c": "val", "x": "val", "y": "test"}


def test_consultation_in_both_zips_goes_to_train():
    result = split(tl={"s1": BAL}, vl={"s1": BAL, "s2": BAL, "s3": BAL})
    assert result["s1"] == "train"
    assert [result["s2"], result["s3"]] == ["val", "test"]  # 겹친 상담은 VL 순번에서도 빠진다


def test_split_is_deterministic_regardless_of_input_order():
    vl = {"b": BAL, "a": BAL, "d": LOAN, "c": LOAN}
    reversed_vl = dict(reversed(list(vl.items())))
    assert split(tl={}, vl=vl) == split(tl={}, vl=reversed_vl)


def _write_zip(path, files: dict[str, dict]) -> None:
    with zipfile.ZipFile(path, "w") as z:
        for name, doc in files.items():
            z.writestr(name, json.dumps(doc, ensure_ascii=False))


def _doc(source_id: str, topic: str, category: str = "은행") -> dict:
    return {
        "source": {"source_id": source_id, "source_institution": "하나은행"},
        "consulting": {"consulting_category": category, "consulting_topic": topic},
        "qa_data": [{"qa_topic": topic, "input": {"question": "잔액 알려줘"}, "output": "..."}],
    }


def test_read_consultations_groups_files_by_source_id_and_keeps_bank_only(tmp_path):
    zip_path = tmp_path / "TL_은행.zip"
    _write_zip(zip_path, {
        "01/s1_001.json": _doc("s1", BAL),
        "01/s1_002.json": _doc("s1", BAL),          # 같은 상담의 두 번째 QA
        "08/s2_001.json": _doc("s2", LOAN),
        "08/s3_001.json": _doc("s3", LOAN, category="카드"),   # 은행 아님 → 제외
    })
    assert read_consultations(zip_path) == {"s1": BAL, "s2": LOAN}


def test_main_writes_split_json(tmp_path, monkeypatch):
    tl, vl = tmp_path / "TL_은행.zip", tmp_path / "VL_은행.zip"
    _write_zip(tl, {"01/t1_001.json": _doc("t1", BAL)})
    _write_zip(vl, {"01/v1_001.json": _doc("v1", BAL), "01/v2_001.json": _doc("v2", BAL)})
    out = tmp_path / "processed" / "split.json"
    monkeypatch.setattr(split_mod, "TL_ZIP", tl)
    monkeypatch.setattr(split_mod, "VL_ZIP", vl)
    monkeypatch.setattr(split_mod, "OUT_PATH", out)

    split_mod.main()

    assert json.loads(out.read_text(encoding="utf-8")) == {"t1": "train", "v1": "val", "v2": "test"}
