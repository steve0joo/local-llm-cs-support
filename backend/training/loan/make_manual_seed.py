import json
from pathlib import Path

# 수동 샘플은 서비스처럼 첫 메시지에 바로 최종 답을 주는 구조로 학습한다.
# prepare.to_messages가 answer/follow_up이 둘 다 비면 가짜 히스토리를 붙이지 않는다.
PAIRS = [("", "")]

D_YES = "2027-03-31"  # C002 신용대출, 연장 가능
D_NO = "2035-06-30"   # C003 주택담보대출, 연장 불가

# mock 날짜 2개 + 학습용 날짜. 풀 크기를 홀수(7)로 둬서 연장 가능/불가 교대 패턴과 날짜가 짝지어지지 않게 한다.
DATE_POOL = [D_YES, D_NO, "2026-12-20", "2028-09-15", "2030-12-31", "2032-03-10", "2033-11-25"]

rows = []


def combo_date(i, ext, cross_n, aligned_n=2):
    """날짜-연장 여부 조합 배정. 앞 cross_n건은 mock 날짜와 반대 연장 여부(가능=D_NO, 불가=D_YES),
    다음 aligned_n건은 mock과 같은 조합, 나머지는 학습용 날짜 풀을 돌린다."""
    if i < cross_n:
        return D_NO if ext else D_YES
    if i < cross_n + aligned_n:
        return D_YES if ext else D_NO
    return DATE_POOL[2:][i % len(DATE_POOL[2:])]


def add(prefix, question, output, extendable, maturity=None):
    idx = sum(1 for r in rows if r["source_id"].startswith(prefix + "-"))
    ans, fu = PAIRS[len(rows) % len(PAIRS)]
    row = {
        "source_id": f"{prefix}-{idx:02d}",
        "qa_id": f"{prefix}-{idx:02d}",
        "question": question,
        "answer": ans,
        "follow_up_question": fu,
        "output": output,
        "extendable": extendable,
        # 만기가 답에 안 나오는 샘플은 날짜를 풀에서 돌려 배정한다(연장 여부와 무관하게)
        "maturity_date": maturity or DATE_POOL[len(rows) % len(DATE_POOL)],
    }
    rows.append(row)


# 1. 만기일: 날짜 없는 질문 위주
MAT_Q = [
    "제 대출 만기가 언제예요?",
    "만기일 좀 알려주세요.",
    "대출 만기가 언제인가요?",
    "만기일이 궁금합니다.",
    "언제까지 갚아야 하나요?",
    "제 대출 만기일 확인해 주세요.",
    "대출 만기가 언제까지인가요?",
    "만기일이 며칠인지 알려주세요.",
    "제 대출은 언제 만기가 되나요?",
    "대출 만기 날짜 좀 확인해 주세요.",
    # 2026-09-29 v2 확장: 표현 다양화. Golden Set·검증기 개발 질문과 겹치지 않는다(tests/loan/test_golden_set.py).
    "만기가 언제 도래하나요?",
    "대출 상환 기한이 언제로 잡혀 있나요?",
    "마지막 상환일이 언제예요?",
    "대출 끝나는 시점을 알려주세요.",
    "만기일이 언제로 조회되나요?",
    "언제 만기인지 확인 부탁드려요.",
    "계약 만기가 어떻게 되나요?",
    "대출 만료일이 궁금해요.",
]
MAT_OUT = [
    "고객님의 {{loan_label}} 만기일은 {d}입니다.",
    "확인 결과, 고객님의 {{loan_label}} 만기일은 {d}인 것으로 조회됩니다.",
    "조회해 보니 고객님의 {{loan_label}} 만기는 {d}입니다.",
]
for i, q in enumerate(MAT_Q[:6]):
    for ext, d in ((True, D_YES), (False, D_NO)):
        add("manual-maturity", q, MAT_OUT[i % 3].replace("{d}", d), ext, d)
# mock 날짜와 반대 연장 여부 조합: 날짜만 보고 연장 여부를 맞히는 지름길을 막는다
for i, q in enumerate(MAT_Q[6:]):
    for ext, d in ((False, D_YES), (True, D_NO)):
        add("manual-maturity", q, MAT_OUT[(i + 1) % 3].replace("{d}", d), ext, d)
# 풀의 나머지 날짜로 만기 샘플 추가. 프롬프트 날짜와 답 날짜는 같은 값이다.
for i, d in enumerate(DATE_POOL[2:]):
    add("manual-maturity", MAT_Q[i % len(MAT_Q)],
        MAT_OUT[i % 3].replace("{d}", d), i % 2 == 0, d)
    
