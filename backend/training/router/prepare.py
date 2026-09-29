import json
import re
import zipfile
from collections import Counter
from pathlib import Path

from app.masking import mask
from app.router.topics import SYSTEM_PROMPT, TOPIC_LABELS
from training.common.split import BANK, OUT_PATH as SPLIT_PATH, TL_ZIP, VL_ZIP

OUT_DIR = SPLIT_PATH.parent / "router"
CAP_PER_TOPIC = 3000                                    # train만. 대출·이자/연체가 절반을 넘어서 (RT-005)
CODE_BY_LABEL = {label: code for code, label in TOPIC_LABELS.items()}
HIDDEN_AMOUNT = re.compile(r"●[●\s]*원")                # 원본이 이미 가린 금액: "●●●원", "●●● ●원"


def mask_question(text: str) -> str:
    result = mask(text)
    next_no = sum(1 for token in result.mask_map if token.startswith("[금액_")) + 1
    seen: dict[str, str] = {}

    def replace(m):
        if m.group(0) not in seen:
            seen[m.group(0)] = f"[금액_{next_no + len(seen)}]"
        return seen[m.group(0)]

    return HIDDEN_AMOUNT.sub(replace, result.masked_text)


def read_examples(zip_path: Path):
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if not name.endswith(".json"):
                continue
            doc = json.loads(z.read(name))
            topic = doc["consulting"]["consulting_topic"]
            code = CODE_BY_LABEL.get(topic)
            if doc["consulting"]["consulting_category"] != BANK or code is None:
                continue
            for qa in doc["qa_data"]:
                if qa.get("qa_topic") == topic:                       # 두 라벨이 다르면 어느 쪽이 맞는지 알 수 없다
                    yield {"source_id": doc["source"]["source_id"], "qa_id": qa["qa_id"],
                           "code": code, "question": mask_question(qa["input"]["question"])}


def to_record(example: dict) -> dict:
    return {"messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": example["question"]},
        {"role": "assistant", "content": example["code"]},
    ]}


def main(zips=(TL_ZIP, VL_ZIP), split_path: Path = SPLIT_PATH, out_dir: Path = OUT_DIR, cap: int = CAP_PER_TOPIC) -> None:
    split_map = json.loads(split_path.read_text(encoding="utf-8"))
    sets: dict[str, list[dict]] = {"train": [], "val": [], "test": []}
    for zip_path in zips:
        for example in read_examples(zip_path):
            name = split_map.get(example["source_id"])                # split.json에 없는 상담은 버린다
            if name in sets:
                sets[name].append(example)

    out_dir.mkdir(parents=True, exist_ok=True)

    for name, examples in sets.items():
        examples.sort(key=lambda e: (e["code"], e["source_id"], e["qa_id"]))
        if name == "train" and cap:
            taken: Counter[str] = Counter()                           # 정렬돼 있으므로 주제별 앞 cap개
            examples = [e for e in examples if taken.update([e["code"]]) or taken[e["code"]] <= cap]
        with (out_dir / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            for example in examples:
                f.write(json.dumps(to_record(example), ensure_ascii=False) + "\n")
        counts = Counter(e["code"] for e in examples)
        print(f"{name:5s} {len(examples):6d}  " + "  ".join(f"{code}={counts[code]}" for code in TOPIC_LABELS))


if __name__ == "__main__":
    main()
