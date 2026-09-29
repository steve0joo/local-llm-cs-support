import json
import subprocess
import sys
import threading
import zipfile
from pathlib import Path

import pytest

from app.agents.balance.validate import DOCUMENT_KEYWORDS
from training.balance import prepare, rewrite
from training.common.split import OUT_PATH, TL_ZIP, VL_ZIP

TOPIC = "거래내역/잔액조회"
NAMES = "가나다라마바"


def _qa(name, **fields):
    return {"source_id": f"S{name}", "question": f"{name} 계좌 잔액 궁금해요", "answer": "네, 안내해 드리겠습니다.",
            "follow_up": f"{name} 통장도 되나요?", "output": "앱에서 확인하실 수 있습니다.", **fields}


QAS = [_qa(name) for name in NAMES[:5]]


def _envelope(items, cost=0.01, **extra):
    return json.dumps({"type": "result", "is_error": False, "structured_output": {"items": items},
                       "total_cost_usd": cost, **extra}, ensure_ascii=False)


class FakeClaude:
    """실제 claude CLI 대신 쓴다. 받은 명령·입력을 기록하고 items를 거꾸로 돌려준다."""

    def __init__(self, drop=(), cost=0.01):
        self.calls = []
        self.drop = set(drop)
        self.cost = cost
        self._lock = threading.Lock()

    def __call__(self, command, prompt):
        with self._lock:
            self.calls.append((command, prompt))
        items = json.loads(prompt)["items"]
        return _envelope([
            {"key": item["key"], "answer": "다시 쓴 " + item["question"], "output": "다시 쓴 " + item["follow_up"]}
            for item in reversed(items) if item["key"] not in self.drop
        ], cost=self.cost)

    def sent_keys(self):
        return [item["key"] for _, prompt in self.calls for item in json.loads(prompt)["items"]]


def _cache_lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_constants():
    assert rewrite.MODEL == "claude-haiku-4-5"
    assert rewrite.CHUNK == 20
    item = rewrite.OUTPUT_SCHEMA["properties"]["items"]["items"]
    assert item["required"] == ["key", "answer", "output"]
    assert item["additionalProperties"] is False


def test_rewrite_system_matches_code_constants():
    assert str(prepare.MAX_CHARS) in rewrite.REWRITE_SYSTEM
    assert [word for word in DOCUMENT_KEYWORDS if word not in rewrite.REWRITE_SYSTEM] == []
    assert "key" in rewrite.REWRITE_SYSTEM


# 1차 시범 판독에서 나온 위반을 막는 규칙 5·7·10·11 문구(BAL-010 보강)
@pytest.mark.parametrize("phrase", [
    "정확한 원인을 파악하여 안내해 드리겠습니다",
    "해결되면 문자로 안내하므로 기다려 주세요",
    "수수료는 발생하지 않습니다",
    "출금일이 휴일이면 전 영업일에 처리됩니다",
    "보류 금액은 자동으로 해제됩니다",
    "금융보안 관련 규정이 변경되었습니다",
    "개인 정보 관리 메뉴에서 변경하실 수 있습니다",
    "지급정지 상태는 해외 결제 등으로 자금이 일시적으로 보류된 상태를 의미합니다",
    "앱을 최신 버전으로 업데이트한 뒤 다시 시도",
    "모바일 앱이나 인터넷 뱅킹에서 거래내역 확인",
    "송금한 은행이나 카드사에 문의",
    "비밀번호 정기 변경",
    "items는 서로 다른 상담이다",
    "다른 item의 내용을 가져오지 않는다",
])
def test_rewrite_system_has_pilot_rule_phrases(phrase):
    assert phrase in rewrite.REWRITE_SYSTEM


def test_build_command_shape():
    command = rewrite.build_command("claude-test-model")
    assert command[:2] == ["claude", "-p"]
    assert command[command.index("--model") + 1] == "claude-test-model"
    assert command[command.index("--system-prompt") + 1] == rewrite.REWRITE_SYSTEM
    assert command[command.index("--tools") + 1] == ""
    assert json.loads(command[command.index("--json-schema") + 1]) == rewrite.OUTPUT_SCHEMA
    assert command[command.index("--output-format") + 1] == "json"
    for flag in ("--no-session-persistence", "--strict-mcp-config", "--disable-slash-commands"):
        assert flag in command
    assert "--bare" not in command


def test_build_prompt_sends_masked_fields_with_keys():
    qa = _qa("가", question="제 계좌 110-9876-5432 잔액이요", follow_up="010-2222-3333으로 연락 주세요")
    prompt = rewrite.build_prompt([qa, QAS[1]])
    assert json.loads(prompt) == {"items": [
        {"key": prepare.qa_key(qa), **prepare.mask_fields(qa)},
        {"key": prepare.qa_key(QAS[1]), **prepare.mask_fields(QAS[1])},
    ]}
    for original in ("110-9876-5432", "010-2222-3333"):
        assert original not in prompt


