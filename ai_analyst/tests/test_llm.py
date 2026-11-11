"""app/llm.py 테스트. OpenAI 클라이언트를 가짜로 바꿔 실제 API 는 부르지 않는다."""
from types import SimpleNamespace

import pytest

from app import llm


class FakeClient:
    """client.chat.completions.create(...) 모양만 흉내 내고, 받은 인자를 기록한다."""

    def __init__(self, content="응답"):
        self.calls = []
        self.content = content
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))],
            usage=SimpleNamespace(total_tokens=123),
        )


@pytest.fixture
def client(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(llm, "_client", lambda: fake)
    monkeypatch.setenv("FANLOG_MODEL", "test-model")
    return fake


def test_model_env_missing_raises(client, monkeypatch):
    monkeypatch.delenv("FANLOG_MODEL")
    with pytest.raises(RuntimeError):
        llm.complete("system", [{"role": "user", "content": "hi"}])
    assert client.calls == []  # API 를 부르기 전에 멈춘다


def test_returns_text_and_tokens(client):
    out = llm.complete("system", [{"role": "user", "content": "hi"}])
    assert out == {"text": "응답", "tokens": 123}
    sent = client.calls[0]
    assert sent["model"] == "test-model"
    assert sent["messages"][0] == {"role": "system", "content": "system"}
    assert "response_format" not in sent  # 일반 텍스트 모드


def test_json_mode_sets_response_format(client):
    llm.complete("Respond with a JSON object.", [{"role": "user", "content": "hi"}], json_mode=True)
    assert client.calls[0]["response_format"] == {"type": "json_object"}


def test_json_mode_requires_word_json(client):
    with pytest.raises(ValueError):
        llm.complete("system", [{"role": "user", "content": "hi"}], json_mode=True)
    assert client.calls == []  # 400 에러로 호출 1회를 날리지 않는다


def test_none_content_becomes_empty_string(client):
    client.content = None
    assert llm.complete("system", [{"role": "user", "content": "hi"}])["text"] == ""
