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


# =====================================================================
# 추론 계열 모델 대응: 도구 호출에 reasoning_effort, 출력 상한 소진 구분
# =====================================================================
BASE_ARGS = {"model", "messages", "tools", "tool_choice", "parallel_tool_calls", llm.OUTPUT_TOKEN_PARAM}


def recording_client(monkeypatch, content="답", finish_reason="stop", tool_calls=None):
    """요청 인자를 기록하는 가짜 클라이언트. 응답의 content, finish_reason, tool_calls 를 고를 수 있다."""
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        message = SimpleNamespace(content=content, tool_calls=tool_calls)
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish_reason)],
                               usage=SimpleNamespace(total_tokens=7))

    monkeypatch.setattr(llm, "_client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    monkeypatch.setenv("FANLOG_MODEL", "test-model")
    return calls


def call_tools(**kwargs):
    return llm.complete_with_tools("system", [{"role": "user", "content": "hi"}], tools=[], **kwargs)


def call_plain(**kwargs):
    return llm.complete("system", [{"role": "user", "content": "hi"}], **kwargs)


def test_tool_call_sends_reasoning_effort_none_and_keeps_the_other_arguments(monkeypatch):
    calls = recording_client(monkeypatch)
    monkeypatch.setattr(llm, "_sdk_accepts_reasoning_effort", lambda: True)
    call_tools()
    sent = calls[0]
    assert llm.TOOL_REASONING_EFFORT == "none" and sent["reasoning_effort"] == "none"
    assert set(sent) == BASE_ARGS | {"reasoning_effort"}  # 기존 인자는 그대로, 늘어난 것은 reasoning_effort 하나
    assert sent["parallel_tool_calls"] is False and sent["tool_choice"] == "auto" and sent[llm.OUTPUT_TOKEN_PARAM] == 4000


def test_the_final_answer_call_also_sends_it_and_keeps_tool_choice_none(monkeypatch):
    calls = recording_client(monkeypatch)
    monkeypatch.setattr(llm, "_sdk_accepts_reasoning_effort", lambda: True)
    call_tools(allow_tools=False)
    assert calls[0]["tool_choice"] == "none" and calls[0]["reasoning_effort"] == "none"


def test_the_value_comes_from_one_constant(monkeypatch):
    calls = recording_client(monkeypatch)
    monkeypatch.setattr(llm, "_sdk_accepts_reasoning_effort", lambda: True)
    monkeypatch.setattr(llm, "TOOL_REASONING_EFFORT", "low")
    call_tools()
    assert calls[0]["reasoning_effort"] == "low"


def test_it_goes_through_extra_body_when_the_sdk_does_not_take_the_argument(monkeypatch):
    calls = recording_client(monkeypatch)
    monkeypatch.setattr(llm, "_sdk_accepts_reasoning_effort", lambda: False)
    call_tools()
    sent = calls[0]
    assert "reasoning_effort" not in sent and sent["extra_body"] == {"reasoning_effort": "none"}
    assert set(sent) == BASE_ARGS | {"extra_body"}


def test_with_the_installed_sdk_the_argument_goes_the_way_the_sdk_signature_allows(monkeypatch):
    """가짜 없이 실제로 설치된 SDK 의 시그니처로 판단한다: 받으면 직접, 못 받으면 extra_body."""
    import inspect
    from openai.resources.chat.completions import Completions
    takes_it = "reasoning_effort" in inspect.signature(Completions.create).parameters
    calls = recording_client(monkeypatch)
    call_tools()
    sent = calls[0]
    assert llm._sdk_accepts_reasoning_effort() is takes_it
    if takes_it:
        assert sent["reasoning_effort"] == "none" and "extra_body" not in sent
    else:
        assert sent["extra_body"] == {"reasoning_effort": "none"} and "reasoning_effort" not in sent


def test_plain_complete_does_not_send_reasoning_effort(monkeypatch):
    calls = recording_client(monkeypatch)
    call_plain()
    for sent in calls:
        assert "reasoning_effort" not in sent and "extra_body" not in sent
        assert set(sent) == {"model", "messages", llm.OUTPUT_TOKEN_PARAM}
    calls.clear()
    llm.complete("Respond with a JSON object.", [{"role": "user", "content": "hi"}], json_mode=True)
    assert set(calls[0]) == {"model", "messages", llm.OUTPUT_TOKEN_PARAM, "response_format"}  # complete() 의 인자는 그대로


# ---------- 출력 상한 소진: finish_reason 이 length 이고 내용이 비어 있다 ----------
@pytest.mark.parametrize("content", ["", None])
def test_empty_output_cut_by_the_length_limit_is_a_distinct_error(monkeypatch, content):
    recording_client(monkeypatch, content=content, finish_reason="length")
    with pytest.raises(llm.OutputLimitError):
        call_tools()
    with pytest.raises(llm.OutputLimitError):
        call_plain()


def test_the_error_carries_no_response_text(monkeypatch):
    recording_client(monkeypatch, content="", finish_reason="length")
    with pytest.raises(llm.OutputLimitError) as info:
        call_tools()
    assert info.value.args == ()  # 응답 본문도 오류 문장도 담지 않는다


def test_length_finish_with_content_is_returned_as_before(monkeypatch):
    recording_client(monkeypatch, content="잘린 답", finish_reason="length")
    assert call_tools()["text"] == "잘린 답" and call_plain()["text"] == "잘린 답"


def test_length_finish_with_a_tool_call_is_returned_as_before(monkeypatch):
    call = SimpleNamespace(id="c1", function=SimpleNamespace(name="echo", arguments="{}"))
    recording_client(monkeypatch, content="", finish_reason="length", tool_calls=[call])
    assert call_tools()["tool_calls"] == [{"id": "c1", "name": "echo", "arguments": "{}"}]


@pytest.mark.parametrize("finish", ["stop", "tool_calls", "content_filter", None])
def test_empty_output_for_other_reasons_is_not_an_output_limit_error(monkeypatch, finish):
    recording_client(monkeypatch, content="", finish_reason=finish)
    assert call_tools()["text"] == "" and call_plain()["text"] == ""  # 기존 처리(파싱 실패 등)에 맡긴다


def test_a_normal_response_is_unchanged(monkeypatch):
    recording_client(monkeypatch, content="정상", finish_reason="stop")
    assert call_tools() == {"text": "정상", "tool_calls": [], "tokens": 7}
    assert call_plain() == {"text": "정상", "tokens": 7}
