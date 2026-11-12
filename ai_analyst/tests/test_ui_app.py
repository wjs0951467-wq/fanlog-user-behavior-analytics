"""화면(ui/app.py) 스모크 테스트: Streamlit 의 AppTest 로 브라우저 없이 화면을 돌린다.

가짜로 바꾸는 것: 에이전트의 LLM(agent.complete_with_tools), 액션 LLM(tools.complete), ask()(DB 와 SQL 생성), churn 계산(get_report).
진짜로 도는 것: ui/app.py, ui/render.py, agent.run_agent(루프, 예산, 숫자 점검), 도구 3개의 코드.
실제 OpenAI 호출 0회, DB 접속 0회.
"""
import json
import re
from datetime import datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app import actions, agent, tools
from ui import view

from .test_actions import draft
from .test_agent import ask_result, call, says
from .test_tools import FakeComplete, make_report, reply

APP_FILE = str(Path(__file__).resolve().parent.parent / "ui" / "app.py")
SEG_ARGS = {"tier": "상위 10%군", "purchase": "있음"}  # 가짜 report 에서 300명 (표본 수 판정은 "검증할 수 없다")


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(agent, "LOG_DIR", tmp_path / "logs")  # 진짜 logs/ 에 쓰지 않고, 진짜 일일 합계도 읽지 않는다
    monkeypatch.delenv(view.DAILY_LIMIT_ENV, raising=False)  # 사용자의 환경 설정이 시험 결과를 바꾸지 않게 한다
    monkeypatch.setattr(tools, "get_report", lambda: make_report())
    monkeypatch.setattr(tools, "complete", FakeComplete(reply()))


def script_agent(monkeypatch, *replies):
    """에이전트의 LLM 이 준비한 응답을 순서대로 하도록 바꾸고, 호출 횟수를 셀 리스트를 돌려준다."""
    calls, queue = [], iter(replies)

    def fake(system, messages, specs, allow_tools=True):
        calls.append(allow_tools)
        item = next(queue)
        if isinstance(item, Exception):  # 예외 객체를 넣어 두면 그 차례에 던진다 (API 오류 흉내)
            raise item
        return item

    monkeypatch.setattr(agent, "complete_with_tools", fake)
    return calls


def new_app():
    return AppTest.from_file(APP_FILE, default_timeout=30).run()


def submit(at, question="질문입니다"):
    at.text_area[0].set_value(question)
    return at.button[0].click().run()


def everything(at) -> str:
    """화면에 그려진 모든 글과 표 값을 한 덩어리로 모은다 (무엇이 화면에 있는지 / 없는지 확인용)."""
    parts = []
    # 마크다운을 해석하는 자리(제목, 알림, 캡션)의 글은 화면 코드가 이스케이프해서 넣으므로, 비교하기 쉽게 역슬래시를 푼다
    for kind in ("markdown", "warning", "error", "info", "success", "caption"):
        parts += [re.sub(r"\\(.)", r"\1", str(e.value)) for e in getattr(at, kind)]
    for kind in ("text", "code", "title"):
        parts += [str(e.value) for e in getattr(at, kind)]
    parts += [df.value.to_csv() for df in at.dataframe]
    parts += [e.label for e in at.expander]
    parts += [m.value for m in at.metric]
    return "\n".join(parts)


def esc(text):
    return view.escape_markdown(text)


# ---------- 첫 화면 ----------
def test_first_screen_renders_without_calling_the_agent(monkeypatch):
    calls = script_agent(monkeypatch, says("호출되면 안 된다"))
    at = new_app()

    assert not at.exception
    assert at.title[0].value == "FANLOG AI 분석가"
    assert at.text_area[0].max_chars == 500 and at.button[0].label == "제출"
    assert [m.value for m in at.metric] == ["-", "0회", "30회", "0회 / 100회"]  # 이번 질문 / 세션 누적 / 세션 한도 / 오늘 전체와 일일 한도
    assert not at.warning and "--server.address localhost" in everything(at)  # 외부에 열지 않는다는 안내
    assert not at.text_area[0].disabled and not at.button[0].disabled
    assert calls == []  # 화면을 그리는 것만으로는 LLM 을 부르지 않는다


