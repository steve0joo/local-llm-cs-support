import datetime
import hashlib
import json
import math
import random
import re
from pathlib import Path

# 수동 샘플은 서비스처럼 첫 메시지에 바로 최종 답을 주는 구조로 학습한다.
# prepare.to_messages가 answer/follow_up이 둘 다 비면 가짜 히스토리를 붙이지 않는다.
PAIRS = [("", "")]

D_YES = "2027-03-31"  # C002 신용대출, 연장 가능
D_NO = "2035-06-30"   # C003 주택담보대출, 연장 불가

# mock 날짜 2개 + 학습용 날짜 38개(v3). 모델이 날짜를 프롬프트에서 복사하지 않고 mock 두 날짜를 외우는 것을 막는다.
# 실재하는 날짜만 쓰고(datetime), 고정 seed로 뽑은 뒤 섞어서 연장 가능/불가 교대 패턴과 날짜가 짝지어지지 않게 한다.
_rng = random.Random(2026)
_extra = set()
while len(_extra) < 38:
    _d = (datetime.date(2026, 11, 1) + datetime.timedelta(days=_rng.randrange(3650))).isoformat()
    if _d not in (D_YES, D_NO):
        _extra.add(_d)
EXTRA_DATES = sorted(_extra)
_rng.shuffle(EXTRA_DATES)
DATE_POOL = [D_YES, D_NO] + EXTRA_DATES

rows = []

# ---------------------------------------------------------------------------
# 답변 문형 풀 (v3, 2026-09-29). 사실(만기·원금·연장 여부)마다 여러 서술을 직접 썼다. AI Hub 문구는 없다.
# FIRST는 대출을 처음 언급하는 문장({{loan_label}} 포함), NEXT는 앞 문장에 이어 붙는 짧은 문장이다.
# {{extendable_status}}는 화면에서 고정 문장으로 바뀌므로 그 앞뒤 문장만 바꿀 수 있다.
# 원금 슬롯은 항상 "○○원"으로 치환되므로 조사는 이/으로/입니다만 쓴다.
# ---------------------------------------------------------------------------
FIRST = {
    "date": [
        "고객님의 {{loan_label}} 만기일은 {d}입니다.",
        "{{loan_label}}의 만기 조회 결과는 {d}입니다.",
        "고객님의 {{loan_label}}은 {d}에 만기가 도래합니다.",
        "이 {{loan_label}}의 상환 만기일은 {d}입니다.",
        "말씀하신 {{loan_label}}의 만기일은 조회 결과 {d}입니다.",
        "조회된 {{loan_label}}의 만기는 {d}입니다.",
        "고객님께서 이용 중인 {{loan_label}}의 만기일은 {d}입니다.",
    ],
    "principal": [
        "고객님의 {{loan_label}} 남은 원금은 {{principal_remaining}}입니다.",
        "{{loan_label}}의 잔여 원금은 {{principal_remaining}}으로 조회됩니다.",
        "고객님의 {{loan_label}}은 현재 {{principal_remaining}}이 남아 있습니다.",
        "이 {{loan_label}}에서 아직 상환하지 않은 원금은 {{principal_remaining}}입니다.",
        "말씀하신 {{loan_label}}의 잔여 원금은 {{principal_remaining}}입니다.",
        "조회된 {{loan_label}}의 잔여 원금은 {{principal_remaining}}입니다.",
        "{{loan_label}}에서 상환하실 남은 원금은 {{principal_remaining}}입니다.",
        "고객님의 {{loan_label}} 원금 잔액은 {{principal_remaining}}입니다.",
        "{{loan_label}}은 아직 {{principal_remaining}}이 남아 있는 것으로 조회됩니다.",
        "이용 중이신 {{loan_label}}의 잔여 원금은 {{principal_remaining}}입니다.",
    ],
    "extend": [
        "고객님의 {{loan_label}}은 {{extendable_status}}",
        "{{loan_label}}의 연장 여부를 조회했습니다. {{extendable_status}}",
        "이 {{loan_label}}의 연장 관련 조회 결과입니다. {{extendable_status}}",
        "말씀하신 {{loan_label}}은 {{extendable_status}}",
        "조회 결과, 고객님의 {{loan_label}}은 {{extendable_status}}",
        "조회된 {{loan_label}}은 {{extendable_status}}",
        "이용 중이신 {{loan_label}}의 만기 연장 조회 결과입니다. {{extendable_status}}",
        "{{loan_label}}의 연장 대상 여부를 확인했습니다. {{extendable_status}}",
        "말씀하신 {{loan_label}}의 연장 관련 조회 결과입니다. {{extendable_status}}",
        "고객님께서 문의하신 {{loan_label}}은 {{extendable_status}}",
    ],
}
NEXT = {
    "date": ["만기일은 {d}입니다.", "{d}에 만기가 도래합니다.", "상환 만기일은 {d}입니다.", "만기는 {d}에 도래합니다.", "상환 기한은 {d}까지입니다."],
    "principal": [
        "남은 원금은 {{principal_remaining}}입니다.",
        "잔여 원금은 {{principal_remaining}}으로 확인됩니다.",
        "현재 {{principal_remaining}}이 남아 있습니다.",
        "아직 상환하지 않은 원금은 {{principal_remaining}}입니다.",
        "원금 잔액은 {{principal_remaining}}입니다.",
        "상환하실 남은 원금은 {{principal_remaining}}입니다.",
    ],
    "extend": [
        "{{extendable_status}}", "연장 여부를 보면, {{extendable_status}}", "연장은 다음과 같습니다. {{extendable_status}}",
        "결과는 다음과 같습니다. {{extendable_status}}", "연장 대상 여부는 다음과 같습니다. {{extendable_status}}",
        "문의하신 연장은 {{extendable_status}}",
    ],
}
OPEN_P = ["", "조회해 보니 ", "확인 결과 ", "확인해 보니 ", "말씀하신 대출 기준으로 조회했습니다. ",
          "문의해 주신 내용을 조회한 결과입니다. ", "문의하신 내용은 다음과 같습니다. "]
