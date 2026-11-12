"""화면(ui/app.py) 스모크 테스트: Streamlit 의 AppTest 로 브라우저 없이 화면을 돌린다.

가짜로 바꾸는 것: 에이전트의 LLM(agent.complete_with_tools), 액션 LLM(tools.complete), ask()(DB 와 SQL 생성), churn 계산(get_report).
진짜로 도는 것: ui/app.py, ui/render.py, agent.run_agent(루프, 예산, 숫자 점검), 도구 3개의 코드.
실제 OpenAI 호출 0회, DB 접속 0회.
"""
import json
import re
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
    monkeypatch.setattr(agent, "LOG_DIR", tmp_path / "logs")  # 진짜 logs/ 에 쓰지 않는다
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
    assert [m.value for m in at.metric] == ["-", "0회", "30회"]  # 이번 질문 / 세션 누적 / 세션 한도
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
    assert [m.value for m in at.metric] == ["3회", "3회", "30회"]
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
def test_input_is_blocked_at_the_session_limit(monkeypatch):
    calls = script_agent(monkeypatch, says("호출되면 안 된다"))
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.session_state["calls_total"] = 30
    at.run()

    assert at.text_area[0].disabled and at.button[0].disabled
    assert any("한도" in e.value for e in at.error) and calls == []


def test_input_is_still_open_just_below_the_limit(monkeypatch):
    script_agent(monkeypatch, says("호출되면 안 된다"))
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.session_state["calls_total"] = 29
    at.run()
    assert not at.text_area[0].disabled and not at.button[0].disabled and not at.error


def test_a_question_that_reaches_the_limit_blocks_the_next_one(monkeypatch):
    monkeypatch.setattr(tools, "ask", lambda q, summarize_result=True: ask_result())
    script_agent(monkeypatch, says("", call("ask_data", question="q")), says("답"))
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.session_state["calls_total"] = 27  # 이 질문이 3회를 쓰면 정확히 30회
    at.run()

    submit(at)

    assert at.session_state["calls_total"] == 30
    assert at.text_area[0].disabled and at.button[0].disabled  # 제출이 끝난 화면에서 바로 막힌다
    assert any("한도" in e.value for e in at.error)


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
