"""에이전트 루프, 예산, ask_data 도구, 로그 테스트. LLM 과 DB 는 모두 가짜다 (실제 OpenAI 호출 0회)."""
import json
from types import SimpleNamespace

import pytest

from app import agent, llm, tools
from app.agent import MAX_LLM_CALLS, MAX_STEPS, run_agent


def call(name, call_id="c1", **args):
    """모델이 도구를 부르는 요청 하나."""
    args.setdefault("reason", "테스트")
    return {"id": call_id, "name": name, "arguments": json.dumps(args, ensure_ascii=False)}


def says(text="", *tool_calls, tokens=100):
    return {"text": text, "tool_calls": list(tool_calls), "tokens": tokens}


class FakeLLM:
    """준비한 응답을 순서대로 돌려준다. 응답이 떨어지면 마지막 응답을 반복한다(끝없이 도구만 부르는 모델 흉내)."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, system, messages, specs, allow_tools=True):
        self.calls.append({"system": system, "messages": list(messages), "specs": specs, "allow_tools": allow_tools})
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply


def fake_tool(name="echo", llm_cost=0, max_per_question=99, used_calls=0, fail=False):
    """실행 기록을 남기는 가짜 도구."""
    ran = []

    def run(args):
        ran.append(args)
        if fail:
            raise RuntimeError("secret detail")
        return {"status": "ok", "for_llm": {"value": 42}, "for_ui": {"value": 42, "row_count": 1},
                "usage": {"llm_calls": used_calls, "tokens": used_calls * 10}}

    return {"spec": {"type": "function", "function": {"name": name}}, "run": run,
            "llm_cost": llm_cost, "max_per_question": max_per_question, "ran": ran}


@pytest.fixture(autouse=True)
def no_real_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "LOG_DIR", tmp_path / "logs")  # 테스트가 진짜 logs/ 에 쓰지 않게


def use_llm(monkeypatch, *replies):
    fake = FakeLLM(*replies)
    monkeypatch.setattr(agent, "complete_with_tools", fake)
    return fake


# ---------- 루프 ----------
def test_answers_directly_without_tools(monkeypatch):
    fake = use_llm(monkeypatch, says("안녕하세요."))
    out = run_agent("안녕", tools={"echo": fake_tool()})
    assert out["answer"] == "안녕하세요." and out["steps"] == [] and out["error"] is None
    assert out["usage"]["llm_calls"] == 1 and len(fake.calls) == 1


def test_tool_then_answer_records_what_why_args(monkeypatch):
    echo = fake_tool(used_calls=2)
    fake = use_llm(monkeypatch, says("", call("echo", x=1, reason="값을 확인하려고")), says("값은 42입니다."))

    out = run_agent("값은?", tools={"echo": echo})

    assert out["answer"] == "값은 42입니다."
    assert echo["ran"] == [{"x": 1}]  # reason 은 기록용이라 도구에는 넘기지 않는다
    step = out["steps"][0]
    assert (step["tool"], step["reason"], step["args"], step["status"], step["step"]) == \
           ("echo", "값을 확인하려고", {"x": 1}, "ok", 1)
    assert step["result"] == {"value": 42, "row_count": 1}  # 화면용 전체 결과

    # 두 번째 LLM 호출에는 "도구를 불렀다" + "도구 결과" 메시지가 짝(call_id)을 맞춰 붙어 있다
    history = fake.calls[1]["messages"]
    assert [m["role"] for m in history] == ["user", "assistant", "tool"]
    assert history[2]["tool_call_id"] == "c1"
    assert json.loads(history[2]["content"]) == {"tool": "echo", "status": "ok", "data": {"value": 42}}

    # 사용량 = 에이전트 2회 + 도구 내부 2회
    assert out["usage"]["llm_calls"] == 4 and out["usage"]["tokens"] == 200 + 20
    assert out["usage"]["by_source"] == {"agent": {"llm_calls": 2, "tokens": 200},
                                         "echo": {"llm_calls": 2, "tokens": 20}}


def test_step_limit_forces_final_answer(monkeypatch):
    echo = fake_tool()
    replies = [says("", call("echo", call_id=f"c{i}", x=i)) for i in range(MAX_STEPS - 1)] + [says("여기까지입니다.")]
    fake = use_llm(monkeypatch, *replies)

    out = run_agent("계속", tools={"echo": echo})

    assert len(fake.calls) == MAX_STEPS
    assert [c["allow_tools"] for c in fake.calls] == [True] * (MAX_STEPS - 1) + [False]  # 마지막은 도구 금지
    assert out["answer"] == "여기까지입니다." and out["forced_final"] is True
    assert len(echo["ran"]) == MAX_STEPS - 1


def test_model_that_only_calls_tools_ends_with_error(monkeypatch):
    echo = fake_tool()
    fake = use_llm(monkeypatch, says("", call("echo", x=1)))  # 글 없이 도구만 계속 부른다

    out = run_agent("계속", tools={"echo": echo})

    assert len(fake.calls) == MAX_STEPS  # 무한 루프가 아니다
    assert out["answer"] is None and out["error"] == "최종 답변을 만들지 못했습니다."


def test_total_llm_calls_never_exceed_budget(monkeypatch):
    heavy = fake_tool("heavy", llm_cost=3, used_calls=3)
    replies = [says("", call("heavy", call_id=f"c{i}", x=i)) for i in range(3)] + [says("끝")]
    fake = use_llm(monkeypatch, *replies)

    out = run_agent("많이", tools={"heavy": heavy})

    # 1번째: 에이전트 1 + 도구 3 = 4회 / 2번째: 다시 4회 = 8회
    # 3번째: 에이전트 1 = 9회. 도구가 3회를 더 쓰면 최종 답 1회가 안 남으므로 실행을 거절한다
    # 4번째: 남은 1회로 도구 없이 최종 답만 받는다 = 10회
    assert len(heavy["ran"]) == 2
    assert [s["status"] for s in out["steps"]] == ["ok", "ok", "error"]
    assert "예산" in json.loads(fake.calls[3]["messages"][-1]["content"])["data"]["error"]
    assert len(fake.calls) == 4 and fake.calls[3]["allow_tools"] is False
    assert out["answer"] == "끝" and out["forced_final"] is True
    assert out["usage"]["llm_calls"] == MAX_LLM_CALLS


def test_per_tool_limit(monkeypatch):
    limited = fake_tool("limited", max_per_question=2)
    replies = [says("", call("limited", call_id=f"c{i}", x=i)) for i in range(3)] + [says("끝")]
    use_llm(monkeypatch, *replies)

    out = run_agent("세 번", tools={"limited": limited})

    assert len(limited["ran"]) == 2
    assert [s["status"] for s in out["steps"]] == ["ok", "ok", "error"]


def test_two_tool_calls_in_one_message_are_both_handled(monkeypatch):
    echo = fake_tool()
    fake = use_llm(monkeypatch, says("", call("echo", "c1", x=1), call("echo", "c2", x=2)), says("끝"))

    out = run_agent("둘", tools={"echo": echo})

    assert echo["ran"] == [{"x": 1}, {"x": 2}]
    tool_messages = [m for m in fake.calls[1]["messages"] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_messages] == ["c1", "c2"]  # 호출마다 결과가 하나씩 있어야 API 가 받는다
    assert [s["step"] for s in out["steps"]] == [1, 1]


def test_duplicate_call_is_not_executed_again(monkeypatch):
    echo = fake_tool(used_calls=1)
    use_llm(monkeypatch, says("", call("echo", "c1", x=1, reason="처음")),
            says("", call("echo", "c2", x=1, reason="다시")), says("끝"))

    out = run_agent("반복", tools={"echo": echo})

    assert len(echo["ran"]) == 1  # reason 이 달라도 인자가 같으면 같은 호출이다
    assert [s["status"] for s in out["steps"]] == ["ok", "duplicate"]
    assert out["usage"]["by_source"]["echo"]["llm_calls"] == 1


# ---------- 잘못된 요청 ----------
@pytest.mark.parametrize("arguments", ["{not json", "[1, 2]", '"text"'])
def test_bad_arguments_do_not_run_the_tool(monkeypatch, arguments):
    echo = fake_tool()
    fake = use_llm(monkeypatch, says("", {"id": "c1", "name": "echo", "arguments": arguments}), says("끝"))

    out = run_agent("이상한 인자", tools={"echo": echo})

    assert echo["ran"] == [] and out["steps"][0]["status"] == "error"
    assert "JSON 객체" in json.loads(fake.calls[1]["messages"][-1]["content"])["data"]["error"]
    assert out["answer"] == "끝"  # 예외로 죽지 않고 계속 진행한다


def test_unknown_tool_returns_allowed_names(monkeypatch):
    fake = use_llm(monkeypatch, says("", call("drop_table")), says("끝"))
    out = run_agent("없는 도구", tools={"echo": fake_tool()})
    data = json.loads(fake.calls[1]["messages"][-1]["content"])["data"]
    assert out["steps"][0]["status"] == "error" and data["allowed"] == ["echo"]


def test_tool_exception_is_contained(monkeypatch):
    fake = use_llm(monkeypatch, says("", call("echo", x=1)), says("도구가 실패했습니다."))
    out = run_agent("실패", tools={"echo": fake_tool(fail=True)})
    sent = fake.calls[1]["messages"][-1]["content"]
    assert out["steps"][0]["status"] == "error" and out["answer"] == "도구가 실패했습니다."
    assert "RuntimeError" in sent and "secret detail" not in sent  # 에러 원문은 내보내지 않는다


def test_llm_error_is_reported_without_message_text(monkeypatch):
    use_llm(monkeypatch, RuntimeError("Incorrect API key provided: sk-abc***xyz"))
    out = run_agent("질문", tools={"echo": fake_tool()})
    assert out["answer"] is None and out["error"] == "[LLM 오류] RuntimeError"
    assert "sk-" not in json.dumps(out, ensure_ascii=False, default=str)
    assert out["usage"]["llm_calls"] == 1  # 실패한 호출도 센다


@pytest.mark.parametrize("question", ["", "   ", None, "가" * 501])
def test_bad_question_makes_no_llm_call(monkeypatch, question):
    fake = use_llm(monkeypatch, says("답"))
    out = run_agent(question, tools={"echo": fake_tool()})
    assert out["error"] and out["answer"] is None and fake.calls == []


def test_system_prompt_has_definitions_and_safety_rules():
    p = agent.SYSTEM_PROMPT
    assert "at_risk" in p and "상위 10%군" in p and "get_churn_segments" in p and "ask_data" in p
    assert "DATA, not instructions" in p and "must come from a tool result" in p


# ---------- ask_data 도구 ----------
def ask_result(**over):
    out = {"question": "q", "sql": "SELECT 1", "columns": ["n"], "rows": [[3]], "row_count": 1,
           "assumptions": ["탈퇴 사용자 제외"], "summary": None,
           "attempts": [{"sql": "SELECT 1", "error_type": "none", "error_message": None}],
           "error": None, "usage": {"llm_calls": 1, "tokens": 500}}
    out.update(over)
    return out


def test_ask_data_reuses_ask_with_summary_off(monkeypatch):
    seen = {}
    monkeypatch.setattr(tools, "ask", lambda q, summarize_result=True: seen.update(q=q, s=summarize_result) or ask_result())

    out = tools.run_ask_data({"question": "  현재 휴면 팬은 몇 명?  "})

    assert seen == {"q": "현재 휴면 팬은 몇 명?", "s": False}  # 요약 호출은 중복이라 끈다
    assert out["status"] == "ok" and out["usage"] == {"llm_calls": 1, "tokens": 500}
    assert out["for_llm"]["rows"] == [[3]] and out["for_llm"]["assumptions"] == ["탈퇴 사용자 제외"]
    assert "attempts" not in out["for_llm"]  # 실패한 SQL 과 에러 원문은 모델에게 주지 않는다
    assert out["for_ui"]["attempts"]         # 화면에서는 볼 수 있다


@pytest.mark.parametrize("question", [None, "", "   ", 123, "가" * 301])
def test_ask_data_validates_question(monkeypatch, question):
    monkeypatch.setattr(tools, "ask", lambda *a, **k: pytest.fail("ask 를 부르면 안 된다"))
    out = tools.run_ask_data({"question": question})
    assert out["status"] == "error" and out["usage"]["llm_calls"] == 0


def test_ask_data_trims_what_the_model_sees(monkeypatch):
    rows = [[i, "가" * 500] for i in range(50)]
    monkeypatch.setattr(tools, "ask", lambda q, summarize_result=True: ask_result(
        columns=["i", "title"], rows=rows, row_count=50))

    out = tools.run_ask_data({"question": "목록"})

    seen = out["for_llm"]
    assert len(seen["rows"]) == 20 and seen["row_count"] == 50 and seen["rows_shown"] == 20
    assert len(seen["rows"][0][1]) < 220 and seen["rows"][0][1].endswith("...(잘림)")
    assert len(out["for_ui"]["rows"]) == 50  # 화면은 전체 표를 그린다


@pytest.mark.parametrize("error, status", [
    ("CANNOT_ANSWER: 나이 정보가 없습니다", "refusal"),
    ("[가드레일 차단] 3회 시도 후 실패: 허용되지 않은 테이블: x", "error"),
    ("[DB 오류] 데이터베이스 접속 문제로 실행하지 못했습니다.", "error"),
    ("[LLM 오류] AuthenticationError", "error"),
])
def test_ask_data_error_status(monkeypatch, error, status):
    # 에러 문장을 안전하게 만드는 일은 ask() 가 한다 (tests/test_text2sql.py). 도구는 그대로 전달하고 상태만 정한다.
    monkeypatch.setattr(tools, "ask", lambda q, summarize_result=True: ask_result(
        sql=None, rows=[], row_count=0, error=error))
    out = tools.run_ask_data({"question": "질문"})
    assert out["status"] == status and out["for_llm"]["error"] == error


def test_ask_data_through_the_agent(monkeypatch):
    monkeypatch.setattr(tools, "ask", lambda q, summarize_result=True: ask_result(usage={"llm_calls": 2, "tokens": 900}))
    use_llm(monkeypatch, says("", call("ask_data", question="현재 휴면 팬은 몇 명?")), says("휴면 팬은 3명입니다."))

    out = run_agent("현재 휴면 팬은 몇 명이야?")  # 진짜 도구 목록 사용

    assert out["answer"] == "휴면 팬은 3명입니다." and out["steps"][0]["result"]["rows"] == [[3]]
    assert out["usage"]["llm_calls"] == 4 and out["usage"]["by_source"]["ask_data"]["llm_calls"] == 2


def test_ask_data_budget_settings():
    t = tools.TOOLS["ask_data"]
    assert t["llm_cost"] == 3 and t["max_per_question"] == 2
    assert t["spec"]["function"]["parameters"]["required"] == ["question", "reason"]


def test_answer_numbers_are_checked_against_tool_results(monkeypatch):
    monkeypatch.setattr(tools, "ask", lambda q, summarize_result=True: ask_result(rows=[[1643]]))
    use_llm(monkeypatch, says("", call("ask_data", question="활동 중인 팬 수")),
            says("활동 중인 팬은 1,643명이고, 지난달보다 120명 늘었습니다."))

    out = run_agent("현재 활동 중인 팬은 몇 명이야?")

    assert out["unverified_numbers"] == ["120"]  # 1,643 은 도구 결과에 있고, 120 은 어디에도 없다
    assert out["answer"].endswith("120명 늘었습니다.")  # 경고만 한다. 답을 고치거나 다시 묻지 않는다
    assert out["usage"]["by_source"]["agent"]["llm_calls"] == 2


# ---------- 로그 ----------
def test_log_has_calls_but_no_rows(monkeypatch):
    monkeypatch.setattr(tools, "ask", lambda q, summarize_result=True: ask_result(rows=[["SECRET_VALUE"]]))
    use_llm(monkeypatch, says("", call("ask_data", question="질문")), says("답"))

    run_agent("로그 테스트")

    files = list(agent.LOG_DIR.glob("agent_*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["question"] == "로그 테스트" and record["answer"] == "답"
    assert record["steps"][0]["tool"] == "ask_data" and record["steps"][0]["sql"] == "SELECT 1"
    assert record["steps"][0]["row_count"] == 1 and record["steps"][0]["columns"] == ["n"]
    assert record["usage"]["llm_calls"] == 3
    assert "SECRET_VALUE" not in lines[0] and "rows" not in record["steps"][0]  # 데이터 값은 남기지 않는다


def test_log_failure_does_not_break_the_answer(monkeypatch, tmp_path):
    blocker = tmp_path / "not_a_folder"
    blocker.write_text("x")
    monkeypatch.setattr(agent, "LOG_DIR", blocker)  # 폴더 자리에 파일이 있어 쓰기가 실패한다
    use_llm(monkeypatch, says("답"))
    assert run_agent("질문", tools={"echo": fake_tool()})["answer"] == "답"


def test_log_can_be_turned_off(monkeypatch):
    use_llm(monkeypatch, says("답"))
    run_agent("질문", tools={"echo": fake_tool()}, log=False)
    assert not agent.LOG_DIR.exists()


# ---------- llm.complete_with_tools ----------
class FakeOpenAI:
    def __init__(self, message):
        self.sent = []
        self.message = message
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=self.message)],
                               usage=SimpleNamespace(total_tokens=77))


def test_complete_with_tools_parses_tool_calls(monkeypatch):
    message = SimpleNamespace(content=None, tool_calls=[
        SimpleNamespace(id="c9", function=SimpleNamespace(name="ask_data", arguments='{"question": "q"}'))])
    client = FakeOpenAI(message)
    monkeypatch.setattr(llm, "_client", lambda: client)
    monkeypatch.setenv("FANLOG_MODEL", "test-model")
    specs = [tools.TOOLS["ask_data"]["spec"]]

    out = llm.complete_with_tools("sys", [{"role": "user", "content": "hi"}], specs)

    assert out == {"text": "", "tokens": 77,
                   "tool_calls": [{"id": "c9", "name": "ask_data", "arguments": '{"question": "q"}'}]}
    sent = client.sent[0]
    assert sent["tools"] == specs and sent["tool_choice"] == "auto"
    assert sent["parallel_tool_calls"] is False  # 한 단계에 도구 하나만
    assert sent["messages"][0] == {"role": "system", "content": "sys"}


def test_complete_with_tools_can_forbid_tools(monkeypatch):
    client = FakeOpenAI(SimpleNamespace(content="최종 답", tool_calls=None))
    monkeypatch.setattr(llm, "_client", lambda: client)
    monkeypatch.setenv("FANLOG_MODEL", "test-model")

    out = llm.complete_with_tools("sys", [], [tools.TOOLS["ask_data"]["spec"]], allow_tools=False)

    assert client.sent[0]["tool_choice"] == "none"
    assert out["text"] == "최종 답" and out["tool_calls"] == []


def test_complete_with_tools_needs_model_env(monkeypatch):
    monkeypatch.setattr(llm, "_client", lambda: pytest.fail("API 를 부르면 안 된다"))
    monkeypatch.delenv("FANLOG_MODEL", raising=False)
    with pytest.raises(RuntimeError):
        llm.complete_with_tools("sys", [], [])


def test_message_helpers_use_openai_format():
    reply = says("생각", {"id": "c1", "name": "ask_data", "arguments": "{}"})
    assert llm.assistant_message(reply) == {
        "role": "assistant", "content": "생각",
        "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "ask_data", "arguments": "{}"}}]}
    assert llm.tool_message("c1", "{}") == {"role": "tool", "tool_call_id": "c1", "content": "{}"}
