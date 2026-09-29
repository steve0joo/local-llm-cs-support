"""잔액조회 학습 데이터 생성 (docs/agent-balance/ARCHITECTURE.md "`prepare.py` 인터페이스", BAL-008).

AI Hub 잔액조회 QA의 정답은 재작성 캐시(rewrite.py가 쓴 REWRITE_PATH)의 다시 쓴 답만 쓴다(BAL-010). 캐시에 없는 QA는 뺀다.
QA 하나에서 첫 턴·이어진 턴 샘플을 추론과 같은 입력(prompt.build_messages)으로 만들고,
목표 답마다 안전망 필터(출력 검증·상품명·콜센터식 정답·조회 결과 단정·비식별 표시·길이)에 걸리면 그 샘플을 뺀다.
잔액·거래내역 슬롯 응답은 원천에 없으므로 템플릿 합성 샘플을 더한다. 무작위와 네트워크를 쓰지 않는다.

실행: cd backend && .venv/bin/python -m training.balance.prepare
출력: data/processed/balance/{train,valid,test}.jsonl — gitignore, 커밋 금지
"""

import argparse
import hashlib
import itertools
import json
import re
import zipfile
from collections.abc import Iterator
from pathlib import Path

from app.agents.balance.mock_api import get_accounts
from app.agents.balance.prompt import build_messages
from app.agents.balance.resolve import ASK_TEXT, account_label
from app.agents.balance.validate import is_valid
from app.masking import mask   # 게이트웨이와 같은 마스킹(계약 4). import에 실패하면 여기서 멈춘다(BAL-006)
from training.common.split import OUT_PATH as SPLIT_PATH, TL_ZIP, VL_ZIP

TOPIC = "거래내역/잔액조회"
OUT_DIR = SPLIT_PATH.parent / "balance"         # backend/data/processed/balance
SPLIT_FILES = {"train": "train.jsonl", "val": "valid.jsonl", "test": "test.jsonl"}   # MLX LM은 valid.jsonl 이름을 쓴다
REWRITE_PATH = OUT_DIR / "rewrites.jsonl"       # LLM 재작성 캐시(BAL-010, rewrite.py가 쓴다) — gitignore
MAX_CHARS = 200                                 # 다시 쓴 답·합성 응답 길이 상한(공백 포함)
_FIELDS = ("question", "answer", "follow_up", "output")

# 정답에 있어도 되는 일반 명칭 상품(ADR-005). 그 밖의 상품명은 입력에 있을 때만 허용한다
GENERIC_PRODUCT_NAMES = frozenset({
    "입출금통장", "정기예금", "정기적금", "신용카드", "체크카드", "신용대출", "주택담보대출", "전세자금대출",
})

# 비식별 금액 "●●●원" (RT-005). mask()의 금액 규칙에서 숫자 자리를 ●로 바꾼 모양이다
_HIDDEN_AMOUNT = re.compile(r"●[●,]*(?:\s*[억만천백십])*(?:\s*●[●,]*(?:\s*[억만천백십])*)*\s*원")
_PRODUCT = re.compile(r"[가-힣A-Za-z]+(?:통장|적금|예금|카드|대출)")
# 콜센터식 정답(BAL-009): 개인정보 항목 뒤 같은 문장 25자 안의 요구, 챗봇이 할 수 없는 행동의 약속
_ASKS_PERSONAL_INFO = re.compile(
    r"(?:성함|생년월일|계좌 ?번호|비밀번호|주민(?:등록)?번호|카드 ?번호)[^.?!\n]{0,25}(?:알려|말씀해|입력해|눌러|제공해)"
)
# "드릴 수 없"은 할 수 없다는 안내라 남긴다
_PROMISES_ACTION = re.compile(
    r"(?:보내|전송해|발급해|조치해|정정해|처리해|발송해|전달해|제공해|진행해|정리해|접수해|신청해|조회해)"
    r" ?(?:드리겠|드리니|드립니다|드릴 수(?! ?없))"
    r"|(?:즉시|바로) ?(?:진행하겠|처리하겠)"
)
# 조회 결과 단정(BAL-010): "결과는·결과를"은 조회 방법 안내라 남긴다
_CLAIMS_LOOKUP = re.compile(
    r"(?:조회|확인)(?:한|해 본|해 보니|해 드린)? ?결과(?![는를])|확인한 바에 따르면|확인되었습니다"
)
_DEID_MARK = re.compile(r"[★●○]|OO")   # AI Hub 비식별 표시(BAL-010)

