import json
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
TL_ZIP = BACKEND / "data" / "raw" / "TL_은행.zip"              # Training 40,000 QA
VL_ZIP = BACKEND / "data" / "raw" / "VL_은행.zip"              # Validation 5,000 QA
OUT_PATH = BACKEND / "data" / "processed" / "split.json"      # {source_id: "train" | "val" | "test"} — gitignore

BANK = "은행"


# zip 하나 → {source_id: consulting_topic}. 압축은 풀지 않고 파일 단위로 읽는다.
def read_consultations(zip_path: Path) -> dict[str, str]:
    consultations: dict[str, str] = {}

    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if not name.endswith(".json"):
                continue
            doc = json.loads(z.read(name))
            if doc["consulting"]["consulting_category"] != BANK:   # 은행 상담만
                continue
            # 파일 1개 = QA 1개. 같은 상담(source_id)의 QA 여러 개가 여기서 키 하나로 합쳐진다 -> 한 상담의 주제는 하나라고 가정
            consultations[doc["source"]["source_id"]] = doc["consulting"]["consulting_topic"]

    return consultations


# 분할 규칙 (ADR-008). 무작위 없음 — split.json으로
def split(tl: dict[str, str], vl: dict[str, str]) -> dict[str, str]:
    result = {source_id: "train" for source_id in tl}          # TL 상담은 전부 train

    by_topic: dict[str, list[str]] = defaultdict(list)          # VL 상담을 주제별로 모은다
    for source_id, topic in vl.items():
        if source_id not in tl:                                 # TL·VL 양쪽에 있는 상담은 train에 남긴다
            by_topic[topic].append(source_id)

    for topic in sorted(by_topic):
        for i, source_id in enumerate(sorted(by_topic[topic])):     # source_id 정렬 → 실행 순서와 무관하게 같은 결과
            result[source_id] = "val" if i % 2 == 0 else "test"    # 주제별로 번갈아 배정 → 반씩 나뉜다

    return result


def main() -> None:
    result = split(read_consultations(TL_ZIP), read_consultations(VL_ZIP))
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")

    print(f"{OUT_PATH}: {dict(Counter(result.values()))}")


if __name__ == "__main__":      # python -m training.common.split
    main()