def test_parse_envelope_returns_requested_answers_and_cost():
    stdout = _envelope([{"key": "k1", "answer": "답", "output": "출력"}], cost=0.25)
    assert rewrite.parse_envelope(stdout, {"k1"}) == ({"k1": {"answer": "답", "output": "출력"}}, 0.25)


@pytest.mark.parametrize("stdout", [
    "",
    "not json",
    _envelope([{"key": "k1", "answer": "답", "output": "출력"}], is_error=True),
    json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0.1}),
])
def test_parse_envelope_rejects_failed_results(stdout):
    assert rewrite.parse_envelope(stdout, {"k1"}) == ({}, 0.0)


def test_parse_envelope_drops_unrequested_keys_and_empty_answers():
    stdout = _envelope([
        {"key": "k1", "answer": "답", "output": "출력"},
        {"key": "other", "answer": "답", "output": "출력"},
        {"key": "k2", "answer": "", "output": "출력"},
        {"key": "k3", "answer": "답", "output": "  "},
    ])
    results, _ = rewrite.parse_envelope(stdout, {"k1", "k2", "k3"})
    assert results == {"k1": {"answer": "답", "output": "출력"}}


def test_parse_envelope_cost_defaults_to_zero():
    stdout = json.dumps({"type": "result", "is_error": False,
                         "structured_output": {"items": [{"key": "k1", "answer": "답", "output": "출력"}]}})
    assert rewrite.parse_envelope(stdout, {"k1"}) == ({"k1": {"answer": "답", "output": "출력"}}, 0.0)


def test_run_claude_passes_prompt_on_stdin_in_empty_temp_dir():
    script = "import os, sys; print(os.getcwd()); print(len(os.listdir('.'))); print(sys.stdin.read())"
    lines = rewrite.run_claude([sys.executable, "-c", script], "입력 JSON").splitlines()
    assert Path(lines[0]).resolve() != Path.cwd().resolve()
    assert lines[1:] == ["0", "입력 JSON"]


@pytest.mark.parametrize("command", [
    ["this-command-does-not-exist-xyz"],
    [sys.executable, "-c", "import sys; print('partial'); sys.exit(1)"],
])
def test_run_claude_returns_empty_on_failure(command):
    assert rewrite.run_claude(command, "입력") == ""


def test_run_claude_returns_empty_on_timeout(monkeypatch):
    seen = {}

    def fake_run(command, **kwargs):
        seen.update(kwargs)
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(rewrite.subprocess, "run", fake_run)
    assert rewrite.run_claude(["claude"], "입력") == ""
    assert seen["timeout"] == 600 and seen["input"] == "입력"


def test_run_all_saves_by_key_even_if_order_differs(tmp_path):
    cache = tmp_path / "rewrites.jsonl"
    fake = FakeClaude(cost=0.01)
    stats = rewrite.run_all(QAS, cache, model="claude-test-model", chunk=2, run=fake)

    assert len(fake.calls) == 3
    assert [len(json.loads(prompt)["items"]) for _, prompt in fake.calls] == [2, 2, 1]
    assert all(command == rewrite.build_command("claude-test-model") for command, _ in fake.calls)
    assert stats["saved"] == 5 and stats["missing"] == 0
    assert stats["cost_usd"] == pytest.approx(0.03)

    saved = prepare.load_rewrites(cache)
    for qa in QAS:
        fields = prepare.mask_fields(qa)
        assert saved[prepare.qa_key(qa)] == {"answer": "다시 쓴 " + fields["question"],
                                             "output": "다시 쓴 " + fields["follow_up"]}


def test_run_all_cache_line_shape(tmp_path):
    cache = tmp_path / "rewrites.jsonl"
    rewrite.run_all(QAS[:2], cache, chunk=2, run=FakeClaude())
    lines = _cache_lines(cache)
    assert [set(line) for line in lines] == [{"key", "source", "answer", "output"}] * 2
    by_key = {line["key"]: line for line in lines}
    for qa in QAS[:2]:
        assert by_key[prepare.qa_key(qa)]["source"] == prepare.mask_fields(qa)


def test_run_all_skips_cached_keys(tmp_path):
    cache = tmp_path / "rewrites.jsonl"
    rewrite.run_all(QAS[:2], cache, chunk=2, run=FakeClaude())

    fake = FakeClaude()
    stats = rewrite.run_all(QAS, cache, chunk=2, run=fake)
    assert sorted(fake.sent_keys()) == sorted(prepare.qa_key(qa) for qa in QAS[2:])
    assert stats["saved"] == 3
    assert set(prepare.load_rewrites(cache)) == {prepare.qa_key(qa) for qa in QAS}