# 합성 질문: classify_intent가 자기 의도로 판단해야 한다(test_prepare.py)
BALANCE_QUESTIONS = (
    "잔액 알려줘",
    "제 계좌 잔액이 얼마예요?",
    "통장에 돈 얼마 남았어요?",
    "잔고 확인해 주세요",
    "지금 잔액 좀 알려주세요",
    "계좌 잔액 조회해 주세요",
    "남은 돈이 얼마인지 알려주세요",
    "잔액 좀 보여주세요",
    "현재 잔고가 궁금해요",
    "생활비 계좌 잔액 알려줘",
    "입출금 계좌 잔액 얼마예요?",
    "제 통장 잔고 좀 알려주세요",
    "잔액 확인 부탁드립니다",
    "계좌에 남은 금액 알려주세요",
    "오늘 기준 잔액 알려주세요",
    "잔액 조회 부탁해요",
    "지금 통장에 얼마 있어요?",
    "생활비 통장 잔고 보여줘",
    "잔액이 얼마나 되나요?",
    "입출금 통장에 남은 돈 확인해 주세요",
)
TRANSACTION_QUESTIONS = (
    "최근 거래내역 보여줘",
    "거래내역 알려주세요",
    "최근 입금 내역 확인해 주세요",
    "출금 내역 보여주세요",
    "요즘 거래내역 좀 볼 수 있을까요?",
    "최근 입출금 내역 알려줘",
    "통장 거래내역 조회해 주세요",
    "최근에 돈 들어온 내역 보여주세요",
    "최근에 출금된 거 알려주세요",
    "생활비 계좌 거래내역 보여줘",
    "입금된 내역 확인하고 싶어요",
    "최근 거래 내역 좀 알려주세요",
    "계좌 거래내역 확인 부탁드립니다",
    "최근에 빠져나간 돈 내역 보여주세요",
    "입금 들어왔는지 확인해 주세요",
    "최근 사용 내역 알려줘",
    "통장 입출금 내역 좀 볼게요",
    "출금 기록 좀 보여줘",
    "입출금 계좌 거래내역 알려주세요",
    "급여 입금됐는지 내역 보여주세요",
)
# 합성 응답: 그 의도의 is_valid를 통과해야 한다. 슬롯과 안내 문구만 쓰고 사실은 넣지 않는다(BAL-008)
BALANCE_ANSWERS = (
    "{{account_label}} 계좌의 현재 잔액은 {{balance}}입니다.",
    "조회하신 {{account_label}} 계좌의 잔액은 {{balance}}입니다. 더 궁금하신 점이 있으시면 말씀해 주세요.",
    "고객님의 {{account_label}} 계좌 잔액은 {{balance}}으로 확인됩니다.",
    "{{account_label}} 계좌에 현재 {{balance}}이 남아 있습니다.",
    "확인해 보니 {{account_label}} 계좌의 잔액은 {{balance}}입니다. 다른 도움이 필요하시면 말씀해 주세요.",
    "요청하신 {{account_label}} 계좌의 현재 잔액을 안내해 드립니다. 잔액은 {{balance}}입니다.",
)
TRANSACTION_ANSWERS = (
    "{{account_label}} 계좌의 최근 거래내역입니다.\n{{recent_transactions}}",
    "요청하신 {{account_label}} 계좌의 최근 거래내역을 안내해 드립니다.\n{{recent_transactions}}",
    "{{account_label}} 계좌의 최근 거래내역은 다음과 같습니다.\n{{recent_transactions}}\n더 궁금하신 점이 있으시면 말씀해 주세요.",
    "조회하신 {{account_label}} 계좌의 최근 입출금 내역입니다.\n{{recent_transactions}}",
    "고객님의 {{account_label}} 계좌에서 확인된 최근 거래내역입니다.\n{{recent_transactions}}\n다른 도움이 필요하시면 말씀해 주세요.",
    "{{account_label}} 계좌의 최근 거래내역을 보여 드립니다.\n{{recent_transactions}}",
)


def load_qas(zip_path: Path) -> Iterator[dict]:
    """원본 필드 접근은 여기에만 둔다. 상담 주제와 QA 주제가 모두 TOPIC인 QA만 (RT-005 라벨 규칙)."""
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if not name.endswith(".json"):
                continue
            doc = json.loads(z.read(name))
            if doc["consulting"]["consulting_topic"] != TOPIC:
                continue
            for qa in doc["qa_data"]:
                if qa["qa_topic"] != TOPIC:
                    continue
                yield {
                    "source_id": doc["source"]["source_id"],
                    "question": qa["input"]["question"],
                    "answer": qa["input"]["answer"],
                    "follow_up": qa["input"]["follow_up_question"],
                    "output": qa["output"],
                }


def normalize_amounts(text: str) -> str:
    counter = itertools.count(1)
    return _HIDDEN_AMOUNT.sub(lambda _: f"[금액_{next(counter)}]", text)


def mask_fields(qa: dict) -> dict:
    return {key: mask(normalize_amounts(qa[key])).masked_text for key in _FIELDS}


def qa_key(qa: dict) -> str:
    """재작성 캐시 키. 필드 경계가 섞이지 않게 구분자(\\x1f)로 잇는다."""
    text = "\x1f".join(qa[key] for key in ("source_id", *_FIELDS))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def load_rewrites(path: Path) -> dict[str, dict]:
    """같은 키가 여러 줄이면 마지막 줄을 쓴다."""
    if not path.exists():
        return {}
    rewrites = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            rewrites[row["key"]] = {"answer": row["answer"], "output": row["output"]}
    return rewrites


