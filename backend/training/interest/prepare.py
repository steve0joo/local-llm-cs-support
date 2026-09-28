"""cs-interest QLoRA 학습 데이터 생성.

AI Hub 라벨링데이터(이자/연체금액)를 추론과 같은 입력 형식(app.agents.interest.prompt)으로 바꾸고,
추론 때 출력 검증(validate.is_valid)에 걸릴 정답은 학습에서 뺀다.

실행: cd backend && .venv/bin/python -m training.interest.prepare
"""

import hashlib
import json
import random
import re
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from app.agents.interest.prompt import build_messages, build_slots
from app.agents.interest.validate import _RATE, is_valid

BACKEND = Path(__file__).resolve().parents[2]
RAW_DIR = BACKEND / "data/raw/02_labeled/VL_bank/06"
SPLIT_FILE = BACKEND / "data/processed/split.json"
OUT_DIR = BACKEND / "data/processed/interest"

TOPIC = "이자/연체금액"

# AI Hub 비식별 기호(●○■…)와 자리표시(OOO, 0000)를 포함한 금액 표현. "원금"의 "원"은 제외한다.
_AMOUNT = re.compile(r"(?:약\s*)?[●○O0-9](?:[●○O0-9,.\s]*[●○O0-9])?\s*(?:[만천백억]\s*)?원(?!금)")
_DEID = re.compile(r"[●○■◆▲★]+(?:\s*[●○■◆▲★]+)*|O{2,}")
_ORG_PLACEHOLDER = re.compile(r"★+\s*(?=[가-힣])")
_DIGIT = re.compile(r"\d")
_BANK = re.compile(r"하나\s*(?:은행|원큐|카드|금융)")
_DOCUMENT = ("서류", "사본", "증명서", "등본", "초본", "거래내역서", "신분증", "재직", "소득")
_MENU = ("메뉴",)
_OVERDUE_STATE = re.compile(r"연체\s*(?:중|상태)|연체되어|연체되었|연체된\s*상태")

# 금액 바로 앞 절에 이 말이 있으면 원금·합계 등 이 에이전트 슬롯이 아닌 금액이다.
_NOT_OUR_AMOUNT = ("원금", "합", "포함", "총", "잔액", "원리금", "한도")
_OVERDUE_AMOUNT = re.compile(r"연체\s*금액|연체된\s*금액|미납된?\s*금액")
_OVERDUE_INTEREST = re.compile(r"연체\s*이자")


