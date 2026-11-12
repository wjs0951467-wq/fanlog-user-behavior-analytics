"""실제 부품끼리 맞물리는 화면 테스트.

진짜 view.daily_calls 와 진짜 임시 로그 폴더로 ui/app.py 전체를 돌린다. 가짜는 에이전트 LLM, ask(), churn 계산뿐이다.
계기: 화면이 튜플 언패킹에서 터진 적이 있는데(옛 모듈이 메모리에 남은 서버), 부품을 전부 가짜로 바꾼 시험은 그것을 못 잡는다.
"""
import json
from datetime import datetime

import pytest

from app import agent, tools
from ui import render, view

from .test_agent import ask_result, call, says
from .test_tools import FakeComplete, make_report, reply
from .test_ui_app import everything, new_app, script_agent, submit


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(agent, "LOG_DIR", tmp_path / "logs")
    monkeypatch.delenv(view.DAILY_LIMIT_ENV, raising=False)
    monkeypatch.setattr(tools, "get_report", lambda: make_report())
    monkeypatch.setattr(tools, "complete", FakeComplete(reply()))


def write_log(tmp_path, good=(), broken=0):
    folder = tmp_path / "logs"
    folder.mkdir(exist_ok=True)
    lines = [json.dumps({"usage": {"llm_calls": n}}) for n in good] + ["{깨진 줄"] * broken
    (folder / f"agent_{datetime.now():%Y%m%d}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def plain(items):
    return [str(i.value).replace(chr(92), "") for i in items]


def input_disabled(at):
    return at.text_area[0].disabled


# ---------- 진짜 daily_calls 와 app.py 전체 ----------
def test_healthy_log(tmp_path):
    write_log(tmp_path, good=[4, 3])
    at = new_app()
    assert not at.exception and not input_disabled(at)
    assert any("7회 / 100회" in m.value for m in at.metric)
    assert not at.warning and not at.error


def test_missing_log_folder():
    at = new_app()
    assert not at.exception and not input_disabled(at)
    assert any("0회 / 100회" in m.value for m in at.metric)


@pytest.mark.parametrize("broken", [1, 2, 3, 4])
def test_a_few_broken_lines_warn_but_do_not_block(tmp_path, broken):
    write_log(tmp_path, good=[2], broken=broken)
    at = new_app()
    assert not at.exception and not input_disabled(at)
    assert any(f"깨진 줄 {broken}개" in w for w in plain(at.warning))
    assert any("2회 이상" in m.value for m in at.metric)


@pytest.mark.parametrize("broken", [5, 6, 20])
def test_five_or_more_broken_lines_block(tmp_path, broken):
    write_log(tmp_path, good=[2], broken=broken)
    at = new_app()
    assert not at.exception and input_disabled(at)
    assert view.BROKEN_LOG_MESSAGE in plain(at.error)


def test_log_path_that_is_a_folder_shows_the_unreadable_warning_and_does_not_block(tmp_path):
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / f"agent_{datetime.now():%Y%m%d}.jsonl").mkdir()  # 파일 자리에 폴더
    at = new_app()
    assert not at.exception and not input_disabled(at)
    assert any("확인하지 못함" in w for w in plain(at.warning))


# ---------- 결과 그리기 경로(render.py 의 언패킹 2곳)를 진짜 view 함수로 ----------
@pytest.mark.parametrize("rows,masked", [([["user_000123", 3], ["txn_000001", 4]], 1),
                                         ([["user_000123", 3], ["user_000456", 4]], 2),
                                         ([["a", 3], ["b", 4]], 0)])
def test_result_rendering_runs_with_the_real_view_functions(monkeypatch, rows, masked):
    monkeypatch.setattr(tools, "ask", lambda q, summarize_result=True: ask_result(
        columns=["id", "n"], rows=rows, row_count=2, masked_ids=masked))
    script_agent(monkeypatch, says("", call("ask_data", question="q")), says("끝"))
    at = submit(new_app())
    assert not at.exception and "끝" in everything(at)