CLOSE_P = ["", " 더 궁금하신 점이 있으시면 말씀해 주세요.", " 추가로 궁금하신 내용은 편하게 문의해 주세요.",
           " 다른 문의사항이 있으시면 말씀해 주세요."]
TAIL_NO = " 자세한 사항은 상담원에게 확인해 주세요."  # 연장 불가일 때만 붙인다
_YES_NO = re.compile(r"(나요|가요|까요|죠|지요)\??$")
_WH = re.compile(r"언제|얼마|어떻게|무엇|뭐|왜|어디|몇|어떤|어느")


def is_yes_no(question):
    return bool(_YES_NO.search(question.strip())) and not _WH.search(question)


def _lookups(text):
    """화면에 보이는 "조회" 횟수. {{extendable_status}}는 "…조회됩니다"로 치환되므로 1로 센다."""
    return text.count("조회") + ("{{extendable_status}}" in text)


def frame(i, body, allow_close=True):
    """도입은 5건 중 1건, 맺음은 5건 중 2건에 붙인다(나머지는 본문만). 전부 붙이면 그 자체가 패턴이 된다.
    맺음은 상담원 안내가 이미 들어간 답(allow_close=False)에는 붙이지 않는다 — 안내가 두 번 나온다.
    본문이 이미 "조회"를 쓰면 "조회"가 든 도입은 고르지 않는다(답변당 한 번만)."""
    r = i % 5
    openings = [o for o in OPEN_P[1:] if _lookups(body) + o.count("조회") <= 1]
    opening = openings[(i // 5) % len(openings)] if (r == 1 and openings) else ""
    closing = CLOSE_P[1 + (i // 5) % 3] if (r in (3, 4) and allow_close) else ""
    return opening + body + closing


def single(kind, n, d=None, ext=True, question=None):
    """사실 하나만 묻는 질문의 답. FIRST·NEXT 문형을 함께 돌린다.
    "네,"는 예/아니오 질문에 긍정(연장 가능)으로 답할 때만 붙인다. 연장 불가에 "네,"를 붙이면 모순이다."""
    pool = FIRST[kind] + NEXT[kind]
    body = pool[n % len(pool)]
    if d:
        body = body.replace("{d}", d)
    if kind == "extend" and not ext:
        body += TAIL_NO
    if (kind == "extend" and ext and question and is_yes_no(question) and n % 3 == 0
            and body.startswith(("고객님의", "말씀하신"))):
        return "네, " + body
    return frame(n, body, allow_close=ext)


def fact(kinds, ext, d, i):
    """질문에서 함께 물은 항목만 순서대로 한 답에 담는다. 첫 문장만 대출을 언급한다.
    "조회"는 화면에 보이는 답변 전체에서 한 번만 쓴다(연장 슬롯이 있으면 그 슬롯이 그 한 번이다)."""
    budget = 0 if "extend" in kinds else 1
    parts = []
    for pos, kind in enumerate(kinds):
        pool = (FIRST if pos == 0 else NEXT)[kind]
        if budget <= 0:
            pool = [f for f in pool if "조회" not in f]
        form = pool[(i + pos * 2) % len(pool)]
        budget -= form.count("조회")
        parts.append(form.replace("{d}", d))
    return " ".join(parts) + ("" if ext else TAIL_NO)


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
for i, q in enumerate(MAT_Q[:6]):
    for ext, d in ((True, D_YES), (False, D_NO)):
        add("manual-maturity", q, single("date", len(rows), d), ext, d)
# mock 날짜와 반대 연장 여부 조합: 날짜만 보고 연장 여부를 맞히는 지름길을 막는다
for i, q in enumerate(MAT_Q[6:]):
    for ext, d in ((False, D_YES), (True, D_NO)):
        add("manual-maturity", q, single("date", len(rows), d), ext, d)
# 풀의 나머지 날짜로 만기 샘플 추가(v3: 5 → 12건). 프롬프트 날짜와 답 날짜는 같은 값이다.
for i, d in enumerate(DATE_POOL[2:14]):
    add("manual-maturity", MAT_Q[i % len(MAT_Q)], single("date", len(rows), d), i % 2 == 0, d)
    
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
for i, q in enumerate(PR_Q):
    ext = i % 2 == 0
    add("manual-principal", q, single("principal", len(rows)), ext, combo_date(i, ext, cross_n=6))

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
for i, q in enumerate(EXT_Q):
    add("manual-extend-yes", q, single("extend", len(rows), question=q), True, combo_date(i, True, cross_n=4))
    add("manual-extend-no", q, single("extend", len(rows), ext=False), False, combo_date(i, False, cross_n=4))

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

# 일반 조회: 원금·만기일·연장 여부를 한 번에 안내 (v2는 연장 여부가 빠져 있어 "전반" 질문에서 회피했다)
for q, ext, d in (("제 대출 현황 좀 알려주세요.", True, D_YES), ("대출 조회해 주세요.", False, D_NO)):
    tail = "" if ext else " 자세한 사항은 상담원에게 확인해 주세요."
    add("manual-info", q,
        f"고객님의 {{{{loan_label}}}} 남은 원금은 {{{{principal_remaining}}}}이고, 만기일은 {d}입니다. "
        f"{{{{extendable_status}}}}{tail}", ext, d)

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
    "{t} 관련 정보는 제가 볼 수 있는 항목에 없습니다. 상담원에게 문의해 주세요.",
    "{t}에 대해서는 제가 조회할 수 있는 내용이 없어 안내하기 어렵습니다. 상담원에게 확인해 주시기 바랍니다.",
    "{t} 문의는 조회되는 정보만으로는 답변드리기 어렵습니다. 상담원에게 문의해 주세요.",
]
n = 0
for key, (topic, qs) in REFUSE.items():
    for q in qs:
        add(f"manual-{key}", q, REF_OUT[n % len(REF_OUT)].replace("{t}", topic), n % 2 == 0)
        n += 1

# ---------------------------------------------------------------------------
# v3 확장 (2026-09-29): Golden Set v2에서 드러난 약점 보강 — 복합 질문 답 누락(R06), 수수료 주제 어긋남(F09),
# 전반 조회 회피(C28), 문형 반복(고유 답변 66개·평균 57자). 문구는 아래 풀을 조합하며 전부 직접 썼다
# (AI Hub 문구 없음). 질문은 Golden Set v2·v3와 겹치지 않는다(tests/loan/test_golden_set*.py).
# ---------------------------------------------------------------------------
# 1. 복합 질문: 물어본 항목을 하나도 빠뜨리지 않는다
COMBO_V3 = [
    (("date", "principal"), ["만기일하고 아직 남은 대출금이 얼마인지 궁금해요.", "끝나는 날짜랑 잔액을 같이 확인하고 싶어요."]),
    (("principal", "date"), ["남은 돈이 얼마고 언제까지 갚는 건지 알려 주세요.", "잔액이랑 상환 기한을 함께 알려 주실래요?"]),
    (("date", "extend"), ["만기가 언제고 연장 신청이 되는 대출인지 알고 싶습니다.", "언제 끝나는지, 연장은 가능한 상태인지 궁금합니다."]),
    (("extend", "date"), ["연장 대상인지 먼저 알려 주시고 만기도 말씀해 주세요.", "연장 가능 여부랑 만기일을 순서대로 알려주세요."]),
    (("principal", "extend"), ["잔여 원금이랑 연장 가능 여부를 한꺼번에 확인해 주세요.", "얼마 남았는지랑 연장이 되는지 궁금해요."]),
    (("extend", "principal"), ["연장 가능한지 보고, 남은 대출금도 알려 주세요.", "연장 여부와 남은 금액을 확인하고 싶어요."]),
    (("date", "principal", "extend"), ["만기일, 남은 원금, 연장 여부를 모두 알려 주세요.",
                                       "만기랑 잔액이랑 연장 가능 여부까지 한 번에 확인 부탁드려요.",
                                       "원금 만기 연장 여부 다 알려주세요.",
                                       "대출 내용 중에 만기일, 원금, 연장 가능 여부를 정리해서 알려주세요."]),
]
i = 0
for kinds, qs in COMBO_V3:
    for q in qs:
        for ext in (True, False):
            d = combo_date(i, ext, cross_n=4)
            add("manual-combo", q, frame(i, fact(kinds, ext, d, i), allow_close=ext), ext, d)
            i += 1

# 2. 전반 조회: 만기·원금·연장 여부를 모두 안내한다(순서를 돌린다)
INFO_ORDERS = [("date", "principal", "extend"), ("principal", "date", "extend"), ("extend", "date", "principal")]
INFO_V3 = [
    "제 대출 관련해서 지금 조회되는 정보를 정리해 주세요.", "대출 상태를 한눈에 볼 수 있게 알려 주세요.",
    "지금 제 대출 어떻게 되어 있는지 궁금해요.", "제 대출의 기본 정보가 궁금합니다.",
    "받아 둔 대출에 대해 확인 가능한 내용을 알려 주세요.", "대출 상세 내용 좀 볼 수 있을까요?",
    "제 대출이 지금 어떤 상태인지 알려주세요.", "가진 대출 정보 전체 요약 부탁해요.",
]
for j, q in enumerate(INFO_V3):
    for ext in (True, False):
        d = combo_date(j, ext, cross_n=2)
        add("manual-info", q, frame(len(rows), fact(INFO_ORDERS[j % 3], ext, d, len(rows)), allow_close=ext), ext, d)

# 3. 비용·수수료·위약금 질문: 질문에 나온 주제어로 답한다("금리"로 답하지 않는다). 연장 관련이면 연장 여부를 먼저 답한다.
REF_P = [
    "조회되는 정보에 {t} 관련 내용이 없어 제가 정확히 안내하기 어렵습니다. 상담원에게 문의해 주세요.",
    "{t} 관련 내용은 제가 조회할 수 있는 항목이 아니라 정확히 안내하기 어렵습니다. 상담원에게 확인해 주시기 바랍니다.",
    "죄송하지만 {t} 관련 내용은 제가 확인해 드릴 수 없습니다. 상담원에게 문의하시면 정확히 확인하실 수 있습니다.",
    "{t} 관련 정보는 제가 볼 수 있는 항목에 없습니다. 상담원에게 문의해 주세요.",
    "{t}에 대해서는 제가 조회할 수 있는 내용이 없어 안내하기 어렵습니다. 상담원에게 확인해 주시기 바랍니다.",
    "{t} 문의는 조회되는 정보만으로는 답변드리기 어렵습니다. 상담원에게 문의해 주세요.",
]
PARTIAL_P = [
    "{{extendable_status}} 다만 {t} 관련 내용은 조회되지 않아 제가 안내하기 어렵습니다. 상담원에게 확인해 주세요.",
    "고객님의 {{loan_label}}은 {{extendable_status}} 다만 {t} 관련 내용은 제가 확인해 드리기 어렵습니다. 상담원에게 문의해 주세요.",
    "{{extendable_status}} {t} 관련 내용은 조회되는 정보에 없어 제가 안내하기 어렵습니다. 상담원에게 문의해 주세요.",
    "이 {{loan_label}}은 {{extendable_status}} {t} 관련해서는 제가 확인해 드리기 어렵습니다. 상담원에게 확인해 주세요.",
]


def refuse(i, topic, related_to_extension):
    if related_to_extension:
        return PARTIAL_P[i % len(PARTIAL_P)].replace("{t}", topic)
    return REF_P[i % len(REF_P)].replace("{t}", topic)


FEE_V3 = [
    ("비용", "연장하는 데 돈이 더 들어가나요?", True), ("비용", "연장 때 추가로 내야 하는 금액이 있을까요?", True),
    ("비용", "대출 유지하는 데 들어가는 돈이 따로 있나요?", False), ("수수료", "중간에 갚을 때 떼는 수수료가 있나요?", False),
    ("수수료", "연장 신청 시 수수료는 얼마 정도인가요?", True), ("위약금", "일찍 갚으면 위약금을 물어야 하나요?", False),
    ("위약금", "만기 전에 상환하면 위약금이 생기나요?", False), ("페널티", "앞당겨 갚으면 불이익이 있을까요?", False),
    ("페널티", "부분 상환에 제약이나 페널티가 있나요?", False), ("비용", "대출 연장하면 부대비용이 더 붙나요?", True),
    ("수수료", "상환 수수료 면제되는 경우가 있나요?", False), ("추가 비용", "연장 신청 후에 청구되는 금액이 있나요?", True),
    ("위약금", "해지하면 위약금 나오나요?", False), ("비용", "연장 심사 비용을 따로 받나요?", True),
]
for k, (topic, q, about_ext) in enumerate(FEE_V3):
    ext = k % 2 == 0
    add("manual-fee", q, refuse(k, topic, about_ext), ext, combo_date(k, ext, cross_n=2))

# 4. 서류·조건·기간·금리 질문의 회피를 다양화한다(연장 관련은 조회되는 연장 여부를 먼저 답하고 나머지를 넘긴다)
REF_V3 = [
    ("doc", "서류 목록", "연장 접수하러 갈 때 챙길 게 있나요?", True),
    ("doc", "서류 목록", "연장 서류는 어떤 게 필요한지 궁금해요.", True),
    ("cond", "연장 조건", "연장 받으려면 충족해야 하는 기준이 뭔가요?", True),
    ("cond", "연장 조건", "어떤 경우에 연장이 승인되는지 알고 싶어요.", True),
    ("period", "처리 기간", "연장 결과가 나오기까지 시간이 얼마나 걸릴까요?", True),
    ("period", "처리 기간", "신청 후 승인 통보는 언제쯤 오나요?", True),
    ("period", "연장 기간", "연장 기간은 최대 얼마까지 가능한가요?", True),
    ("rate", "금리", "연장 후 금리가 달라지는지 궁금해요.", True),
    ("rate", "금리", "이 대출의 이자 비율이 어떻게 되나요?", False),
    ("rate", "금리", "금리 인하를 신청할 수 있는 조건이 있나요?", False),
    ("rate", "금리", "우대금리 적용 대상인지 알고 싶어요.", False),
    ("doc", "서류 목록", "대출 관련해서 미리 준비해 둘 서류가 있을까요?", False),
]
for k, (key, topic, q, about_ext) in enumerate(REF_V3):
    ext = k % 2 == 1
    add(f"manual-{key}", q, refuse(k, topic, about_ext), ext, combo_date(k, ext, cross_n=2))

# 5. 기본 질문(만기·원금·연장)의 말투 다양화: 새 표현의 질문에 도입·맺음을 돌려 붙인다
MAT_V3 = [
    "상환 종료일이 며칠로 되어 있나요?", "제 대출이 언제 만료되는지 확인해 주세요.", "마지막으로 갚아야 하는 날이 언제인가요?",
    "대출 기간이 언제까지인지 알고 싶어요.", "만기 도래일 조회 부탁드립니다.", "이 대출 언제 끝나는지 알려 주실 수 있나요?",
    "만기가 며칠인지 헷갈려서요, 확인해 주세요.", "대출 종료 날짜가 언제인가요?",
]
for j, q in enumerate(MAT_V3):
    ext = j % 2 == 0
    d = combo_date(j, ext, cross_n=2)
    add("manual-maturity", q, single("date", len(rows), d), ext, d)
PR_V3 = [
    "아직 상환하지 않은 금액이 얼마나 되나요?", "지금 시점 잔여 대출금을 알려 주세요.", "남은 빚이 얼마인지 궁금합니다.",
    "갚아야 할 돈이 얼마나 남았는지 확인해 주세요.", "제 대출 잔금이 얼마죠?", "원금이 아직 얼마 남았을까요?",
    "현재 상환해야 할 원금이 궁금합니다.", "대출 잔여금 확인 부탁드려요.",
]
for j, q in enumerate(PR_V3):
    ext = j % 2 == 1
    add("manual-principal", q, single("principal", len(rows)), ext, combo_date(j, ext, cross_n=2))
EXT_V3 = [
    "이 대출은 기간 연장이 되는 건가요?", "연장 신청이 받아들여지는 대출인지 알고 싶어요.", "만기 뒤에도 이어 갈 수 있는 대출인가요?",
    "연장 가능한 상품인지 확인 부탁드립니다.", "제 대출은 연장 대상에 들어가나요?", "기간 연장이 허용되는지 조회해 주세요.",
    "연장 자격이 되는지 봐 주실 수 있나요?", "만기 연장 대상 여부를 알려주세요.",
]
for j, q in enumerate(EXT_V3):
    for ext in (True, False):
        add("manual-extend-yes" if ext else "manual-extend-no", q, single("extend", len(rows), ext=ext, question=q),
            ext, combo_date(j, ext, cross_n=2))

# 6. 맥락: 이전 턴(질문→답)을 이어 묻는 후속 질문. 이전 답과 같은 말을 되풀이하지 않고 후속 질문에 답한다.
CTX_V3 = [
    # (첫 질문, 이전 답, 후속 질문, 답, 연장 가능 여부, 만기일)
    ("만기가 언제인가요?", "고객님의 {{loan_label}} 만기일은 {d}입니다.", "그럼 연장은 할 수 있는 건가요?",
     "고객님의 {{loan_label}}은 {{extendable_status}}", True, D_YES),
    ("남은 원금이 궁금해요.", "고객님의 {{loan_label}} 남은 원금은 {{principal_remaining}}입니다.", "그건 언제까지 갚아야 하죠?",
     "고객님의 {{loan_label}} 만기일은 {d}입니다.", False, D_NO),
    ("연장 가능한 대출인가요?", "고객님의 {{loan_label}}은 {{extendable_status}}", "남은 원금은 얼마예요?",
     "고객님의 {{loan_label}} 남은 원금은 {{principal_remaining}}입니다.", True, "2030-12-31"),
    ("만기일 알려주세요.", "고객님의 {{loan_label}} 만기일은 {d}입니다.", "그러면 남은 돈은요?",
     "고객님의 {{loan_label}} 남은 원금은 {{principal_remaining}}입니다.", False, D_YES),
    ("대출 잔액이 얼마인가요?", "고객님의 {{loan_label}} 남은 원금은 {{principal_remaining}}입니다.", "연장도 되는지 궁금해요.",
     "고객님의 {{loan_label}}은 {{extendable_status}} 자세한 사항은 상담원에게 확인해 주세요.", False, D_NO),
    ("연장이 되나요?", "고객님의 {{loan_label}}은 {{extendable_status}}", "만기는 언제로 되어 있어요?",
     "고객님의 {{loan_label}} 만기일은 {d}입니다.", True, "2028-09-15"),
    ("만기가 언제죠?", "고객님의 {{loan_label}} 만기일은 {d}입니다.", "연장하면 수수료가 더 드나요?",
     "{{extendable_status}} 다만 수수료 관련 내용은 조회되지 않아 제가 안내하기 어렵습니다. 상담원에게 확인해 주세요.", True, D_YES),
    ("연장이 안 되나요?", "고객님의 {{loan_label}}은 {{extendable_status}} 자세한 사항은 상담원에게 확인해 주세요.", "이유가 뭔가요?",
     "{{extendable_status}} 다만 사유까지는 조회되지 않습니다. 자세한 사유는 상담원에게 확인해 주세요.", False, D_NO),
    ("원금이 얼마 남았죠?", "고객님의 {{loan_label}} 남은 원금은 {{principal_remaining}}입니다.", "만기랑 연장 여부도 알려주세요.",
     "고객님의 {{loan_label}} 만기일은 {d}입니다. {{extendable_status}}", True, D_YES),
    ("만기일이 궁금합니다.", "고객님의 {{loan_label}} 만기일은 {d}입니다.", "원금이랑 연장 여부까지 알려주세요.",
     "고객님의 {{loan_label}} 남은 원금은 {{principal_remaining}}입니다. {{extendable_status}} 자세한 사항은 상담원에게 확인해 주세요.", False, D_NO),
    ("남은 원금 알려주세요.", "고객님의 {{loan_label}} 남은 원금은 {{principal_remaining}}입니다.", "고마워요. 위약금은 있나요?",
     "위약금 관련 내용은 제가 조회할 수 있는 항목이 아니라 정확히 안내하기 어렵습니다. 상담원에게 확인해 주시기 바랍니다.", True, D_NO),
    ("연장 여부 확인해 주세요.", "고객님의 {{loan_label}}은 {{extendable_status}}", "그럼 만기일도 같이 알려 주세요.",
     "고객님의 {{loan_label}} 만기일은 {d}입니다.", True, "2026-12-20"),
]
for k, (q1, a1, q2, out_text, ext, d) in enumerate(CTX_V3):
    rows.append({
        "source_id": f"manual-ctx-{k:02d}",
        "qa_id": f"manual-ctx-{k:02d}",
        "question": q1,
        "answer": a1.replace("{d}", d),
        "follow_up_question": q2,
        # 사실만 답하는 맥락 시드는 기존 기본 문형과 같은 문장이 되므로 도입·맺음을 돌려 붙인다(같은 답변 6회 이하 규칙)
        "output": frame(k + 1, out_text.replace("{d}", d)) if out_text.startswith("고객님의") else out_text.replace("{d}", d),
        "extendable": ext,
        "maturity_date": d,
    })


# 7. 말투 변형(v3, 2026-09-29): 반말·명사형 짧은 질문·오타. 질문이 어떻든 답은 정중체 문형을 그대로 쓴다.
CASUAL_KINDS = {
    "date": ("date",), "principal": ("principal",), "extend": ("extend",),
    "date+principal": ("date", "principal"), "extend+principal": ("extend", "principal"),
    "all3": ("date", "principal", "extend"),
}
CASUAL_V3 = [
    ("만기 언제야?", "date"), ("대출 언제 끝나?", "date"), ("만기일 알려줘", "date"), ("언제까지 갚아야 돼?", "date"),
    ("얼마 남았어?", "principal"), ("남은 원금 알려줘", "principal"), ("원금 얼마야?", "principal"), ("잔액 얼마 남았음?", "principal"),
    ("연장 돼?", "extend"), ("연장 되냐?", "extend"), ("연장할 수 있어?", "extend"), ("연장 가능해?", "extend"),
    ("만기?", "date"), ("잔액", "principal"), ("연장?", "extend"), ("원금", "principal"), ("만기일", "date"),
    ("만기일이 언제에요", "date"), ("언제까지 갚아야되요", "date"), ("연장 가능한가여", "extend"), ("대출 연장 대나요?", "extend"),
    ("마기일 알려주세요", "date"), ("잔액이 얼마나 남았나여", "principal"), ("원금 얼만지 알려조", "principal"), ("만기가 언제쥬", "date"),
    ("만기랑 잔액 알려줘", "date+principal"), ("연장되는지랑 원금 좀", "extend+principal"), ("내 대출 다 알려줘", "all3"),
]


def answer_for(kind_key, n, ext, d, question=None):
    kinds = CASUAL_KINDS[kind_key]
    if len(kinds) == 1:
        return single(kinds[0], n, d, ext=ext, question=question)
    return frame(n, fact(kinds, ext, d, n), allow_close=ext)


for j, (q, kind_key) in enumerate(CASUAL_V3):
    ext = j % 2 == 0
    d = combo_date(j, ext, cross_n=2)
    add("manual-casual", q, answer_for(kind_key, len(rows), ext, d, q), ext, d)

# 8. 마스킹 토큰이 든 질문(계약 4): 토큰을 되풀이하거나 값을 맞다/틀리다 하지 않고 조회되는 사실만 답한다.
MASK_V3 = [
    ("[계좌번호_1] 계좌에 연결된 대출 남은 원금 알려주세요.", "principal"),
    ("[카드번호_1] 카드로 받은 대출 연장 되나요?", "extend"),
    ("전화번호 [전화번호_1]로 가입했는데 만기일 확인해 주세요.", "date"),
    ("[주민번호_1] 명의 대출 잔액이 얼마인가요?", "principal"),
    ("[금액_1] 대출 받았는데 만기가 언제죠?", "date"),
    ("[금액_1]이 남아 있다는 게 사실인가요?", "principal"),
    ("[주소_1]에 사는데 대출 연장 가능한가요?", "extend"),
    ("[계좌번호_1] 계좌 대출 만기일이랑 원금 알려주세요.", "date+principal"),
    ("[전화번호_1]로 안내받은 연장 가능 여부 다시 확인해 주세요.", "extend"),
    ("[금액_1] 갚았는데 남은 원금 얼마예요?", "principal"),
    ("[카드번호_1] 연동 대출 전반 정보 알려주세요.", "all3"),
    ("[주민번호_1] 본인인데 연장 신청 되나요?", "extend"),
    ("[금액_1] 정도 남은 것 같은데 원금 확인해 주세요.", "principal"),
    ("[계좌번호_1]이랑 [전화번호_1]로 등록된 대출 만기 알려주세요.", "date"),
    ("내 [계좌번호_1] 계좌 대출 이자율이 얼마예요?", "refuse:금리"),
    ("[금액_1] 대출 수수료가 얼마예요?", "refuse:수수료"),
]
for j, (q, kind_key) in enumerate(MASK_V3):
    ext = j % 2 == 1
    d = combo_date(j, ext, cross_n=2)
    if kind_key.startswith("refuse:"):
        add("manual-mask", q, refuse(j, kind_key.split(":")[1], False), ext, d)
    else:
        add("manual-mask", q, answer_for(kind_key, len(rows), ext, d, q), ext, d)

# 9. 구체적인 서류명·숫자가 든 서류·조건·금리 질문: 맞다/틀리다 하지 않고, 질문의 서류명·숫자도 되풀이하지 않는다.
CONCRETE_V3 = [
    ("doc", "서류 목록", "재직증명서 내야 연장되나요?", True),
    ("doc", "서류 목록", "소득증빙 서류 안 내도 되나요?", True),
    ("doc", "서류 목록", "주민등록등본이랑 인감증명서 필요한가요?", False),
    ("doc", "서류 목록", "신분증만 가져가면 연장 신청 되나요?", True),
    ("doc", "서류 목록", "원천징수영수증 제출해야 하나요?", False),
    ("doc", "서류 목록", "사업자등록증 사본도 필요한가요?", False),
    ("cond", "연장 조건", "연장하려면 신용점수가 700점 넘어야 하나요?", True),
    ("cond", "연장 조건", "연체가 3개월 이상이면 연장 안 되나요?", True),
    ("cond", "연장 조건", "만기 30일 전에 신청해야 하나요?", True),
    ("cond", "연장 조건", "만기 1개월 전까지만 연장 신청 되나요?", True),
    ("rate", "금리", "금리가 3.5%라고 들었는데 맞나요?", False),
    ("rate", "금리", "연 4% 넘게 나오나요?", False),
    ("rate", "금리", "금리 0.5%p 내려 준다던데 사실인가요?", False),
    ("rate", "금리", "지금 금리 5% 아니에요?", False),
    ("rate", "금리", "연장하면 금리가 1%p 오르나요?", True),
    ("rate", "금리", "고정금리 2.9%가 맞나요?", False),
    ("rate", "금리", "금리가 연 3%대인가요?", False),
]
for k, (key, topic, q, about_ext) in enumerate(CONCRETE_V3):
    ext = k % 2 == 0
    add(f"manual-{key}", q, refuse(k + 3, topic, about_ext), ext, combo_date(k, ext, cross_n=2))

# 10. val 분리: 질문 단위로 약 12%를 떼어 둔다(유형별로 골고루, 같은 질문의 모든 변형이 함께 val로 간다).
# 같은 질문이 train과 val에 걸치면 val 손실이 외운 것을 재게 된다. prepare.py는 val 행을 복제 없이 1배로 쓴다.
_held = set()
_by_kind = {}
for r in rows:
    _by_kind.setdefault(re.sub(r"-\d+$", "", r["source_id"]), []).append(r)
for _krows in _by_kind.values():
    _questions = sorted({r["question"] for r in _krows}, key=lambda q: hashlib.sha1(q.encode()).hexdigest())
    if len(_questions) >= 5:
        _held.update(_questions[: math.ceil(len(_questions) * 0.12)])
for r in rows:
    if r["question"] in _held:
        r["split"] = "val"

out = Path(__file__).parent / "manual_seed.jsonl"
with out.open("w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"{len(rows)}건 -> {out}")
