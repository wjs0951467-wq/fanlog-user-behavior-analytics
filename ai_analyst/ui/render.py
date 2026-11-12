"""도구 결과를 화면에 그리는 함수들.

그리는 규칙 (면접에서 설명할 포인트)
- 표와 숫자는 도구 결과(for_ui)에서 코드가 직접 그린다. 에이전트의 문장에서 숫자를 가져오지 않는다.
- 모델이 쓴 글, 질문, DB 값은 st.text 와 st.dataframe 으로만 그린다. st.markdown 은 고정 문구에만 쓴다.
  (링크, 이미지, 취소선이 켜지면 데이터 속 문장이 화면을 바꿀 수 있다. 예: "11~30%군" 의 ~ 하나로도 취소선이 생길 수 있다.)
- 알림 상자(st.warning 등)는 마크다운을 해석하므로, 동적 문자열은 escape_markdown 을 거쳐 넣는다.
"""
import pandas as pd
import streamlit as st

from . import view
from .view import escape_markdown as md

SEGMENT_TOOLS = ("get_churn_segments", "recommend_actions")


def text(value) -> None:
    st.text("" if value is None else str(value))


def _frame(df) -> None:
    st.dataframe(df, hide_index=True, width="stretch")


def _bold(label) -> None:
    st.markdown(f"**{md(label)}**")  # 라벨은 코드가 만든 고정 문구지만, 안전하게 같은 경로로 이스케이프한다


# ---------- 답변 ----------
def show_answer(result: dict) -> None:
    if result["error"]:
        st.error(md(result["error"]))
    if result["answer"]:
        text(result["answer"])  # 일반 텍스트: 마크다운 이미지와 링크가 그림이나 링크가 되지 않는다
    if result.get("forced_final"):
        st.caption("호출 예산이 다 되어 도구 없이 지금까지의 결과로 답했습니다.")
    if result["unverified_numbers"]:
        st.warning(md("답변의 숫자 중 질문과 도구 결과에서 근거를 찾지 못한 것: "
                      + ", ".join(result["unverified_numbers"])
                      + ". 아래 표의 값과 직접 비교하세요. (이 점검은 경고 전용이라 못 잡는 경우도 있습니다)"))


# ---------- 도구별 결과 ----------
def show_ask_data(step: dict) -> None:
    r = step["result"]
    if "columns" not in r:  # 인자 오류 등으로 질문이 ask() 까지 가지 못한 경우: 표도 가정도 없다
        st.warning(md(r.get("error")))
        return
    if step["status"] != "ok":
        (st.info if step["status"] == "refusal" else st.warning)(md(r.get("error")))
    else:
        df, hidden = view.result_table(r["columns"], r["rows"])
        st.caption(md(f"행 수 {r['row_count']:,}"))
        _frame(df)
        if hidden:
            st.caption(md(f"개인 식별 컬럼({', '.join(hidden)})은 화면에서 숨겼습니다."))
    if r.get("sql"):
        with st.expander("SQL 보기"):
            st.code(r["sql"], language="sql")
            if r.get("attempts"):
                _bold("시도 이력")
                _frame(view.attempts_frame(r["attempts"]))
    with st.expander("계산 가정(assumptions) 보기"):
        for a in r.get("assumptions") or ["가정이 기록되지 않았습니다."]:
            text(a)


def _selection_line(r: dict) -> str:
    sel = r["selection"]
    size = r.get("n", r.get("segment_size"))
    line = f"조건: 군={sel['tier']} / 구매 경험={sel['purchase']} / 소통 공백={sel['gap_group']}  →  {size:,}명"
    if "population_total" in r:
        line += f" (기준일 {r['ref_date']} 활동 중인 팬 {r['population_total']:,}명 중 {r['share_pct']}%)"
    return line


def _show_hold(r: dict) -> None:
    st.warning(md(f"해석 보류: {r.get('reason', '인원이 적습니다.')} 인원이 적은 칸은 우연으로도 크게 흔들립니다."))
    if r.get("alternatives"):
        _bold("대안: 조건을 하나 빼고 합치기")
        _frame(pd.DataFrame([{"조건": " / ".join(f"{k}={v}" for k, v in a["selection"].items()), "인원": a["n"]}
                             for a in r["alternatives"]]))


def show_evidence(evidence: dict) -> None:
    """군의 의미를 보여주는 근거. 이탈 위험 도구 결과에는 이것이 항상 같이 나온다."""
    _bold("군별 실제 비율 (근거)")
    st.caption(md(evidence["what"]))
    _frame(view.tiers_frame(evidence["tiers"]))
    vs = evidence["model_vs_simple_baseline"]
    _bold("모델로 나눈 군과 단순 기준선(M0)으로 나눈 군의 비교")
    _frame(view.versus_frame(vs["by_tier"]))
    st.info(md(vs["summary"]))
    for note in evidence["notes"]:
        st.info(md(note))