def load_qas(raw_dir: Path) -> list[dict]:
    rows = []
    for path in sorted(raw_dir.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for q in doc["qa_data"]:
            rows.append(
                {
                    "source_id": doc["source"]["source_id"],
                    "qa_id": q["qa_id"],
                    "qa_topic": q.get("qa_topic"),
                    "question": q["input"]["question"],
                    "answer": q["input"]["answer"],
                    "follow_up": q["input"]["follow_up_question"],
                    "output": q["output"],
                }
            )
    return rows


def _strip_org(text: str) -> str:
    """★★은행 → 은행, ★★카드 → 카드"""
    return _ORG_PLACEHOLDER.sub("", text)


def normalize_input(text: str) -> str:
    """고객·상담원 입력의 비식별 기호를 추론 때 모델이 보는 형태(마스킹 토큰)로 맞춘다."""
    text = _strip_org(text)
    counter = iter(range(1, 1000))
    text = _AMOUNT.sub(lambda _: f"[금액_{next(counter)}]", text)
    return _DEID.sub("○○", text)


def _slot_for(clause: str) -> str | None:
    if any(word in clause for word in _NOT_OUR_AMOUNT) or _OVERDUE_INTEREST.search(clause):
        return None
    if _OVERDUE_AMOUNT.search(clause):
        return "overdue_amount"
    if "이자" in clause:
        return "interest_due"
    return None


def convert_amounts(output: str) -> tuple[str, set[str]] | None:
    """정답 문장의 금액을 슬롯으로 바꾼다. 어느 슬롯인지 분명하지 않은 금액이 하나라도 있으면 None."""
    slots: set[str] = set()
    parts, last = [], 0
    for m in _AMOUNT.finditer(output):
        clause = re.split(r"[,.]", output[max(0, m.start() - 20) : m.start()])[-1]
        slot = _slot_for(clause)
        if slot is None:
            return None
        slots.add(slot)
        parts += [output[last : m.start()], f"{{{{{slot}}}}}"]
        last = m.end()
    return "".join(parts) + output[last:], slots


def make_item(qa_id: str, overdue: bool) -> dict:
    """학습용 가상 조회 결과. 금액은 슬롯으로만 쓰이므로 모델 입력에는 나타나지 않는다."""
    rng = random.Random(qa_id)
    return {
        "loan_id": "L000",
        "product_type": rng.choice(["신용대출", "주택담보대출"]),
        "next_due_date": (date(2026, 10, 1) + timedelta(days=rng.randint(0, 90))).isoformat(),
        "interest_due": rng.randrange(10_000, 1_000_000, 10),
        "overdue_amount": rng.randrange(10_000, 3_000_000, 10) if overdue else 0,
        "overdue_days": rng.randint(1, 60) if overdue else 0,
    }


def build_sample(qa: dict, mask_fn) -> tuple[dict | None, str | None]:
    """(샘플, None) 또는 (None, 제외 사유)."""
    if qa["qa_topic"] != TOPIC:
        return None, "topic"
    output = _strip_org(qa["output"].strip())
    if not output:
        return None, "empty"
    if _RATE.search(output):
        return None, "rate"
    converted = convert_amounts(output)
    if converted is None:
        return None, "amount"
    output, used = converted
    if _DEID.search(output):
        return None, "deid"
    if _DIGIT.search(output):
        return None, "digit"
    if _BANK.search(output):
        return None, "bank"
    if any(word in output for word in _DOCUMENT):
        return None, "document"
    if any(word in output for word in _MENU):
        return None, "menu"

    overdue = "overdue_amount" in used or bool(_OVERDUE_STATE.search(output))
    item = make_item(qa["qa_id"], overdue)
    required = {"overdue_amount"} if overdue else set()
    if not is_valid(output, allowed_slots=set(build_slots(item)), required_slots=required):
        return None, "invalid"

    history = [
        {"role": "user", "content": mask_fn(normalize_input(qa["question"]))},
        {"role": "assistant", "content": normalize_input(qa["answer"])},
    ]
    messages = build_messages(mask_fn(normalize_input(qa["follow_up"])), history, item)
    messages.append({"role": "assistant", "content": output})
    return {"source_id": qa["source_id"], "qa_id": qa["qa_id"], "messages": messages}, None


def assign_split(source_id: str, split_map: dict[str, str] | None = None) -> str | None:
    """공통 분할(split.json)이 있으면 그것을 따른다. 없으면 source_id 해시로 8:1:1."""
    if split_map is not None:
        return split_map.get(source_id)
    bucket = int(hashlib.sha1(source_id.encode()).hexdigest(), 16) % 10
    return "train" if bucket < 8 else "val" if bucket == 8 else "test"


def build_dataset(rows: list[dict], mask_fn, split_map=None) -> tuple[dict[str, list], dict]:
    splits: dict[str, list] = {"train": [], "val": [], "test": []}
    excluded: Counter = Counter()
    for qa in rows:
        split = assign_split(qa["source_id"], split_map)
        if split is None:
            excluded["unsplit"] += 1
            continue
        sample, reason = build_sample(qa, mask_fn)
        if sample is None:
            excluded[reason] += 1
        else:
            splits[split].append(sample)
    kept = sum(len(v) for v in splits.values())
    return splits, {"total": len(rows), "kept": kept, "excluded": dict(excluded)}


# --- 마스킹: 팀원C의 app.masking이 머지되면 그것을 쓴다 -------------------------

_FALLBACK_PATTERNS = [  # 계약 4 순서(긴 패턴 먼저)
    ("주민번호", re.compile(r"\d{6}-\d{7}")),
    ("카드번호", re.compile(r"\d{4}-\d{4}-\d{4}-\d{4}")),
    ("전화번호", re.compile(r"01[016789]-?\d{3,4}-?\d{4}")),
    ("계좌번호", re.compile(r"\d{2,6}-\d{2,6}-\d{2,6}")),
    ("금액", re.compile(r"\d[\d,]*\s*[만천]?\s*원(?!금)")),
]


def fallback_mask(text: str) -> str:
    for kind, pattern in _FALLBACK_PATTERNS:
        seen: dict[str, str] = {}
        existing = len(re.findall(rf"\[{kind}_\d+\]", text))

        def repl(m, kind=kind, seen=seen, existing=existing):
            if m.group() not in seen:
                seen[m.group()] = f"[{kind}_{existing + len(seen) + 1}]"
            return seen[m.group()]

        text = pattern.sub(repl, text)
    return text


def resolve_mask():
    try:
        from app.masking import mask
    except ImportError:
        return fallback_mask, "fallback"
    return (lambda text: mask(text).masked_text), "app.masking"


def main() -> None:
    mask_fn, mask_source = resolve_mask()
    split_map = json.loads(SPLIT_FILE.read_text(encoding="utf-8")) if SPLIT_FILE.exists() else None

    splits, stats = build_dataset(load_qas(RAW_DIR), mask_fn, split_map)
    stats |= {
        "mask": mask_source,
        "split": "split.json" if split_map is not None else "fallback-hash",
        "sizes": {name: len(rows) for name, rows in splits.items()},
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, rows in splits.items():
        with (OUT_DIR / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    (OUT_DIR / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
