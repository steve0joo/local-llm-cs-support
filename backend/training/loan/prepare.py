"""대출문의 학습 데이터 준비 (docs/agent-loan/ARCHITECTURE.md 학습 데이터 절, phases/agent-loan/step3.md).

원천 데이터 필드 구조는 실제 은행 라벨링 데이터로 확인했다(2026-09-29): 파일 하나 = 상담 하나,
qa_data에는 QA가 1건. 필드 위치는 source.source_id, qa_data[0].qa_id, qa_data[0].qa_topic,
qa_data[0].input.{question,answer,follow_up_question}, qa_data[0].output. 필드 접근은
_extract_turns 한 곳에만 모은다 — 구조가 바뀌면 그 함수만 고치면 된다.

주제 필터는 consulting_topic이 아니라 qa_topic을 쓴다(QA 단위 정제·학습이라 더 정확하다고 판단했다.
2026-09-28 실측: 대출 QA 13,010건 중 두 필드 값이 다른 건 1,452건(11%)). consulting_topic으로
바꾸려면 _extract_turns의 "topic" 줄만 고치면 된다 — 팀 합의 전까지는 잠정 값이다.

익명화 기호(●●●·★★·OO 등)는 이 step에서 처리하지 않는다(계약 4 합의 대상).
"""
from __future__ import annotations

import argparse
import itertools
import json
import random
import re
import zipfile
from collections.abc import Iterator
from pathlib import Path

from app.agents.loan.prompt import SYSTEM_PROMPT
from app.agents.loan.validate import DOCUMENT_KEYWORDS
from app.masking import mask

TOPIC = "대출문의(만기/연장/조회등)"   # 실제 데이터 값 — "조회"와 "등" 사이에 공백이 없다(docs의 표기와 다름)

_RAW_ZIP_NAMES = ("TL_은행.zip", "VL_은행.zip")  # train은 TL, val·test는 VL(split.json이 나눈다)

# 학습 대화에 붙이는 합성 대출 정보(고정값). 실제 mock 값과 무관하고, 형식만 prompt.build_messages와 맞춘다.
_SAMPLE_LOAN_LABEL = "신용대출"
_SAMPLE_MATURITY = "2027-03-31"
_ALT_MATURITY = "2029-11-30"  # 복제본에 쓰는 다른 날짜(사실 자체는 안 바뀐다 — 답변에 안 들어가므로)

# is_clean 상품명 휴리스틱: 접미사 앞에 2~6자가 붙은 합성어만 "상품명으로 보이는 표현"으로 본다.
# 접미사만 단독으로 나오는 "통장"·"카드" 같은 일반 단어는 걸지 않는다(정상 답변을 과도하게 걸러내지 않기 위해).
_ALLOWED_PRODUCT_NAMES = ("신용대출", "주택담보대출", "전세자금대출")
_PRODUCT_PATTERN = re.compile(r"[가-힣]{2,6}(?:대출|통장|카드|적금|예금)")

_NUM_PATTERN = re.compile(r"\d[\d,.]*")

_NEGSIG = re.compile(r"불가|어렵|가능하지\s*(?:않|못)")
_NEGEXT = re.compile(r"연장[^.!?\n]{0,15}(?:불가|어렵|가능하지\s*(?:않|못))")
_SENTENCE_SPLIT = re.compile(r"[.!?\n]+")

NO_EXTEND_COPIES = 2  # 연장 불가 근거가 있는 "아니오" 샘플을 train에 넣는 횟수


def _extract_turns(raw: dict) -> dict:
    """원본 JSON 한 건 → 학습에 쓰는 필드만 모은 dict. 필드 구조가 바뀌면 여기만 고친다."""
    qa = raw["qa_data"][0]
    return {
        "source_id": raw["source"]["source_id"],
        "qa_id": qa["qa_id"],
        "topic": qa["qa_topic"],
        "question": qa["input"]["question"],
        "answer": qa["input"]["answer"],
        "follow_up_question": qa["input"]["follow_up_question"],
        "output": qa["output"],
    }


def iter_conversations(raw_dir: Path, split_path: Path, split: str = "train") -> Iterator[dict]:
    """raw_dir의 TL_은행.zip·VL_은행.zip에서 split_path 기준 split 분할·TOPIC 항목만 돌려준다."""
    split_map: dict[str, str] = json.loads(Path(split_path).read_text(encoding="utf-8"))
    raw_dir = Path(raw_dir)
    seen_qa_ids: set[str] = set()

    for zip_name in _RAW_ZIP_NAMES:
        zip_path = raw_dir / zip_name
        if not zip_path.exists():
            continue
        with zipfile.ZipFile(zip_path) as z:
            for name in z.namelist():
                if not name.endswith(".json"):
                    continue
                item = _extract_turns(json.loads(z.read(name)))
                if item["qa_id"] in seen_qa_ids:
                    continue  # source_id가 TL·VL 양쪽에 있는 상담(계약 6 겹침) 중복 방지
                seen_qa_ids.add(item["qa_id"])

                if split_map.get(item["source_id"]) != split:
                    continue
                if item["topic"] != TOPIC:
                    continue
                yield item


