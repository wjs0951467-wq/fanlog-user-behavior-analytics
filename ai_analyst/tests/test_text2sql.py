"""ask() 파이프라인 테스트.

LLM(complete), DB(run_query), 프로파일(load_profile)을 모두 가짜로 바꾼다.
- 실제 OpenAI API 를 부르지 않는다 (공용 크레딧 보호).
- schema_profile.json 은 git 제외 파일이라, 그 파일이 없는 환경에서도 테스트가 돌아야 한다.
"""
import json

import pytest

from app import text2sql
from app.text2sql import DB_CONNECTION_ERROR, NO_ASSUMPTION_NOTE, NO_DATA_SUMMARY, ask

PROFILE = {
    "dim_user": {"kind": "table", "row_count": 10,
                 "columns": {"user_id": {"type": "text"}, "is_deleted": {"type": "boolean"}}},
    "mart_user_daily": {"kind": "view", "row_count": 100,
                        "columns": {"user_id": {"type": "text"}, "activity_status": {"type": "text"}}},
    # 프로파일에는 있지만 허용 테이블이 아닌 것
    "meta_generation_run": {"kind": "table", "row_count": 1, "columns": {"run_id": {"type": "text"}}},
}

GOOD_SQL = "SELECT COUNT(*) AS n FROM dim_user"


def answer(sql=GOOD_SQL, assumptions=("탈퇴 사용자 제외",)):
    return json.dumps({"sql": sql, "assumptions": list(assumptions)}, ensure_ascii=False)


def refusal(reason, missing):
    return json.dumps({"sql": None, "cannot_answer": reason, "missing": missing}, ensure_ascii=False)


class FakeLLM:
    """준비해 둔 응답을 순서대로 돌려준다. 예외 객체를 넣어 두면 그 차례에 예외를 던진다."""

    def __init__(self):
        self.replies = []
        self.calls = []

    def __call__(self, system, messages, json_mode=False):
        # messages 는 ask() 가 계속 덧붙이는 리스트라, 호출 시점의 모습을 복사해 둔다
        self.calls.append({"system": system, "messages": list(messages), "json_mode": json_mode})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return {"text": reply, "tokens": 100}


class FakeDB:
    """준비해 둔 결과를 순서대로 돌려준다. 예외 객체면 던진다."""

    def __init__(self):
        self.results = []
        self.queries = []

    def __call__(self, sql):
        self.queries.append(sql)
        r = self.results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class FakeDriverError(Exception):
    """psycopg 예외 흉내: PostgreSQL 오류 코드(sqlstate)를 가진다."""

    def __init__(self, message, sqlstate):
        super().__init__(message)
        self.sqlstate = sqlstate


class FakeDBError(Exception):
    """SQLAlchemy 예외 흉내: 원래 드라이버 예외를 .orig 에 담는다."""

    def __init__(self, message, sqlstate):
        super().__init__(f"(psycopg.Error) {message}\n[SQL: ...]")
        self.orig = FakeDriverError(message, sqlstate)


@pytest.fixture
def llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(text2sql, "complete", fake)
    monkeypatch.setattr(text2sql, "build_system_prompt", lambda: "SYSTEM (JSON)")
    monkeypatch.setattr(text2sql, "load_profile", lambda: PROFILE)
    return fake


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(text2sql, "run_query", fake)
    return fake


# ---------- 설계서 지정 테스트 ----------
def test_success_on_first_try(llm, db):
    llm.replies = [answer(), "가입자는 10명입니다."]
    db.results = [(["n"], [[10]])]

    out = ask("가입자 수는?")

    assert out["error"] is None
    assert out["rows"] == [[10]] and out["row_count"] == 1 and out["columns"] == ["n"]
    assert "LIMIT" in out["sql"]  # 가드레일을 거친 SQL 이 실행됐다
    assert out["assumptions"] == ["탈퇴 사용자 제외"]
    assert out["summary"] == "가입자는 10명입니다."
    assert out["attempts"] == [{"sql": GOOD_SQL, "error_type": "none", "error_message": None}]
    assert out["usage"] == {"llm_calls": 2, "tokens": 200}  # SQL 1 + 요약 1
    assert llm.calls[0]["json_mode"] is True and llm.calls[1]["json_mode"] is False


def test_fail_once_then_success(llm, db):
    llm.replies = [answer("SELECT nope FROM dim_user"), answer(), "요약"]
    db.results = [FakeDBError('column "nope" does not exist\nHINT: Perhaps you meant "user_id".', "42703"),
                  (["n"], [[10]])]

    out = ask("가입자 수는?")

    assert out["error"] is None and out["rows"] == [[10]]
    assert [a["error_type"] for a in out["attempts"]] == ["db", "none"]
    assert out["usage"]["llm_calls"] == 3