# 고객이 말한 날짜가 맞을 때 1건씩, 틀릴 때 2건 (고객 말을 그대로 확인해 주지 않도록)
add("manual-maturity", f"제 대출 만기가 {D_YES} 맞나요?",
    f"네, 조회해 보니 고객님의 {{{{loan_label}}}} 만기일은 {D_YES}이 맞습니다.", True, D_YES)
add("manual-maturity", f"만기가 {D_NO}이라고 알고 있는데 맞나요?",
    f"네, 고객님의 {{{{loan_label}}}} 만기일은 {D_NO}으로 조회됩니다.", False, D_NO)
add("manual-maturity", "만기가 2027-04-30이라고 들었는데 맞나요?",
    f"확인해 보니 고객님의 {{{{loan_label}}}} 만기일은 {D_YES}인 것으로 조회됩니다.", True, D_YES)
add("manual-maturity", "안내 문자에 만기일이 2034-01-15로 왔는데 맞나요?",
    f"확인해 보니 고객님의 {{{{loan_label}}}} 만기일은 {D_NO}인 것으로 조회됩니다.", False, D_NO)
# 2. 남은 원금
PR_Q = [
    "제 대출 남은 원금이 얼마예요?",
    "대출 잔액이 궁금합니다.",
    "남은 대출 원금 좀 알려주세요.",
    "제가 갚아야 할 원금이 얼마나 남았나요?",
    "대출 남은 금액 확인해 주세요.",
    "원금이 얼마나 남았는지 궁금해요.",
    "지금 기준 대출 남은 금액이 얼마인가요?",
    "제 대출 잔여 원금을 알고 싶어요.",
    "대출금이 얼마나 남았는지 알려주세요.",
    "남아 있는 대출 원금 확인 부탁드립니다.",
    "현재 대출 잔액이 어떻게 되나요?",
    "아직 갚지 못한 원금이 얼마인가요?",
    "갚을 원금이 얼마나 남아 있나요?",
    "대출 원금 잔액을 알려 주세요.",
    "지금 남아 있는 대출 금액이 어느 정도인가요?",
    "제 대출에서 아직 남은 원금이 궁금합니다.",
    "원금 잔액 확인 부탁해요.",
    "남은 대출 원금이 얼마인지 알 수 있을까요?",
]
PR_OUT = [
    "고객님의 {{loan_label}} 남은 원금은 {{principal_remaining}}입니다.",
    "확인 결과, 고객님의 {{loan_label}} 남은 원금은 {{principal_remaining}}으로 조회됩니다.",
    "조회해 보니 고객님의 {{loan_label}} 잔여 원금은 {{principal_remaining}}입니다.",
]
for i, q in enumerate(PR_Q):
    ext = i % 2 == 0
    add("manual-principal", q, PR_OUT[i % 3], ext, combo_date(i, ext, cross_n=6))

# 갚은 금액은 데이터에 없으므로 남은 원금만 안내
for q, ext in (("지금까지 얼마나 갚았고 얼마 남았나요?", True),
               ("제 대출 원금 상환 현황이 궁금합니다.", False)):
    add("manual-principal", q,
        "갚으신 금액은 제가 확인해 드리기 어렵고, 남은 원금은 {{principal_remaining}}입니다. "
        "상환 내역은 상담원에게 확인해 주세요.", ext)

# 3. 만기일 + 원금 복합
for q, ext, d in (("만기일이랑 남은 원금 같이 알려주세요.", True, D_YES),
                  ("대출 만기일하고 잔액 좀 알려주세요.", False, D_NO)):
    add("manual-combo", q,
        f"고객님의 {{{{loan_label}}}} 만기일은 {d}이고, 남은 원금은 {{{{principal_remaining}}}}입니다.",
        ext, d)

