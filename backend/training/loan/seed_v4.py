"""v4 시드 (2026-09-30). make_manual_seed.py --version v4 일 때만 불린다. v3 경로는 건드리지 않는다.

v3 평가(docs/agent-loan/EVAL_CRITERIA_v3.md)에서 나온 결함만 고친다. 최종 확인용 10문항(golden_set_final_v4.jsonl)은 시드 설계에
쓰지 않았다(겹침 검사에만 쓴다: tests/loan/test_manual_seed_v4.py). 문구는 전부 직접 썼고 AI Hub 문구는 없다.

1. 거절 문형 치환: "~ㄹ 수 있/없", "처리해 드"를 없앤다(뒤집히면 처리 약속·사실 단정이 된다).
2. 중복성 높은 거절 시드 정리: 같은 유형·같은 문장이 3건 이상이면 앞의 KEEP건만 남긴다.
3. 결함 유형 추가: 범위 밖(연체·기한 초과·상환액·갈아타기·상환 방식), 처리 요청, 조건+해당 여부, 손해·이득, 수수료↔금리 대조,
   원금+상환액 복합.
4. 정상 답변 추가(과다 거절 방지): 말투 변형, 마스킹 토큰, 맥락 각 20건.
"""
import re

# 정상 답변 문구 풀(v3 풀의 "확인 결과 조회된 …", "…의 만기 조회 결과는 …입니다" 같은 어색한 문형을 고친 것). 슬롯·날짜 규칙은 v3와 같다.
FIRST = {
    "date": [
        "고객님의 {{loan_label}} 만기일은 {d}입니다.",
        "{{loan_label}}의 만기일은 {d}입니다.",
        "고객님이 이용 중인 {{loan_label}}은 {d}에 만기가 도래합니다.",
        "이 {{loan_label}}의 상환 만기일은 {d}입니다.",
        "말씀하신 {{loan_label}}의 만기일은 {d}입니다.",
        "{{loan_label}}은 {d}에 만기가 됩니다.",
    ],
    "principal": [
        "고객님의 {{loan_label}} 남은 원금은 {{principal_remaining}}입니다.",
        "{{loan_label}}의 남은 원금은 {{principal_remaining}}입니다.",
        "고객님의 {{loan_label}}은 현재 {{principal_remaining}}이 남아 있습니다.",
        "이 {{loan_label}}에서 아직 갚지 않은 원금은 {{principal_remaining}}입니다.",
        "말씀하신 {{loan_label}}의 잔여 원금은 {{principal_remaining}}입니다.",
        "{{loan_label}}의 원금 잔액은 {{principal_remaining}}입니다.",
    ],
    "extend": [
        "고객님의 {{loan_label}}은 {{extendable_status}}",
        "{{loan_label}}의 연장 여부를 확인했습니다. {{extendable_status}}",
        "말씀하신 {{loan_label}}은 {{extendable_status}}",
        "이 {{loan_label}}의 연장 관련 결과는 다음과 같습니다. {{extendable_status}}",
        "고객님께서 문의하신 {{loan_label}}은 {{extendable_status}}",
        "이 {{loan_label}}의 연장 여부는 다음과 같습니다. {{extendable_status}}",
    ],
}
NEXT = {
    "date": ["만기일은 {d}입니다.", "{d}에 만기가 도래합니다.", "상환 만기일은 {d}입니다.", "만기는 {d}입니다.", "상환 기한은 {d}까지입니다."],
    "principal": [
        "남은 원금은 {{principal_remaining}}입니다.",
        "잔여 원금은 {{principal_remaining}}입니다.",
        "현재 {{principal_remaining}}이 남아 있습니다.",
        "아직 갚지 않은 원금은 {{principal_remaining}}입니다.",
        "원금 잔액은 {{principal_remaining}}입니다.",
    ],
    "extend": ["{{extendable_status}}", "연장은 다음과 같습니다. {{extendable_status}}", "연장 여부를 보면, {{extendable_status}}",
               "결과는 다음과 같습니다. {{extendable_status}}"],
}
OPEN_P = ["", "확인해 보니 ", "확인 결과 ", "문의하신 내용은 다음과 같습니다. ", "말씀하신 대출 기준으로 확인했습니다. "]
CLOSE_P = ["", " 더 궁금하신 점이 있으시면 말씀해 주세요.", " 추가로 궁금하신 내용은 편하게 문의해 주세요.",
           " 다른 문의사항이 있으시면 말씀해 주세요."]