def iter_manual_samples(manual_path: Path | None, split: str = "train") -> Iterator[dict]:
    """직접 쓴 input/output 샘플을 자동 추출 결과와 같은 형태로 돌려준다.

    파일이 없거나(None) 존재하지 않으면 아무것도 돌려주지 않는다 — 없어도 동작해야 한다.
    형식: JSONL, 한 줄에 {"question", "answer", "follow_up_question", "output"} 필수,
    "source_id"·"qa_id"·"split"은 선택(비우면 각각 "manual-<줄번호>", "manual-<줄번호>", "train").
    이후 정제(is_clean)·연장 판정(infer_extendable)·복제·마스킹은 자동 추출분과 똑같이 적용된다.
    """
    if manual_path is None:
        return
    path = Path(manual_path)
    if not path.exists():
        return

    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            if raw.get("split", "train") != split:
                continue
            yield {
                "source_id": raw.get("source_id", f"manual-{i}"),
                "qa_id": raw.get("qa_id", f"manual-{i}"),
                "question": raw["question"],
                "answer": raw["answer"],
                "follow_up_question": raw["follow_up_question"],
                "output": raw["output"],
            }


def _has_unattested_number(output: str, input_text: str) -> bool:
    out_nums = set(_NUM_PATTERN.findall(output))
    in_nums = set(_NUM_PATTERN.findall(input_text))
    return bool(out_nums - in_nums)


def _has_unattested_document_keyword(output: str, input_text: str) -> bool:
    return any(keyword in output and keyword not in input_text for keyword in DOCUMENT_KEYWORDS)


def _has_unattested_product_name(output: str, input_text: str) -> bool:
    for match in _PRODUCT_PATTERN.finditer(output):
        token = match.group(0)
        if token in _ALLOWED_PRODUCT_NAMES:
            continue
        if token in input_text:
            continue
        return True
    return False


def is_clean(item: dict) -> bool:
    """output에 input(question+answer+follow_up_question)에 없는 숫자·서류명·상품명이 있으면 False(ADR-005)."""
    output = item["output"]
    input_text = item["question"] + item["answer"] + item["follow_up_question"]

    if _has_unattested_number(output, input_text):
        return False
    if _has_unattested_document_keyword(output, input_text):
        return False
    if _has_unattested_product_name(output, input_text):
        return False
    return True


def _has_extension_positive_evidence(output: str) -> bool:
    return any(
        "가능" in sentence and not _NEGSIG.search(sentence)
        for sentence in _SENTENCE_SPLIT.split(output)
    )


def _has_extension_negative_evidence(output: str) -> bool:
    return any(_NEGEXT.search(sentence) for sentence in _SENTENCE_SPLIT.split(output))


def infer_extendable(output: str, rng: random.Random) -> bool | None:
    """답변에 맞는 연장 가능 값. 모호하면 None(샘플 제외), 근거 없으면 rng로 무작위 배정."""
    positive = _has_extension_positive_evidence(output)
    negative = _has_extension_negative_evidence(output)

    if positive and negative:
        return None
    if positive:
        return True
    if negative:
        return False
    return rng.random() < 0.5


def to_messages(item: dict, extendable: bool, maturity_date: str = _SAMPLE_MATURITY) -> list[dict]:
    """system → user → assistant → user(+대출 정보·슬롯 줄) → assistant(목표). masking.mask() 적용."""
    question = mask(item["question"]).masked_text
    answer = mask(item["answer"]).masked_text
    follow_up = mask(item["follow_up_question"]).masked_text
    target = mask(item["output"]).masked_text

    extendable_text = "예" if extendable else "아니오(사유는 알 수 없음)"
    last_user = (
        f"{follow_up}\n"
        f"대출 정보: 종류={_SAMPLE_LOAN_LABEL}, 만기일={maturity_date}, 연장 가능={extendable_text}\n"
        "사용할 수 있는 슬롯: {{loan_label}}, {{principal_remaining}}, {{extendable_status}}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer},
        {"role": "user", "content": last_user},
        {"role": "assistant", "content": target},
    ]


def build_dataset(
    raw_dir: Path,
    split_path: Path,
    out_path: Path,
    split: str = "train",
    limit: int | None = None,
    manual_path: Path | None = None,
) -> int:
    """정제·연장 판정·복제·마스킹을 거쳐 JSONL로 쓰고 기록한 샘플 수를 돌려준다."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    ambiguous_excluded = 0

    items = itertools.chain(
        iter_conversations(raw_dir, split_path, split),
        iter_manual_samples(manual_path, split),
    )

    with out_path.open("w", encoding="utf-8") as f:
        for item in items:
            if not is_clean(item):
                continue

            rng = random.Random(item["source_id"])
            extendable = infer_extendable(item["output"], rng)
            if extendable is None:
                ambiguous_excluded += 1
                continue

            copies = 1
            if split == "train" and extendable is False and _has_extension_negative_evidence(item["output"]):
                copies = NO_EXTEND_COPIES

            for i in range(copies):
                maturity_date = _SAMPLE_MATURITY if i == 0 else _ALT_MATURITY
                messages = to_messages(item, extendable, maturity_date)
                f.write(json.dumps({"messages": messages}, ensure_ascii=False) + "\n")
                written += 1
                if limit is not None and written >= limit:
                    print(f"{out_path}: {written} samples ({split}), 모호해서 제외 {ambiguous_excluded}")
                    return written

    print(f"{out_path}: {written} samples ({split}), 모호해서 제외 {ambiguous_excluded}")
    return written


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="대출문의 학습 데이터 준비")
    parser.add_argument("--raw", required=True, type=Path, help="TL_은행.zip·VL_은행.zip이 있는 디렉터리")
    parser.add_argument("--split", required=True, type=Path, help="split.json 경로(ADR-008)")
    parser.add_argument("--out", required=True, type=Path, help="출력 JSONL 경로")
    parser.add_argument("--which", default="train", choices=["train", "val", "test"], help="분할 이름")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--manual", type=Path, default=None, help="직접 쓴 샘플 JSONL(선택)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    build_dataset(
        args.raw, args.split, args.out,
        split=args.which, limit=args.limit, manual_path=args.manual,
    )


if __name__ == "__main__":
    main()