def test_typing_without_submit_never_calls_the_agent(monkeypatch):
    calls = script_agent(monkeypatch, says("호출되면 안 된다"))
    at = new_app()
    at.text_area[0].set_value("입력만 하고 제출은 안 함").run()
    assert not at.exception and calls == []


# ---------- 제출 ----------
def test_submit_runs_the_agent_once_and_keeps_the_result_in_session_state(monkeypatch):
    monkeypatch.setattr(tools, "ask", lambda q, summarize_result=True: ask_result(
        columns=["status", "n"], rows=[["dormant", 1643]], row_count=1,
        usage={"llm_calls": 1, "tokens": 500}))
    calls = script_agent(monkeypatch, says("", call("ask_data", question="휴면 팬은 몇 명?", reason="휴면 수가 필요해서")),
                         says("휴면 팬은 1,643명이고 지난달보다 120명 늘었습니다."))
    at = new_app()

    submit(at, "현재 휴면 팬은 몇 명이야?")

    assert not at.exception and len(calls) == 2  # 에이전트 2회 (도구 호출 1 + 최종 답 1)
    assert at.session_state["calls_total"] == 3  # 에이전트 2회 + ask 내부 1회
    assert [m.value for m in at.metric] == ["3회", "3회", "30회", "3회 / 100회"]  # 끝난 질문은 로그를 거쳐 일일 합계에 들어간다
    assert at.session_state["result"]["question"] == "현재 휴면 팬은 몇 명이야?"
    assert "휴면 팬은 1,643명이고" in "".join(t.value for t in at.text)

    # 표는 모델의 문장이 아니라 도구 결과에서 그려진다
    table = at.dataframe[0].value
    assert table.iloc[0].tolist() == ["dormant", 1643]
    # 120 은 도구 결과에 없는 숫자라 경고가 뜬다 (경고 전용: 답은 그대로다)
    assert any("120" in w.value for w in at.warning)

    labels = [e.label for e in at.expander]
    assert labels == ["SQL 보기", "계산 가정(assumptions) 보기", "도구 호출 기록(reason 포함) 보기"]
    page = everything(at)
    assert "SELECT 1" in page and "탈퇴 사용자 제외" in page and "휴면 수가 필요해서" in page  # SQL, 가정, reason


def test_rerun_after_a_result_does_not_call_the_agent_again(monkeypatch):
    monkeypatch.setattr(tools, "ask", lambda q, summarize_result=True: ask_result())
    calls = script_agent(monkeypatch, says("", call("ask_data", question="q")), says("답입니다."))
    at = new_app()
    submit(at)
    before = len(calls)

    at.run()  # 위젯 변화나 새로고침 같은 재실행

    assert len(calls) == before and at.session_state["calls_total"] == 3
    assert "답입니다." in "".join(t.value for t in at.text)  # session_state 의 결과를 다시 그린다


@pytest.mark.parametrize("question", ["", "   \n  "])
def test_empty_question_makes_no_call(monkeypatch, question):
    calls = script_agent(monkeypatch, says("호출되면 안 된다"))
    at = submit(new_app(), question)
    assert calls == [] and at.warning and "질문을 입력" in at.warning[0].value
    assert at.session_state["calls_total"] == 0 and at.session_state["result"] is None


# ---------- 세션 한도 ----------
def session_app(total):
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.session_state["calls_total"] = total
    return at.run()


@pytest.mark.parametrize("total", [21, 29, 30, 39])
def test_input_is_blocked_when_the_remaining_session_limit_is_under_one_question(monkeypatch, total):
    calls = script_agent(monkeypatch, says("호출되면 안 된다"))
    at = session_app(total)

    assert at.text_area[0].disabled and at.button[0].disabled
    assert any("한도" in e.value and "10회" in e.value for e in at.error) and calls == []