KEEP = 2  # 같은 (유형, 문장) 거절이 3건 이상이면 남길 건수
TARGET_DROP = 30  # 정리할 중복 거절 총 건수(승인 범위 "약 30건"). 1차로 부족하면 2건짜리 중복에서 채운다

# ---------------------------------------------------------------------------
# 1. 거절 문형 치환 (순서대로 적용). 치환 결과는 v3 문형과 같은 의미의 거절이다.
# ---------------------------------------------------------------------------
REWRITES = [
    (r"연장 신청과 처리는 제가 직접 (?:도와드리기 어렵습니다|해 드릴 수 없습니다)", "연장 신청과 처리는 제가 도와드리는 범위가 아닙니다"),
    (r"제가 안내드릴 수 없어, 상담원에게 문의해 주시기 바랍니다", "제가 안내드리기 어렵습니다. 상담원에게 확인해 주세요"),
    (r"제가 확인해 드릴 수 없습니다\. 상담원에게 문의하시면 정확히 확인하실 수 있습니다", "제가 안내드리기 어렵습니다. 상담원에게 확인해 주세요"),
    (r"제가 확인해 드릴 수 없습니다", "제가 안내드리기 어렵습니다"),
    (r"상담원에게 문의하시면 정확히 확인하실 수 있습니다", "상담원에게 확인해 주세요"),
    (r"제가 볼 수 있는 항목에 없습니다", "제가 확인하는 항목에 없습니다"),
    (r"제가 조회할 수 있는 내용이 없어 안내하기 어렵습니다", "제가 확인하는 정보에 없어 안내드리기 어렵습니다"),
    (r"제가 조회할 수 있는 항목이 아니라 정확히 안내하기 어렵습니다", "제가 확인하는 항목이 아니라 정확히 안내드리기 어렵습니다"),
    (r"상담원을 통해 받아보실 수 있습니다", "상담원을 통해 확인해 주세요"),
    (r"조회된 내용으로는 ", "확인된 내용으로는 "),
]


def _rewrite(text):
    for pattern, repl in REWRITES:
        text = re.sub(pattern, repl, text)
    return text


def _norm(text):
    return re.sub(r"\{\{[^}]+\}\}", "<슬롯>", re.sub(r"\d{4}-\d{2}-\d{2}", "<날짜>", text))


def _kind(row):
    return re.sub(r"-\d+$", "", row["source_id"])


TRIM_KINDS = {"manual-why", "manual-guess", "manual-auto", "manual-rate", "manual-fee", "manual-doc", "manual-cond",
              "manual-period", "manual-request"}

# ---------------------------------------------------------------------------
# 3·4. 새 시드의 문형. "~ㄹ 수 있/없", "확인해 드", "조회되지 않아"를 쓰지 않는다.
# ---------------------------------------------------------------------------
REF = "{t} 관련 내용은 제가 안내드리기 어렵습니다. 상담원에게 확인해 주세요."
REF_ALT = [
    "이 부분은 제가 안내드리기 어렵습니다. 상담원에게 확인해 주세요.",
    REF,
    "{t} 정보는 상담원 확인이 필요한 사항입니다. 상담원에게 문의해 주세요.",
    "죄송하지만 {t} 관련 내용은 제가 안내드리기 어렵습니다. 상담원에게 확인해 주세요.",
]

