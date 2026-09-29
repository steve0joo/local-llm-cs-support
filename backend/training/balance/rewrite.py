"""AI Hub 잔액조회 답변을 챗봇 답변으로 다시 쓴다 (docs/agent-balance/ARCHITECTURE.md "`rewrite.py` 인터페이스", BAL-010).

Claude Code 헤드리스 모드(`claude -p`, 사용자 구독 로그인)를 subprocess로 부른다. 마스킹을 거친 텍스트만 보낸다(계약 4).
결과는 prepare.REWRITE_PATH 캐시에 덧붙이고, prepare.py는 이 캐시만 읽는다. 학습용 외부 호출이라 app.llm.generate()를 쓰지 않는다.

실행(사람, train-export step): cd backend && .venv/bin/python -m training.balance.rewrite --limit 30
"""

import argparse
import json
import subprocess
import tempfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app.agents.balance.validate import DOCUMENT_KEYWORDS
from training.balance import prepare
from training.common.split import OUT_PATH as SPLIT_PATH, TL_ZIP, VL_ZIP

MODEL = "claude-haiku-4-5"
CHUNK = 20                        # 호출 한 번에 보낼 QA 수

REWRITE_SYSTEM = f"""너는 은행 콜센터 상담 기록을 은행 잔액조회 챗봇의 답으로 다시 쓰는 편집자다.

입력은 {{"items": [...]}} JSON이다. item 하나가 상담 기록 한 건이고 key·question·answer·follow_up·output 필드가 있다.

규칙
1. 역할: question·answer·follow_up·output은 콜센터 상담 기록 한 건이다. 이것을 은행 잔액조회 챗봇의 답으로 다시 쓴다. 다시 쓴 answer는 question에 대한 답이고, 다시 쓴 output은 다시 쓴 answer 다음에 온 follow_up에 대한 답이다.
2. 챗봇이 할 수 있는 일은 등록된 계좌의 잔액과 최근 거래내역을 보여 주는 것뿐이다. 이 답을 쓰는 턴에서는 계좌를 조회하지 않는다.
3. 정중한 존댓말로 쓴다. 답마다 공백 포함 {prepare.MAX_CHARS}자 이내, 두세 문장이다.
4. 조회·확인 결과를 말하지 않는다. 예: "확인 결과 정상 입금되었습니다"
5. 할 수 없는 행동을 약속하지 않는다(문자·서면 발송, 발급, 정정, 처리, 접수, "조회해 드리겠습니다"). 은행·상담원이 나중에 해 줄 일도 약속하지 않는다(예: "정확한 원인을 파악하여 안내해 드리겠습니다", "해결되면 문자로 안내하므로 기다려 주세요"). 상담원·담당 부서 연결 안내와 고객센터 문의 안내는 괜찮다.
6. 성함·생년월일·계좌번호·비밀번호·주민번호·카드번호를 요구하지 않는다.
7. 금리·수수료·한도·상품명·메뉴 이름·화면 위치·준비물을 지어내지 않는다. 원래 답에 있던 것도 옮기지 않는다. 수수료·한도가 있는지 없는지, 처리·해제·반영에 걸리는 기간, 휴일·영업일 처리 방식, 자동 처리·자동 해제 여부, 규정 변경도 말하지 않는다(예: "수수료는 발생하지 않습니다", "출금일이 휴일이면 전 영업일에 처리됩니다", "보류 금액은 자동으로 해제됩니다", "금융보안 관련 규정이 변경되었습니다", "개인 정보 관리 메뉴에서 변경하실 수 있습니다"). 원래 답이 한 고객의 조회 결과로 원인을 설명했다면 그 원인을 일반 설명으로 바꾸지 않는다(예: "지급정지 상태는 해외 결제 등으로 자금이 일시적으로 보류된 상태를 의미합니다"). 모르는 내용은 상담원에게 확인하라고 안내한다.
8. 아라비아 숫자·%·날짜·금액을 쓰지 않는다. [금액_1] 같은 대괄호 토큰, ★·●·○·OO 같은 가림 표시, 은행 이름을 답에 옮기지 않는다. 은행은 "저희 은행"이나 "해당 은행"이라고 쓴다.
9. {"·".join(f'"{word}"' for word in DOCUMENT_KEYWORDS)}이라는 단어를 쓰지 않는다.
10. 원래 답에 있던 일반 안내는 살린다. 일반 안내는 고객이 어느 은행에서나 스스로 할 수 있는 일이다(앱을 최신 버전으로 업데이트한 뒤 다시 시도, 모바일 앱이나 인터넷 뱅킹에서 거래내역 확인, 송금한 은행이나 카드사에 문의, 비밀번호 정기 변경). 7에 해당하는 내용은 일반 안내가 아니다.
11. items는 서로 다른 상담이다. 다른 item의 내용을 가져오지 않는다.

출력: 입력 items마다 key를 그대로 돌려주고, 다시 쓴 answer와 output을 채운다."""

OUTPUT_SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": {
                     "type": "object", "properties": {"key": {"type": "string"}, "answer": {"type": "string"}, "output": {"type": "string"}},
                     "required": ["key", "answer", "output"], "additionalProperties": False}}},
                 "required": ["items"], "additionalProperties": False}


