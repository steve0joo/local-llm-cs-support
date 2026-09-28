"""계약 5(모델 호출과 로그)와 RT-004.

- generate(model, messages, **options)는 Ollama /api/chat을 비스트리밍으로 호출해 응답 텍스트를 돌려준다.
- 호출마다 logs/model_inputs.jsonl에 {ts, model, messages} 한 줄을 추가한다. PM이 이 파일로 마스킹을 확인한다.
- Ollama HTTP는 목으로 바꾼다. 실제 서버는 필요 없다.
"""
import json

import httpx
import pytest

from app import llm
from app.llm import client

MESSAGES = [{"role": "user", "content": "[계좌번호_1] 잔액 알려줘"}]


@pytest.fixture
def ollama(monkeypatch, tmp_path):
    """httpx.post를 가로채 요청을 기록하고 고정 응답을 돌려준다. 로그는 tmp_path에 쓴다."""
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append({"url": url, "json": json})
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "balance"}}, request=request)

    monkeypatch.setattr(client.httpx, "post", fake_post)
    monkeypatch.setattr(client, "LOG_PATH", tmp_path / "logs" / "model_inputs.jsonl")
    return calls


def test_generate_returns_assistant_content(ollama):
    assert llm.generate("cs-router", MESSAGES) == "balance"


def test_generate_calls_ollama_chat_without_streaming(ollama):
    llm.generate("cs-router", MESSAGES, temperature=0)
    assert len(ollama) == 1
    assert ollama[0]["url"] == f"{client.OLLAMA_URL}/api/chat"
    assert ollama[0]["json"] == {
        "model": "cs-router",
        "messages": MESSAGES,
        "stream": False,
        "think": False,  # Qwen3 thinking 모드를 끄지 않으면 content가 비어 온다
        "options": {"temperature": 0},
    }


def test_every_call_appends_one_log_line(ollama):
    llm.generate("cs-router", MESSAGES)
    llm.generate("cs-balance", MESSAGES + [{"role": "assistant", "content": "{{balance}}"}])

    lines = client.LOG_PATH.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first, second = (json.loads(line) for line in lines)
    assert set(first) == {"ts", "model", "messages"}
    assert first["model"] == "cs-router" and first["messages"] == MESSAGES
    assert second["model"] == "cs-balance" and len(second["messages"]) == 2


def test_log_keeps_korean_readable(ollama):
    """PM이 파일을 열어 눈으로 확인하므로 유니코드 이스케이프 없이 기록한다."""
    llm.generate("cs-router", MESSAGES)
    assert "[계좌번호_1] 잔액 알려줘" in client.LOG_PATH.read_text(encoding="utf-8")


def test_log_directory_is_created_when_missing(ollama):
    assert not client.LOG_PATH.parent.exists()
    llm.generate("cs-router", MESSAGES)
    assert client.LOG_PATH.exists()


def test_http_error_is_raised_not_swallowed(monkeypatch, tmp_path):
    def fake_post(url, json=None, timeout=None):
        return httpx.Response(404, json={"error": "model not found"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(client.httpx, "post", fake_post)
    monkeypatch.setattr(client, "LOG_PATH", tmp_path / "model_inputs.jsonl")
    with pytest.raises(httpx.HTTPStatusError):
        llm.generate("cs-missing", MESSAGES)


def test_documented_monkeypatch_seam_replaces_generate(monkeypatch):
    """다른 영역의 테스트는 monkeypatch.setattr("app.llm.generate", 가짜) 한 곳만 바꾼다 (공통 코드·테스트 규칙)."""
    monkeypatch.setattr("app.llm.generate", lambda model, messages, **options: "가짜 응답")
    assert llm.generate("cs-balance", MESSAGES) == "가짜 응답"