RANGE = [  # (질문, 주제, 만기일을 함께 답하는가)
    ("만기일까지 못 갚으면 어떤 조치가 취해지나요?", "기한 초과", True),
    ("상환 기한을 넘기면 불이익이 있는지 알고 싶어요.", "기한 초과", False),
    ("갚는 날짜를 놓치면 어떻게 되는 거예요?", "기한 초과", False),
    ("며칠 늦게 갚아도 문제없나요?", "연체", False),
    ("납부일이 지나면 추가로 붙는 게 있나요?", "연체", False),
    ("연체료 같은 건 얼마나 붙어요?", "연체", False),
    ("기한 넘기면 페널티 있나요?", "기한 초과", False),
    ("다음 달에 통장에서 빠져나가는 금액이 얼마예요?", "상환액", False),
    ("월 납입금 좀 알려 주세요.", "상환액", False),
    ("이번 회차 상환할 금액 확인해 주세요.", "상환액", False),
    ("다른 곳으로 대출을 옮기면 더 유리한가요?", "대출 갈아타기", False),
    ("대환 대출로 바꾸는 게 나을까요?", "대출 갈아타기", False),
    ("타 은행 상품이랑 비교해 주실 수 있나요?", "타 은행 상품 비교", False),
    ("만기일에 원금을 한꺼번에 갚는 방식인가요?", "상환 방식", True),
    ("나눠서 갚는 건지 한 번에 갚는 건지 궁금합니다.", "상환 방식", False),
    ("중도에 일부 원금만 갚아도 되는 구조인가요?", "상환 방식", False),
]
REQUEST = [
    "제 대신 연장 접수 좀 해 주세요.", "연장 절차 진행해 주시면 안 될까요?", "바로 연장 처리해 주세요.", "연장 신청서 넣어 줘.",
    "이 대출 연장되게 해 주세요.", "만기 연장을 지금 확정해 주실 수 있나요?", "연장 승인 좀 부탁드립니다.",
    "그냥 연장으로 처리해 줘요.", "대출 기간 늘려서 등록해 주세요.", "지금 연장 요청 넣어 주세요.",
]
REQUEST_OUT = [
    "연장 신청과 처리는 제가 도와드리는 범위가 아닙니다. 상담원에게 확인해 주세요.",
    "연장 신청과 처리는 제가 도와드리는 범위가 아닙니다. {{extendable_status}} 상담원에게 확인해 주세요.",
    "고객님의 {{loan_label}}은 {{extendable_status}} 다만 연장 신청과 처리는 제가 도와드리는 범위가 아닙니다. 상담원에게 확인해 주세요.",
]
COND = [
    "연장 조건이 뭐고, 제 대출은 거기 해당돼요?", "연장 요건 알려 주시고 저한테 적용되는지도 봐 주세요.",
    "어떤 조건이 필요한지, 제가 되는 건지 궁금합니다.", "연장 가능한 조건이 따로 있나요? 저는 어떤가요?",
    "연장 자격이 뭔지, 저는 해당하는지 알고 싶어요.", "조건 충족해야 연장된다던데 저는 충족한 건가요?",
    "연장 기준과 제 상태를 같이 확인하고 싶어요.", "요건이 뭔지 말고 제가 연장 대상인지만이라도 알려 주세요.",
]
COND_OUT = [
    "연장 조건은 제가 안내드리기 어렵습니다. {{extendable_status}} 자세한 사항은 상담원에게 확인해 주세요.",
    "고객님의 {{loan_label}}은 {{extendable_status}} 다만 연장 조건은 제가 안내드리기 어렵습니다. 상담원에게 확인해 주세요.",
    "{{extendable_status}} 연장 조건은 제가 안내드리기 어렵습니다. 상담원에게 확인해 주세요.",
]
LOSS = [
    "일찍 다 갚으면 저한테 손해인가요?", "미리 갚는 게 유리한지 알려 주세요.", "빨리 상환하면 이득이 있나요?",
    "만기까지 그냥 두는 게 나은가요, 갚는 게 나은가요?", "지금 일부 갚으면 제 입장에서 불리한가요?",
    "연장하는 게 더 이득일까요?", "갚지 않고 유지하는 편이 낫나요?", "중간에 갚으면 손실 보는 건 없어요?",
]
LOSS_OUT = [
    "이 부분은 제가 안내드리기 어렵습니다. 상담원에게 확인해 주세요.",
    "유불리에 대한 판단은 제가 안내드리기 어렵습니다. 상담원에게 확인해 주세요.",
    "죄송하지만 어느 쪽이 유리한지는 제가 안내드리기 어렵습니다. 상담원에게 확인해 주세요.",
]
FEE_RATE = [  # (질문, 주제) — 같은 문형의 수수료/금리 질문을 짝지어 넣어 주제 혼동을 막는다
    ("수수료가 있는지 궁금해요.", "수수료"), ("금리가 얼마인지 궁금해요.", "금리"),
    ("취급 수수료 붙나요?", "수수료"), ("적용 금리가 궁금해요.", "금리"),
    ("연장할 때 나가는 수수료가 얼마인지 궁금해요.", "수수료"), ("연장 때 금리 얼마 적용돼요?", "금리"),
    ("상환 수수료 면제 조건이 있나요?", "수수료"), ("우대 금리 조건이 있나요?", "금리"),
    ("수수료가 많이 나오는 편인가요?", "수수료"), ("금리가 높은 편인가요?", "금리"),
]
PAY_COMBO = [
    ("남은 원금이랑 이번 달 납부액 알려 주세요.", "납부액"), ("잔액이 얼마고 매달 얼마씩 빠지는지도 알려 주세요.", "월 상환액"),
    ("원금은 얼마 남았고 월 상환금은 얼마인가요?", "월 상환금"), ("남은 원금하고 다음 회차 상환금 좀 확인해 주세요.", "다음 회차 상환금"),
]
TONE = [  # (질문, 유형)
    ("만기일이 정확히 언제로 잡혀 있나요?", "date"), ("대출이 끝나는 날짜가 궁금해서요.", "date"), ("만기 날짜 좀 알려 주시겠어요?", "date"),
    ("언제 만기인지 한 번만 확인해 주세요.", "date"), ("상환 종료일이 언제인지 알려줘", "date"), ("만기가 언제임?", "date"), ("대출 마감 날짜가 궁금합니다", "date"),
    ("아직 갚지 않은 원금이 얼마 남았는지 궁금합니다.", "principal"), ("잔여 대출금이 얼마인지 알려 주세요.", "principal"), ("원금 잔액 좀 확인해 줄래요?", "principal"),
    ("얼마 더 갚아야 해요?", "principal"), ("남은 대출 금액 알려줘", "principal"), ("지금 원금이 얼마 남았을까요?", "principal"), ("잔액 알려주세요", "principal"),
    ("저 연장 신청 가능한 상태인가요?", "extend"), ("만기 연장이 가능한 대출인지 확인 부탁드려요.", "extend"), ("연장 되는 대출이야?", "extend"),
    ("이 대출 연장할 수 있는 건지 알려 주세요.", "extend"), ("연장 가능 여부만 확인해 주세요.", "extend"), ("연장 대상에 들어가는지 궁금해요.", "extend"),
]
MASK = [  # (질문, 답에 담을 항목)
    ("[계좌번호_1]로 실행된 대출은 언제까지 갚아야 해요?", ("date",)),
    ("[카드번호_1] 카드 연동 대출 남은 원금이 얼마죠?", ("principal",)),
    ("[전화번호_1] 명의 대출은 연장이 되는 상태인가요?", ("extend",)),
    ("[주민번호_1] 제 명의로 된 대출 만기일 확인 부탁드려요.", ("date",)),
    ("[금액_1] 정도 빌렸는데 지금 원금이 얼마나 남았어요?", ("principal",)),
    ("[주소_1] 거주 기준으로 받은 대출 연장 가능한지 알려주세요.", ("extend",)),
    ("[계좌번호_1] 대출의 만기일과 잔여 원금을 한 번에 알고 싶어.", ("date", "principal")),
    ("[계좌번호_1]이랑 연결된 대출 전체 현황 좀 볼 수 있을까요?", ("date", "principal", "extend")),
    ("[전화번호_1]로 인증했는데 만기일이 언제인가요?", ("date",)),
    ("[카드번호_1]로 신청한 대출 연장 여부를 알고 싶어요.", ("extend",)),
    ("[금액_1] 대출 남은 기간이 언제까지인가요?", ("date",)),
    ("[주민번호_1] 본인 대출 잔여 원금 확인해 주세요.", ("principal",)),
    ("[계좌번호_1] 계좌 대출, 만기일이랑 연장 여부 확인하고 싶어요.", ("extend", "date")),
    ("[주소_1] 집 담보 대출 만기일 알려주세요.", ("date",)),
    ("[전화번호_1] 이 번호 대출 원금이랑 연장 여부 알려줘.", ("principal", "extend")),
    ("[금액_1] 대출 잔액 좀 알려줘요.", ("principal",)),
    ("[카드번호_1] 연결 대출 만기가 지났는지 확인해 주세요.", ("date",)),
    ("[계좌번호_2] 계좌에 걸린 대출 연장 신청 가능한가요?", ("extend",)),
    ("[전화번호_1]로 문의드려요, 대출 만기랑 연장 여부 모두 알려 주세요.", ("date", "extend")),
    ("[주민번호_1] 명의 대출 전반 정보 알려주세요.", ("date", "principal", "extend")),
]
Q1 = {"date": ["만기가 대략 언제쯤이에요?", "제 대출 끝나는 시점이 궁금합니다.", "만기일 좀 봐 주세요."],
      "principal": ["갚을 원금이 아직 얼마 있어요?", "잔액이 궁금합니다.", "남아 있는 원금 좀 알려 주세요."],
      "extend": ["이 대출 연장 가능해요?", "연장 쪽으로 확인 부탁드립니다.", "연장 요청 가능한 대출인가요?"]}
