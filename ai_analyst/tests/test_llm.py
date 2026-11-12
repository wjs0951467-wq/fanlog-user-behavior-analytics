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


# ---------- 보안 점검: 재시도 끄기, 시간 제한, 출력 상한 ----------
def test_client_is_built_without_sdk_retries_and_with_a_60s_timeout(monkeypatch):
    """SDK 는 실패하면 몰래 다시 요청한다. 우리가 세는 호출 수와 실제 요청 수가 어긋나지 않게 끈다."""
    seen = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr(llm, "OpenAI", FakeOpenAI)
    llm._client.cache_clear()
    try:
        llm._client()
    finally:
        llm._client.cache_clear()
    assert seen["max_retries"] == 0 and seen["timeout"] == 60
    assert llm.CLIENT_TIMEOUT_SECONDS == 60


def test_complete_sends_an_output_token_cap(client):
    llm.complete("system", [{"role": "user", "content": "hi"}])
    sent = client.calls[0]
    assert llm.MAX_OUTPUT_TOKENS == 4000 and sent[llm.OUTPUT_TOKEN_PARAM] == 4000


def test_complete_with_tools_sends_the_same_cap(monkeypatch):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="답", tool_calls=None))],
                               usage=SimpleNamespace(total_tokens=5))

    monkeypatch.setattr(llm, "_client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    monkeypatch.setenv("FANLOG_MODEL", "test-model")
    out = llm.complete_with_tools("system", [{"role": "user", "content": "hi"}], tools=[])
    assert out["text"] == "답" and calls[0][llm.OUTPUT_TOKEN_PARAM] == llm.MAX_OUTPUT_TOKENS
    assert calls[0]["parallel_tool_calls"] is False  # 기존 설정은 그대로


def test_token_param_name_is_a_single_switch(client, monkeypatch):
    """모델에 따라 max_tokens / max_completion_tokens 중 하나만 받는다. 이름은 상수 한 곳에서만 바꾼다."""
    monkeypatch.setattr(llm, "OUTPUT_TOKEN_PARAM", "max_tokens")
    llm.complete("system", [{"role": "user", "content": "hi"}])
    sent = client.calls[0]
    assert sent["max_tokens"] == llm.MAX_OUTPUT_TOKENS and "max_completion_tokens" not in sent
    assert llm.OUTPUT_TOKEN_PARAM == "max_tokens"
