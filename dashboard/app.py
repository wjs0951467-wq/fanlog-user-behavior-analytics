"""FANLOG 운영 대시보드 — 메인 진입점.

실행: streamlit run dashboard/app.py
페이지는 Streamlit 멀티페이지 자동 네비게이션(다음 pages/ 폴더)을 그대로 쓴다.
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from theme import inject_theme, render_virtual_data_badge  # noqa: E402
from data import get_data_generation_meta, ANALYSIS_START, ANALYSIS_END  # noqa: E402

st.set_page_config(page_title="FANLOG 운영 대시보드", page_icon="🎤", layout="wide")
inject_theme()

with st.sidebar:
    render_virtual_data_badge()
    st.markdown("### FANLOG")
    st.caption("아티스트 소통과 팬 행동을 연결해 분석하는 가상 팬덤 플랫폼 대시보드")
    st.markdown("---")
    st.markdown(
        "**페이지 안내**\n\n"
        "- **01 종합 현황**: 핵심 KPI, 아티스트 비교, 세그먼트 구성\n"
        "- **02 아티스트 소통·리텐션** _(준비 중)_\n"
        "- **03 팬 행동·커머스 퍼널** _(준비 중)_\n\n"
        "왼쪽 목록에서 페이지를 선택하세요."
    )

render_virtual_data_badge()
st.title("FANLOG 운영 대시보드")
st.markdown(
    "아티스트의 게시글·메시지·라이브 활동과 팬의 방문·참여·구매 행동을 연결하여, "
    "소통 공백과 팬 활동 감소가 함께 나타나는 패턴 및 커머스 전환 과정을 분석하는 "
    "**가상의 팬덤 플랫폼 운영 대시보드**입니다."
)
st.info(
    "이 대시보드의 모든 수치는 포트폴리오 프로젝트를 위해 생성한 **가상 데이터**를 대상으로 합니다. "
    "실제 팬덤에 대한 사실이 아니라 가정한 시나리오의 탐지 결과로 읽어야 하며, 관찰된 관계는 상관관계이지 "
    "인과관계가 아닙니다."
)

meta = get_data_generation_meta()
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("분석 기간", f"{ANALYSIS_START} ~ {ANALYSIS_END}")
with col2:
    if meta is not None:
        st.metric("데이터 생성 시각(UTC)", str(meta["generated_at_utc"]))
    else:
        st.metric("데이터 생성 시각(UTC)", "기록 없음")
with col3:
    if meta is not None:
        st.metric("생성 설정 버전 / 시나리오", f"{meta['config_version']} / {meta['scenario']}")
    else:
        st.metric("생성 설정 버전 / 시나리오", "-")

st.markdown("---")
st.markdown("왼쪽 사이드바에서 페이지를 선택해 상세 분석을 확인하세요.")