def test_all_three_attempts_fail(llm, db):
    llm.replies = [answer("DROP TABLE dim_user")] * 3

    out = ask("테이블 지워줘")

    assert out["sql"] is None and out["rows"] == []  # 실패하면 sql 은 null, 실패한 SQL 은 attempts 에만
    assert "3회 시도 후 실패" in out["error"]
    assert [a["error_type"] for a in out["attempts"]] == ["guard"] * 3
    assert db.queries == []  # 가드레일에 막힌 SQL 은 DB 에 가지 않는다
    assert out["usage"]["llm_calls"] == 3  # 요약은 부르지 않는다


def test_false_refusal_corrected(llm, db):
    llm.replies = [refusal("휴면 상태 테이블이 없습니다", ["mart_user_daily"]), answer(), "요약"]
    db.results = [(["n"], [[3]])]

    out = ask("현재 휴면 팬은 몇 명?")

    assert out["error"] is None and out["rows"] == [[3]]
    assert [a["error_type"] for a in out["attempts"]] == ["false_refusal", "none"]
    feedback = llm.calls[1]["messages"][-1]["content"]
    assert "mart_user_daily" in feedback and "activity_status" in feedback  # 존재한다는 근거(컬럼 목록)를 준다


def test_false_refusal_table_dot_column_format(llm, db):
    llm.replies = [refusal("탈퇴 여부 컬럼이 없습니다", ["dim_user.is_deleted"]), answer(), "요약"]
    db.results = [(["n"], [[10]])]

    out = ask("탈퇴자 수는?")

    assert [a["error_type"] for a in out["attempts"]] == ["false_refusal", "none"]


def test_genuine_refusal_accepted(llm, db):
    llm.replies = [refusal("나이 정보가 없습니다", ["dim_user.age", "user_profile"])]

    out = ask("팬 평균 나이는?")

    assert out["error"] == "CANNOT_ANSWER: 나이 정보가 없습니다"
    assert out["sql"] is None
    assert [a["error_type"] for a in out["attempts"]] == ["refusal"]
    assert out["usage"]["llm_calls"] == 1  # 재시도도 요약도 없다


def test_zero_rows_is_not_an_error(llm, db):
    llm.replies = [answer()]
    db.results = [(["n"], [])]

    out = ask("조건에 맞는 팬은?")

    assert out["error"] is None and out["row_count"] == 0
    assert out["summary"] == NO_DATA_SUMMARY
    assert out["usage"]["llm_calls"] == 1  # 재시도하지 않고, 요약 LLM 도 부르지 않는다


# ---------- 추가 테스트 ----------
def test_parse_fallback_to_sql_block(llm, db):
    llm.replies = [f"여기 있습니다.\n```sql\n{GOOD_SQL}\n```", "요약"]
    db.results = [(["n"], [[10]])]

    out = ask("가입자 수는?")

    assert out["error"] is None and out["rows"] == [[10]]
    assert out["assumptions"] == [NO_ASSUMPTION_NOTE]  # 가정을 못 받았다는 사실을 숨기지 않는다
    assert out["usage"]["llm_calls"] == 2  # SQL 을 건졌으므로 재시도하지 않는다


def test_no_sql_at_all_retries_as_parse(llm, db):
    llm.replies = ["죄송하지만 잘 모르겠습니다.", answer(), "요약"]
    db.results = [(["n"], [[10]])]

    out = ask("가입자 수는?")

    assert out["error"] is None
    assert [a["error_type"] for a in out["attempts"]] == ["parse", "none"]


def test_retry_message_has_previous_sql_and_error(llm, db):
    bad_sql = "SELECT nope FROM dim_user"
    llm.replies = [answer(bad_sql), answer(), "요약"]
    db.results = [FakeDBError('column "nope" does not exist\nHINT: Perhaps you meant "user_id".', "42703"),
                  (["n"], [[10]])]

    ask("가입자 수는?")

    second = llm.calls[1]["messages"]
    assert [m["role"] for m in second] == ["user", "assistant", "user"]  # 질문, 이전 응답, 에러 피드백
    assert second[0]["content"] == "가입자 수는?"
    feedback = second[-1]["content"]
    assert bad_sql in feedback
    assert 'column "nope" does not exist' in feedback
    assert "Perhaps you meant" in feedback  # HINT 줄까지 전달된다
    assert "[SQL:" not in feedback  # SQLAlchemy 가 붙이는 군더더기는 뺀다
    assert "do not repeat" in feedback


