"""시간 제한 테스트: DB 연결 시간 제한, 질문 전체 마감, 연결 실패의 고정 문구.

사건: Docker(DB 컨테이너)가 꺼진 채로 질문을 제출했더니 질문이 3분 넘게 끝나지 않았고 서버가 Ctrl+C 로도 꺼지지 않았다.
실제 OpenAI 호출 0회, DB 접속 0회 (가짜 엔진, 가짜 시계, 가짜 LLM).
"""
import json

import pytest
from sqlalchemy.exc import InterfaceError, OperationalError, ProgrammingError

from app import agent, db, deadline, llm, text2sql, tools
from app.agent import run_agent
from app.text2sql import DB_CONNECTION_ERROR, ask

from .test_agent import call, fake_tool, says
from .test_text2sql import FakeDB, FakeDBError, FakeLLM, PROFILE, answer
from .test_tools import SEG, report, use_complete  # noqa: F401  (report 는 fixture)

SECRET = "host=db.internal.example port=5432 user=fanlog_ro password=hunter2"


class Clock:
    """가짜 시계. 실제로 기다리지 않고 시간을 앞으로 보낸다."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(deadline, "_now", c)
    return c


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "LOG_DIR", tmp_path / "logs")  # 진짜 logs/ 에 쓰지 않는다
    monkeypatch.setattr(text2sql, "build_system_prompt", lambda: "SYSTEM (JSON)")
    monkeypatch.setattr(text2sql, "load_profile", lambda: PROFILE)


def scripted_llm(monkeypatch, clock, *steps):
    """에이전트의 LLM 을 (응답, 이 호출이 흘려보내는 시간(초)) 순서대로 흉내 낸다. 호출 시각을 기록한다."""
    queue, seen = list(steps), []

    def fake(system, messages, specs, allow_tools=True):
        seen.append(clock.t)
        reply, spend = queue.pop(0)
        clock.advance(spend)
        return reply

    monkeypatch.setattr(agent, "complete_with_tools", fake)
    return seen


def slow_tool(clock, seconds, name="echo"):
    tool = fake_tool(name)
    plain = tool["run"]

    def run(args):
        clock.advance(seconds)
        return plain(args)

    tool["run"] = run
    return tool


# ---------- 값 ----------
def test_the_limits_and_their_order():
    assert db.CONNECT_TIMEOUT_SECONDS == 5
    assert deadline.QUESTION_DEADLINE_SECONDS == 120
    # 마감 뒤에 시작되는 호출은 없고, 마감 전에 시작된 호출은 호출당 제한 안에 끝난다 -> 최악의 종료 = 마감 + 호출 제한
    assert llm.CLIENT_TIMEOUT_SECONDS < deadline.QUESTION_DEADLINE_SECONDS
    assert str(deadline.QUESTION_DEADLINE_SECONDS) in deadline.TIMEOUT_ERROR and deadline.TIMEOUT_ERROR.startswith("[시간 초과]")


def test_get_engine_passes_connect_timeout_and_keeps_the_other_options(monkeypatch):
    seen = {}
    monkeypatch.setenv("DATABASE_URL_RO", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setattr(db, "create_engine", lambda url, **kwargs: seen.update(url=url, **kwargs) or object())
    db.get_engine.cache_clear()
    try:
        db.get_engine()
    finally:
        db.get_engine.cache_clear()
    connect_args = seen["connect_args"]
    assert connect_args["connect_timeout"] == 5
    assert "default_transaction_read_only=on" in connect_args["options"] and "statement_timeout=5000" in connect_args["options"]
    assert seen["pool_pre_ping"] is True


# ---------- 마감 모듈 ----------
def test_no_deadline_set_means_never_expired(clock):
    assert deadline.expired() is False
    clock.advance(10_000)
    assert deadline.expired() is False


def test_deadline_expires_exactly_at_the_limit(clock):
    token = deadline.start()
    try:
        clock.advance(119.9)
        assert deadline.expired() is False
        clock.advance(0.1)
        assert deadline.expired() is True
    finally:
        deadline.clear(token)
    assert deadline.expired() is False


def test_start_accepts_a_custom_length_and_clear_restores_the_previous_one(clock):
    outer = deadline.start(10)
    inner = deadline.start(1000)
    clock.advance(50)
    assert deadline.expired() is False
    deadline.clear(inner)
    assert deadline.expired() is True  # 바깥 마감(10초)으로 돌아왔다
    deadline.clear(outer)


# ---------- 에이전트 루프 ----------
def test_normal_run_is_unaffected_and_the_deadline_is_cleared(monkeypatch, clock):
    seen = scripted_llm(monkeypatch, clock, (says("", call("echo")), 5), (says("끝났습니다."), 5))
    tool = slow_tool(clock, 3)
    out = run_agent("질문", tools={"echo": tool})
    assert out["answer"] == "끝났습니다." and out["error"] is None
    assert len(seen) == 2 and len(tool["ran"]) == 1 and out["usage"]["llm_calls"] == 2
    assert deadline.expired() is False and deadline._deadline.get() is None


def test_no_tool_runs_when_the_deadline_passed_during_the_llm_call(monkeypatch, clock):
    seen = scripted_llm(monkeypatch, clock, (says("", call("echo")), 121))
    tool = slow_tool(clock, 0)
    out = run_agent("질문", tools={"echo": tool})
    assert out["error"] == deadline.TIMEOUT_ERROR and out["answer"] is None
    assert tool["ran"] == [] and len(seen) == 1 and out["steps"] == []
    assert out["usage"]["llm_calls"] == 1


def test_no_new_llm_call_starts_after_a_tool_pushed_past_the_deadline(monkeypatch, clock):
    seen = scripted_llm(monkeypatch, clock, (says("", call("echo")), 10), (says("두 번째"), 10))
    tool = slow_tool(clock, 115)  # 10 + 115 = 125초: 마감(120초) 뒤
    out = run_agent("질문", tools={"echo": tool})
    assert out["error"] == deadline.TIMEOUT_ERROR and out["answer"] is None
    assert len(seen) == 1 and len(out["steps"]) == 1 and out["usage"]["llm_calls"] == 1  # 두 번째 LLM 호출은 시작되지 않았다


def test_an_answer_that_arrives_after_the_deadline_is_kept(monkeypatch, clock):
    """이미 시작된 호출은 끊을 수 없다. 최종 답이 마감 뒤에 도착해도 버리지 않는다 (새 호출은 필요 없다)."""
    scripted_llm(monkeypatch, clock, (says("마감 직후 도착한 답"), 130))
    out = run_agent("질문", tools={"echo": fake_tool()})
    assert out["answer"] == "마감 직후 도착한 답" and out["error"] is None


def test_each_question_gets_its_own_fresh_deadline(monkeypatch, clock):
    scripted_llm(monkeypatch, clock, (says("첫째"), 100), (says("둘째"), 100))
    first = run_agent("질문 1", tools={"echo": fake_tool()})
    second = run_agent("질문 2", tools={"echo": fake_tool()})  # 첫 질문이 100초를 썼어도 둘째는 새로 시작한다
    assert first["answer"] == "첫째" and second["answer"] == "둘째" and second["error"] is None


def test_the_deadline_is_cleared_even_when_the_run_is_interrupted(monkeypatch, clock):
    def interrupted(system, messages, specs, allow_tools=True):
        raise KeyboardInterrupt()

    monkeypatch.setattr(agent, "complete_with_tools", interrupted)
    with pytest.raises(KeyboardInterrupt):
        run_agent("질문", tools={"echo": fake_tool()})
    assert deadline._deadline.get() is None
    clock.advance(10_000)
    assert deadline.expired() is False  # 중단된 질문의 마감이 다음 질문에 남지 않았다


def test_the_timeout_is_reported_in_the_log_and_the_budget_is_counted(monkeypatch, clock):
    scripted_llm(monkeypatch, clock, (says("", call("echo")), 121))
    out = run_agent("질문", tools={"echo": fake_tool()})
    assert agent.build_log_record(out)["error"] == deadline.TIMEOUT_ERROR
    logged = "".join(p.read_text(encoding="utf-8") for p in agent.LOG_DIR.glob("agent_*.jsonl"))
    assert deadline.TIMEOUT_ERROR in logged and json.loads(logged.splitlines()[0])["usage"]["llm_calls"] == 1


# ---------- ask() ----------
@pytest.fixture
def llm_and_db(monkeypatch):
    fake_llm, fake_db = FakeLLM(), FakeDB()
    monkeypatch.setattr(text2sql, "complete", fake_llm)
    monkeypatch.setattr(text2sql, "run_query", fake_db)
    return fake_llm, fake_db


def test_ask_without_a_deadline_is_unchanged(llm_and_db, clock):
    fake_llm, fake_db = llm_and_db
    fake_llm.replies, fake_db.results = [answer(), "요약"], [(["n"], [[10]])]
    clock.advance(100_000)  # 마감이 걸리지 않은 호출(/ask, CLI, 평가)은 시간이 얼마가 흘러도 그대로다
    out = ask("가입자 수는?")
    assert out["error"] is None and out["summary"] == "요약" and out["usage"]["llm_calls"] == 2


def test_ask_does_not_start_when_the_deadline_has_passed(llm_and_db, clock):
    fake_llm, _ = llm_and_db
    token = deadline.start(1)
    try:
        clock.advance(5)
        out = ask("가입자 수는?")
    finally:
        deadline.clear(token)
    assert out["error"] == deadline.TIMEOUT_ERROR and out["usage"]["llm_calls"] == 0 and fake_llm.calls == []


def test_ask_does_not_retry_after_the_deadline_passed(llm_and_db, clock):
    fake_llm, fake_db = llm_and_db
    blocked = json.dumps({"sql": "SELECT * FROM secret_table", "assumptions": []})  # 가드레일에 막힌다 -> 재시도 대상
    fake_llm.replies = [blocked, answer()]
    original = fake_llm.__call__

    def slow(system, messages, json_mode=False):
        clock.advance(130)  # 첫 호출이 마감을 넘겼다
        return original(system, messages, json_mode)

    text2sql.complete = slow  # llm_and_db 가 monkeypatch 로 바꿔 둔 자리라 테스트 뒤에 원복된다
    token = deadline.start()
    try:
        out = ask("가입자 수는?")
    finally:
        deadline.clear(token)
    assert out["error"] == deadline.TIMEOUT_ERROR and out["usage"]["llm_calls"] == 1
    assert len(fake_llm.calls) == 1 and len(fake_llm.replies) == 1  # 두 번째 SQL 호출은 시작되지 않았다
    assert fake_db.queries == [] and [a["error_type"] for a in out["attempts"]] == ["guard"]


def test_ask_skips_the_summary_call_after_the_deadline(llm_and_db, clock):
    fake_llm, fake_db = llm_and_db
    fake_llm.replies, fake_db.results = [answer(), "요약"], [(["n"], [[10]])]
    original = fake_llm.__call__

    def slow(system, messages, json_mode=False):
        clock.advance(130)
        return original(system, messages, json_mode)

    text2sql.complete = slow
    token = deadline.start()
    try:
        out = ask("가입자 수는?")
    finally:
        deadline.clear(token)
    assert out["error"] is None and out["rows"] == [[10]] and out["summary"] is None  # 숫자는 살리고 요약만 건너뛴다
    assert out["usage"]["llm_calls"] == 1 and len(fake_llm.calls) == 1


def test_recommend_actions_does_not_call_the_llm_after_the_deadline(report, monkeypatch, clock):
    fake = use_complete(monkeypatch, "{}")
    token = deadline.start(1)
    try:
        clock.advance(5)
        out = tools.run_recommend_actions(SEG)
    finally:
        deadline.clear(token)
    assert out["status"] == "error" and out["for_llm"]["error"] == deadline.TIMEOUT_ERROR
    assert fake.calls == [] and out["usage"]["llm_calls"] == 0


# ---------- 연결 시간 초과: 고정 문구, 원문은 숨김 ----------
def test_a_connection_timeout_shows_only_the_fixed_text(llm_and_db):
    fake_llm, fake_db = llm_and_db
    fake_llm.replies = [answer()]
    fake_db.results = [FakeDBError(f"connection timeout expired {SECRET}", None)]  # SQLSTATE 없음: 연결 단계 실패
    out = ask("가입자 수는?")
    assert out["error"] == DB_CONNECTION_ERROR and out["usage"]["llm_calls"] == 1 and len(fake_llm.calls) == 1  # 재시도 없음
    text = json.dumps(out, ensure_ascii=False, default=str)
    assert "hunter2" not in text and "db.internal" not in text and "fanlog_ro" not in text
    assert out["attempts"][-1]["error_message"] == DB_CONNECTION_ERROR
    assert "hunter2" not in json.dumps(fake_llm.calls, ensure_ascii=False)  # 모델에게도 가지 않았다


# ---------- DB 를 쓰는 도구의 연결 실패도 같은 고정 문구 ----------
def db_error(cls, sqlstate, message=f"connection failed {SECRET}"):
    class Driver(Exception):
        pass

    orig = Driver(message)
    orig.sqlstate = sqlstate
    return cls("SELECT 1", {}, orig)


CONNECTION_ERRORS = [
    ("연결 시간 초과(SQLSTATE 없음)", db_error(OperationalError, None)),
    ("연결 거부(SQLSTATE 없음)", db_error(OperationalError, None, "connection refused")),
    ("서버 연결 끊김 08006", db_error(OperationalError, "08006")),
    ("인증 실패 28P01", db_error(OperationalError, "28P01")),
    ("InterfaceError", db_error(InterfaceError, None)),
]
OTHER_DB_ERRORS = [
    ("문 시간 제한 57014", db_error(OperationalError, "57014")),
    ("없는 컬럼 42703", db_error(ProgrammingError, "42703")),
    ("데이터 오류 22012", db_error(OperationalError, "22012")),
]


@pytest.mark.parametrize("label, exc", CONNECTION_ERRORS, ids=[c[0] for c in CONNECTION_ERRORS])
def test_is_db_connection_error_recognises_connection_problems(label, exc):
    assert text2sql.is_db_connection_error(exc) is True


@pytest.mark.parametrize("label, exc", OTHER_DB_ERRORS, ids=[c[0] for c in OTHER_DB_ERRORS])
def test_is_db_connection_error_ignores_query_errors(label, exc):
    assert text2sql.is_db_connection_error(exc) is False


@pytest.mark.parametrize("exc", [RuntimeError(SECRET), ValueError("x"), KeyError("DATABASE_URL_RO"), TimeoutError()])
def test_is_db_connection_error_is_false_for_non_database_exceptions(exc):
    assert text2sql.is_db_connection_error(exc) is False


def run_failing_tool(monkeypatch, exc, llm_cost=0):
    tool = fake_tool("get_churn_segments", llm_cost=llm_cost)

    def run(args):
        raise exc

    tool["run"] = run
    fake = []

    def llm_stub(system, messages, specs, allow_tools=True):
        fake.append(messages)
        return says("", call("get_churn_segments")) if len(fake) == 1 else says("도구가 실패했습니다.")

    monkeypatch.setattr(agent, "complete_with_tools", llm_stub)
    out = run_agent("질문", tools={"get_churn_segments": tool})
    return out, fake


@pytest.mark.parametrize("label, exc", CONNECTION_ERRORS, ids=[c[0] for c in CONNECTION_ERRORS])
def test_a_db_tool_with_a_connection_failure_shows_the_fixed_text_and_leaks_nothing(monkeypatch, label, exc):
    out, sent = run_failing_tool(monkeypatch, exc)
    step = out["steps"][0]
    assert step["status"] == "error" and step["result"]["error"] == DB_CONNECTION_ERROR
    everything = json.dumps({"out": out, "sent_to_model": sent}, ensure_ascii=False, default=str)
    for secret in ("hunter2", "db.internal", "fanlog_ro", "connection failed", "OperationalError", "InterfaceError"):
        assert secret not in everything, secret
    assert DB_CONNECTION_ERROR in json.dumps(sent, ensure_ascii=False)  # 모델에게도 같은 고정 문구가 간다
    logged = "".join(p.read_text(encoding="utf-8") for p in agent.LOG_DIR.glob("agent_*.jsonl"))
    assert "hunter2" not in logged and "db.internal" not in logged and DB_CONNECTION_ERROR in logged


@pytest.mark.parametrize("label, exc", OTHER_DB_ERRORS, ids=[c[0] for c in OTHER_DB_ERRORS])
def test_a_db_tool_with_a_query_error_still_shows_only_the_type_name(monkeypatch, label, exc):
    out, sent = run_failing_tool(monkeypatch, exc)
    message = out["steps"][0]["result"]["error"]
    assert message == f"도구 실행 중 오류가 났습니다 ({type(exc).__name__})." and DB_CONNECTION_ERROR not in message
    assert "hunter2" not in json.dumps({"out": out, "sent": sent}, ensure_ascii=False, default=str)


def test_other_exceptions_in_a_tool_are_unchanged(monkeypatch):
    out, _ = run_failing_tool(monkeypatch, RuntimeError(SECRET))
    assert out["steps"][0]["result"]["error"] == "도구 실행 중 오류가 났습니다 (RuntimeError)."


def test_a_connection_failure_in_a_tool_is_still_counted_at_the_tool_cost(monkeypatch):
    """연결 실패여도 예산과 일일 합계 집계 규칙은 그대로다 (실제보다 많이 셀 수는 있어도 적게 세지 않는다)."""
    out, _ = run_failing_tool(monkeypatch, CONNECTION_ERRORS[0][1], llm_cost=2)
    assert out["steps"][0]["llm_calls"] == 2 and out["usage"]["by_source"]["get_churn_segments"]["llm_calls"] == 2
