"""FANLOG AI 분석가 화면 (Streamlit).

실행 (ai_analyst 폴더에서):
    python -m streamlit run ui/app.py --server.port 8502 --server.headless true

규칙
- 에이전트를 함수로 직접 부른다 (agent.run_agent). 별도 서버(FastAPI /chat)는 만들지 않는다.
- OpenAI 호출은 "제출" 버튼을 눌렀을 때만 일어난다. 위젯을 바꾸거나 화면이 다시 그려질 때는 부르지 않는다.
- 결과는 st.session_state 에 두고, 다시 그릴 때는 거기서 꺼내 그린다.
- 세션 누적 호출이 한도(30회)에 닿으면 입력창과 제출 버튼을 막는다.
"""
import sys
from pathlib import Path

# 이 파일의 이름이 app.py 라서, 스트림릿이 ui/ 폴더를 경로 맨 앞에 넣으면 "import app" 이 이 파일로 잡힌다.
# 프로젝트 루트(ai_analyst)를 맨 앞에 고정해서 app 패키지(app/agent.py 등)가 먼저 잡히게 한다.
ROOT = str(Path(__file__).resolve().parent.parent)
sys.path[:] = [ROOT] + [p for p in sys.path if p != ROOT]

import streamlit as st  # noqa: E402

from app import agent  # noqa: E402  (함수 이름이 아니라 모듈로 가져와야 시험에서 run_agent 를 바꿔 끼울 수 있다)
from ui import render, view  # noqa: E402

EXAMPLES = ("현재 휴면 팬은 몇 명이야?",
            "이탈 위험 순위가 높은 팬(상위 10%군) 중 구매 경험이 있는 팬은 몇 명이야?",
            "상위 10%군 중 구매 경험이 있는 팬에게 보낼 메시지 초안과 효과 검증 방법을 알려줘.")

st.set_page_config(page_title="FANLOG AI 분석가", layout="wide")

# 세션 상태는 한 곳에서 초기화한다
st.session_state.setdefault("calls_total", 0)  # 세션 누적 LLM 호출 수
st.session_state.setdefault("result", None)    # 가장 최근 질문의 결과

st.title("FANLOG AI 분석가")
st.caption("모든 결과는 가상 데이터에서 가정한 생성 규칙의 탐지 결과이며 인과가 아닙니다. "
           "제출 버튼을 누를 때만 OpenAI 를 호출합니다.")

total = st.session_state.calls_total
blocked = view.calls_blocked(total)
last = st.session_state.result

# ---------- 호출 수 ----------
c1, c2, c3 = st.columns(3)
c1.metric("이번 질문의 LLM 호출", f"{last['usage']['llm_calls']}회" if last else "-")
c2.metric("세션 누적 호출", f"{total}회")
c3.metric("세션 한도", f"{view.SESSION_CALL_LIMIT}회")
if blocked:
    st.error(f"세션 호출 한도({view.SESSION_CALL_LIMIT}회)에 도달해서 입력을 막았습니다.")

# ---------- 질문 입력 ----------
with st.form("ask_form"):
    question = st.text_area("질문", max_chars=agent.MAX_QUESTION_CHARS, height=100, disabled=blocked,
                            placeholder="예: " + EXAMPLES[0])
    submitted = st.form_submit_button("제출", type="primary", disabled=blocked)

if submitted:
    clean = (question or "").strip()
    if not clean:
        st.warning("질문을 입력해 주세요.")  # 빈 질문은 LLM 을 부르지 않는다
    elif not blocked:
        with st.spinner("분석 중입니다. 이탈 위험 순위를 처음 계산할 때는 약 3초가 더 걸립니다 (이후에는 저장된 결과를 씁니다)."):
            try:
                outcome = agent.run_agent(clean)
            except Exception as e:  # 예상 못한 오류: 원문은 화면에 내지 않고 종류만 알린다
                outcome = {"question": clean, "answer": None, "steps": [], "unverified_numbers": [],
                           "forced_final": False, "error": f"[실행 오류] {type(e).__name__}",
                           "usage": {"llm_calls": 0, "tokens": 0, "by_source": {}}}
        st.session_state.result = outcome
        st.session_state.calls_total += outcome["usage"]["llm_calls"]
        st.rerun()  # 한도에 닿았으면 입력창이 막힌 상태로, 호출 수 표시가 갱신된 상태로 다시 그린다

# ---------- 결과 ----------
if last:
    st.divider()
    render.text(f"질문: {last['question']}")
    st.caption(view.escape_markdown(view.usage_text(last["usage"]) + f", 걸린 시간 {last.get('elapsed_ms', 0):,}ms"))
    render.show_result(last)
else:
    st.info("질문을 입력하고 제출 버튼을 누르세요.")
    for example in EXAMPLES:
        st.text(f"예: {example}")