def test_connection_error_stops_immediately(llm, db):
    llm.replies = [answer()]
    db.results = [FakeDBError("connection refused", "08006")]

    out = ask("가입자 수는?")

    assert out["error"].startswith("[DB 오류]")
    assert [a["error_type"] for a in out["attempts"]] == ["db"]
    assert len(llm.calls) == 1  # 에러 원문을 모델에게 보내지 않는다


def test_db_error_without_sqlstate_stops_immediately(llm, db):
    llm.replies = [answer()]
    db.results = [RuntimeError("알 수 없는 오류")]

    out = ask("가입자 수는?")

    assert out["error"].startswith("[DB 오류]") and len(llm.calls) == 1


@pytest.mark.parametrize("exc", [
    FakeDBError('connection to server at "db.internal" (10.0.0.5), port 5432 failed for user "fanlog_ro"', "08006"),
    FakeDBError('password authentication failed for user "fanlog_ro"', "28P01"),
    RuntimeError('SQLSTATE 없음: host=db.internal user=fanlog_ro'),
])
def test_connection_error_text_is_fixed_and_leaks_nothing(llm, db, exc):
    # 접속/인증 오류의 원문(호스트, 계정 이름)은 error 에도 attempts 에도 싣지 않고 고정 문구만 남긴다
    llm.replies = [answer()]
    db.results = [exc]

    out = ask("가입자 수는?")

    assert out["error"] == DB_CONNECTION_ERROR
    assert out["attempts"][0]["error_type"] == "db" and out["attempts"][0]["error_message"] == DB_CONNECTION_ERROR
    dumped = json.dumps(out, ensure_ascii=False)
    assert "db.internal" not in dumped and "fanlog_ro" not in dumped and "10.0.0.5" not in dumped
    assert len(llm.calls) == 1  # 모델에게도 보내지 않는다


def test_retryable_db_error_text_still_goes_to_the_model_and_attempts(llm, db):
    # 반대쪽: SQL 이 틀려서 난 오류(42xxx)는 모델이 고치려면 원문이 필요하므로 그대로 둔다
    llm.replies = [answer("SELECT x FROM dim_user"), answer()]
    db.results = [FakeDBError('column "x" does not exist', "42703"), (["n"], [[1]])]

    out = ask("가입자 수는?", summarize_result=False)

    assert out["error"] is None
    assert 'column "x" does not exist' in out["attempts"][0]["error_message"]
    assert 'column "x" does not exist' in llm.calls[1]["messages"][-1]["content"]


def test_timeout_is_retried(llm, db):
    llm.replies = [answer(), answer(), "요약"]
    db.results = [FakeDBError("canceling statement due to statement timeout", "57014"), (["n"], [[10]])]

    out = ask("가입자 수는?")

    assert [a["error_type"] for a in out["attempts"]] == ["db", "none"]


def test_refusal_naming_disallowed_table_is_genuine(llm, db):
    # meta_generation_run 은 프로파일에 있지만 허용 테이블이 아니다 -> "없는 것"으로 본다
    llm.replies = [refusal("생성 이력은 조회할 수 없습니다", ["meta_generation_run"])]

    out = ask("데이터 생성 이력 보여줘")

    assert [a["error_type"] for a in out["attempts"]] == ["refusal"]
    assert len(llm.calls) == 1


def test_refusal_again_after_correction_ends(llm, db):
    llm.replies = [refusal("테이블이 없습니다", ["mart_user_daily"]),
                   refusal("그래도 답할 수 없습니다", ["mart_user_daily"])]

    out = ask("현재 휴면 팬은 몇 명?")

    assert [a["error_type"] for a in out["attempts"]] == ["false_refusal", "refusal"]
    assert out["error"] == "CANNOT_ANSWER: 그래도 답할 수 없습니다"
    assert len(llm.calls) == 2  # 거짓 거절 교정은 질문당 1회만


def test_call_cap_and_usage_sum(llm, db):
    # 최악의 경우: SQL 2회 실패 + 3번째 성공 + 요약 = 4회
    llm.replies = [answer("DROP TABLE dim_user"), "잡담", answer(), "요약"]
    db.results = [(["n"], [[10]])]

    out = ask("가입자 수는?")

    assert out["error"] is None
    assert out["usage"] == {"llm_calls": 4, "tokens": 400}
    assert len(llm.calls) == 4