# 4. 연장 여부: "네," 없이 슬롯 문장으로 끝, 불가는 상담원 안내 추가
EXT_Q = [
    "만기 연장이 가능한가요?",
    "대출 연장 신청할 수 있나요?",
    "만기가 다가오는데 연장할 수 있을까요?",
    "이 대출 연장되나요?",
    "제 대출이 연장 대상인지 궁금합니다.",
    "만기 전에 연장 신청 가능한가요?",
    "대출 기간을 늘릴 수 있나요?",
    "연장이 되는 대출인지 확인해 주세요.",
    "만기 연장 조건이 되는지 봐주세요.",
    "제 대출도 연장 신청할 수 있는 건가요?",
    "만기를 연장하는 게 되는지 알고 싶어요.",
    "지금 대출이 연장 대상에 해당하나요?",
    "연장 여부 좀 조회해 주세요.",
    "이 대출은 만기 연장이 되는 상품인가요?",
    "이 대출은 만기 후에도 기간을 늘릴 수 있나요?",
    "연장 신청이 가능한 대출인지 알려주세요.",
    "만기 연장이 허용되는 대출로 조회되나요?",
    "연장할 수 있는 상태인지 확인 부탁드립니다.",
    "이 대출로 연장 신청을 넣을 수 있을까요?",
    "연장이 허용되는 대출인지 궁금합니다.",
]
EXT_OUT = [
    "확인해 드린 결과, 고객님의 {{loan_label}}은 {{extendable_status}}",
    "고객님의 {{loan_label}}의 연장 여부는 다음과 같습니다. {{extendable_status}}",
    "조회 결과, 고객님의 {{loan_label}}은 {{extendable_status}}",
    "말씀하신 {{loan_label}}의 연장 여부를 확인해 보니, {{extendable_status}}",
]
for i, q in enumerate(EXT_Q):
    add("manual-extend-yes", q, EXT_OUT[i % 4], True, combo_date(i, True, cross_n=4))
    add("manual-extend-no", q,
        EXT_OUT[i % 4] + " 자세한 사항은 상담원에게 확인해 주세요.", False, combo_date(i, False, cross_n=4))

# 5. 연장 불가 사유: 사유는 데이터에 없으므로 상담원 안내
WHY_Q = [
    "왜 연장이 안 되나요?",
    "연장이 안 된다는데 이유가 뭐예요?",
    "제 대출은 왜 연장 대상이 아닌가요?",
    "연장 안 되는 사유 좀 알려주세요.",
    "연장이 거절된 이유가 궁금합니다.",
    "무엇 때문에 연장이 안 되는 건지 알려주세요.",
    "연장 대상이 아니라고 나오는데 왜 그런가요?",
    "안 되는 이유를 알려주시면 좋겠어요.",
    "연장이 되지 않는 원인을 알고 싶습니다.",
    "연장 대상에서 제외된 사정이 있나요?",
    "연장 불가 판정이 나온 배경이 뭔가요?",
    "연장을 못 하는 이유를 확인해 주세요.",
    "연장이 안 되는 원인이 뭔지 궁금해요.",
    "왜 연장 신청이 안 되는지 알려주세요.",
]
WHY_NO_OUT = [
    "{{extendable_status}} 구체적인 사유는 조회되지 않아, 상담원에게 확인해 주세요.",
    "{{extendable_status}} 다만 사유까지는 조회되지 않습니다. 자세한 사유는 상담원에게 확인해 주세요.",
    "조회된 내용으로는 {{extendable_status}} 사유는 제가 확인해 드리기 어려우니 상담원에게 확인해 주세요.",
    "{{extendable_status}} 연장이 안 되는 이유는 알려 드리기 어렵습니다. 상담원에게 확인해 주세요.",
]
for i, q in enumerate(WHY_Q):
    add("manual-why", q, WHY_NO_OUT[i % 4], False)

# 6. 자동 연장은 데이터에 없는 사실이라 상담원 안내
AUTO_OUT = [
    "자동 연장 여부는 제가 확인해 드리기 어렵습니다. 상담원에게 확인해 주세요.",
    "만기 시 자동으로 처리되는지는 조회되지 않습니다. 상담원에게 확인해 주세요.",
]
for i, (q, ext) in enumerate((("만기 되면 자동으로 연장되나요?", True),
                              ("만기일에 알아서 연장되는 건가요?", False))):
    add("manual-auto", q, AUTO_OUT[i], ext)

# 연장 가능 고객이 "왜 안 되나요"를 묻는 경우: 사유를 지어내지 않고 조회된 상태만 안내
WHY_YES_OUT = [
    "{{extendable_status}} 다른 안내를 받으셨다면 상담원에게 확인해 주세요.",
    "조회된 내용으로는 {{extendable_status}} 다르게 안내받으신 부분은 상담원에게 확인해 주세요.",
    "{{extendable_status}} 안내받으신 내용과 다르다면 상담원에게 확인해 주시기 바랍니다.",
]
for i, (q, d) in enumerate((("왜 연장이 안 되나요?", D_YES), ("연장이 안 된다고 들었는데 맞나요?", "2030-12-31"),
                            ("연장 안 된다는 얘기를 들었어요.", D_NO), ("제 대출은 연장이 안 되는 거죠?", "2028-09-15"))):
    add("manual-why", q, WHY_YES_OUT[i % 3], True, d)

# 일반 조회: 남은 원금과 만기일을 한 번에 안내
for q, ext, d in (("제 대출 현황 좀 알려주세요.", True, D_YES), ("대출 조회해 주세요.", False, D_NO)):
    add("manual-info", q,
        f"고객님의 {{{{loan_label}}}} 남은 원금은 {{{{principal_remaining}}}}이고, 만기일은 {d}입니다.", ext, d)