def build_prompt(qas: list[dict]) -> str:
    return json.dumps({"items": [{"key": prepare.qa_key(q), **prepare.mask_fields(q)} for q in qas]}, ensure_ascii=False)


def build_command(model: str) -> list[str]:
    # --bare는 API 키 인증만 받아서 구독 로그인으로 돌 수 없다(BAL-010)
    return ["claude", "-p", "--model", model, "--system-prompt", REWRITE_SYSTEM, "--tools", "",
            "--json-schema", json.dumps(OUTPUT_SCHEMA), "--output-format", "json",
            "--no-session-persistence", "--strict-mcp-config", "--disable-slash-commands"]


def parse_envelope(stdout: str, keys: set[str]) -> tuple[dict[str, dict], float]:
    """`--output-format json` 결과 한 개 → ({key: {"answer", "output"}}, total_cost_usd). 실패면 ({}, 0.0)."""
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError:
        return {}, 0.0
    if envelope.get("is_error") or not envelope.get("structured_output"):
        return {}, 0.0
    results = {}
    for item in envelope["structured_output"]["items"]:
        answer, output = item["answer"], item["output"]
        if item["key"] in keys and answer.strip() and output.strip():
            results[item["key"]] = {"answer": answer, "output": output}
    return results, float(envelope.get("total_cost_usd", 0.0))


def run_claude(command: list[str], prompt: str) -> str:
    # 빈 임시 폴더에서 실행해 프로젝트 CLAUDE.md가 읽히지 않게 한다
    with tempfile.TemporaryDirectory() as cwd:
        try:
            result = subprocess.run(command, input=prompt, capture_output=True, text=True, timeout=600, cwd=cwd)
        except (OSError, subprocess.TimeoutExpired):
            return ""
    return result.stdout if result.returncode == 0 else ""


def split_qas(split_path: Path, zip_paths: list[Path]) -> list[dict]:
    split_of = json.loads(split_path.read_text(encoding="utf-8"))   # {source_id: "train" | "val" | "test"}
    return [qa for zip_path in zip_paths for qa in prepare.load_qas(zip_path) if qa["source_id"] in split_of]


def run_all(qas: list[dict], cache_path: Path, model: str = MODEL, chunk: int = CHUNK, jobs: int = 1,
            run: Callable[[list[str], str], str] = run_claude) -> dict[str, float]:
    cached = prepare.load_rewrites(cache_path)
    pending: dict[str, dict] = {}                   # key → QA. 결과는 응답 순서가 아니라 key로 맞춘다
    for qa in qas:
        key = prepare.qa_key(qa)
        if key not in cached:
            pending.setdefault(key, qa)
    keys = list(pending)
    batches = [keys[i:i + chunk] for i in range(0, len(keys), chunk)]
    command = build_command(model)

    stats = {"saved": 0, "missing": 0, "cost_usd": 0.0}
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(run, command, build_prompt([pending[k] for k in batch])): batch for batch in batches}
        for done, future in enumerate(as_completed(futures), 1):   # 캐시 쓰기는 메인 스레드에서만
            batch = futures[future]
            results, cost = parse_envelope(future.result(), set(batch))
            lines = [
                json.dumps({"key": key, "source": prepare.mask_fields(pending[key]), **results[key]}, ensure_ascii=False) + "\n"
                for key in batch if key in results
            ]
            with cache_path.open("a", encoding="utf-8") as f:
                f.write("".join(lines))
            stats["saved"] += len(results)
            stats["missing"] += len(batch) - len(results)
            stats["cost_usd"] += cost
            print(f"[{done}/{len(batches)}] 저장 {len(results)}건, 누락 {len(batch) - len(results)}건", flush=True)
    return stats


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="잔액조회 학습 답변 LLM 재작성 (BAL-010)")
    parser.add_argument("--limit", type=int, help="캐시에 없는 split QA 중 앞에서 N개 (기본 전부)")
    parser.add_argument("--chunk", type=int, default=CHUNK, help="호출 한 번에 보낼 QA 수")
    parser.add_argument("--jobs", type=int, default=1, help="동시에 돌릴 호출 수")
    parser.add_argument("--model", default=MODEL)
    args = parser.parse_args(argv)

    cached = prepare.load_rewrites(prepare.REWRITE_PATH)
    todo = [qa for qa in split_qas(SPLIT_PATH, [TL_ZIP, VL_ZIP]) if prepare.qa_key(qa) not in cached][:args.limit]
    if not todo:
        print(f"{prepare.REWRITE_PATH}: 보낼 QA가 없습니다 (캐시 {len(cached)}건)")
        return
    stats = run_all(todo, prepare.REWRITE_PATH, model=args.model, chunk=args.chunk, jobs=args.jobs)
    print(f"{prepare.REWRITE_PATH}: 저장 {stats['saved']}건, 누락 {stats['missing']}건, "
          f"total_cost_usd {stats['cost_usd']:.4f} (캐시 {len(cached) + stats['saved']}건)")


if __name__ == "__main__":      # python -m training.balance.rewrite
    main()
