"""대출문의 학습 데이터 준비 (docs/agent-loan/ARCHITECTURE.md 학습 데이터 절, phases/agent-loan/step3.md).

원천 데이터 필드 구조는 실제 은행 라벨링 데이터로 확인했다(2026-09-29): 파일 하나 = 상담 하나,
qa_data에는 QA가 1건. 필드 위치는 source.source_id, qa_data[0].qa_id, qa_data[0].qa_topic,
qa_data[0].input.{question,answer,follow_up_question}, qa_data[0].output. 필드 접근은
_extract_turns 한 곳에만 모은다 — 구조가 바뀌면 그 함수만 고치면 된다.

주제 필터는 consulting_topic이 아니라 qa_topic을 쓴다(QA 단위 정제·학습이라 더 정확하다고 판단했다.
2026-09-28 실측: 대출 QA 13,010건 중 두 필드 값이 다른 건 1,452건(11%)). consulting_topic으로
바꾸려면 _extract_turns의 "topic" 줄만 고치면 된다 — 팀 합의 전까지는 잠정 값이다.

익명화 기호(●●●·★★·OO 등)는 이 step에서 처리하지 않는다(계약 4 합의 대상).

2026-09-29 정제 규칙 개정: is_clean이 input(question+answer+follow_up_question)에 이미 나온 숫자·서류명은
통과시키던 것을, 금리·수수료(%)·기간(N일/영업일/개월/년)·서류명은 input에 있어도 무조건 제외하는 엄격 규칙으로
바꿨다. 실측(2026-09-29) 결과 3필드를 합쳐 비교하는 기존 방식은 상담원이 먼저 설명한 값을 "이미 안 사실"로
오인해 정제 통과분(10,154건)의 35.6%에 금리·수수료·서류명·기간 숫자가 남아 있었다 — 실제 서비스에는 그
사전 설명이 없으므로 지어낸 사실과 같은 위험이 있다. infer_extendable도 판정 근거(긍정/부정 문장)가 없을 때
무작위로 배정하던 분기를 제거했다 — 근거 없으면 무조건 제외한다(모호 배정이 target 텍스트와 모순되는 샘플을
만들던 문제). 슬롯({{extendable_status}} 등)만 쓰는 수동 샘플은 근거 문장이 없으므로 manual JSONL에 "extendable"
필드를 직접 넣으면 추론을 건너뛰고 그 값을 그대로 쓴다(iter_manual_samples 참고).
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
import zipfile
from collections.abc import Iterator
from pathlib import Path

from app.agents.loan.prompt import SYSTEM_PROMPT
from app.agents.loan.validate import DOCUMENT_KEYWORDS
from app.masking import mask

TOPIC = "대출문의(만기/연장/조회등)"   # 실제 데이터 값 — "조회"와 "등" 사이에 공백이 없다(docs의 표기와 다름)

_RAW_ZIP_NAMES = ("TL_은행.zip", "VL_은행.zip")  # train은 TL, val·test는 VL(split.json이 나눈다)

# 학습 대화에 붙이는 합성 대출 정보(고정값). 실제 mock 값과 무관하고, 형식만 prompt.build_messages와 맞춘다.
_SAMPLE_LOAN_LABEL = "신용대출"
_SAMPLE_MATURITY = "2027-03-31"
_ALT_MATURITY = "2029-11-30"  # 복제본에 쓰는 다른 날짜(사실 자체는 안 바뀐다 — 답변에 안 들어가므로)

# is_clean 상품명 휴리스틱: 접미사 앞에 2~6자가 붙은 합성어만 "상품명으로 보이는 표현"으로 본다.
# 접미사만 단독으로 나오는 "통장"·"카드" 같은 일반 단어는 걸지 않는다(정상 답변을 과도하게 걸러내지 않기 위해).
_ALLOWED_PRODUCT_NAMES = ("신용대출", "주택담보대출", "전세자금대출")
_PRODUCT_PATTERN = re.compile(r"[가-힣]{2,6}(?:대출|통장|카드|적금|예금)")

_NUM_PATTERN = re.compile(r"\d[\d,.]*")

# 엄격 규칙(2026-09-29): 아래 셋은 input에 있어도 output에 있으면 무조건 제외한다(모듈 docstring 참고).
_RATE_OR_FEE_PATTERN = re.compile(r"\d[\d,.]*\s*%")
_PERIOD_PATTERN = re.compile(r"\d[\d,.]*\s*(?:영업일|일|주|개월|년)")
# validate.py의 DOCUMENT_KEYWORDS(런타임 검증용)에 학습 정제 전용으로 "명세서"·"등기부"를 더한다.
# 런타임 검증(validate.py)까지 바꾸는 건 별도 결정 대상이라 여기서는 손대지 않는다.
_TRAIN_DOC_KEYWORDS = DOCUMENT_KEYWORDS + ("명세서", "등기부")

_NEGSIG = re.compile(r"불가|어렵|가능하지\s*(?:않|못)")
_NEGEXT = re.compile(r"연장[^.!?\n]{0,15}(?:불가|어렵|가능하지\s*(?:않|못))")
_SENTENCE_SPLIT = re.compile(r"[.!?\n]+")

NO_EXTEND_COPIES = 2  # 연장 불가 근거가 있는 "아니오" 샘플을 train에 넣는 횟수
MANUAL_COPIES = 3  # 수동 샘플을 train에 넣는 횟수(표현 다양화 후 3배로 시작 — 과적합을 보며 조정)


def _extract_turns(raw: dict) -> dict:
    """원본 JSON 한 건 → 학습에 쓰는 필드만 모은 dict. 필드 구조가 바뀌면 여기만 고친다."""
    qa = raw["qa_data"][0]
    return {
        "source_id": raw["source"]["source_id"],
        "qa_id": qa["qa_id"],
        "topic": qa["qa_topic"],
        "question": qa["input"]["question"],
        "answer": qa["input"]["answer"],
        "follow_up_question": qa["input"]["follow_up_question"],
        "output": qa["output"],
    }


def iter_conversations(raw_dir: Path, split_path: Path, split: str = "train") -> Iterator[dict]:
    """raw_dir의 TL_은행.zip·VL_은행.zip에서 split_path 기준 split 분할·TOPIC 항목만 돌려준다."""
    split_map: dict[str, str] = json.loads(Path(split_path).read_text(encoding="utf-8"))
    raw_dir = Path(raw_dir)
    seen_qa_ids: set[str] = set()

    for zip_name in _RAW_ZIP_NAMES:
        zip_path = raw_dir / zip_name
        if not zip_path.exists():
            continue
        with zipfile.ZipFile(zip_path) as z:
            for name in z.namelist():
                if not name.endswith(".json"):
                    continue
                item = _extract_turns(json.loads(z.read(name)))
                if item["qa_id"] in seen_qa_ids:
                    continue  # source_id가 TL·VL 양쪽에 있는 상담(계약 6 겹침) 중복 방지
                seen_qa_ids.add(item["qa_id"])

                if split_map.get(item["source_id"]) != split:
                    continue
                if item["topic"] != TOPIC:
                    continue
                yield item


def iter_manual_samples(manual_path: Path | None, split: str = "train") -> Iterator[dict]:
    """직접 쓴 input/output 샘플을 자동 추출 결과와 같은 형태로 돌려준다.

    파일이 없거나(None) 존재하지 않으면 아무것도 돌려주지 않는다 — 없어도 동작해야 한다.
    형식: JSONL, 한 줄에 {"question", "answer", "follow_up_question", "output"} 필수,
    "source_id"·"qa_id"·"split"은 선택(비우면 각각 "manual-<줄번호>", "manual-<줄번호>", "train").
    "extendable"(true/false)도 선택 — 있으면 infer_extendable을 건너뛰고 그 값을 그대로 쓴다.
    {{extendable_status}} 슬롯만 쓰는 답변은 "가능"/"불가" 문구가 없어 infer_extendable로 판정할 수
    없으므로, 그런 샘플은 이 필드를 반드시 넣어야 한다(2026-09-29).
    이후 정제(is_clean)·복제·마스킹은 자동 추출분과 똑같이 적용된다.
    """
    if manual_path is None:
        return
    path = Path(manual_path)
    if not path.exists():
        return

    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            if raw.get("split", "train") != split:
                continue
            item = {
                "source_id": raw.get("source_id", f"manual-{i}"),
                "qa_id": raw.get("qa_id", f"manual-{i}"),
                "question": raw["question"],
                "answer": raw["answer"],
                "follow_up_question": raw["follow_up_question"],
                "output": raw["output"],
            }
            if "extendable" in raw:
                item["extendable"] = raw["extendable"]
            if "maturity_date" in raw:
                item["maturity_date"] = raw["maturity_date"]
            yield item


def _has_unattested_number(output: str, input_text: str) -> bool:
    out_nums = set(_NUM_PATTERN.findall(output))
    in_nums = set(_NUM_PATTERN.findall(input_text))
    return bool(out_nums - in_nums)


def _has_rate_or_fee(output: str) -> bool:
    return bool(_RATE_OR_FEE_PATTERN.search(output))


def _has_period_mention(output: str) -> bool:
    return bool(_PERIOD_PATTERN.search(output))


def _has_document_keyword(output: str) -> bool:
    return any(keyword in output for keyword in _TRAIN_DOC_KEYWORDS)


def _has_unattested_product_name(output: str, input_text: str) -> bool:
    for match in _PRODUCT_PATTERN.finditer(output):
        token = match.group(0)
        if token in _ALLOWED_PRODUCT_NAMES:
            continue
        if token in input_text:
            continue
        return True
    return False


def is_clean(item: dict) -> bool:
    """output이 지어낸 숫자·서류명·상품명을 담고 있으면 False(ADR-005, 2026-09-29 엄격 규칙).

    금리·수수료(%)·기간(N일 등)·서류명은 input에 이미 나온 값이라도 무조건 제외한다(모듈 docstring 참고).
    그 밖의 숫자·상품명은 기존대로 input(question+answer+follow_up_question)에 없을 때만 제외한다.
    """
    output = item["output"]
    input_text = item["question"] + item["answer"] + item["follow_up_question"] + item.get("maturity_date", "")

    if _has_unattested_number(output, input_text):
        return False
    if _has_rate_or_fee(output):
        return False
    if _has_period_mention(output):
        return False
    if _has_document_keyword(output):
        return False
    if _has_unattested_product_name(output, input_text):
        return False
    return True


def _has_extension_positive_evidence(output: str) -> bool:
    return any(
        "가능" in sentence and not _NEGSIG.search(sentence)
        for sentence in _SENTENCE_SPLIT.split(output)
    )


def _has_extension_negative_evidence(output: str) -> bool:
    return any(_NEGEXT.search(sentence) for sentence in _SENTENCE_SPLIT.split(output))


def infer_extendable(output: str) -> bool | None:
    """답변 문장의 연장 긍정/부정 근거로 값을 정한다. 모호하거나 근거가 없으면 None(샘플 제외, 2026-09-29:
    무작위 배정 분기를 제거했다 — output 내용과 무관한 값이 last_user 정보 줄에 들어가 target과
    모순되는 샘플을 만들던 원인이었다). 근거 문장이 없는 수동 샘플(슬롯만 쓰는 답변)은 이 함수 대신
    manual JSONL의 "extendable" 필드를 직접 쓴다(iter_manual_samples, build_dataset 참고)."""
    positive = _has_extension_positive_evidence(output)
    negative = _has_extension_negative_evidence(output)

    if positive and negative:
        return None
    if positive:
        return True
    if negative:
        return False
    return None


def to_messages(item: dict, extendable: bool, maturity_date: str = _SAMPLE_MATURITY) -> list[dict]:
    """히스토리가 있으면 system → user → assistant → user(+정보) → assistant(목표), 없으면 system → user(+정보) → assistant(목표). masking.mask() 적용."""
    question = mask(item["question"]).masked_text
    answer = mask(item["answer"]).masked_text
    follow_up = mask(item["follow_up_question"]).masked_text
    target = mask(item["output"]).masked_text

    extendable_text = "예" if extendable else "아니오(사유는 알 수 없음)"
    info_lines = (
        f"대출 정보: 종류={_SAMPLE_LOAN_LABEL}, 만기일={maturity_date}, 연장 가능={extendable_text}\n"
        "사용할 수 있는 슬롯: {{loan_label}}, {{principal_remaining}}, {{extendable_status}}"
    )

    # 수동 샘플은 answer/follow_up이 비어 있다: 서비스는 첫 메시지에 바로 최종 답을 주므로 같은 구조로 학습한다.
    if not answer and not follow_up:
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{question}\n{info_lines}"},
            {"role": "assistant", "content": target},
        ]

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer},
        {"role": "user", "content": f"{follow_up}\n{info_lines}"},
        {"role": "assistant", "content": target},
    ]


def build_dataset(
    raw_dir: Path,
    split_path: Path,
    out_path: Path,
    split: str = "train",
    limit: int | None = None,
    manual_path: Path | None = None,
) -> int:
    """정제·연장 판정·복제·마스킹을 거쳐 JSONL로 쓰고 기록한 샘플 수를 돌려준다.

    limit은 자동 추출분에만 적용한다 — 수동 샘플은 뒤에 붙으므로 limit이 앞에서 자르면 전부 사라진다.
    복제: 자동 추출분은 연장 불가 근거가 있으면 NO_EXTEND_COPIES배, 수동 샘플은 train에서 MANUAL_COPIES배.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    auto_written = 0
    ambiguous_excluded = 0
    sources = (
        (False, iter_conversations(raw_dir, split_path, split)),
        (True, iter_manual_samples(manual_path, split)),
    )

    with out_path.open("w", encoding="utf-8") as f:
        for is_manual, items in sources:
            for item in items:
                if not is_manual and limit is not None and auto_written >= limit:
                    break
                if not is_clean(item):
                    continue

                if "extendable" in item:
                    extendable = item["extendable"]  # 수동 샘플이 직접 지정한 값(iter_manual_samples 참고)
                else:
                    extendable = infer_extendable(item["output"])
                if extendable is None:
                    ambiguous_excluded += 1
                    continue

                copies = 1
                if split == "train":
                    if is_manual:
                        copies = MANUAL_COPIES
                    elif extendable is False and _has_extension_negative_evidence(item["output"]):
                        copies = NO_EXTEND_COPIES

                for i in range(copies):
                    # 정답에 날짜가 들어 있는 수동 샘플은 복제본도 같은 날짜를 써야 프롬프트와 정답이 맞는다.
                    if "maturity_date" in item:
                        maturity_date = item["maturity_date"]
                    else:
                        maturity_date = _SAMPLE_MATURITY if i == 0 else _ALT_MATURITY
                    messages = to_messages(item, extendable, maturity_date)
                    f.write(json.dumps({"messages": messages}, ensure_ascii=False) + "\n")
                    written += 1
                    if not is_manual:
                        auto_written += 1
                        if limit is not None and auto_written >= limit:
                            break

    print(f"{out_path}: {written} samples ({split}), 모호해서 제외 {ambiguous_excluded}")
    return written


