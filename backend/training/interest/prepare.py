"""cs-interest QLoRA 학습 데이터 생성 (docs/agent-interest/TRAINING_DATA_PLAN.md).

AI Hub 라벨링데이터(이자/연체금액)를 추론과 같은 입력 형식(app.agents.interest.prompt)으로 바꾸고,
추론 때 출력 검증(validate.is_valid)에 걸릴 정답은 학습에서 뺀다(INT-004).
합성 샘플(synth.py)은 --with-synth일 때만 넣는다(팀 합의 대기). 사람 검수(reviews.json)를 통과한 레코드만 학습에 쓴다.

실행: cd backend && python -m training.interest.prepare [--with-synth] [--with-manual] [--include-unreviewed] [--allow-fallback-mask]
출력: data/processed/interest/candidates.jsonl(검수 대상 전체), {train,val,test}.jsonl, stats.json
검수: data/processed/interest/reviews.json = {"<id>": {"ok": true|false, "note": "...", "output": "고친 정답(선택)"}}
"""

import argparse
import hashlib
import json
import random
import re
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from app.agents.interest.prompt import build_messages, build_slots
from app.agents.interest.validate import _RATE, is_valid, required_slots

BACKEND = Path(__file__).resolve().parents[2]
# 이자/연체금액 QA만 모은 폴더(원본 02_labeled/VL_bank/06에서 복사, 설명은 _manifest.json)
RAW_DIR = BACKEND / "data/raw/03_interest"
SPLIT_FILE = BACKEND / "data/processed/split.json"
OUT_DIR = BACKEND / "data/processed/interest"
REVIEWS_FILE = OUT_DIR / "reviews.json"

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
# 이자 정보 줄에 없는 대출 상품. 정답이 이런 상품을 말하면 이자 정보와 모순된다.
_OTHER_PRODUCT = re.compile(r"청약|소상공인|마이너스|햇살론|사잇돌|보증서|자동차|학자금|사업자|중도금|예금\s*담보|적금\s*담보")
_GENERIC_PRODUCT = {
    "주택담보대출": re.compile(r"주택\s*담보\s*대출"),
    "신용대출": re.compile(r"신용\s*대출"),
    "전세자금대출": re.compile(r"전세\s*(?:자금\s*)?대출"),
}
# 모델은 조회만 한다. 무언가를 처리했다고 말하면 지어낸 사실이다.
_CLAIM = re.compile(r"(?:완료|처리|적용|등록|신청|접수|변경|해지|정지|발송)(?:해\s?드렸|되었|됐|했|하였)")
# 챗봇이 나중에 할 수 없는 일을 약속하는 정답(문자 발송·연락·상담원 연결·확인 후 회신). "안내해 드리겠습니다"는 제외.
_PROMISE = re.compile(r"(?:발송|연결|처리|확인|등록|접수|전송|변경|신청)(?:해|하여)?\s?드리겠|연락\s?드리겠|보내\s?드리겠")
# 통화 상담의 대기 표현
_CALL_CONTEXT = re.compile(r"잠시만|기다려\s?주|대기해")
# 상담 톤(evaluate.tone_ok와 공유): 마크다운 없음, 요약체 아님, 존댓말 끝맺음, 5문장 이하
_MARKDOWN = re.compile(r"\*\*|^\s*[-*•]\s|^\s*\d+[.)]\s|^#{1,6}\s", re.M)
_SUMMARY_START = re.compile(r"^\s*고객님(?:께서는|께서)")
_POLITE_END = re.compile(r"(?:니다|세요|까요|어요|에요|예요|해요|돼요|네요|아요)[.!?]?\s*$")
_SENTENCE = re.compile(r"[^.!?]+[.!?]?")


def tone_ok(answer: str) -> bool:
    sentences = [x for x in _SENTENCE.findall(answer) if x.strip()]
    return (
        not _MARKDOWN.search(answer)
        and not _SUMMARY_START.search(answer)
        and bool(_POLITE_END.search(answer))
        and len(sentences) <= 5
    )


# 고객에게 개인정보·인증정보를 요구하는 정답. 챗봇은 원본 개인정보를 받지 않는다.
_PII_REQUEST = re.compile(r"주민\s*(?:등록)?\s*번호|비밀\s*번호|생년월일|인증\s*번호|보안\s*카드|OTP")
# 통화 요약체로 시작하는 정답("고객님께서는 ~하고자 하셨습니다")
_SUMMARY = re.compile(r"^고객님(?:께서는|께서|은|는)\s[^.]*?(?:하셨습니다|하셨고|원하십니다|원하셨|하고자|문의하셨)")

_CATEGORY_RULES = [
    ("rate", re.compile(r"금리|이율|%|퍼센트|프로")),
    ("overdue_status", re.compile(r"연체|밀린|미납")),
    ("due_date", re.compile(r"언제|납부일|며칠|날짜")),
    ("interest_amount", re.compile(r"이자.*(?:얼마|금액)|(?:얼마|금액).*이자")),
]

