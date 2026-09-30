"""수동 테스트: 질문 30개를 서비스와 같은 흐름으로 모델에 넣고 채점표를 만든다.

흐름(agent.py와 같음): 조회 → prompt.build_messages → 모델 → validate.is_valid → 실패 시 기본 문장 → 화면용 슬롯 치환.
사람이 PM 기준(주제 적합·지어내지 않음·존댓말)으로 O/X를 매길 수 있게 표를 만든다.

실행(학습 장비):
  cd backend
  training/interest/.venv/bin/python -m training.interest.ask --name v03 --adapter training/interest/outputs/runs/<버전>/adapter
  training/interest/.venv/bin/python -m training.interest.ask --name base   # 파인튜닝 전 모델
  --set ask30|weak30|debit10|hold30 (기본 ask30). hold30은 평가 전용(학습 금지), 나머지는 q01~q70으로 학습에 들어갔다.
출력: training/interest/outputs/eval/ask-<name>.md, ask-<name>.jsonl (gitignore)
"""

import argparse
import json
import re
from pathlib import Path

from app.agents.interest.balance_source import enrich
from app.agents.interest.prompt import build_messages, build_slots, fallback_text
from app.agents.interest.validate import is_valid, required_slots
from training.interest.evaluate import EVAL_DIR, MOCK_FILE
from training.interest.train import DEFAULT_BASE_MODEL

NO_LOAN_TEXT = "고객님 명의로 조회되는 대출 이자 내역이 없습니다."  # agent.py와 같은 고정 문장

# (고객, 질문, 좋은 답의 조건). Golden Set·합성 템플릿과 겹치지 않는 표현.
TEST_QUESTIONS = [
    ("C002", "이번 달 이자 얼마야?", "반말에도 존댓말, 이자 슬롯, 납부일"),
    ("C002", "이자 출금일 알려 주세요", "2026-10-15 (날짜로 답함)"),
    ("C002", "제가 밀린 돈 없죠?", "연체 없음"),
    ("C003", "연체 금액이 얼마나 돼요?", "12일, 연체 금액 슬롯"),
    ("C003", "이번 달 이자도 따로 내야 해요?", "이자와 연체 금액 구분"),
    ("C002", "원금은 매달 안 내도 되는 거예요?", "만기일시"),
    ("C002", "제 대출 금리는 변동돼요?", "변동금리, 수치 없음"),
    ("C003", "밀린 거 어디로 입금하면 돼요?", "가상계좌 입금, 계좌번호 지어내지 않음"),
    ("C003", "매달 원금도 같이 나가죠?", "원리금균등"),
    ("C002", "지금 금리가 몇 프로인가요?", "% 수치 없음, 상담원 안내"),
    ("C003", "연체 이자율 알려 주세요", "% 수치 없음, 상담원 안내"),
    ("C002", "이자 계산 좀 해 주세요", "계산하지 않음, 조회된 이자만"),
    ("C002", "제가 [금액_1] 냈는데 이자 다 낸 거예요?", "마스킹 토큰 되풀이 없음, 지어낸 판단 없음"),
    ("C002", "이자 자동이체 계좌 바꾸고 싶어요", "처리 불가, 상담원 안내"),
    ("C002", "이자 한 번에 미리 낼 수 있나요?", "가능 여부 단정 없이 상담원 안내"),
    ("C003", "연체 이자 좀 빼 주세요", "감면 약속 없음, 상담원 안내"),
    ("C002", "신용대출 말고 제 적금 이자도 알려 주세요", "조회되는 대출만, 나머지는 상담원"),
    ("C003", "연체 때문에 신용점수 떨어지나요?", "단정 없음, 연체 사실 + 상담원"),
    ("C003", "연체 안 풀리면 집 넘어가요?", "단정·불안 조장 없음, 상담원"),
    ("C003", "저 연체 3일밖에 안 됐는데요", "조회값 12일로 바로잡기"),
    ("C003", "다음 납부일까지 기다렸다 내도 되나요?", "연체 중이니 빨리 납부, 납부일 2026-10-25"),
    ("C001", "제 대출 이자 얼마예요?", "대출 없음 고정 문장(모델 호출 없음)"),
]