def test_summary_failure_keeps_result(llm, db):
    llm.replies = [answer(), RuntimeError("rate limit")]
    db.results = [(["n"], [[10]])]

    out = ask("가입자 수는?")

    assert out["error"] is None and out["rows"] == [[10]]  # 숫자는 살린다
    assert out["summary"] is None
    assert out["usage"]["llm_calls"] == 2  # 실패한 호출도 센다


def test_summarize_can_be_turned_off(llm, db):
    llm.replies = [answer()]
    db.results = [(["n"], [[10]])]

    out = ask("가입자 수는?", summarize_result=False)

    assert out["summary"] is None and out["usage"]["llm_calls"] == 1


def test_summary_input_has_row_count_and_top_rows_only(llm, db):
    llm.replies = [answer("SELECT user_id FROM dim_user"), "요약"]
    db.results = [(["user_id"], [[f"u{i}"] for i in range(50)])]

    ask("사용자 목록")

    payload = json.loads(llm.calls[1]["messages"][0]["content"])
    assert payload["row_count"] == 50 and len(payload["rows"]) == 20
    assert payload["assumptions"] == ["탈퇴 사용자 제외"]


def test_llm_api_error_is_not_retried(llm, db):
    llm.replies = [RuntimeError("invalid api key")]

    out = ask("가입자 수는?")

    assert out["error"].startswith("[LLM 오류]")
    assert out["usage"]["llm_calls"] == 1 and out["attempts"] == []


@pytest.mark.parametrize("exc, expected", [
    (RuntimeError("Incorrect API key provided: sk-abc***xyz"), "[LLM 오류] RuntimeError"),
    (KeyError("secret-detail"), "[LLM 오류] KeyError"),
])
def test_llm_error_shows_only_the_exception_type_name(llm, db, exc, expected):
    # OpenAI 인증 오류 메시지에는 API 키 일부가 들어 있을 수 있어, 메시지 대신 종류 이름만 알린다
    llm.replies = [exc]

    out = ask("가입자 수는?")

    assert out["error"] == expected
    assert "sk-" not in json.dumps(out, ensure_ascii=False) and "secret-detail" not in json.dumps(out, ensure_ascii=False)


def test_real_system_rules_mention_json():
    # OpenAI json_object 모드의 필수 조건: 프롬프트에 "JSON" 이 있어야 한다
    assert "JSON" in text2sql.SYSTEM_RULES


# ---------- 행 수 상한에서 잘린 결과 ----------
def test_truncated_flag_is_false_for_a_normal_result(llm, db):
    llm.replies = [json.dumps({"sql": "SELECT COUNT(*) AS n FROM dim_user", "assumptions": ["a"]}), "요약"]
    db.results = [(["n"], [[10]])]  # 가짜 DB 는 그냥 list 를 돌려준다 (예전 형태 그대로)
    assert text2sql.ask("q")["truncated"] is False


def test_truncated_flag_is_carried_from_run_query(llm, db):
    from app.db import Rows
    rows = Rows([[1], [2]])
    rows.truncated = True
    llm.replies = [json.dumps({"sql": "SELECT user_id FROM dim_user", "assumptions": ["a"]}), "요약"]
    db.results = [(["user_id"], rows)]
    out = text2sql.ask("q")
    assert out["truncated"] is True and out["row_count"] == 2 and out["error"] is None


def test_guard_error_text_reaches_the_retry_prompt_with_the_function_name(llm, db):
    """막힌 함수 이름이 재시도 프롬프트와 attempts 에 그대로 남아야 모델이 고칠 수 있다."""
    llm.replies = [json.dumps({"sql": "SELECT query_to_xml('select 1', true, false, '')", "assumptions": []}),
                   json.dumps({"sql": "SELECT COUNT(*) AS n FROM dim_user", "assumptions": ["a"]}), "요약"]
    db.results = [(["n"], [[10]])]
    out = text2sql.ask("q")
    assert out["error"] is None and len(db.queries) == 1  # 막힌 SQL 은 DB 에 가지 않았다
    assert out["attempts"][0]["error_type"] == "guard"
    assert "허용되지 않는 함수: query_to_xml" in out["attempts"][0]["error_message"]
    retry_prompt = llm.calls[1]["messages"][-1]["content"]
    assert "허용되지 않는 함수: query_to_xml" in retry_prompt


def test_guard_error_after_all_retries_keeps_the_function_name_in_the_final_error(llm, db):
    bad = json.dumps({"sql": "SELECT some_unknown_function(1)", "assumptions": []})
    llm.replies = [bad, bad, bad]
    out = text2sql.ask("q")
    assert db.queries == [] and "허용되지 않는 함수: some_unknown_function" in out["error"]