def test_run_all_counts_missing_keys_and_retries_them(tmp_path):
    cache = tmp_path / "rewrites.jsonl"
    dropped = prepare.qa_key(QAS[3])
    stats = rewrite.run_all(QAS, cache, chunk=2, run=FakeClaude(drop={dropped}))
    assert stats["saved"] == 4 and stats["missing"] == 1
    assert dropped not in prepare.load_rewrites(cache)

    fake = FakeClaude()
    stats = rewrite.run_all(QAS, cache, chunk=2, run=fake)
    assert fake.sent_keys() == [dropped]
    assert stats["saved"] == 1 and stats["missing"] == 0


def test_run_all_failed_call_saves_nothing(tmp_path):
    cache = tmp_path / "rewrites.jsonl"
    stats = rewrite.run_all(QAS, cache, chunk=2, run=lambda command, prompt: "")
    assert stats == {"saved": 0, "missing": 5, "cost_usd": 0.0}
    assert prepare.load_rewrites(cache) == {}


def test_run_all_with_jobs_saves_same_keys(tmp_path):
    serial, parallel = tmp_path / "serial.jsonl", tmp_path / "parallel.jsonl"
    rewrite.run_all(QAS, serial, chunk=2, jobs=1, run=FakeClaude())
    stats = rewrite.run_all(QAS, parallel, chunk=2, jobs=2, run=FakeClaude())
    assert stats["saved"] == 5
    assert prepare.load_rewrites(parallel) == prepare.load_rewrites(serial)


def _doc(source_id, question, *, topic=TOPIC):
    return {
        "source": {"source_id": source_id},
        "consulting": {"consulting_category": "은행", "consulting_topic": topic},
        "qa_data": [{
            "qa_id": f"{source_id}-1",
            "qa_topic": topic,
            "input": {"question": question, "answer": "네.", "follow_up_question": "어떻게 하나요?"},
            "output": "앱에서 확인하실 수 있습니다.",
        }],
    }


def _write_zip(path, docs):
    with zipfile.ZipFile(path, "w") as z:
        for i, doc in enumerate(docs):
            z.writestr(f"{i}.json", json.dumps(doc, ensure_ascii=False))
    return path


def test_split_qas_keeps_only_split_consultations_in_load_order(tmp_path):
    tl = _write_zip(tmp_path / "TL.zip", [
        _doc("S1", "학습용 질문"),
        _doc("S4", "다른 주제 질문", topic="대출문의(만기/연장/조회등)"),
    ])
    vl = _write_zip(tmp_path / "VL.zip", [_doc("S2", "검증용 질문"), _doc("S6", "분할에 없는 질문")])
    split_path = tmp_path / "split.json"
    split_path.write_text(json.dumps({"S1": "train", "S2": "val", "S4": "train"}), encoding="utf-8")

    assert [qa["question"] for qa in rewrite.split_qas(split_path, [tl, vl])] == ["학습용 질문", "검증용 질문"]


@pytest.fixture
def cli(monkeypatch, tmp_path):
    cache = tmp_path / "rewrites.jsonl"
    seen = {"split_qas": [], "run_all": []}

    def fake_split_qas(split_path, zip_paths):
        seen["split_qas"].append((split_path, zip_paths))
        return QAS

    def fake_run_all(qas, cache_path, **kwargs):
        seen["run_all"].append((qas, cache_path, kwargs))
        return {"saved": len(qas), "missing": 0, "cost_usd": 0.0}

    monkeypatch.setattr(prepare, "REWRITE_PATH", cache)
    monkeypatch.setattr(rewrite, "split_qas", fake_split_qas)
    monkeypatch.setattr(rewrite, "run_all", fake_run_all)
    return cache, seen


def test_main_sends_first_uncached_qas_up_to_limit(cli):
    cache, seen = cli
    line ={"key": prepare.qa_key(QAS[0]), "source": {}, "answer": "답", "output": "출력"}
    cache.write_text(json.dumps(line, ensure_ascii=False) + "\n", encoding="utf-8")

    rewrite.main(["--limit", "2", "--chunk", "5", "--jobs", "3", "--model", "claude-test-model"])
    assert seen["split_qas"] == [(OUT_PATH, [TL_ZIP, VL_ZIP])]
    [(qas, cache_path, kwargs)] = seen["run_all"]
    assert qas == QAS[1:3]
    assert cache_path == cache
    assert kwargs == {"model": "claude-test-model", "chunk": 5, "jobs": 3}


def test_main_defaults_send_all_uncached(cli):
    cache, seen = cli
    rewrite.main([])
    [(qas, _, kwargs)] = seen["run_all"]
    assert qas == QAS
    assert kwargs == {"model": rewrite.MODEL, "chunk": rewrite.CHUNK, "jobs": 1}


def test_main_stops_when_nothing_to_send(cli, capsys):
    cache, seen = cli
    cache.write_text("".join(
        json.dumps({"key": prepare.qa_key(qa), "source": {}, "answer": "답", "output": "출력"}) + "\n" for qa in QAS
    ), encoding="utf-8")
    rewrite.main([])
    assert seen["run_all"] == []
    assert capsys.readouterr().out.strip()