@pytest.mark.parametrize("total", [0, 19, 20])
def test_input_is_open_while_one_whole_question_still_fits(monkeypatch, total):
    script_agent(monkeypatch, says("호출되면 안 된다"))
    at = session_app(total)  # 20회 사용: 남은 10회로 질문 하나가 끝까지 돌 수 있다
    assert not at.text_area[0].disabled and not at.button[0].disabled and not at.error


def test_a_blocked_widget_cannot_be_used_at_all(monkeypatch):
    calls = script_agent(monkeypatch, says("호출되면 안 된다"))
    at = session_app(25)
    with pytest.raises(Exception, match="disabled"):  # AppTest 도 브라우저처럼 비활성 위젯을 못 건드린다
        at.text_area[0].set_value("막혔는데 입력")
    with pytest.raises(Exception, match="disabled"):
        at.button[0].click()
    assert calls == [] and at.session_state["result"] is None


def test_a_question_that_leaves_less_than_one_question_blocks_the_next_one(monkeypatch):
    monkeypatch.setattr(tools, "ask", lambda q, summarize_result=True: ask_result())
    script_agent(monkeypatch, says("", call("ask_data", question="q")), says("답"))
    at = session_app(18)  # 이 질문이 3회를 쓰면 21회: 남은 9회라 다음 질문은 막는다
    assert not at.button[0].disabled

    submit(at)

    assert at.session_state["calls_total"] == 21
    assert at.text_area[0].disabled and at.button[0].disabled  # 제출이 끝난 화면에서 바로 막힌다
    assert any("한도" in e.value for e in at.error)


