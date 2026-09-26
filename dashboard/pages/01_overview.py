"""Page 1 — 종합 현황 (PRD 12.3절).

플랫폼의 핵심 상태와 점검할 변화를 빠르게 확인하는 페이지.
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from theme import inject_theme, render_kpi, render_virtual_data_badge, get_plotly_theme  # noqa: E402
from data import (  # noqa: E402
    ANALYSIS_START,
    ANALYSIS_END,
    get_artist_list,
    get_overview_kpis,
    get_artist_comparison,
    get_low_engagement_content,
    get_segment_distribution,
)

st.set_page_config(page_title="종합 현황 · FANLOG", page_icon="🎤", layout="wide")
inject_theme()
render_virtual_data_badge()

st.title("종합 현황")
st.caption("플랫폼의 핵심 상태와 점검할 변화를 빠르게 확인합니다 (PRD 12.3절).")

# ------------------------------------------------------------------
# 사이드바 필터 (FR-002)
# ------------------------------------------------------------------
artist_df = get_artist_list()
artist_label_map = dict(zip(artist_df["artist_id"], artist_df["artist_name"]))

with st.sidebar:
    st.markdown("### 필터")
    date_range = st.date_input(
        "기간",
        value=(ANALYSIS_START, ANALYSIS_END),
        min_value=ANALYSIS_START,
        max_value=ANALYSIS_END,
    )
    selected_artist_ids = st.multiselect(
        "아티스트",
        options=artist_df["artist_id"].tolist(),
        default=artist_df["artist_id"].tolist(),
        format_func=lambda aid: artist_label_map.get(aid, aid),
    )

if not isinstance(date_range, tuple) or len(date_range) != 2:
    st.warning("기간을 시작일과 종료일 두 개 모두 선택해 주세요.")
    st.stop()

start_date, end_date = date_range
if start_date > end_date:
    st.warning("시작일이 종료일보다 늦습니다. 기간을 다시 선택해 주세요.")
    st.stop()

# ------------------------------------------------------------------
# 적용 중인 필터·표본 수 (PRD 12.2절)
# ------------------------------------------------------------------
if not selected_artist_ids:
    st.warning("조건에 해당하는 데이터 없음 (아티스트를 최소 1개 이상 선택하세요)")
    st.stop()

all_artist_selected = set(selected_artist_ids) == set(artist_df["artist_id"].tolist())
artist_filter_text = "전체 아티스트" if all_artist_selected else ", ".join(
    artist_label_map[aid] for aid in selected_artist_ids
)

kpis = get_overview_kpis(start_date, end_date, selected_artist_ids)

st.markdown(
    f"**적용 중인 필터**: {start_date} ~ {end_date} ({(end_date - start_date).days + 1}일) · "
    f"아티스트: {artist_filter_text} · **표본 팬 수**: {kpis['n_fans_in_scope']:,}명"
)

if kpis["current"]["dau"] is None and kpis["current"]["content_viewers_n"] == 0:
    st.info("조건에 해당하는 데이터 없음")
    st.stop()


def _fmt(value, suffix="") -> str:
    if value is None:
        return "계산 불가"
    return f"{value:,.1f}{suffix}"


def _delta_pp(cur, prev) -> str | None:
    """비율 지표용: %p 차이."""
    if cur is None or prev is None:
        return None
    return f"{cur - prev:+.1f}%p"


def _delta_relative(cur, prev) -> str | None:
    """카운트 지표용: 상대 변화율."""
    if cur is None or prev is None or prev == 0:
        return None
    return f"{100 * (cur - prev) / prev:+.1f}%"


cur = kpis["current"]
prev = kpis["previous"]
prev_note = (
    f"이전 동일 기간({kpis['prev_start']} ~ {kpis['prev_end']}) 대비"
    if kpis["prev_available"]
    else "이전 동일 기간 데이터 없음(분석 시작일 이전)"
)

# ------------------------------------------------------------------
# KPI 행 (FR-010, FR-011)
# ------------------------------------------------------------------
st.markdown("### 핵심 지표")
st.caption(prev_note)

kpi_cols = st.columns(6)
with kpi_cols[0]:
    render_kpi("DAU (일평균)", _fmt(cur["dau"], "명"), _delta_relative(cur["dau"], prev["dau"] if prev else None))
with kpi_cols[1]:
    render_kpi("WAU (주평균)", _fmt(cur["wau"], "명"), _delta_relative(cur["wau"], prev["wau"] if prev else None))
with kpi_cols[2]:
    render_kpi(
        "W1 참여 재방문율",
        _fmt(cur["w1_return_rate_pct"], "%"),
        _delta_pp(cur["w1_return_rate_pct"], prev["w1_return_rate_pct"] if prev else None),
    )
with kpi_cols[3]:
    render_kpi(
        "14일 이탈위험률",
        _fmt(cur["at_risk_14d_pct"], "%"),
        _delta_pp(cur["at_risk_14d_pct"], prev["at_risk_14d_pct"] if prev else None),
        gradient=False,
    )
with kpi_cols[4]:
    render_kpi(
        "콘텐츠 참여율",
        _fmt(cur["content_engagement_pct"], "%"),
        _delta_pp(cur["content_engagement_pct"], prev["content_engagement_pct"] if prev else None),
    )
with kpi_cols[5]:
    render_kpi(
        "상품 조회→구매 전환율",
        _fmt(cur["purchase_conversion_pct"], "%"),
        _delta_pp(cur["purchase_conversion_pct"], prev["purchase_conversion_pct"] if prev else None),
    )

st.caption(
    f"W1 재방문율: {cur['w1_return_days']:,} / {cur['w1_eligible_days']:,}일(기준 참여일 대비 1~7일 이내 재활동) · "
    f"14일 이탈위험률: {cur['at_risk_n']:,} / {cur['at_risk_denom']:,}명(이전 30일 활동 팬 중) · "
    f"콘텐츠 참여율: {cur['content_engagers_n']:,} / {cur['content_viewers_n']:,}명"
    "(선택 기간 중 아무 콘텐츠나 조회한 팬 대비, 같은 기간 중 아무 콘텐츠에나 좋아요·댓글을 남긴 팬의 비율 — "
    "같은 콘텐츠·24시간 이내 제약이 없는 느슨한 정의라 콘텐츠 단위 참여율보다 높게 나온다) · "
    f"구매 전환율(순서 기반 닫힌 퍼널): {cur['purchase_n']:,} / {cur['purchase_denom']:,}건(첫 조회 후 7일 이내 구매). "
    "DAU/WAU는 스냅샷이 아니라 선택 기간의 일평균/주평균이며, 아티스트 필터는 해당 아티스트를 "
    "팔로우 중인 팬 집단으로 모집단을 제한한 값이다(콘텐츠 참여율·구매 전환율은 콘텐츠·상품의 소속 아티스트로 직접 필터링). "
    "모든 관계는 상관관계이며 인과관계로 해석하지 않는다."
)

st.markdown("---")

# ------------------------------------------------------------------
# 아티스트별 핵심 지표 비교
# ------------------------------------------------------------------
st.markdown("### 아티스트별 핵심 지표 비교")
artist_comp = get_artist_comparison(start_date, end_date)
artist_comp = artist_comp[artist_comp["artist_id"].isin(selected_artist_ids)]

if artist_comp.empty:
    st.info("조건에 해당하는 데이터 없음")
else:
    plot_theme = get_plotly_theme()
    palette = plot_theme["colorway"]
    chart_cols = st.columns(2)
    with chart_cols[0]:
        # px.bar는 color= 없이 만들면 단일 트레이스에 Plotly 기본 파란색을 그 자리에서
        # 확정해버려서, 나중에 update_layout(colorway=...)를 적용해도 되돌아 바뀌지 않는다
        # (실제로 발생했던 버그, docs/decisions_log.md 참고). 아티스트별로 색을 나눠
        # 팔레트가 실제 막대 색에 반영되도록 color="artist_name"을 명시한다.
        fig1 = px.bar(
            artist_comp, x="artist_name", y="communication_days", color="artist_name",
            color_discrete_sequence=palette,
            labels={"artist_name": "아티스트", "communication_days": "소통 활동일수"},
            title="아티스트별 소통 활동일수",
        )
        fig1.update_layout(**plot_theme, showlegend=False)
        st.plotly_chart(fig1, width="stretch")
    with chart_cols[1]:
        fig2 = px.bar(
            artist_comp, x="artist_name", y="avg_active_followers", color="artist_name",
            color_discrete_sequence=palette,
            labels={"artist_name": "아티스트", "avg_active_followers": "일평균 활성 팔로워"},
            title="아티스트별 평균 활성 팔로워",
        )
        fig2.update_layout(**plot_theme, showlegend=False)
        st.plotly_chart(fig2, width="stretch")
    st.caption(
        "소통 활동일수 = 선택 기간 중 게시글·메시지·라이브가 하나 이상 있었던 날짜 수(총 "
        f"{int(artist_comp['total_days'].iloc[0]) if len(artist_comp) else 0}일 중). "
        "활성 팔로워 = 그날 그 아티스트를 팔로우 중이면서 관련 핵심 활동을 한 팬 수의 일평균. "
        "표본이 아티스트당 3팀뿐이라 작은 차이를 확정적으로 해석하지 않는다."
    )

st.markdown("---")

# ------------------------------------------------------------------
# 조회는 높지만 참여율이 낮은 콘텐츠
# ------------------------------------------------------------------
st.markdown("### 조회는 높지만 참여율이 낮은 콘텐츠")
low_engagement = get_low_engagement_content(start_date, end_date, selected_artist_ids, min_viewers=5)

if low_engagement.empty:
    st.info("조건에 해당하는 데이터 없음 (조회자 5명 이상인 콘텐츠가 없거나, 선택 기간에 발행된 콘텐츠가 없습니다)")
else:
    display_df = low_engagement.copy()
    display_df["engagement_rate"] = (display_df["engagement_rate"] * 100).round(1)
    display_df = display_df.rename(columns={
        "content_id": "콘텐츠 ID", "artist_id": "아티스트", "content_type": "유형", "title": "제목",
        "unique_viewers": "고유 조회자", "unique_engagers": "고유 참여자",
        "engagement_rate": "참여율(%)", "published_date_kst": "발행일",
    })
    st.dataframe(display_df, width="stretch", hide_index=True)

st.caption(
    "콘텐츠 참여율 = 고유 조회자 중 좋아요 또는 댓글을 수행한 팬 비율(PRD 8.2절). 분모(고유 조회자)가 0이면 "
    "계산 불가로 처리하며, 조회자 5명 미만인 콘텐츠는 표본이 너무 작아 이 표에서 제외했다. "
    "발행일이 선택 기간 안에 있는 콘텐츠만 대상으로 하며, 참여 수치 자체는 발행 이후 생애 전체 누적값이다."
)

st.markdown("---")

# ------------------------------------------------------------------
# 팬 세그먼트 구성
# ------------------------------------------------------------------
st.markdown("### 팬 세그먼트 구성")
segment_df = get_segment_distribution(end_date, selected_artist_ids)

if segment_df.empty:
    st.info("조건에 해당하는 데이터 없음")
else:
    segment_order = ["신규", "조회중심", "참여", "코어", "미분류"]
    # 5색 팔레트(brand_violet/brand_pink/signal_cyan/#F59E0B/positive)를 세그먼트 5개에
    # 하나씩 순서대로 배정한다 (5번째 색 positive 추가로 더 이상 순환할 필요가 없다).
    palette = get_plotly_theme()["colorway"]
    segment_colors = {seg: palette[i % len(palette)] for i, seg in enumerate(segment_order)}
    segment_df["segment"] = pd.Categorical(segment_df["segment"], categories=segment_order, ordered=True)
    segment_df = segment_df.sort_values("segment")

    fig3 = go.Figure(
        data=[
            go.Pie(
                labels=segment_df["segment"],
                values=segment_df["n"],
                hole=0.55,
                marker=dict(colors=[segment_colors.get(s, "#888") for s in segment_df["segment"]]),
                textinfo="label+percent",
            )
        ]
    )
    fig3.update_layout(**get_plotly_theme())
    fig3.update_layout(title=f"세그먼트 분포 (기준일: {end_date})")
    st.plotly_chart(fig3, width="stretch")

st.caption(
    "세그먼트 규칙(PRD 11.1절, 우선순위 신규→코어→참여→조회중심): 신규(가입 14일 이내) · "
    "코어(참여 기준 충족 + 최근 30일 유효 구독 또는 구매) · 참여(최근 30일 참여 행동 2종 이상) · "
    "조회중심(참여 기준 미달이지만 조회는 있음) · 미분류(둘 다 없음). "
    f"선택한 종료일({end_date}) 기준 최근 30일 윈도우로 계산했다."
)