# ---------------------------------------------------------------------------
# v2 교체 모드 (2026-09-29, docs/agent-loan/ADR.md)
#
# AI Hub 상담사 답변은 절차·채널·서류를 지어내므로(v1 실측: 답변 30건 점검에서 안전한 것 0건) 학습 정답으로
# 쓰지 않는다. AI Hub는 질문 공급원으로만 쓰고, 질문 유형에 맞는 정답을 우리가 정한 문장으로 붙인다.
# 질문 첫 턴만 쓰는 단일 턴이라 상담사의 이전 답변(가짜 히스토리)이 학습 정답으로 새어 들어가지 않는다.
# ---------------------------------------------------------------------------
_SYMBOL_PATTERN = re.compile(r"●|★|○|\bO(?:\s?O)+\b")
_REPLACE_DOC_PATTERN = re.compile(r"서류|증빙|구비|준비물|제출|조건|자격|요건")
_REPLACE_RATE_PATTERN = re.compile(r"금리|이율|이자율")
# 다른 에이전트(이자/연체) 담당이거나 아직 교체 대상이 아닌 주제. 수수료는 v2 결과를 보고 추가한다.
_REPLACE_EXCLUDE_PATTERN = re.compile(r"수수료|위약|이자(?!율)|상환|갚|납부|연체|한도|카드|자동이체|입금|출금|앱|어플|모바일|뱅킹")
_REPLACE_MAX_QUESTION_LEN = 120

