"""사람이 고친 모범 답변(수동 샘플) → 개별 JSON → 학습 레코드.

manual/answers_fix.md·answers_ok.md의 `수정 답:`을 읽어 manual/qNN.json으로 저장하고(직접 쓴 데이터라 커밋 가능),
prepare.py --with-manual이 이를 학습 레코드로 바꾼다.

답에 쓸 수 있는 자리표시: {due} 다음 납부일 · {days} 연체 일수 · {pay} 납부 방법 · {repay} 상환 방식 · {rate_type} 금리 방식.
늘리기: 질문이 특정 조회값(연체 2일·65일, 납부일 임박, 자동이체 등)을 전제할 수 있어 원래 고객의 조회값은 그대로 두고
대출 종류만 바꾼다(문항당 3개). 모든 레코드는 학습 데이터와 같은 검사를 통과해야 한다.

변환: cd backend && python -m training.interest.manual_data
"""

import json
import re
from pathlib import Path

from app.agents.interest.balance_source import enrich
from app.agents.interest.prompt import build_messages, build_slots
from app.agents.interest.validate import is_valid, required_slots
from training.interest import prepare
from training.interest.synth import PRODUCT_TYPES

MANUAL_DIR = Path(__file__).resolve().parent / "manual"
_BLOCK = re.compile(r"(?m)^## (\d{2})\. \[(C\d{3})\] (.+)$")
_FIELD = re.compile(r"(?m)^- (좋은 답의 조건|v03 답|판정 메모): (.*)$")
_ANSWER = re.compile(r"(?m)^수정 답:[ \t]*(.*)$")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DAYS = re.compile(r"(\d+)일(?=\s?(?:연체|째))")
_PRODUCT = re.compile("|".join(sorted(PRODUCT_TYPES, key=len, reverse=True)))


def _templatize(text: str) -> str:
    """'그대로' 쓰는 v03 답의 고객 값을 자리표시로: 날짜 → {due}, N일 연체 → {days}일, 상품명 → {{loan_label}}."""
    text = _DATE.sub("{due}", text)
    text = _DAYS.sub("{days}일", text)
    return _PRODUCT.sub("{{loan_label}}", text)


def parse_answers_md(text: str, source: str) -> list[dict]:
    rows = []
    heads = list(_BLOCK.finditer(text))
    for i, head in enumerate(heads):
        body = text[head.end() : heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        fields = dict(_FIELD.findall(body))
        m = _ANSWER.search(body)
        answer = (m.group(1).strip() if m else "")
        no = int(head.group(1))
        v03 = fields.get("v03 답", "").strip()
        if not answer:
            raise ValueError(f"{no:02d}번 수정 답이 비어 있다")
        train = answer != "(학습 제외)"
        if answer in ("그대로", "(학습 제외)"):
            answer = _templatize(v03) if train else v03
        rows.append(
            {
                "no": no,
                "customer": head.group(2),
                "question": head.group(3).strip(),
                "check": fields.get("좋은 답의 조건", "").strip(),
                "v03_answer": v03,
                "note": fields.get("판정 메모", "").strip(),
                "source": source,
                "answer": answer,
                "train": train,
            }
        )
    return rows


def fill(text: str, item: dict) -> str:
    for key, value in {
        "{due}": item["next_due_date"],
        "{days}": str(item["overdue_days"]),
        "{pay}": item["payment_method"],
        "{repay}": item["repayment_method"],
        "{rate_type}": item["interest_type"],
    }.items():
        text = text.replace(key, value)
    return text


def write_json(rows: list[dict], out_dir: Path = MANUAL_DIR) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for r in rows:
        (out_dir / f"q{r['no']:02d}.json").write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_manual(manual_dir: Path = MANUAL_DIR) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(manual_dir).glob("q*.json"))]


def _problems(text: str, question: str, item: dict) -> list[str]:
    """학습 데이터(prepare.build_sample)와 같은 기준."""
    checks = {
        "출력 검증": is_valid(text, set(build_slots(item)), required_slots(question, item["overdue_days"] > 0)),
        "서류": not any(w in text for w in prepare._DOCUMENT),
        "메뉴": not any(w in text for w in prepare._MENU),
        "은행명": not prepare._BANK.search(text),
        "처리 주장": not prepare._CLAIM.search(text),
        "행동 약속": not prepare._PROMISE.search(text),
        "개인정보 요구": not prepare._PII_REQUEST.search(text),
        "통화 대기": not prepare._CALL_CONTEXT.search(text),
        "상담 톤": prepare.tone_ok(text),
        "자리표시 남음": not re.search(r"\{(?:due|days|pay|repay|rate_type)\}", text),
    }
    return [name for name, ok in checks.items() if not ok]


def expand(rows: list[dict], mock: dict) -> list[dict]:
    from training.interest.ask import HOLD_QUESTIONS  # 평가 전용 질문은 학습에 넣지 않는다

    held = {q for _, q, _ in HOLD_QUESTIONS}
    records = []
    for r in rows:
        if not r["train"]:
            continue
        if r["question"] in held:
            raise ValueError(f"q{r['no']:02d}: hold30 평가 전용 질문이라 학습에 넣을 수 없다 — {r['question']}")
        base = mock[r["customer"]][0]
        for i, product in enumerate(PRODUCT_TYPES):
            item = enrich({**base, "product_type": product}, r["customer"])  # 서비스와 같이 자동이체 잔액 비교 결과 포함
            text = fill(r["answer"], item)
            problems = _problems(text, r["question"], item)
            if problems:
                raise ValueError(f"q{r['no']:02d} ({product}): {', '.join(problems)} — {text}")
            messages = build_messages(r["question"], [], item)
            messages.append({"role": "assistant", "content": text})
            records.append(
                {
                    "id": f"manual-q{r['no']:02d}-{i}",
                    "origin": "manual",
                    "source_id": f"manual-q{r['no']:02d}",
                    "group_id": f"manual-q{r['no']:02d}",
                    "no": r["no"],
                    "customer": r["customer"],
                    "question": r["question"],
                    "category": prepare.categorize(r["question"]),
                    "scenario": "overdue" if item["overdue_days"] > 0 else "normal",
                    "reviewed": True,  # 사람이 확인한 답
                    "review_note": r.get("note", ""),
                    "item": item,
                    "messages": messages,
                }
            )
    return records


def main() -> None:
    rows = []
    for name, source in (("answers_fix.md", "fix"), ("answers_ok.md", "ok"), ("weak_fix.md", "fix"), ("weak_ok.md", "ok"),
                         ("debit_fix.md", "fix"), ("debit_ok.md", "ok"), ("reinforce_v05.md", "fix")):
        if (MANUAL_DIR / name).exists():
            rows += parse_answers_md((MANUAL_DIR / name).read_text(encoding="utf-8"), source)
    rows.sort(key=lambda r: r["no"])
    mock = json.loads((prepare.BACKEND / "app/agents/interest/mock_data.json").read_text(encoding="utf-8"))
    records = expand(rows, mock)  # 검사 실패가 있으면 여기서 멈춘다
    write_json(rows)
    print(f"JSON {len(rows)}개 저장 ({MANUAL_DIR}) · 학습 {sum(r['train'] for r in rows)}문항 → 레코드 {len(records)}개")


if __name__ == "__main__":
    main()
