"""모델 출력 검증. 실패하면 에이전트가 기본 문장(prompt.fallback_text)으로 대체한다."""

import re

# 날짜(2026-10-25, 10월 25일)와 연체 일수(12일)는 걸리지 않아야 한다.
_AMOUNT = re.compile(r"\d{1,3}(?:,\d{3})+|\d+\s*[만천백]?\s*원")
_RATE = re.compile(r"\d+(?:\.\d+)?\s*(?:%|퍼센트|프로)")
_MASK_TOKEN = re.compile(r"\[[가-힣]+_\d+\]")
_SLOT = re.compile(r"\{\{\s*(\w+)\s*\}\}")
# 연체 "상태"를 묻는 질문. "연체 가산금리", "연체이자가 뭐예요"처럼 규정·용어를 묻는 질문은 제외한다.
_OVERDUE_QUESTION = re.compile(r"연체(?:된|됐|되었|되어|\s*금액|\s*중)|연체.{0,6}(?:있|없)|밀린|미납")

# 조회 정보 밖의 내용을 지어낸 표현. 자동 채점이 통과시켰지만 사람이 문제로 본 v03 답에서 뽑았다.
# 거절("보내 드릴 수 없습니다")·상담원 안내("상담원이 안내해 드립니다")·현재 상태("정상적으로 납부되고 있습니다")는
# 걸리지 않아야 한다.
_FORBIDDEN_PHRASES = [
    ("결과 보장", re.compile(
        r"해소됩니다|해결됩니다|해제됩니다|정리됩니다|이행됩니다|사라집니다|문제\s*없습니다|"
        r"정상적으로\s*(?:이체|출금|처리|납부|진행|실행)됩니다|정상적으로\s*이루어집니다|자동으로\s*(?:처리|계산)됩니다|다시\s*(?:진행|시작)됩니다"
    )),
    ("규정 단정", re.compile(
        r"때문입니다|간주|위반|법적|가능하지만|설정되어\s*있습니다|"
        r"영향을\s*(?:주지|미치지|주는\s*것은\s*아니)|영향이\s*없|불이익(?:이|은)\s*없|"
        r"신용[^.]{0,10}영향을\s*(?:줄|줍|미치|미칠|미칩)|(?:적어|부족해|부족하여|때문에)\s*(?:연체|출금|이체)"
    )),
    ("지어낸 채널", re.compile(r"앱|애플리케이션|고객센터|콜센터|홈페이지|인터넷\s*뱅킹|모바일\s*뱅킹|영업점|지점|ARS|창구")),
    ("지어낸 절차", re.compile(r"입력(?:해|하시|하면|하여)|로그인|클릭|누르(?:시|면)|선택하(?:시|여|면)")),
    ("행동 약속", re.compile(
        r"(?:발송|송부|전송|보내|진행|처리|발급|적용|조정|지원|제공|검토|통보|연결|변경|등록|접수|해지|감면|면제|연락)"
        r"(?:해|하여)?\s?(?:드리겠|드립니다|드릴게)|드릴\s*예정"
    )),
    ("서류", re.compile(r"서류|증명서|사본|등본|초본|신분증")),
    ("개인정보 요구", re.compile(r"주민\s*(?:등록)?\s*번호|비밀\s*번호|생년월일|인증\s*번호|보안\s*카드|OTP")),
    ("마크다운", re.compile(r"\*\*|^\s*[-*•]\s|^\s*\d+[.)]\s|^#{1,6}\s", re.M)),
]
_SENTENCE = re.compile(r"[^.!?\n]+")


def phrase_problems(text: str) -> list[str]:
    """지어낸 사실·약속·형식 문제의 이름 목록. 비어 있으면 통과."""
    found = [name for name, pattern in _FORBIDDEN_PHRASES if pattern.search(text)]
    sentences = [s.strip() for s in _SENTENCE.findall(text) if len(s.strip()) >= 8]
    if len(sentences) != len(set(sentences)):  # 같은 문장 반복(생성 루프)
        found.append("반복")
    return found


def is_valid(text: str, allowed_slots: set[str], required_slots: set[str]) -> bool:
    if not text.strip():
        return False
    if _AMOUNT.search(text) or _RATE.search(text) or _MASK_TOKEN.search(text):
        return False
    if phrase_problems(text):
        return False
    used = set(_SLOT.findall(text))
    return used <= allowed_slots and required_slots <= used


def required_slots(question: str, overdue: bool) -> set[str]:
    """연체 고객이 연체 상태를 물으면 답에 {{overdue_amount}}가 있어야 한다."""
    return {"overdue_amount"} if overdue and _OVERDUE_QUESTION.search(question) else set()