def show_churn(step: dict) -> None:
    r = step["result"]
    if step["status"] == "error":
        st.warning(md(r.get("error")))
        return
    text(_selection_line(r))
    if step["status"] == "hold":
        _show_hold(r)
    _frame(view.cells_frame(r["cells"]))
    show_evidence(r["evidence"])
    with st.expander("전체 세그먼트 표 보기"):
        _frame(view.cells_frame(r["segments_table"]))


def _show_alternative(alt: dict) -> None:
    with st.container(border=True):
        _bold(f"{alt['kind']}: {alt['label']}")
        if "scenarios" in alt:  # 합쳐서 인원을 늘리는 대안: 인원과 필요 인원을 다시 계산한 값
            text(_selection_line({"selection": alt["selection"], "segment_size": alt["segment_n"]})
                 + f"  / 기준 비율 {alt['base_rate_pct']}%")
            st.caption(md(alt["verdict"]))
            _frame(view.scenarios_frame(alt["scenarios"]))
        elif "rounds" in alt:
            _frame(view.rounds_frame(alt["rounds"]))
            st.caption(md(alt["assumption"]))
        else:
            st.caption(md(alt["description"]))


def show_recommend(step: dict) -> None:
    r = step["result"]
    if step["status"] == "hold":
        text(_selection_line({"selection": r["selection"], "segment_size": r["n"]}))
        _show_hold(r)
        return
    if step["status"] != "ok":
        st.error(md(r.get("error")))
        for line in (r.get("details") or []) + (r.get("violations") or []):
            text(line)
        return

    draft, plan = r["draft"], r["sample_size"]
    text(_selection_line(r))
    with st.container(border=True):
        _bold("운영 액션 초안 (LLM 이 쓴 글. 효과를 약속하지 않는 가설입니다)")
        for label, key in (("세그먼트 설명", "segment_description"), ("가설", "hypothesis"),
                           ("메시지 초안", "message_draft")):
            _bold(label)
            text(draft[key])
        _bold("채널")
        text(f"{draft['channel']}  (채널 목록은 가정입니다. 데이터에 발송 채널 정보가 없습니다)")
        _bold("검증 방법")
        v = draft["validation"]
        text(f"지표: {v['metric']}\n비교 그룹: {v['comparison_group']}\n기간: {v['period']}")
        _bold("운영자 주의사항")
        for c in draft["cautions"]:
            text(f"- {c}")
        if r.get("unverified_numbers_in_draft"):
            st.warning(md("초안에 사실 자료에 없는 숫자가 있습니다: " + ", ".join(r["unverified_numbers_in_draft"])))

    # 여기부터는 모두 코드가 계산하거나 붙인 것이다
    with st.container(border=True):
        _bold("필요 표본 수 판정 (코드 계산: 유의수준 5% 양측, 검정력 80%)")
        (st.success if plan["feasible"] else st.error)(md(plan["verdict"]))
        _frame(view.scenarios_frame(plan["scenarios"]))
        st.caption(md(plan["note"]))
    if r.get("alternatives"):
        st.markdown("**대안 (검증할 수 없다는 판정이므로 코드가 계산해 붙인 것)**")
        for alt in r["alternatives"]:
            _show_alternative(alt)
    with st.container(border=True):
        _bold("주의 문구 (코드가 붙인 것)")
        for note in r["notes"]:
            st.warning(md(note))
    _bold("군별 실제 비율 (근거)")
    _frame(view.tiers_frame(r["evidence"]))


STEP_RENDERERS = {"ask_data": show_ask_data, "get_churn_segments": show_churn, "recommend_actions": show_recommend}


def show_step(step: dict) -> None:
    with st.container(border=True):
        _bold(f"도구 결과: {step['tool']}")
        if step["status"] == "duplicate" or step["result"] is None:
            st.caption("같은 호출이라 다시 실행하지 않았습니다.")
        elif step["tool"] in STEP_RENDERERS and isinstance(step["result"], dict):
            STEP_RENDERERS[step["tool"]](step)
        else:  # 없는 도구 이름 등: 에이전트가 이미 에러 결과로 돌려준 호출이다
            st.warning(md(f"결과를 표시할 수 없습니다 (상태: {step['status']})."))


def show_result(result: dict) -> None:
    """에이전트 결과 전체: 답변, 경고, 도구 결과(표), 호출 기록."""
    show_answer(result)
    for step in result["steps"]:
        show_step(step)
    if result["steps"]:
        with st.expander("도구 호출 기록(reason 포함) 보기"):
            _frame(view.history_frame(result["steps"]))