REFUSAL_TEMPLATES = (
    "정확한 {t} 내용은 제가 바로 안내해 드리기 어려워, 상담원에게 확인해 주시기 바랍니다.",
    "죄송하지만 {t} 관련 내용은 제가 안내드릴 수 없어, 상담원에게 문의해 주시기 바랍니다.",
    "{t} 정보는 상담원 확인이 필요한 사항입니다. 상담원에게 문의해 주세요.",
    "{t}에 대한 자세한 안내는 상담원을 통해 받아보실 수 있습니다.",
    "제공된 정보로는 {t_eul} 확인해 드리기 어렵습니다. 상담원에게 확인해 주세요.",
    "{t_eun} 저희가 확인할 수 있는 정보에 없어, 상담원에게 문의해 주시면 자세히 안내받으실 수 있습니다.",
)
# v4 거절 문형(2026-09-30): "~ㄹ 수 있/없"은 모델이 뒤집으면 처리 약속·사실 단정이 된다(v3 평가: "안내드릴 수 있습니다").
# v3 상수는 v3 데이터 재현을 위해 그대로 두고, --refusal-version v4 일 때만 쓴다. 순서·슬롯(t, t_eul, t_eun)은 v3와 같다.
REFUSAL_TEMPLATES_V4 = (
    "정확한 {t} 내용은 제가 바로 안내해 드리기 어려워, 상담원에게 확인해 주시기 바랍니다.",
    "죄송하지만 {t} 관련 내용은 제가 안내드리기 어렵습니다. 상담원에게 확인해 주세요.",
    "{t} 정보는 상담원 확인이 필요한 사항입니다. 상담원에게 문의해 주세요.",
    "{t}에 대한 자세한 안내는 상담원을 통해 확인해 주세요.",
    "제공된 정보로는 {t_eul} 확인해 드리기 어렵습니다. 상담원에게 확인해 주세요.",
    "{t_eun} 제가 확인하는 정보에 없어, 상담원에게 문의해 주세요.",
)
_REFUSAL_BY_VERSION = {"v3": REFUSAL_TEMPLATES, "v4": REFUSAL_TEMPLATES_V4}
# AI Hub 상담사 답변에서 가장 흔한 마무리 표현을 "문의"로 통일한 것(연락 채널을 암시하는 "연락"은 뺐다).
CLOSINGS = (
    "추가로 궁금한 사항이 있으면 언제든 문의해 주세요.",
    "궁금하신 점이 있으시면 언제든지 문의해 주시기 바랍니다.",
    "추가로 궁금하신 사항이 있으면 언제든지 문의해 주시기 바랍니다.",
    "추가로 궁금하신 점이 있으면 언제든 문의해 주세요.",
)
_CLOSING_EVERY = 3  # 교체 문장 세 개 중 하나에만 마무리 문장을 붙인다(단조로움 방지)
_REPLACE_DATES = (_SAMPLE_MATURITY, _ALT_MATURITY, "2035-06-30")
DEFAULT_REPLACE_CAPS = {"서류·조건": 125, "금리": 126}