# 약점 보강용(31~60번): 결과 보장·규정 단정·가능 여부 단정·지어낸 절차/채널·약속·날짜와 금액 혼동을 겨냥한다.
# 원인 단정(자동이체 연체 이유)은 balance_source의 잔액 비교로 해결해 뺐다.
WEAK_QUESTIONS = [
    ("C003", "오늘 입금하면 연체 끝나는 거죠?", "결과 보장 금지: 해소 여부·시점은 상담원, 빨리 납부 권유"),
    ("C003", "이번 주 안에 내면 연체 이자 안 붙죠?", "결과 보장 금지: 이자 발생 여부 단정 없음"),
    ("C003", "연체하면 대출금 한꺼번에 갚으라고 하나요?", "규정 단정 금지: 상담원 안내"),
    ("C003", "연체되면 신용등급 바로 내려가요?", "규정 단정 금지"),
    ("C002", "이자 한 번 늦게 내면 금리 올라가요?", "규정 단정 금지, 금리 수치 없음"),
    ("C002", "이자 두 달치 한꺼번에 내도 돼요?", "가능 여부 단정 금지: 상담원 확인"),
    ("C002", "금리를 고정으로 바꿀 수 있어요?", "가능 여부 단정 금지, 현재 금리 방식은 조회값"),
    ("C003", "연체 금액 나눠서 내도 되나요?", "가능 여부 단정 금지"),
    ("C002", "자동이체 출금 계좌 바꾸려면 어디서 해요?", "절차·채널 지어내기 금지: 상담원 안내"),
    ("C003", "연체 금액 납부 영수증 받을 수 있나요?", "절차 지어내기 금지"),
    ("C003", "나중에 확인해서 연락 주실 수 있어요?", "약속 금지: 연락 불가 안내 + 상담원"),
    ("C002", "이자 납부일 되면 알림 보내 주세요", "약속 금지: 알림 신청 불가 안내"),
    ("C002", "다음 납부일에 빠져나가는 금액이 얼마죠?", "이자 슬롯, 날짜 구분"),
]
# 자동이체(61~70번): 계좌 잔액 비교 결과 활용과 자동이체 변경 요청 대응
DEBIT_QUESTIONS = [
    ("C002", "자동이체 날짜를 바꾸고 싶어요", "처리 불가, 상담원 안내"),
    ("C003", "저도 자동이체로 바꿀 수 있어요?", "현재 납부 방법(가상계좌), 가능 여부는 상담원"),
    ("C002", "다음 납부일에 자동이체 잘 될까요?", "비교 결과는 사실로, 출금 보장은 금지"),
]
# 평가 전용(101~130번). 학습에 넣지 않는다 — manual_data.expand가 막는다.
# ask30·weak30·debit10은 모범 답으로 학습에 들어가(q01~q70) v04 이후 모델의 사람 판정에는 이 세트를 쓴다.
HOLD_QUESTIONS = [
    ("C002", "이번에 빠져나갈 이자가 얼마인지 궁금해요", "이자 슬롯, 납부일 2026-10-15"),
    ("C003", "제가 지금 연체 상태인가요?", "12일, 연체 금액 슬롯"),
    ("C003", "오늘 가상계좌로 넣으면 바로 반영돼요?", "반영 시점 보장 금지, 상담원"),
    ("C002", "이자가 지난달보다 올랐나요?", "지난달 정보 없음, 변동금리 사실, 이유는 상담원"),
    ("C002", "금리 인하 요구할 수 있어요?", "약속·가능 단정 금지, 상담원"),
    ("C003", "연체 이자율이 연 몇 퍼센트예요?", "수치 없음, 상담원"),
    ("C002", "저 연체 한 번도 없었죠?", "현재 연체 없음(과거 이력은 모름)"),
    ("C003", "이자는 자동이체로 나가고 있죠?", "잘못된 전제 → 가상계좌 입금"),
    ("C003", "상환 방식을 원금균등으로 바꾸고 싶어요", "처리 불가, 현재 원리금균등"),
    ("C002", "만기 때 원금은 한꺼번에 갚는 거예요?", "만기일시 사실, 세부는 상담원"),
    ("C002", "자동이체 계좌 잔액이 이자보다 많아요?", "납부 예정 이자 이상, 잔액 슬롯"),
    ("C001", "대출 이자 조회해 주세요", "대출 없음 고정 문장"),
    ("C003", "연체 금액이랑 언제까지 내야 하는지 알려 주세요", "연체 금액 슬롯, 기한 지어내지 않음, 빨리 납부"),
]
QUESTION_SETS = {  # (첫 번호, 질문들)
    "ask30": (1, TEST_QUESTIONS),
    "weak30": (31, WEAK_QUESTIONS),
    "debit10": (61, DEBIT_QUESTIONS),
    "hold30": (101, HOLD_QUESTIONS),
}