# 고객이 사유를 추측해서 묻는 경우: 맞장구치지 않고 조회된 상태만 안내
GUESS_OUT = [
    "{{extendable_status}} 말씀하신 사유가 맞는지는 제가 확인해 드리기 어렵습니다. 상담원에게 확인해 주세요.",
    "{{extendable_status}} 그 부분이 원인인지는 조회되지 않아, 상담원에게 확인해 주세요.",
    "조회된 내용으로는 {{extendable_status}} 사유가 무엇인지는 제가 알려 드리기 어렵습니다. 상담원에게 확인해 주세요.",
]
for i, q in enumerate(("연체 때문에 연장이 안 되는 거죠?", "신용점수가 낮아서 안 되는 건가요?", "담보 문제 때문인가요?",
                       "소득이 줄어서 그런 건가요?", "제가 뭘 잘못해서 안 되는 건가요?")):
    add("manual-guess", q, GUESS_OUT[i % 3], False)

# 연장 신청·처리 요청: 이 에이전트 범위 밖이라 직접 처리하지 않음. 불가 고객에게는 신청 절차를 약속하지 않는다.
for q, ext in (("지금 연장 신청해 주세요.", True), ("연장 처리 좀 해주세요.", False),
               ("만기 연장 신청 대신 해주실 수 있나요?", True), ("이 대출 연장해 주세요.", False)):
    head = ("연장 신청과 처리는 제가 직접 도와드리기 어렵습니다.", "연장 신청과 처리는 제가 직접 해 드릴 수 없습니다.")[len(rows) % 2]
    add("manual-request", q, f"{head} {{{{extendable_status}}}} 자세한 사항은 상담원에게 확인해 주세요.", ext)

# 연장 여부 + 만기일 복합
for q, ext, d in (("연장 가능한지랑 만기일 같이 알려주세요.", True, D_YES),
                  ("만기일이랑 연장 여부 알려주세요.", False, D_NO)):
    tail = "" if ext else " 자세한 사항은 상담원에게 확인해 주세요."
    add("manual-combo", q,
        f"고객님의 {{{{loan_label}}}} 만기일은 {d}입니다. {{{{extendable_status}}}}{tail}", ext, d)

# 7. 금리 / 수수료 / 서류 / 처리기간 거절
REFUSE = {
    "rate": ("금리", ["이 대출 금리가 몇 %예요?", "제 대출 이자율이 궁금해요.", "금리가 오를 수도 있나요?",
                     "지금 적용되는 금리가 얼마인가요?", "제 대출 금리 좀 알려주세요.",
                     "적용 이율이 궁금합니다.", "변동금리인가요 고정금리인가요?", "금리 감면 받을 수 있나요?"]),
    "fee": ("수수료", ["중도상환수수료가 얼마나 되나요?", "연장할 때 수수료가 드나요?", "수수료가 얼마인지 알려주세요.",
                      "대출 관련 수수료가 있나요?", "상환할 때 수수료 붙나요?"]),
    "doc": ("서류 목록", ["연장하려면 무슨 서류가 필요한가요?", "제출해야 할 서류가 뭐가 있나요?",
                        "필요 서류 목록 좀 알려주세요.", "연장 신청할 때 서류 뭐 챙겨야 하나요?"]),
    "cond": ("연장 조건", ["연장 조건이 뭔지 알려주세요.", "연장하려면 자격 요건이 있나요?", "연장 신청에 필요한 게 뭔가요?"]),
    "period": ("처리 기간", ["연장 심사에 얼마나 걸리나요?", "신청하면 처리 기간이 어느 정도예요?",
                           "연장 승인까지 며칠 걸리나요?", "심사 기간이 궁금합니다."]),
}
REF_OUT = [
    "정확한 {t} 내용은 제가 바로 안내해 드리기 어려워, 상담원에게 확인해 주시기 바랍니다.",
    "죄송하지만 {t} 관련 내용은 제가 안내드릴 수 없어, 상담원에게 문의해 주시기 바랍니다.",
    "{t} 정보는 상담원 확인이 필요한 사항입니다. 상담원에게 문의해 주세요.",
    "{t}에 대한 자세한 안내는 상담원을 통해 받아보실 수 있습니다.",
]
n = 0
for key, (topic, qs) in REFUSE.items():
    for q in qs:
        add(f"manual-{key}", q, REF_OUT[n % 4].replace("{t}", topic), n % 2 == 0)
        n += 1

out = Path(__file__).parent / "manual_seed.jsonl"
with out.open("w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"{len(rows)}건 -> {out}")
