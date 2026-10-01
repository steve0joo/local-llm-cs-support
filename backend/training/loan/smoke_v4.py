"""v4 스모크 테스트: 등록된 cs-loan-v4가 답을 하는지, 금지 문형이 나오는지 눈으로 보려는 빠른 점검(판정 아님).

최종 확인용 10문항(golden_set_final_v4.jsonl, F01~F10)은 절대 포함하지 않는다. 그 파일은 여기서 "제외 검사"에만 읽는다:
아래 질문 중 F와 유사도 0.75 이상인 것은 건너뛴다. 사용: python training/loan/smoke_v4.py [모델 이름]
"""
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, ".")
from app import llm
from app.agents.loan import prompt, validate
from app.agents.loan.mock_api import get_loans

MODEL = sys.argv[1] if len(sys.argv) > 1 else "cs-loan-v4"
QUESTIONS = [  # (고객, 질문)
    ("C002", "대출이 끝나는 날짜 좀 알려 주세요."),
    ("C003", "잔액이 궁금합니다."),
    ("C002", "연장 신청이 되는 대출인가요?"),
    ("C003", "금리는 몇 퍼센트인가요?"),
    ("C002", "만기가 지나면 어떻게 되나요?"),
    ("C002", "[계좌번호_1] 대출 만기 알려줘."),
]
norm = lambda t: re.sub(r"[\s?.!,]", "", t)
final = [norm(json.loads(l)["question"]) for l in Path("training/loan/golden_set_final_v4.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
for customer, question in QUESTIONS:
    if any(difflib.SequenceMatcher(None, norm(question), f).ratio() >= 0.75 for f in final):
        print(f"[건너뜀] 최종 확인용 문항과 비슷함: {question}")
        continue
    loan = get_loans(customer)[0]
    text = llm.generate(MODEL, prompt.build_messages([], question, loan))
    valid = validate.is_valid_output(text, maturity_date=loan["maturity_date"], extendable=loan["extendable"])
    flags = [k for k, p in (("수있없", r"수 있|수 없"), ("처리해드", r"처리해 드"), ("검증기차단", None)) if (p and re.search(p, text)) or (p is None and not valid)]
    print(f"[{customer}] Q: {question}\n    A: {text}\n    검증기 {'통과' if valid else '차단'} / 주의 {flags or '없음'}")
