"""RT-003: 세션은 프로세스 메모리 dict. session_id마다 history와 되묻기 대기(pending)를 든다."""
import pytest

from app.gateway import session as session_module
from app.gateway.session import Session, get_session
from app.masking import MaskResult


@pytest.fixture(autouse=True)
def fresh_sessions(monkeypatch):
    monkeypatch.setattr(session_module, "sessions", {})


def test_get_session_creates_once_and_returns_same_object():
    first = get_session("s1")
    assert isinstance(first, Session)
    assert get_session("s1") is first


def test_new_session_is_empty():
    s = get_session("s1")
    assert s.history == []
    assert s.pending is None


def test_sessions_do_not_share_state():
    a = get_session("a")
    a.history.append({"role": "user", "content": "잔액"})
    a.pending = MaskResult(masked_text="잔액", mask_map={})
    b = get_session("b")
    assert b.history == []
    assert b.pending is None
