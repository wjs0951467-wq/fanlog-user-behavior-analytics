"""/ask 엔드포인트와 CLI 테스트. 서버를 띄우지 않고 함수를 직접 부른다 (LLM 과 DB 는 가짜)."""
import json

import pytest
from pydantic import ValidationError

from app import agent, main, text2sql
from app.main import AskRequest, ask_endpoint
from ui import view


@pytest.fixture(autouse=True)
def isolated_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "LOG_DIR", tmp_path / "logs")  # 진짜 logs/ 에 쓰지 않는다
    monkeypatch.delenv(view.DAILY_LIMIT_ENV, raising=False)


def fake_ask_result(question="q", llm_calls=3, **over):
    out = {"question": question, "sql": "SELECT 1", "columns": ["n"], "rows": [[1]], "row_count": 1,
           "assumptions": [], "summary": "요약", "attempts": [], "error": None, "truncated": False,
           "masked_ids": 0, "row_cap_note": None, "usage": {"llm_calls": llm_calls, "tokens": 300}}
    out.update(over)
    return out


# ---------- 입력 검증 ----------
@pytest.mark.parametrize("bad", ["", "   ", " " + chr(10) + chr(9) + " ", "가" * 501, None, 123, ["q"]])
def test_bad_questions_are_rejected_before_any_llm_call(monkeypatch, bad):
    monkeypatch.setattr(main, "ask", lambda q: pytest.fail("ask 를 부르면 안 된다"))
    with pytest.raises(ValidationError):
        AskRequest(question=bad)


def test_good_questions_are_accepted_and_stripped():
    assert AskRequest(question="  가입자 수는?  ").question == "가입자 수는?"
    assert len(AskRequest(question="가" * 500).question) == 500  # 500자는 된다
    assert AskRequest.model_json_schema()["properties"]["question"]["maxLength"] == 500


# ---------- /ask 호출 수를 같은 일일 합계에 남긴다 ----------
def test_ask_endpoint_returns_the_result_and_logs_usage_for_the_daily_total(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "ask", lambda q: fake_ask_result(q, llm_calls=3))

    out = ask_endpoint(AskRequest(question="가입자 수는?"))

    assert out["summary"] == "요약"
    assert view.daily_calls(tmp_path / "logs") == (3, 0)  # 화면의 일일 합계가 이 호출을 센다
    record = json.loads(next((tmp_path / "logs").glob("agent_*.jsonl")).read_text(encoding="utf-8").splitlines()[0])
    assert record["source"] == "ask" and record["question"] == "가입자 수는?" and record["usage"]["llm_calls"] == 3


def test_two_calls_add_up(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "ask", lambda q: fake_ask_result(q, llm_calls=2))
    ask_endpoint(AskRequest(question="a"))
    ask_endpoint(AskRequest(question="b"))
    assert view.daily_calls(tmp_path / "logs") == (4, 0)


def test_ask_log_masks_ids_and_keeps_no_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "ask", lambda q: fake_ask_result(q, summary="user_000123 님", rows=[["[ID]"]]))
    ask_endpoint(AskRequest(question="user_000123 은?"))
    text = next((tmp_path / "logs").glob("agent_*.jsonl")).read_text(encoding="utf-8")
    assert "user_000123" not in text and '"rows"' not in text


def test_a_log_failure_does_not_break_the_response(monkeypatch, tmp_path):
    blocker = tmp_path / "not_a_folder"
    blocker.write_text("파일", encoding="utf-8")
    monkeypatch.setattr(agent, "LOG_DIR", blocker / "logs")  # 폴더를 만들 수 없다
    monkeypatch.setattr(main, "ask", lambda q: fake_ask_result(q))
    assert ask_endpoint(AskRequest(question="q"))["summary"] == "요약"


def test_error_result_is_logged_too(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "ask", lambda q: fake_ask_result(q, llm_calls=1, sql=None, summary=None, error="[LLM 오류] RuntimeError"))
    ask_endpoint(AskRequest(question="q"))
    assert view.daily_calls(tmp_path / "logs") == (1, 0)


# ---------- CLI ----------
def test_cli_logs_to_the_same_daily_total_and_prints(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(text2sql, "ask", lambda q: fake_ask_result(q, llm_calls=2))
    text2sql.cli_main(["가입자", "수는?"])
    printed = capsys.readouterr().out
    assert "SQL:" in printed and "사용량" in printed
    assert view.daily_calls(tmp_path / "logs") == (2, 0)
    record = json.loads(next((tmp_path / "logs").glob("agent_*.jsonl")).read_text(encoding="utf-8").splitlines()[0])
    assert record["source"] == "cli" and record["question"] == "가입자 수는?"


def test_cli_still_works_when_the_log_cannot_be_written(monkeypatch, tmp_path, capsys):
    blocker = tmp_path / "not_a_folder"
    blocker.write_text("파일", encoding="utf-8")
    monkeypatch.setattr(agent, "LOG_DIR", blocker / "logs")
    monkeypatch.setattr(text2sql, "ask", lambda q: fake_ask_result(q))
    text2sql.cli_main(["q"])
    assert "요약" in capsys.readouterr().out