Q2 = {"date": ["그럼 종료 시점은 언제예요?", "만기는 언제로 되어 있나요?", "끝나는 날짜도 알려 주세요."],
      "principal": ["남은 원금은요?", "그럼 잔액은 얼마예요?", "갚아야 할 원금도 알려 주세요."],
      "extend": ["연장도 되나요?", "그럼 연장은 가능한가요?", "연장 여부도 알려 주세요."]}


# 고객이 말한 만기일이 실제와 다를 때: "아니요,"로 부정하고 실제 만기일로 정정한다(틀린 날짜를 맞다고 확인하지 않는다).
# 틀린 날짜는 답에 되풀이하지 않는다. 맞는 날짜를 확인해 주는 시드("네, …이 맞습니다")는 v3에서 유지된다.
WRONG_DATE = [
    "제 대출 만기가 2029-12-31 맞나요?", "만기일이 2033-01-15로 되어 있는 거 맞죠?", "대출이 2028-06-30에 끝나는 게 맞나요?",
    "문자로 만기가 2031-09-01이라고 왔는데 맞아요?", "만기 2026-12-31 맞음?", "제 만기일이 2030-05-20이 맞는지 확인해 주세요.",
]
WRONG_OUT = [
    "아니요, 고객님의 {{loan_label}} 만기일은 {d}입니다.",
    "아니요, {{loan_label}}의 만기일은 {d}입니다.",
    "아니요, 확인해 보니 만기일은 {d}입니다.",
    "아니요, 이 {{loan_label}}의 상환 만기일은 {d}입니다.",
]