# ---------- 반환 형태 계약: 화면이 풀어서 쓰는 곳 3군데 ----------
def test_daily_calls_always_returns_a_pair_in_every_log_state(tmp_path):
    states = {"none": lambda: None, "good": lambda: write_log(tmp_path, good=[1]),
              "broken": lambda: write_log(tmp_path, good=[1], broken=3)}
    for make in states.values():
        make()
        out = view.daily_calls(agent.LOG_DIR)
        assert isinstance(out, tuple) and len(out) == 2
        used, skipped = out
        assert (used is None or isinstance(used, int)) and isinstance(skipped, int)
    unreadable = tmp_path / "x"
    unreadable.mkdir()
    (unreadable / f"agent_{datetime.now():%Y%m%d}.jsonl").mkdir()
    assert view.daily_calls(unreadable) == (None, 0)


def test_result_table_and_drop_id_only_columns_return_the_shapes_render_unpacks():
    out = view.result_table(["id", "n"], [["user_000123", 1]])
    assert isinstance(out, tuple) and len(out) == 2 and isinstance(out[1], list)
    out2 = view.drop_id_only_columns(out[0])
    assert isinstance(out2, tuple) and len(out2) == 3 and isinstance(out2[1], list) and isinstance(out2[2], int)


# ---------- 일일 합계 읽기에서 예외가 나도 화면이 터지지 않는다 (종류별로 다른 경고) ----------
def boom(exc):
    def fake(*args, **kwargs):
        raise exc
    return fake


ENV_ERRORS = [OSError("x"), PermissionError("x"), UnicodeDecodeError("utf-8", b"\xff", 0, 1, "x")]
BUG_ERRORS = [TypeError("x"), ValueError("x"), AttributeError("x")]
BAD_RETURNS = [5, (1, 2, 3), ("a", 0), (1, "b"), None, (True, 0)]


def session_limit_still_applies(at):
    at.session_state["calls_total"] = 25
    at.run()
    assert not at.exception and input_disabled(at)
    assert any("세션 호출 한도" in e for e in plain(at.error))


@pytest.mark.parametrize("exc", ENV_ERRORS, ids=lambda e: type(e).__name__)
def test_environment_errors_show_the_unreadable_warning(monkeypatch, exc):
    monkeypatch.setattr(view, "daily_calls", boom(exc))
    at = new_app()
    assert not at.exception and not input_disabled(at)  # 확인하지 못함이면 막지 않는다
    assert any("일일 한도를 확인하지 못함" in w for w in plain(at.warning))
    assert not any("내부 오류" in e for e in plain(at.error))
    session_limit_still_applies(at)


@pytest.mark.parametrize("exc", BUG_ERRORS, ids=lambda e: type(e).__name__)
def test_bug_like_errors_show_a_separate_internal_error(monkeypatch, exc):
    monkeypatch.setattr(view, "daily_calls", boom(exc))
    at = new_app()
    assert not at.exception and not input_disabled(at)
    errors = plain(at.error)
    assert any("내부 오류: 일일 합계 계산 코드를 점검해야 합니다" in e and type(exc).__name__ in e for e in errors)
    assert not any("일일 한도를 확인하지 못함" in w for w in plain(at.warning))  # 환경 경고와 다른 경고
    session_limit_still_applies(at)


@pytest.mark.parametrize("value", BAD_RETURNS, ids=repr)
def test_a_wrong_return_shape_is_reported_as_an_internal_error(monkeypatch, value):
    monkeypatch.setattr(view, "daily_calls", lambda *a, **k: value)
    at = new_app()
    assert not at.exception and not input_disabled(at)
    assert any("내부 오류: 일일 합계 계산 코드를 점검해야 합니다" in e for e in plain(at.error))
    assert not any("일일 한도를 확인하지 못함" in w for w in plain(at.warning))
    session_limit_still_applies(at)


def test_the_two_warnings_differ_and_never_show_values_or_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(view, "daily_calls", boom(OSError(str(tmp_path / "secret_path"))))
    env_page = everything(new_app())
    monkeypatch.setattr(view, "daily_calls", boom(TypeError("secret_value_123")))
    bug_page = everything(new_app())
    assert "secret_path" not in env_page and "secret_value_123" not in bug_page and str(tmp_path) not in env_page
    assert "내부 오류" in bug_page and "내부 오류" not in env_page
    assert "일일 한도를 확인하지 못함" in env_page and "일일 한도를 확인하지 못함" not in bug_page


def test_a_normal_log_is_unchanged_by_the_guard(tmp_path):
    write_log(tmp_path, good=[2])
    at = new_app()
    assert not any("내부 오류" in e for e in plain(at.error))
    assert not any("확인하지 못함" in w for w in plain(at.warning))