def _unknown_product(output: str, inputs: tuple[str, ...]) -> bool:
    """정답에 입력에 없는 상품명이 있으면 지어낸 것으로 본다(ADR-005)."""
    return any(
        name not in GENERIC_PRODUCT_NAMES and not any(name in text for text in inputs)
        for name in _PRODUCT.findall(output)
    )


def _rejected(target: str, inputs: tuple[str, ...]) -> bool:
    """안전망 필터 1~6. 목표 답만 본다. 학습은 --mask-prompt라 입력·history 문장은 loss에 들지 않는다(BAL-009)."""
    return (not is_valid(target, (), ()) or _unknown_product(target, inputs)
            or bool(_ASKS_PERSONAL_INFO.search(target) or _PROMISES_ACTION.search(target))
            or bool(_CLAIMS_LOOKUP.search(target) or _DEID_MARK.search(target))
            or len(target) > MAX_CHARS)


def _sample(messages: list[dict], target: str) -> dict:
    return {"messages": messages + [{"role": "assistant", "content": target}]}


def build_samples(qa: dict, rewrite: dict | None) -> list[dict]:
    """첫 턴 [question] → answer, 이어진 턴 [question, answer, follow_up] → output. 답은 모두 다시 쓴 답이다(BAL-010).

    재작성이 없으면 원문 answer·output으로 대신하지 않고 []를 돌려준다.
    """
    if rewrite is None:
        return []
    fields = mask_fields(qa)
    question, follow_up = fields["question"], fields["follow_up"]
    answer, output = (mask(rewrite[key]).masked_text for key in ("answer", "output"))
    samples = []
    if not _rejected(answer, (question,)):
        samples.append(_sample(build_messages([], question, "general"), answer))
    if not _rejected(output, (question, answer, follow_up)):
        history = [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]
        samples.append(_sample(build_messages(history, follow_up, "general"), output))
    return samples


def synth_samples() -> dict[str, list[dict]]:
    """질문 × 응답 전체 조합. 짝수 질문은 첫 턴 모양, 홀수 질문은 되묻기 뒤 라벨 클릭 턴 모양."""
    labels = itertools.cycle(
        [account_label(a) for customer_id in ("C001", "C002", "C003") for a in get_accounts(customer_id)]
    )
    samples: dict[str, list[dict]] = {split: [] for split in SPLIT_FILES}
    for intent, questions, answers in (
        ("balance", BALANCE_QUESTIONS, BALANCE_ANSWERS),
        ("transactions", TRANSACTION_QUESTIONS, TRANSACTION_ANSWERS),
    ):
        for i, question in enumerate(questions):
            split = "test" if i % 10 == 0 else "val" if i % 10 == 1 else "train"
            for answer in answers:
                if i % 2 == 0:
                    messages = build_messages([], question, intent)
                else:
                    history = [{"role": "user", "content": question}, {"role": "assistant", "content": ASK_TEXT}]
                    messages = build_messages(history, next(labels), intent)
                samples[split].append(_sample(messages, answer))
    return samples


def build_dataset(split_path: Path, out_dir: Path, zip_paths: list[Path],
                  rewrites_path: Path = REWRITE_PATH) -> dict[str, int]:
    return _build_dataset(split_path, out_dir, zip_paths, rewrites_path)[0]


def _build_dataset(split_path: Path, out_dir: Path, zip_paths: list[Path],
                   rewrites_path: Path) -> tuple[dict[str, int], int]:
    """(분할별 기록 수, 재작성 없음으로 빠진 QA 수). main이 zip을 두 번 읽지 않게 한 번에 센다."""
    split_of = json.loads(split_path.read_text(encoding="utf-8"))   # {source_id: "train" | "val" | "test"}
    rewrites = load_rewrites(rewrites_path)
    rows: dict[str, list[dict]] = {split: [] for split in SPLIT_FILES}
    missing = 0
    for zip_path in zip_paths:
        for qa in load_qas(zip_path):
            split = split_of.get(qa["source_id"])      # split.json에 없는 상담은 버린다
            if split is None:
                continue
            rewrite = rewrites.get(qa_key(qa))
            missing += rewrite is None
            rows[split] += build_samples(qa, rewrite)
    for split, samples in synth_samples().items():
        rows[split] += samples

    out_dir.mkdir(parents=True, exist_ok=True)
    for split, file_name in SPLIT_FILES.items():
        with (out_dir / file_name).open("w", encoding="utf-8") as f:
            for row in rows[split]:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {split: len(samples) for split, samples in rows.items()}, missing


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="잔액조회 학습 데이터 생성")
    parser.add_argument("--split", type=Path, default=SPLIT_PATH, help="공통 split.json")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--zip", dest="zips", type=Path, nargs="+", default=[TL_ZIP, VL_ZIP], help="은행 라벨링 zip")
    parser.add_argument("--rewrites", type=Path, default=REWRITE_PATH, help="LLM 재작성 캐시(rewrite.py)")
    args = parser.parse_args(argv)
    counts, missing = _build_dataset(args.split, args.out_dir, args.zips, args.rewrites)
    print(f"{args.out_dir}: {counts}, 재작성 없음으로 빠진 QA {missing}건")


if __name__ == "__main__":      # python -m training.balance.prepare
    main()