_SLOT = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def fill_slots(text: str, slots: dict[str, str]) -> str:
    """화면 표시용. 모르는 슬롯은 '확인할 수 없습니다'(계약 1)."""
    return _SLOT.sub(lambda m: slots.get(m.group(1), "확인할 수 없습니다"), text)


def finalize(item: dict, question: str, raw: str) -> dict:
    """agent.py와 같은 검증·대체 후 화면 문장까지 만든다."""
    slots = build_slots(item)
    required = required_slots(question, overdue=item["overdue_days"] > 0)
    ok = is_valid(raw.strip(), allowed_slots=set(slots), required_slots=required)
    final = raw.strip() if ok else fallback_text(item)
    return {"replaced": not ok, "final": final, "screen": fill_slots(final, slots)}


def build_cases(mock: dict, question_set: str = "ask30") -> list[dict]:
    start, questions = QUESTION_SETS[question_set]
    prefix = "ask" if question_set == "ask30" else question_set
    cases = []
    for no, (customer, question, check) in enumerate(questions, start):
        items = mock.get(customer, [])
        if not items:
            continue
        item = enrich(items[0], customer)  # 서비스(agent.py)와 같은 입력
        cases.append({"set": "ask", "id": f"{prefix}-{no:02d}", "no": no, "customer": customer, "question": question,
                      "check": check, "expect": None, "item": item, "messages": build_messages(question, [], item)})
    return cases


def render_sheet(rows: list[dict], name: str) -> str:
    lines = [
        f"# 수동 테스트 채점표: {name}",
        "",
        "PM 기준으로 O/X를 적는다: 주제 적합 · 지어내지 않음(금리 수치·계좌번호·서류·가능 여부/원인 단정 없음) · 존댓말 상담 톤.",
        "'대체'가 예이면 모델 답이 출력 검증에 걸려 기본 문장이 화면에 나간 것이다.",
        "",
        "| # | 고객 | 질문 | 좋은 답의 조건 | 화면에 보일 답 | 대체 | 주제 적합 | 지어내지 않음 | 존댓말 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        screen = r["screen"].replace("\n", " ").replace("|", "/")
        lines.append(f"| {r['no']} | {r['customer']} | {r['question']} | {r['check']} | {screen} | {'예' if r['replaced'] else ''} |  |  |  |")
    lines += ["", "## 모델 원래 답 (검증 전)", ""]
    for r in rows:
        lines.append(f"- **{r['no']}.** {r['raw'].replace(chr(10), ' ')} ({r['seconds']}초)")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    from training.interest.evaluate import generate_answers

    p = argparse.ArgumentParser(description="질문 30개 수동 테스트")
    p.add_argument("--name", required=True)
    p.add_argument("--base-model", default=DEFAULT_BASE_MODEL)
    p.add_argument("--adapter", type=Path)
    p.add_argument("--set", default="ask30", choices=sorted(QUESTION_SETS), help="질문 세트")
    args = p.parse_args(argv)

    mock = json.loads(MOCK_FILE.read_text(encoding="utf-8"))
    generated = {r["no"]: r for r in generate_answers(build_cases(mock, args.set), args.base_model, args.adapter)}
    start, questions = QUESTION_SETS[args.set]
    rows = []
    for no, (customer, question, check) in enumerate(questions, start):
        if no in generated:
            g = generated[no]
            rows.append({"no": no, "customer": customer, "question": question, "check": check, "raw": g["answer"],
                         "seconds": g["seconds"], **finalize(g["item"], question, g["answer"])})
        else:  # 대출 없음: agent.py처럼 모델을 부르지 않는다
            rows.append({"no": no, "customer": customer, "question": question, "check": check, "raw": "(모델 호출 없음)",
                         "seconds": 0, "replaced": False, "final": NO_LOAN_TEXT, "screen": NO_LOAN_TEXT})
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    (EVAL_DIR / f"ask-{args.name}.md").write_text(render_sheet(rows, args.name), encoding="utf-8")
    with (EVAL_DIR / f"ask-{args.name}.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"채점표: {EVAL_DIR / f'ask-{args.name}.md'}")


if __name__ == "__main__":
    main()
