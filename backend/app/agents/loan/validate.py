import re

# 구체적인 서류명만 막는다. "서류"라는 일반 단어는 허용한다(LN-002: 일반 안내는 허용, LN-004 c)
DOCUMENT_KEYWORDS: tuple[str, ...] = (
    "증명서",
    "등본",
    "초본",
    "재직",
    "소득",
    "신분증",
    "인감",
    "원천징수",
    "사본",
    # v1 모델이 지어낸 서류명(2026-09-29 실측)
    "명세서",
    "등기부",
    "계약서",
    "증빙",
)
# 우리 서비스에 없는 채널. 모델이 안내하면 고객이 존재하지 않는 경로를 찾게 된다.
CHANNEL_KEYWORDS: tuple[str, ...] = (
    "앱",
    "어플",
    "모바일",
    "뱅킹",
    "홈페이지",
    "웹사이트",
    "콜센터",
    "고객센터",
    "영업점",
)
# 챗봇이 지킬 수 없는 약속. 공백이 섞여도 잡도록 정규식으로 둔다.
PROMISE_PATTERNS: tuple[str, ...] = (
    r"확인\s*(?:한\s*)?후",
    r"(?:안내|알려|처리|연결|보내|조회해)\s*(?:해\s*)?(?:드리겠|보겠)",
    r"잠시만\s*기다려",
    r"문자로",
)
ALLOWED_SLOTS: tuple[str, ...] = ("loan_label", "principal_remaining", "extendable_status")

_PROMISE = re.compile("|".join(PROMISE_PATTERNS))
_NEGATIONS = ("불가", "않", "어렵", "없")
_SLOT_PATTERN = re.compile(r"\{\{\s*([^{}]*?)\s*\}\}")
# 계약 4의 마스킹 토큰. 모델이 되풀이해도 원본 값이 아니므로 숫자 검사에서 제외한다(LN-004 a)
_MASK_TOKEN = re.compile(r"\[(?:주민번호|카드번호|계좌번호|전화번호|주소|금액)_\d+\]")
_SENTENCE_SPLIT = re.compile(r"[.!?\n]+")
# 한글 답변에 섞이면 안 되는 일본어·한자(2026-09-30 v4 실측: "확인できません" 등). 한글·영문·기호는 막지 않는다.
# CJK 기호·히라가나·가타카나(3000-30FF), 한자(3400-4DBF, 4E00-9FFF, F900-FAFF), 반각 가타카나(FF66-FF9F)
_NON_KOREAN_CJK = re.compile(r"[\u3000-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff66-\uff9f]")


def _strip_allowed_numbers(text: str, maturity_date: str) -> str:
    year, month, day = (int(part) for part in maturity_date.split("-"))
    korean = rf"{year}년\s*0?{month}월\s*0?{day}일"
    text = _MASK_TOKEN.sub("", text.replace(maturity_date, ""))
    return re.sub(korean, "", text)


def is_valid_output(text: str, *, maturity_date: str, extendable: bool) -> bool:
    if not text.strip():
        return False

    # 0. 일본어·한자 혼입
    if _NON_KOREAN_CJK.search(text):
        return False

    # a. 프롬프트에 준 만기일 표기와 마스킹 토큰 외에 숫자가 있으면 금액·퍼센트·다른 날짜·기간을 지어낸 것으로 본다
    if re.search(r"\d", _strip_allowed_numbers(text, maturity_date)):
        return False

    # b. 허용 밖 슬롯, 깨진 슬롯
    slots = _SLOT_PATTERN.findall(text)
    if any(name not in ALLOWED_SLOTS for name in slots):
        return False
    if text.count("{{") != len(slots) or text.count("}}") != len(slots):
        return False

    # c. 구체적인 서류 요건
    if any(keyword in text for keyword in DOCUMENT_KEYWORDS):
        return False

    # c2. 없는 채널, 못 지키는 약속
    if any(keyword in text for keyword in CHANNEL_KEYWORDS) or _PROMISE.search(text):
        return False

    # d. 연장 불가인데 같은 문장 안에 부정 표현 없이 "가능"이라고 한 경우
    if not extendable:
        for sentence in _SENTENCE_SPLIT.split(text):
            if "가능" in sentence and not any(n in sentence for n in _NEGATIONS):
                return False

    return True