# ---------- 일일 상한 (logs/ 의 당일 합계) ----------
def write_today_log(*call_counts):
    folder = agent.LOG_DIR
    folder.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"question": "q", "usage": {"llm_calls": n, "tokens": 1}}) for n in call_counts]
    (folder / f"agent_{datetime.now():%Y%m%d}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.mark.parametrize("used, blocked", [(0, False), (90, False), (91, True), (100, True)])
def test_daily_boundary_is_the_same_rule_as_the_session_limit(monkeypatch, used, blocked):
    calls = script_agent(monkeypatch, says("호출되면 안 된다"))
    write_today_log(used - 40, 40) if used >= 40 else write_today_log(used)
    at = new_app()  # 이 세션은 한 번도 쓰지 않았다 (새로고침으로 세션 카운터가 0 이 된 경우)

    assert at.session_state["calls_total"] == 0 and calls == []
    assert at.text_area[0].disabled is blocked and at.button[0].disabled is blocked
    assert at.metric[3].value == f"{used}회 / 100회"
    day_errors = [e.value for e in at.error if "일일" in e.value]
    assert bool(day_errors) is blocked
    if blocked:
        assert "10회" in day_errors[0] and "100회" in day_errors[0]
    else:
        assert not at.error and not at.warning


def test_daily_limit_can_be_changed_with_the_environment(monkeypatch):
    script_agent(monkeypatch, says("호출되면 안 된다"))
    monkeypatch.setenv(view.DAILY_LIMIT_ENV, "25")
    write_today_log(14)
    assert not new_app().button[0].disabled  # 남은 11회
    write_today_log(16)
    at = new_app()  # 남은 9회
    assert at.button[0].disabled and at.metric[3].value == "16회 / 25회"


def test_yesterdays_log_does_not_count_today(monkeypatch):
    script_agent(monkeypatch, says("호출되면 안 된다"))
    agent.LOG_DIR.mkdir(parents=True)
    (agent.LOG_DIR / "agent_20200101.jsonl").write_text(json.dumps({"usage": {"llm_calls": 999}}) + "\n", encoding="utf-8")
    at = new_app()
    assert not at.button[0].disabled and at.metric[3].value == "0회 / 100회"


def write_today_raw(*lines):
    agent.LOG_DIR.mkdir(parents=True, exist_ok=True)
    (agent.LOG_DIR / f"agent_{datetime.now():%Y%m%d}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def good(n):
    return json.dumps({"usage": {"llm_calls": n}})


def test_broken_lines_below_the_threshold_warn_with_the_lower_bound_but_do_not_block(monkeypatch):
    script_agent(monkeypatch, says("호출되면 안 된다"))
    write_today_raw(good(20), "{깨진 줄", good(30), "또 깨진 줄")  # 하한값 50, 깨진 줄 2개
    at = new_app()

    assert not at.text_area[0].disabled and not at.button[0].disabled
    warning = next(w.value for w in at.warning if "깨진 줄" in w.value)
    assert "2개" in warning and "하한값" in warning and "더 많을 수 있음" in warning
    assert not any("확인하지 못함" in w.value for w in at.warning)  # 파일은 읽었으므로 다른 경고다
    assert at.metric[3].value == "50회 이상 / 100회"


def test_broken_lines_do_not_prevent_blocking_when_the_lower_bound_already_reaches_it(monkeypatch):
    calls = script_agent(monkeypatch, says("호출되면 안 된다"))
    write_today_raw(good(60), "{깨진 줄", good(31))  # 하한값 91 → 실제는 이상이므로 막아도 오탐이 아니다
    at = new_app()

    assert at.text_area[0].disabled and at.button[0].disabled and calls == []
    assert any("일일" in e.value for e in at.error)
    assert any("깨진 줄 1개" in w.value for w in at.warning)  # 막혀도 합계가 하한값이라는 점은 알린다


@pytest.mark.parametrize("broken, blocked", [(1, False), (4, False), (5, True), (9, True)])
def test_five_or_more_broken_lines_block_even_when_the_lower_bound_is_low(monkeypatch, broken, blocked):
    calls = script_agent(monkeypatch, says("호출되면 안 된다"))
    write_today_raw(good(3), *(["{깨진 줄"] * broken))  # 하한값은 3회뿐이라 한도로는 한참 남았다
    at = new_app()

    assert at.text_area[0].disabled is blocked and at.button[0].disabled is blocked and calls == []
    errors = [e.value for e in at.error]
    assert any("로그가 많이 깨져 사용량을 확인할 수 없습니다. logs/ 를 점검하세요." in e for e in errors) is blocked
    assert not any("남은 호출" in e for e in errors)  # 한도 문구가 아니라 로그 점검 문구가 나온다
    assert any(f"깨진 줄 {broken}개" in w.value and "하한값" in w.value for w in at.warning)  # 하한값 경고는 같이 나온다
    assert at.metric[3].value == "3회 이상 / 100회"


def test_unreadable_log_file_warns_but_does_not_block(monkeypatch):
    script_agent(monkeypatch, says("호출되면 안 된다"))
    (agent.LOG_DIR / f"agent_{datetime.now():%Y%m%d}.jsonl").mkdir(parents=True)  # 파일 자리에 폴더: 읽을 수 없다
    at = new_app()

    assert not at.text_area[0].disabled and not at.button[0].disabled  # 막지 않는다
    assert any("일일 한도를 확인하지 못함" in w.value for w in at.warning)
    assert at.metric[3].value == "?회 / 100회"


def test_unreadable_log_file_still_applies_the_session_limit(monkeypatch):
    script_agent(monkeypatch, says("호출되면 안 된다"))
    (agent.LOG_DIR / f"agent_{datetime.now():%Y%m%d}.jsonl").mkdir(parents=True)
    at = session_app(25)
    assert at.button[0].disabled and any("일일 한도를 확인하지 못함" in w.value for w in at.warning)


def test_daily_total_grows_after_a_question_and_blocks_when_it_reaches_the_limit(monkeypatch):
    monkeypatch.setattr(tools, "ask", lambda q, summarize_result=True: ask_result())
    script_agent(monkeypatch, says("", call("ask_data", question="q")), says("답"))
    monkeypatch.setenv(view.DAILY_LIMIT_ENV, "12")  # 이 질문이 3회를 쓰면 남은 9회: 다음 질문은 막힌다
    at = new_app()
    assert not at.button[0].disabled

    submit(at)

    assert at.metric[3].value == "3회 / 12회"
    assert at.text_area[0].disabled and at.button[0].disabled
    assert any("일일" in e.value for e in at.error)


# ---------- 답변은 일반 텍스트 ----------
EVIL = "![img](http://evil.example/x.png) [클릭](http://evil.example/login) 11~30%군 ~~취소~~ <b>굵게</b>"


def test_answer_is_plain_text_without_images_or_links(monkeypatch):
    script_agent(monkeypatch, says(EVIL))
    at = submit(new_app())

    assert not at.exception
    assert any(t.value == EVIL for t in at.text)  # st.text 로 원문 그대로
    assert not at.get("imgs")  # 이미지 요소 없음
    assert all("evil.example" not in m.value for m in at.markdown)  # 마크다운으로 해석되는 곳에는 들어가지 않는다


def test_errors_are_escaped_and_show_only_the_type(monkeypatch):
    script_agent(monkeypatch, RuntimeError("Incorrect API key provided: sk-abc***xyz"))
    at = submit(new_app())
    assert at.error[0].value == esc("[LLM 오류] RuntimeError")
    assert "sk-" not in everything(at)
    assert at.session_state["calls_total"] == 1  # 실패한 호출도 센다


def test_unexpected_exception_shows_only_the_type_name(monkeypatch):
    def boom(question):
        raise ValueError("host=db.internal password=secret")

    monkeypatch.setattr(agent, "run_agent", boom)
    at = submit(new_app())
    assert not at.exception and at.error[0].value == esc("[실행 오류] ValueError")
    assert "db.internal" not in everything(at) and "secret" not in everything(at)


# ---------- 표에는 user_id 가 없다 ----------
def test_user_id_columns_are_hidden_from_data_tables(monkeypatch):
    monkeypatch.setattr(tools, "ask", lambda q, summarize_result=True: ask_result(
        columns=["user_id", "n"], rows=[["u-12345", 3], ["u-67890", 4]], row_count=2))
    script_agent(monkeypatch, says("", call("ask_data", question="q")), says("끝"))
    at = submit(new_app())

    assert list(at.dataframe[0].value.columns) == ["n"]
    page = everything(at)
    assert "u-12345" not in page and "u-67890" not in page
    assert "개인 식별 컬럼(user_id)은 화면에서 숨겼습니다" in page  # 숨겼다는 사실은 알려 준다


def test_ask_data_refusal_is_shown_as_info(monkeypatch):
    monkeypatch.setattr(tools, "ask", lambda q, summarize_result=True: ask_result(
        sql=None, columns=[], rows=[], row_count=0, error="CANNOT_ANSWER: 나이 정보가 없습니다"))
    script_agent(monkeypatch, says("", call("ask_data", question="q")), says("데이터에 없는 정보입니다."))
    at = submit(new_app())
    assert not at.exception and any("나이 정보가 없습니다" in i.value for i in at.info)


# ---------- 이탈 위험 순위 세그먼트 ----------
def test_churn_result_always_shows_evidence_baseline_and_caveats(monkeypatch):
    script_agent(monkeypatch, says("", call("get_churn_segments", **SEG_ARGS, reason="순위 상위군 인원이 필요해서")),
                 says("상위 10%군 중 구매 경험이 있는 팬은 300명입니다."))
    at = submit(new_app(), "이탈 위험 순위가 높은 팬 중 구매 경험이 있는 팬은?")

    assert not at.exception
    page = everything(at)
    assert "군별 실제 비율 (근거)" in page and "모델로 나눈 군과 단순 기준선(M0)으로 나눈 군의 비교" in page
    assert esc(tools.M0_NOTE) in [i.value for i in at.info]                 # M0 비교 요약
    assert any(esc(note) == i.value for i in at.info for note in make_report()["notes"])  # 안내 문구(가상 데이터, 인과 아님)
    frames = [df.value for df in at.dataframe]
    assert any("14일 안에 다시 활동한 비율(%)" in f.columns for f in frames)  # 상위군도 대부분 다시 활동했다는 근거 표
    assert any("기준선(M0) 군 실제 비율(%)" in f.columns for f in frames)
    selected = next(f for f in frames if list(f.columns)[:2] == ["군", "구매 경험"])
    assert selected["인원"].sum() == 300 and set(selected["군"]) == {"상위 10%군"}
    assert "user_id" not in page.lower()


def test_small_segment_shows_hold_and_alternatives(monkeypatch):
    script_agent(monkeypatch, says("", call("get_churn_segments", tier="상위 10%군", purchase="없음", gap_group="팔로우 없음")),
                 says("해석 보류입니다."))
    at = submit(new_app())
    assert any("해석 보류" in w.value for w in at.warning)
    assert any(list(df.value.columns) == ["조건", "인원"] for df in at.dataframe)  # 합쳐서 볼 수 있는 대안
    assert "군별 실제 비율 (근거)" in everything(at)                           # 보류여도 근거는 같이 나온다


# ---------- 액션 추천 ----------
def test_recommend_actions_shows_code_attached_judgement_alternatives_and_notes(monkeypatch):
    monkeypatch.setattr(tools, "complete", FakeComplete(reply(rec=draft(message_draft="새 소식이 올라왔어요! ~~ 구경 오세요"))))
    script_agent(monkeypatch, says("", call("recommend_actions", **SEG_ARGS, reason="메시지 초안 요청")),
                 says("초안을 만들었습니다. 표본 수 판정을 확인하세요."))
    at = submit(new_app(), "상위 10%군 중 구매 경험이 있는 팬에게 보낼 메시지를 써줘")

    assert not at.exception
    plan = actions.sample_size_plan(0.075, 300)
    assert [e.value for e in at.error if "검증할 수 없다" in e.value] == [esc(plan["verdict"])]  # 눈에 띄는 판정 상자
    warnings = [w.value for w in at.warning]
    for note in (actions.CHANNEL_NOTE, tools.NO_SENDING_NOTE, tools.M0_NOTE):
        assert esc(note) in warnings                                       # 코드가 붙인 주의 문구
    page = everything(at)
    assert "채널 목록은 가정입니다" in page                                  # 채널은 가정이라고 표시
    for label in ("조건 빼기", "군 합치기", "전체 합치기", "반복 모집", "관찰 분석"):
        assert label in page                                               # 대안 목록 (코드가 계산)
    frames = [df.value for df in at.dataframe]
    assert any("그룹당 필요 인원" in f.columns and 589 in f["그룹당 필요 인원"].tolist() for f in frames)
    # LLM 이 쓴 글은 일반 텍스트: ~~ 가 취소선이 되지 않고 그대로 보인다
    assert any("새 소식이 올라왔어요! ~~ 구경 오세요" == t.value for t in at.text)
    assert any(e.label == "도구 호출 기록(reason 포함) 보기" for e in at.expander)
    assert "메시지 초안 요청" in page


def test_recommend_actions_safety_violation_is_shown_as_error(monkeypatch):
    monkeypatch.setattr(tools, "complete", FakeComplete(reply(rec=draft(message_draft="휴면 팬이신가요?"))))
    script_agent(monkeypatch, says("", call("recommend_actions", **SEG_ARGS)), says("초안을 버렸습니다."))
    at = submit(new_app())
    assert not at.exception and any("안전 규칙" in e.value for e in at.error)
    assert any("message_draft" in t.value for t in at.text)         # 위반 사유 줄(어느 칸이 왜)은 보여 준다
    assert "휴면 팬이신가요?" not in everything(at)                    # 버린 초안 원문은 화면에 없다


def test_feasible_verdict_has_no_alternatives(monkeypatch):
    monkeypatch.setattr(tools, "get_report", lambda: make_report(cell_n=400, small=False))
    script_agent(monkeypatch, says("", call("recommend_actions")), says("가능합니다."))
    at = submit(new_app())
    assert not at.exception and any("검증할 수 있는 가정이 있다" in s.value for s in at.success)
    assert "대안 (검증할 수 없다는 판정이므로" not in everything(at)


# ---------- 호출 기록 ----------
def test_tool_history_shows_every_step_with_reason(monkeypatch):
    monkeypatch.setattr(tools, "ask", lambda q, summarize_result=True: ask_result())
    script_agent(monkeypatch,
                 says("", call("ask_data", question="a", reason="첫 번째 이유")),
                 says("", call("get_churn_segments", reason="두 번째 이유")),
                 says("끝"))
    at = submit(new_app())
    history = next(df.value for df in at.dataframe if "이유(reason)" in df.value.columns)
    assert history["도구"].tolist() == ["ask_data", "get_churn_segments"]
    assert history["이유(reason)"].tolist() == ["첫 번째 이유", "두 번째 이유"]
    assert json.loads(history["인자"][0]) == {"question": "a"}  # reason 은 인자가 아니라 따로 기록된다


# ---------- 행 수 상한에서 잘린 결과 ----------
def test_truncated_result_shows_a_warning(monkeypatch):
    monkeypatch.setattr(tools, "ask", lambda q, summarize_result=True: ask_result(
        columns=["n"], rows=[[1], [2]], row_count=2, truncated=True))
    script_agent(monkeypatch, says("", call("ask_data", question="q")), says("끝"))
    at = submit(new_app())
    assert any("상한에서 잘렸습니다" in w.value for w in at.warning)


def test_normal_result_has_no_truncation_warning(monkeypatch):
    monkeypatch.setattr(tools, "ask", lambda q, summarize_result=True: ask_result())
    script_agent(monkeypatch, says("", call("ask_data", question="q")), says("끝"))
    at = submit(new_app())
    assert not any("잘렸습니다" in w.value for w in at.warning)


# =====================================================================
# 보안 점검: 화면의 ID 가리기, 1000행 안내
# =====================================================================
def test_aliased_user_ids_never_reach_the_screen_even_if_ask_did_not_mask_them(monkeypatch):
    """ask() 안의 가리기를 건너뛰는 상황(가짜 ask)을 일부러 만들어서, 화면 쪽 두 번째 방어선만 따로 시험한다."""
    monkeypatch.setattr(tools, "ask", lambda q, summarize_result=True: ask_result(
        columns=["id", "n"], rows=[["user_000123", 3], ["txn_000001", 4]], row_count=2))
    script_agent(monkeypatch, says("", call("ask_data", question="q")), says("끝"))
    at = submit(new_app())
    page = everything(at)
    assert "user_000123" not in page
    assert at.dataframe[0].value["id"].tolist() == ["[ID]", "txn_000001"]  # 전부 [ID] 인 열은 이제 숨겨지므로 일부만 ID 인 열로 확인한다


def test_user_id_in_the_agent_answer_is_masked_on_screen(monkeypatch):
    script_agent(monkeypatch, says("user_000123 님이 가장 많습니다."))
    at = submit(new_app())
    assert "user_000123" not in everything(at) and "[ID] 님이 가장 많습니다." in "".join(t.value for t in at.text)


def test_masked_id_count_is_shown(monkeypatch):
    monkeypatch.setattr(tools, "ask", lambda q, summarize_result=True: ask_result(masked_ids=2))
    script_agent(monkeypatch, says("", call("ask_data", question="q")), says("끝"))
    at = submit(new_app())
    assert any("2개" in c.value and "[ID]" in c.value.replace(chr(92), "") for c in at.caption)


def test_no_mask_caption_when_nothing_was_masked(monkeypatch):
    monkeypatch.setattr(tools, "ask", lambda q, summarize_result=True: ask_result(masked_ids=0))
    script_agent(monkeypatch, says("", call("ask_data", question="q")), says("끝"))
    at = submit(new_app())
    assert not any("가렸습니다" in c.value for c in at.caption)


def test_exactly_max_rows_note_is_shown(monkeypatch):
    from app import text2sql
    monkeypatch.setattr(tools, "ask", lambda q, summarize_result=True: ask_result(
        columns=["n"], rows=[[i] for i in range(1000)], row_count=1000, row_cap_note=text2sql.ROW_CAP_NOTE))
    script_agent(monkeypatch, says("", call("ask_data", question="q")), says("끝"))
    at = submit(new_app())
    assert any("정확히 1000행이라 더 있을 수 있음" in i.value.replace(chr(92), "") for i in at.info)


def test_no_row_cap_note_for_a_normal_result(monkeypatch):
    monkeypatch.setattr(tools, "ask", lambda q, summarize_result=True: ask_result())
    script_agent(monkeypatch, says("", call("ask_data", question="q")), says("끝"))
    at = submit(new_app())
    assert not any("정확히 1000행" in i.value for i in at.info)


# =====================================================================
# [ID] 만 가득한 열 숨기기
# =====================================================================
def _plain(items):
    return [i.value.replace(chr(92), "") for i in items]


def _show(monkeypatch, **over):
    monkeypatch.setattr(tools, "ask", lambda q, summarize_result=True: ask_result(**over))
    script_agent(monkeypatch, says("", call("ask_data", question="q")), says("끝"))
    return submit(new_app())


def test_all_id_column_is_hidden_with_one_line_under_the_table(monkeypatch):
    at = _show(monkeypatch, columns=["id", "n"], rows=[["user_000123", 3], ["user_000456", 4]], row_count=2, masked_ids=2)
    assert list(at.dataframe[0].value.columns) == ["n"]
    assert any("개별 사용자 ID 는 표시하지 않았다 (가린 값 2개)" in c for c in _plain(at.caption))
    assert not any("로 가렸습니다" in c for c in _plain(at.caption))  # 같은 값을 위 캡션에서 또 세지 않는다


def test_partly_id_column_stays_and_gets_the_caption_above(monkeypatch):
    at = _show(monkeypatch, columns=["id", "n"], rows=[["user_000123", 3], ["txn_000001", 4]], row_count=2, masked_ids=1)
    assert list(at.dataframe[0].value.columns) == ["id", "n"]
    captions = _plain(at.caption)
    assert any("1개" in c and "[ID]" in c and "가렸습니다" in c for c in captions)
    assert not any("표시하지 않았다" in c for c in captions)


def test_no_id_at_all_shows_neither_line(monkeypatch):
    at = _show(monkeypatch, columns=["n"], rows=[[1], [2]], row_count=2, masked_ids=0)
    captions = _plain(at.caption)
    assert not any("표시하지 않았다" in c or "가렸습니다" in c for c in captions)


def test_hidden_and_remaining_counts_add_up_to_the_total(monkeypatch):
    """열이 숨겨지고 일부만 [ID] 인 열도 남는 경우: 두 문구의 숫자를 더하면 가린 전체 개수다 (같은 값을 두 번 세지 않는다)."""
    rows = [["user_000001", "user_000011", 1], ["user_000002", "txn_1", 2], ["user_000003", "txn_2", 3]]
    at = _show(monkeypatch, columns=["a", "b", "n"], rows=rows, row_count=3, masked_ids=5)  # a 열 3개 + b 열 2개
    assert list(at.dataframe[0].value.columns) == ["b", "n"]
    captions = _plain(at.caption)
    import re
    below = [int(m.group(1)) for c in captions for m in [re.search(r"표시하지 않았다 .가린 값 (\d+)개", c)] if m]
    above = [int(m.group(1)) for c in captions for m in [re.search(r"ID.? 모양의 값 (\d+)개", c)] if m]
    assert below == [3] and above == [2]
    assert below[0] + above[0] == 5


def test_when_every_column_is_ids_no_empty_table_is_drawn(monkeypatch):
    at = _show(monkeypatch, columns=["id"], rows=[["user_000123"], ["user_000456"]], row_count=2, masked_ids=2)
    assert all(df.value.shape[1] > 0 for df in at.dataframe)  # 열이 하나도 없는 빈 표를 그리지 않는다 (시도 이력 표 등은 따로 있다)
    assert not any("id" in df.value.columns for df in at.dataframe)
    assert any("표시할 표가 없습니다" in c and "2개" in c for c in _plain(list(at.caption) + list(at.info)))