def josa(word: str, pair: tuple[str, str]) -> str:
    """받침이 있으면 pair[0], 없으면 pair[1]을 붙인다(예: ("은", "는"), ("을", "를"))."""
    last = word[-1]
    has_final = "\uac00" <= last <= "\ud7a3" and (ord(last) - 0xAC00) % 28 != 0
    return word + pair[0 if has_final else 1]


def render_refusal(topic: str, index: int, closing: str | None = None, version: str = "v3") -> str:
    if version not in _REFUSAL_BY_VERSION:
        raise ValueError(f"알 수 없는 거절 문형 버전: {version}")
    templates = _REFUSAL_BY_VERSION[version]
    template = templates[index % len(templates)]
    text = template.format(t=topic, t_eul=josa(topic, ("을", "를")), t_eun=josa(topic, ("은", "는")))
    return f"{text} {closing}" if closing else text


def classify_replace_type(question: str) -> str | None:
    """질문이 교체 대상 유형("서류·조건" 또는 "금리") 하나에만 해당하면 그 이름을, 아니면 None을 돌려준다."""
    if len(question) > _REPLACE_MAX_QUESTION_LEN or _SYMBOL_PATTERN.search(question):
        return None
    if _REPLACE_EXCLUDE_PATTERN.search(question):
        return None
    is_doc = "연장" in question and bool(_REPLACE_DOC_PATTERN.search(question))
    is_rate = bool(_REPLACE_RATE_PATTERN.search(question))
    if is_doc == is_rate:  # 둘 다이거나 둘 다 아님
        return None
    return "서류·조건" if is_doc else "금리"