# 고객이 말한 만기일이 실제와 같을 때: "네, 맞습니다."로 확인한다(질문의 {d}는 그 행의 실제 만기일). "조회해 보니" 표현은 쓰지 않는다.
RIGHT_DATE = ["제 대출 만기가 {d} 맞나요?", "만기일이 {d}로 되어 있는 거 맞죠?", "만기 {d} 맞음?", "제 만기일이 {d}이 맞는지 확인해 주세요."]
RIGHT_OUT = [
    "네, 맞습니다. 고객님의 {{loan_label}} 만기일은 {d}입니다.",
    "네, 맞습니다. {{loan_label}}의 만기일은 {d}입니다.",
    "네, 맞습니다. 만기일은 {d}입니다.",
    "네, 맞습니다. 이 {{loan_label}}의 상환 만기일은 {d}입니다.",
]


def apply(g):
    rows, add = g["rows"], g["add"]
    single, fact, frame, combo_date = g["single"], g["fact"], g["frame"], g["combo_date"]
    first, tail_no = g["FIRST"], g["TAIL_NO"]

    # 1) 거절 문형 치환(질문·답 모두).
    for r in rows:
        for field in ("output", "answer"):
            r[field] = _rewrite(r[field])

    # 2) 중복성 높은 거절 정리: 같은 (유형, 문장) 거절이 3건 이상이면 앞의 KEEP건만 남기고, 그래도 TARGET_DROP에 못 미치면
    #    2건짜리 중복의 뒤쪽 행을 (큰 유형부터) 더 뺀다. 순서는 원래 행 순서라 결정적이다.
    def dup_key(r):
        return (_kind(r), _norm(r["output"]))

    def is_trim_candidate(r):
        return _kind(r) in TRIM_KINDS and "상담원" in r["output"]

    groups = {}
    for r in rows:
        if is_trim_candidate(r):
            groups.setdefault(dup_key(r), []).append(r)
    drop = set()
    for members in groups.values():
        if len(members) >= 3:
            drop.update(id(m) for m in members[KEEP:])
    pairs_left = sorted((m for m in groups.values() if len(m) == 2), key=lambda m: (-sum(1 for x in rows if _kind(x) == _kind(m[0])), rows.index(m[0])))
    for members in pairs_left:
        if len(drop) >= TARGET_DROP:
            break
        drop.add(id(members[1]))
    rows[:] = [r for r in rows if id(r) not in drop]

    def ans(kinds, n, ext, d, q=None):
        """정상 답변. 연장 불가면 v3와 같이 끝에 상담원 확인 꼬리(TAIL_NO)가 붙는다(single/fact가 붙인다)."""
        if len(kinds) == 1:
            return single(kinds[0], n, d, ext=ext, question=q)
        return frame(n, fact(kinds, ext, d, n), allow_close=ext)

    def date_of(j, ext):
        return combo_date(j, ext, cross_n=2)

    # 3) 결함 유형
    for j, (q, topic, with_date) in enumerate(RANGE):
        ext, d = j % 2 == 0, date_of(j, j % 2 == 0)
        body = REF_ALT[(0, 1, 3)[j % 3]].replace("{t}", topic)  # 모두 "안내드리기 어렵습니다" 문형
        if with_date:
            body = first["date"][j % len(first["date"])].replace("{d}", d) + " " + REF.replace("{t}", "그 이후의 처리")
        add("manual-v4range", q, body, ext, d)
    for j, q in enumerate(REQUEST):
        ext = j % 2 == 0
        add("manual-v4request", q, REQUEST_OUT[j % 3], ext, date_of(j, ext))
    for j, q in enumerate(COND):
        ext = j % 2 == 1
        add("manual-v4cond", q, COND_OUT[j % 3], ext, date_of(j, ext))
    for j, q in enumerate(LOSS):
        ext = j % 2 == 0
        add("manual-v4loss", q, LOSS_OUT[j % 3], ext, date_of(j, ext))
    for j, (q, topic) in enumerate(FEE_RATE):
        ext = j % 2 == 1
        add("manual-v4feerate", q, REF_ALT[1 + (j // 2) % 3].replace("{t}", topic), ext, date_of(j, ext))
    for j, (q, topic) in enumerate(PAY_COMBO):
        ext = j % 2 == 0
        base = first["principal"][j % len(first["principal"])]
        add("manual-v4combo", q, f"{base} {topic}은 제가 안내드리기 어렵습니다. 상담원에게 확인해 주세요.", ext, date_of(j, ext))

    # 4) 정상 답변(과다 거절 방지)
    for j, (q, kind) in enumerate(TONE):
        ext = j % 2 == 0
        d = date_of(j, ext)
        add("manual-v4tone", q, ans((kind,), len(rows), ext, d, q), ext, d)
    for j, (q, kinds) in enumerate(MASK):
        ext = j % 2 == 1
        d = date_of(j, ext)
        add("manual-v4mask", q, ans(kinds, len(rows), ext, d, q), ext, d)
    pairs = [(a, b) for a in ("date", "principal", "extend") for b in ("date", "principal", "extend") if a != b]
    ctx = []
    for v in range(3):
        for a, b in pairs:
            ctx.append((Q1[a][v], a, Q2[b][(v + 1) % 3], (b,)))
    ctx.append((Q1["date"][1], "date", "나머지 정보도 전부 알려 주세요.", ("principal", "extend")))
    ctx.append((Q1["principal"][2], "principal", "나머지도 다 알려 주세요.", ("date", "extend")))
    for k, (q1, a, q2, target) in enumerate(ctx):
        ext = k % 2 == 0
        d = date_of(k, ext)
        rows.append({
            "source_id": f"manual-v4ctx-{k:02d}", "qa_id": f"manual-v4ctx-{k:02d}", "question": q1,
            "answer": single(a, len(rows), d, ext=ext), "follow_up_question": q2,
            "output": ans(target, len(rows), ext, d, q2), "extendable": ext, "maturity_date": d,
        })

    for j, q in enumerate(WRONG_DATE):
        ext = j % 2 == 1
        d = date_of(j, ext)
        add("manual-v4wrong", q, WRONG_OUT[j % 4].replace("{d}", d), ext, d)
    for j, q in enumerate(RIGHT_DATE):
        ext = j % 2 == 0
        d = date_of(j + 1, ext)
        add("manual-v4right", q.replace("{d}", d), RIGHT_OUT[j % 4].replace("{d}", d), ext, d)
