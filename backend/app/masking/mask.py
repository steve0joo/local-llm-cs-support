"""정규식 기반 개인정보 마스킹 (docs/ADR.md ADR-006, docs/router/ARCHITECTURE.md 마스킹 규칙).

적용 순서는 주민번호 → 카드번호 → 전화번호 → 계좌번호 → 금액 → 주소다. 긴 패턴을 먼저 치환해 서로 겹치지 않게 한다.
모든 숫자 패턴은 앞뒤에 다른 숫자가 없어야 한다(`(?<!\\d)`, `(?!\\d)`). 토큰 `[종류_n]` 안의 숫자는 한 자리뿐이라
어떤 패턴에도 다시 걸리지 않으므로, 이미 마스킹된 텍스트를 다시 넣어도 바뀌지 않는다.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field


# mask 결과 타입
@dataclass
class MaskResult:
    masked_text: str                                        # 토큰으로 바뀐 문장(모델이 사용)
    mask_map: dict[str, str] = field(default_factory=dict)  # 토큰 → 원본


# 마스킹 규칙 하나
@dataclass(frozen=True)
class _Rule:
    kind: str                                          # 토큰에 들어가는 종류 이름
    pattern: re.Pattern[str]                           # 검색할 정규식
    accept: Callable[[str], bool] = lambda _: True   # 정규식 매치를 최종 인정할지 추가 판별


_DATE_PREFIX = re.compile(r"^(?:19|20)\d{2}[-\s]\d{1,2}[-\s]\d{1,2}(?:[-\s]|$)")


# 계좌번호 판별
def _is_account(value: str) -> bool:
    """총 9자리 이상만 계좌로 본다(날짜 2023-10-15는 8자리). 날짜로 시작하는 번호(2023-07-15-001)도 제외한다."""
    return sum(c.isdigit() for c in value) >= 9 and not _DATE_PREFIX.match(value)


_RULES: tuple[_Rule, ...] = (
    # 주민번호: 생년월일 6자리 + 성별 1~4 + 6자리. 하이픈 유무·양쪽 공백 허용.
    _Rule("주민번호", re.compile(r"(?<!\d)\d{6}\s?-?\s?[1-4]\d{6}(?!\d)")),
    # 카드번호: 4자리 × 4. 구분자는 -, 공백, 없음.
    _Rule("카드번호", re.compile(r"(?<!\d)\d{4}(?:[-\s]?\d{4}){3}(?!\d)")),
    # 전화번호: 01로 시작하는 휴대폰 번호만. 그 밖의 하이픈 숫자열은 계좌번호로 본다.
    _Rule("전화번호", re.compile(r"(?<!\d)01[016789][-\s]?\d{3,4}[-\s]?\d{4}(?!\d)")),
    # 계좌번호: 2~6자리로 시작하는 숫자 그룹 3~4개.
    _Rule("계좌번호", re.compile(r"(?<!\d)\d{2,6}(?:[-\s]\d{2,8}){2,3}(?!\d)"), accept=_is_account),
    # 금액: 숫자(천 단위 콤마 허용)와 한글 단위(억·만·천·백·십)의 조합 뒤에 '원'. 예) 1,234,567원 · 50만원 · 11만 5천원 · 100만 원
    _Rule("금액", re.compile(r"(?<![\d,])\d[\d,]*(?:\s*[억만천백십])*(?:\s*\d[\d,]*(?:\s*[억만천백십])*)*\s*원")),
    # 주소: 광역 지명 + 시/군/구(1~2단계) + 로/길/동/읍/면 + 선택적 번지. 데이터셋의 가림 문자 ○도 지명 글자로 허용한다.
    _Rule("주소", re.compile(
        r"(?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충청?[북남]|전라?[북남]|경상?[북남]|제주)"
        r"(?:특별자치시|특별자치도|특별시|광역시|도|시)?"
        r"(?:\s*[가-힣○]+(?:시|군|구)){1,2}"
        r"\s*[가-힣○\d]+(?:로|길|동|읍|면)"
        r"(?:\s*\d+(?:-\d+)?(?:번지)?)?"
    )),
)


def mask(text: str) -> MaskResult:
    """개인정보를 `[종류_n]` 토큰으로 바꾸고 토큰 → 원본 대응표를 함께 돌려준다. 상태가 없어 호출마다 1부터 센다."""
    mask_map: dict[str, str] = {}
    for rule in _RULES:
        text = _apply(rule, text, mask_map)
    return MaskResult(masked_text=text, mask_map=mask_map)


def _apply(rule: _Rule, text: str, mask_map: dict[str, str]) -> str:
    """규칙 하나를 text에 적용한다. 같은 원본 값은 같은 토큰을 받고, 새 값은 다음 번호를 받는다."""
    tokens: dict[str, str] = {}  # 이 종류의 원본 → 토큰

    def replace(match: re.Match[str]) -> str:
        value = match.group(0)                  # 잡힌 원본 문자열
        if not rule.accept(value):              # 계좌번호의 날짜 같은 예외
            return value
        if value not in tokens:
            tokens[value] = f"[{rule.kind}_{len(tokens) + 1}]"
            mask_map[tokens[value]] = value
        return tokens[value]

    return rule.pattern.sub(replace, text)