# 금액 바로 앞 절에 이 말이 있으면 원금·합계 등 이 에이전트 슬롯이 아닌 금액이다.
_NOT_OUR_AMOUNT = ("원금", "합", "포함", "총", "잔액", "원리금", "한도")
_OVERDUE_AMOUNT = re.compile(r"연체\s*금액|연체된\s*금액|미납된?\s*금액")
_OVERDUE_INTEREST = re.compile(r"연체\s*이자")


def load_qas(raw_dir: Path) -> list[dict]:
    rows = []
    for path in sorted(raw_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
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


def categorize(text: str) -> str:
    """TRAINING_DATA_PLAN.md 3절 유형 코드. 규칙에 안 걸리면 general."""
    for category, pattern in _CATEGORY_RULES:
        if pattern.search(text):
            return category
    return "general"


def _mentioned_product(output: str) -> str | None | bool:
    """정답이 말하는 일반 상품명. 없으면 None, 이자 정보와 맞출 수 없으면 False."""
    if _OTHER_PRODUCT.search(output):
        return False
    found = {name for name, pattern in _GENERIC_PRODUCT.items() if pattern.search(output)}
    if len(found) > 1:
        return False
    return found.pop() if found else None


# 정답이 말하는 방식 → 이자 정보 줄 값. 여러 값이 나오면 맞추지 않고 무작위로 둔다.
_TERMS = {
    "payment_method": {"가상계좌 입금": re.compile(r"가상\s*계좌"), "자동이체": re.compile(r"자동\s*이체")},
    "repayment_method": {
        "원리금균등": re.compile(r"원리금\s*균등"),
        "원금균등": re.compile(r"(?<!리)원금\s*균등"),
        "만기일시": re.compile(r"만기\s*일시"),
    },
    "interest_type": {"고정": re.compile(r"고정\s*금리"), "변동": re.compile(r"변동\s*금리")},
}
TERM_CHOICES = {field: list(values) for field, values in _TERMS.items()}


def mentioned_terms(output: str) -> dict[str, str]:
    found = {}
    for field, values in _TERMS.items():
        hits = [value for value, pattern in values.items() if pattern.search(output)]
        if len(hits) == 1:
            found[field] = hits[0]
    return found


def make_item(qa_id: str, overdue: bool, product_type: str | None = None, terms: dict | None = None) -> dict:
    """학습용 가상 조회 결과. 금액은 슬롯으로만 쓰이므로 모델 입력에는 나타나지 않는다."""
    rng = random.Random(qa_id)
    terms = terms or {}
    return {
        "loan_id": "L000",
        "product_type": product_type or rng.choice(["신용대출", "주택담보대출"]),
        **{field: terms.get(field) or rng.choice(choices) for field, choices in TERM_CHOICES.items()},
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
    product = _mentioned_product(output)
    if product is False:
        return None, "product"
    if _SUMMARY.search(output):
        return None, "summary"
    if _PII_REQUEST.search(output):
        return None, "pii_request"
    if _CLAIM.search(output):
        return None, "claim"
    if _PROMISE.search(output):
        return None, "promise"
    if _CALL_CONTEXT.search(output):
        return None, "call_context"
    if not tone_ok(output):
        return None, "tone"

    overdue = "overdue_amount" in used or bool(_OVERDUE_STATE.search(output))
    item = make_item(qa["qa_id"], overdue, product, mentioned_terms(output))
    required = required_slots(qa["follow_up"], overdue)
    if not is_valid(output, allowed_slots=set(build_slots(item)), required_slots=required):
        return None, "invalid"

    history = [
        {"role": "user", "content": mask_fn(normalize_input(qa["question"]))},
        {"role": "assistant", "content": normalize_input(qa["answer"])},
    ]
    messages = build_messages(mask_fn(normalize_input(qa["follow_up"])), history, item)
    messages.append({"role": "assistant", "content": output})
    return {
        "id": qa["qa_id"],
        "origin": "aihub",
        "source_id": qa["source_id"],
        "group_id": qa["source_id"],
        "qa_id": qa["qa_id"],
        "category": categorize(qa["question"] + " " + qa["follow_up"]),
        "scenario": "overdue" if overdue else "normal",
        "reviewed": False,
        "review_note": "",
        "item": item,
        "messages": messages,
    }, None


def assign_split(source_id: str, split_map: dict[str, str] | None = None) -> str | None:
    """공통 분할(split.json)이 있으면 그것을 따른다. 없으면 source_id 해시로 8:1:1."""
    if split_map is not None:
        return split_map.get(source_id)
    bucket = int(hashlib.sha1(source_id.encode()).hexdigest(), 16) % 10
    return "train" if bucket < 8 else "val" if bucket == 8 else "test"


def apply_review(record: dict, review: dict | None) -> dict | None:
    """검수 결과 반영. 반려면 None. 고친 정답은 추론 검증을 통과해야 한다."""
    if review is None:
        return record
    if not review.get("ok"):
        return None
    record = {**record, "reviewed": True, "review_note": review.get("note", "")}
    if "output" in review:
        item = record["item"]
        question = record["messages"][-2]["content"].split("\n")[0]
        required = required_slots(question, item["overdue_days"] > 0)
        if not is_valid(review["output"], allowed_slots=set(build_slots(item)), required_slots=required):
            raise ValueError(f"{record['id']}: 고친 정답이 출력 검증을 통과하지 못한다")
        record["messages"] = [*record["messages"][:-1], {"role": "assistant", "content": review["output"]}]
    return record


def build_dataset(
    rows: list[dict],
    mask_fn,
    split_map=None,
    synth: list[dict] = (),
    reviews: dict | None = None,
    include_unreviewed: bool = False,
) -> tuple[dict[str, list], list[dict], dict]:
    """(분할별 학습 레코드, 검수 대상 전체, 통계). 합성은 train에만 넣는다."""
    reviews = reviews or {}
    excluded: Counter = Counter()
    candidates: list[tuple[str, dict]] = []
    for qa in rows:
        sample, reason = build_sample(qa, mask_fn)
        if sample is None:
            excluded[reason] += 1
            continue
        split = assign_split(qa["source_id"], split_map)
        if split is None:
            excluded["unsplit"] += 1
            continue
        candidates.append((split, sample))
    candidates += [("train", r) for r in synth]

    splits: dict[str, list] = {"train": [], "val": [], "test": []}
    rejected = skipped = 0
    for split, record in candidates:
        record = apply_review(record, reviews.get(record["id"]))
        if record is None:
            rejected += 1
        elif record["reviewed"] or include_unreviewed:
            splits[split].append(record)
        else:
            skipped += 1

    used = [r for rows_ in splits.values() for r in rows_]
    stats = {
        "aihub_total": len(rows),
        "excluded": dict(excluded),
        "candidates": dict(Counter(r["origin"] for _, r in candidates)),
        "rejected": rejected,
        "skipped_unreviewed": skipped,
        "used": {name: len(v) for name, v in splits.items()},
        "by_origin": dict(Counter(r["origin"] for r in used)),
        "by_category": dict(Counter(r["category"] for r in used)),
        "by_scenario": dict(Counter(r["scenario"] for r in used)),
    }
    return splits, [r for _, r in candidates], stats


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


def resolve_mask(allow_fallback: bool = False):
    """공통 app.masking(팀원C)을 쓴다. 없으면 --allow-fallback-mask일 때만 임시 함수로 만든다.
    학습 입력은 서비스 게이트웨이와 같은 마스킹이어야 하므로(계약 4) 최종 학습 데이터에 임시 함수가 섞이지 않게 막는다."""
    try:
        from app.masking import mask
    except ImportError:
        if not allow_fallback:
            raise SystemExit(
                "app.masking이 없다. 실험용으로 임시 마스킹을 쓰려면 --allow-fallback-mask를 준다(최종 학습 데이터에는 쓰지 않는다)."
            )
        return fallback_mask, "fallback"
    return (lambda text: mask(text).masked_text), "app.masking"


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="cs-interest 학습 데이터 생성")
    p.add_argument("--with-synth", action="store_true", help="합성 샘플 포함(팀 합의 후)")
    p.add_argument("--synth-total", type=int, default=400)
    p.add_argument("--with-manual", action="store_true", help="사람이 고친 수동 샘플(training/interest/manual/qNN.json) 포함")
    p.add_argument("--include-unreviewed", action="store_true", help="검수 전 레코드도 학습에 포함(파이프라인 시험용)")
    p.add_argument("--out-dir", type=Path, default=OUT_DIR, help="출력 폴더(기본 data/processed/interest)")
    p.add_argument("--allow-fallback-mask", action="store_true", help="공통 app.masking이 없을 때 임시 마스킹 허용(실험용)")
    args = p.parse_args(argv)
    out_dir = args.out_dir

    mask_fn, mask_source = resolve_mask(args.allow_fallback_mask)
    split_map = json.loads(SPLIT_FILE.read_text(encoding="utf-8")) if SPLIT_FILE.exists() else None
    reviews = json.loads(REVIEWS_FILE.read_text(encoding="utf-8")) if REVIEWS_FILE.exists() else {}
    synth = []
    if args.with_synth:
        from training.interest.synth import generate

        synth = generate(total=args.synth_total)
    if args.with_manual:
        from training.interest import manual_data

        mock = json.loads((BACKEND / "app/agents/interest/mock_data.json").read_text(encoding="utf-8"))
        synth = synth + manual_data.expand(manual_data.load_manual(manual_data.MANUAL_DIR), mock)

    splits, candidates, stats = build_dataset(
        load_qas(RAW_DIR), mask_fn, split_map, synth=synth, reviews=reviews, include_unreviewed=args.include_unreviewed
    )
    stats |= {
        "mask": mask_source,
        "split": "split.json" if split_map is not None else "fallback-hash",
        "with_synth": args.with_synth,
        "with_manual": args.with_manual,
        "include_unreviewed": args.include_unreviewed,
        "reviews": len(reviews),
        "out_dir": str(out_dir),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in [*splits.items(), ("candidates", candidates)]:
        with (out_dir / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    (out_dir / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
