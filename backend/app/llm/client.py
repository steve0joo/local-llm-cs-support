"""Ollama 호출과 모델 입력 로그 (docs/ARCHITECTURE.md 계약 5, docs/router/ADR.md RT-004).

- Ollama `/api/chat`을 비스트리밍으로 호출한다(ADR-007).
- 호출마다 입력을 `backend/logs/model_inputs.jsonl`에 `{ts, model, messages}` 한 줄로 남긴다.
  PM이 인수 때 이 파일을 열어 원본 개인정보가 없는지 확인하므로, 여기 오는 messages는 이미 마스킹된 것이어야 한다.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "model_inputs.jsonl"
TIMEOUT_SECONDS = 60.0      # 모델 적재 고려하여 60초로 지정 - 추후 변경 가능


def generate(model: str, messages: list[dict], **options) -> str:
    """model에 messages를 보내고 응답 텍스트를 돌려준다. options는 Ollama 생성 옵션(temperature 등)이다."""
    _log_input(model, messages)
    response = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": model,
            "messages": messages,
            "stream": False,
            "think": False,             # Qwen3 계열은 thinking 모드가 기본이라 답이 content가 아닌 thinking 필드로 가서 content가 비어온다.
            "options": options,
        },
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]

# tail -3 logs/model_inputs.jsonl로 확인 가능
def _log_input(model: str, messages: list[dict]) -> None:
    record = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": model, "messages": messages}
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