def iter_replacement_samples(
    raw_dir: Path, split_path: Path, split: str = "train", caps: dict[str, int] | None = None,
    refusal_version: str = "v3",
) -> Iterator[dict]:
    """AI Hub 질문 중 교체 대상만 뽑아 (질문, 우리가 정한 정답) 항목으로 돌려준다. 유형별 상한 안에서 결정적으로 고른다."""
    caps = DEFAULT_REPLACE_CAPS if caps is None else caps
    candidates: dict[str, list[dict]] = {t: [] for t in caps}
    for item in iter_conversations(raw_dir, split_path, split):
        kind = classify_replace_type(item["question"].strip())
        if kind in candidates:
            candidates[kind].append(item)

    for kind, items in candidates.items():
        items.sort(key=lambda it: hashlib.sha1(f"{it['source_id']}|{it['qa_id']}".encode()).hexdigest())
        for i, item in enumerate(items[: caps[kind]]):
            closing = CLOSINGS[(i // _CLOSING_EVERY) % len(CLOSINGS)] if i % _CLOSING_EVERY == 0 else None
            yield {
                "source_id": item["source_id"],
                "qa_id": item["qa_id"],
                "question": item["question"].strip(),
                "answer": "",
                "follow_up_question": "",
                "output": render_refusal(kind, i, closing, version=refusal_version),
                "extendable": i % 2 == 0,  # 정답이 연장 여부를 말하지 않으므로 값은 정보 줄에만 영향을 준다
                "maturity_date": _REPLACE_DATES[i % len(_REPLACE_DATES)],
                "kind": kind,
            }


def build_dataset_v2(
    raw_dir: Path,
    split_path: Path,
    out_path: Path,
    split: str = "train",
    manual_path: Path | None = None,
    caps: dict[str, int] | None = None,
    refusal_version: str = "v3",
) -> int:
    """수동 시드(MANUAL_COPIES배) + 교체 샘플(1배)만 쓴다. AI Hub 상담사 답변은 쓰지 않는다."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    counts = {"수동": 0}
    written = 0
    with out_path.open("w", encoding="utf-8") as f:
        # 수동 시드의 val은 질문 단위로 떼어 둔 행("split": "val")이다. 복제하지 않고 1배로 넣어 val 손실이
        # 만기·원금·연장 같은 슬롯 답변도 재게 한다(교체 샘플만으로는 거절 유형만 잰다).
        copies = MANUAL_COPIES if split == "train" else 1
        for item in iter_manual_samples(manual_path, split):
            if not is_clean(item):
                continue
            for _ in range(copies):
                messages = to_messages(item, item["extendable"], item.get("maturity_date", _SAMPLE_MATURITY))
                f.write(json.dumps({"messages": messages}, ensure_ascii=False) + "\n")
                counts["수동"] += 1
                written += 1
        for item in iter_replacement_samples(raw_dir, split_path, split, caps, refusal_version):
            messages = to_messages(item, item["extendable"], item["maturity_date"])
            f.write(json.dumps({"messages": messages}, ensure_ascii=False) + "\n")
            counts[item["kind"]] = counts.get(item["kind"], 0) + 1
            written += 1
    print(f"{out_path}: {written} samples ({split}) — " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    return written


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="대출문의 학습 데이터 준비")
    parser.add_argument("--raw", required=True, type=Path, help="TL_은행.zip·VL_은행.zip이 있는 디렉터리")
    parser.add_argument("--split", required=True, type=Path, help="split.json 경로(ADR-008)")
    parser.add_argument("--out", required=True, type=Path, help="출력 JSONL 경로")
    parser.add_argument("--which", default="train", choices=["train", "val", "test"], help="분할 이름")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--manual", type=Path, default=None, help="직접 쓴 샘플 JSONL(선택). --limit은 자동 추출분에만 적용된다")
    parser.add_argument("--refusal-version", default="v3", choices=["v3", "v4"],
                        help="replace 모드의 교체 문장 문형. v3는 v3 데이터 재현용, v4는 \"~ㄹ 수 있/없\" 없는 문형")
    parser.add_argument("--mode", default="legacy", choices=["legacy", "replace"],
                        help="replace: AI Hub 답변을 쓰지 않고 수동 시드 + 질문 유형별 교체 문장만 쓴다(v2)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.mode == "replace":
        build_dataset_v2(args.raw, args.split, args.out, split=args.which, manual_path=args.manual,
                         refusal_version=args.refusal_version)
        return
    build_dataset(
        args.raw, args.split, args.out,
        split=args.which, limit=args.limit, manual_path=args.manual,
    )


if __name__ == "__main__":
    main()
