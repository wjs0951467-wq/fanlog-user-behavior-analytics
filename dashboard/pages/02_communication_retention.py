"""Page 2 — 아티스트 소통·리텐션 (PRD 12.4절).

아티스트 소통 변화와 팬 활동의 관계를 탐색하는 페이지.
"""

import sys
import textwrap
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from theme import COLORS, inject_theme, render_kpi, render_virtual_data_badge, get_plotly_theme  # noqa: E402
from data import (  # noqa: E402
    ANALYSIS_START,
    ANALYSIS_END,
    get_artist_list,
    get_communication_timeline,
    get_communication_timeline_weekly,
    get_retention_timeline,
    get_status_snapshot,
    get_risk_dormancy_by_gap_bucket,
    get_reactivation_rate,
    get_communication_wau_correlation,
    get_partial_correlation_controlling_signups,
)

st.set_page_config(page_title="아티스트 소통·리텐션 · FANLOG", page_icon="🎤", layout="wide")
inject_theme()
render_virtual_data_badge()

st.title("아티스트 소통·리텐션")
st.caption("아티스트 소통 변화와 팬 활동의 관계를 탐색합니다 (PRD 12.4절).")

PALETTE = get_plotly_theme()["colorway"]


def _fmt(value, suffix: str = "") -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "계산 불가"
    return f"{value}{suffix}"


# ------------------------------------------------------------------
# 사이드바 필터 (FR-002) — Page 1과 동일한 기간 필터 + 단일 아티스트 선택
# ------------------------------------------------------------------
artist_df = get_artist_list()
artist_ids = artist_df["artist_id"].tolist()
artist_label_map = dict(zip(artist_df["artist_id"], artist_df["artist_name"]))

with st.sidebar:
    st.markdown("### 필터")
    date_range = st.date_input(
        "기간",
        value=(ANALYSIS_START, ANALYSIS_END),
        min_value=ANALYSIS_START,
        max_value=ANALYSIS_END,
    )
    selected_artist_id = st.radio(
        "아티스트",
        options=artist_ids,
        index=0,
        format_func=lambda aid: artist_label_map.get(aid, aid),
    )

if not isinstance(date_range, tuple) or len(date_range) != 2:
    st.warning("기간을 시작일과 종료일 두 개 모두 선택해 주세요.")
    st.stop()

start_date, end_date = date_range
if start_date > end_date:
    st.warning("시작일이 종료일보다 늦습니다. 기간을 다시 선택해 주세요.")
    st.stop()

st.markdown(
    f"**적용 중인 필터**: {start_date} ~ {end_date} ({(end_date - start_date).days + 1}일) · "
    f"아티스트: **{artist_label_map[selected_artist_id]}**"
)

st.markdown("---")

# ------------------------------------------------------------------
# 1. 소통과 팬 활동의 흐름
# ------------------------------------------------------------------
st.markdown("## 1. 소통과 팬 활동의 흐름")

timeline_df = get_communication_timeline(selected_artist_id, start_date, end_date)

if timeline_df.empty:
    st.info("조건에 해당하는 데이터 없음")
else:
    retention = get_retention_timeline(selected_artist_id, start_date, end_date)
    weekly = retention["weekly"]
    channel_weekly = get_communication_timeline_weekly(selected_artist_id, start_date, end_date)

    st.caption(
        "차트는 주별(KST 월~일)로 합산해 흐름을 부드럽게 보여준다 — WAU와 동일한 주 경계를 쓴다. "
        "정확한 날짜별 수치는 아래 '일별 소통 상세 보기' 표를 확인한다."
    )

    # 채널 3개를 한 차트에 겹친 선으로 그렸더니 서로 얽혀 가독성이 나빴고(구버전), 4행 세로
    # 서브플롯(게시글/메시지/라이브/WAU 완전 분리)으로 바꿨더니 이번엔 채널끼리 나란히 비교하기가
    # 오히려 어려워졌다. 게시글·메시지·라이브를 barmode="group"으로 한 패널에 그려 같은 주 안에서
    # 세 채널을 바로 옆에서 비교할 수 있게 하고, WAU만 스케일이 달라 별도 패널(2행)에 둔다.
    fig1 = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
        row_heights=[0.6, 0.4],
    )
    # 부분 주(7일을 다 채우지 못한 주 — 이 데이터에서는 선택 기간 첫 주·마지막 주)는 막대
    # opacity를 낮춰(0.85 -> 0.45) "합산 일수가 다른, 덜 채워진 주"임을 시각적으로 구분한다.
    partial_mask = channel_weekly["is_partial_week"] if len(channel_weekly) else pd.Series(dtype=bool)
    bar_opacities = partial_mask.map({True: 0.45, False: 0.85}).tolist() if len(channel_weekly) else []

    fig1.add_trace(
        go.Bar(x=channel_weekly["week_start"], y=channel_weekly["post_count"],
               name="게시글", marker=dict(color=PALETTE[0], opacity=bar_opacities)),
        row=1, col=1,
    )
    fig1.add_trace(
        go.Bar(x=channel_weekly["week_start"], y=channel_weekly["message_count"],
               name="메시지", marker=dict(color=PALETTE[1], opacity=bar_opacities)),
        row=1, col=1,
    )
    fig1.add_trace(
        go.Bar(x=channel_weekly["week_start"], y=channel_weekly["live_count"],
               name="라이브", marker=dict(color=PALETTE[3], opacity=bar_opacities)),
        row=1, col=1,
    )
    if len(weekly):
        fig1.add_trace(
            go.Scatter(x=weekly["week_start"], y=weekly["wau"], name="WAU(주별)",
                       mode="lines+markers", connectgaps=True,
                       line=dict(color=PALETTE[2], width=3), marker=dict(size=6)),
            row=2, col=1,
        )

    plot_theme = get_plotly_theme()
    fig1.update_layout(
        paper_bgcolor=plot_theme["paper_bgcolor"],
        plot_bgcolor=plot_theme["plot_bgcolor"],
        font=plot_theme["font"],
        margin=dict(**{**plot_theme["margin"], "t": 70}),
        title=dict(text="주별 소통 채널별 추이 vs 주별 WAU", font=plot_theme["title"]["font"]),
        height=620,
        # 채널 구분을 이제 행 제목이 아니라 범례가 맡으므로 범례를 켜고, 왼쪽 제목과 겹치지
        # 않도록 우측 상단에 가로 배치한다.
        showlegend=True,
        legend=dict(**plot_theme["legend"], orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        barmode="group",
        bargap=0.3,       # 주(그룹) 사이 간격을 넉넉히 둬 그룹 경계를 뚜렷하게 한다.
        bargroupgap=0.08,  # 그룹 안 막대 3개는 촘촘하게 붙여 슬림하게 보이게 한다.
        # 두 패널(막대/WAU)이 같은 주 x축을 공유(shared_xaxes=True)하므로, x unified로
        # 마우스를 올린 주의 게시글/메시지/라이브/WAU 값을 한 툴팁에 모아 보여준다.
        hovermode="x unified",
    )
    grid_color = plot_theme["xaxis"]["gridcolor"]
    fig1.update_xaxes(gridcolor=grid_color, zerolinecolor=grid_color, linecolor=grid_color,
                       color=COLORS["text_muted"],
                       # 두 패널에 동시에 같은 x위치의 세로 기준선이 뜨도록 스파이크 라인을 켠다.
                       showspikes=True, spikemode="across", spikesnap="cursor",
                       spikethickness=1, spikedash="dot", spikecolor=COLORS["text_muted"])
    fig1.update_yaxes(gridcolor=grid_color, zerolinecolor=grid_color, linecolor=grid_color,
                       color=COLORS["text_muted"], tickfont=dict(size=13, color=COLORS["text_muted"]))

    channel_max = channel_weekly[["post_count", "message_count", "live_count"]].to_numpy().max()
    y_top = max(float(channel_max) * 1.15, 1.0)
    label_font = dict(size=14, color=COLORS["text_muted"])
    fig1.update_yaxes(title_text="건수", title_font=label_font, title_standoff=10, range=[0, y_top], row=1, col=1)
    fig1.update_yaxes(title_text="WAU", title_font=label_font, title_standoff=10, row=2, col=1)

    fig1.update_xaxes(showticklabels=False, row=1, col=1)
    fig1.update_xaxes(showticklabels=True, tickfont=dict(size=13, color=COLORS["text_muted"]),
                       # matches="x": 두 패널의 x축을 명시적으로 동일시해야 x unified 툴팁과
                       # 세로 기준선이 두 패널에 동시에 나타난다(shared_xaxes=True만으로는
                       # 눈금 표시만 감춰질 뿐 축이 실제로 연결되지 않는다).
                       matches="x", row=2, col=1)

    st.plotly_chart(fig1, width="stretch")
    if partial_mask.any():
        st.caption("옅은 막대(투명도 낮음) = 선택 기간 경계에 걸려 7일을 다 채우지 못한 부분 주(합산값이 다른 주보다 작게 보일 수 있음).")

    with st.expander("일별 소통 상세 보기"):
        wau_by_date = weekly.set_index("week_start")["wau"] if len(weekly) else pd.Series(dtype=float)
        detail_df = timeline_df[["activity_date_kst", "post_count", "message_count", "live_count"]].copy()
        detail_df["합계"] = (
            detail_df["post_count"] + detail_df["message_count"] + detail_df["live_count"]
        )
        dates = pd.to_datetime(detail_df["activity_date_kst"])
        week_starts = dates - pd.to_timedelta(dates.dt.weekday, unit="D")
        detail_df["WAU(그 주)"] = week_starts.map(wau_by_date)
        detail_df = detail_df.rename(columns={
            "activity_date_kst": "날짜", "post_count": "게시글", "message_count": "메시지",
            "live_count": "라이브",
        })
        st.dataframe(detail_df, width="stretch", hide_index=True)

    comm_days = int(timeline_df["had_communication"].sum())
    total_days = len(timeline_df)
    max_gap = timeline_df["days_since_last_communication"].max()
    max_gap_display = "계산 불가" if pd.isna(max_gap) else f"{int(max_gap)}일"

    kcol1, kcol2 = st.columns(2)
    with kcol1:
        render_kpi("소통 활동일수", f"{comm_days} / {total_days}일")
    with kcol2:
        render_kpi("최대 연속 공백일", max_gap_display, gradient=False)

    st.caption(
        "소통 활동일수 = 선택 기간 중 게시글·메시지·라이브가 하나 이상 있었던 날짜 수. "
        "최대 연속 공백일 = 그 기간 중 관측된 가장 긴 연속 무소통 일수(이 아티스트의 첫 소통 이전 "
        "구간은 공백일 계산 대상이 아니다). WAU = 이 아티스트에 귀속되는 핵심 활동 12종을 한 주 동안 "
        "수행한 고유 팬 수(PRD 8.1·8.2절)."
    )

st.markdown("---")

# ------------------------------------------------------------------
# 2. 소통 공백과 이탈·휴면
# ------------------------------------------------------------------
st.markdown("## 2. 소통 공백과 이탈·휴면")

snapshot = get_status_snapshot(selected_artist_id, end_date)
reactivation = get_reactivation_rate(selected_artist_id, start_date, end_date)

scol1, scol2, scol3 = st.columns(3)
with scol1:
    render_kpi("14일 이탈위험률", _fmt(snapshot["at_risk_pct"], "%"), gradient=False)
with scol2:
    render_kpi("30일 휴면율", _fmt(snapshot["dormant_pct"], "%"), gradient=False)
with scol3:
    render_kpi("재활성률(날짜 비율)", _fmt(reactivation["rate_pct"], "%"), gradient=False)

st.caption(
    f"14일 이탈위험률: {snapshot['at_risk_n']:,} / {snapshot['at_risk_denom']:,}명"
    f"(이전 30일 활동 팬 중, 기준일 {snapshot['as_of_date']}) · "
    f"30일 휴면율: {snapshot['dormant_n']:,} / {snapshot['total_n']:,}명 · "
    f"재활성률: {reactivation['reactivated_days']:,} / {reactivation['total_days']:,}일"
    "(재활성이 발생한 (팬,날짜) 비율 — PRD 8.2절 공식 정의(팬 단위 코호트 비율)와 분모가 다른 간이 지표)."
)

bucket_df = get_risk_dormancy_by_gap_bucket(selected_artist_id, start_date, end_date)
bucket_order = ["0일(당일 소통)", "1-3일", "4-7일", "8일 이상"]

if bucket_df.empty:
    st.info("조건에 해당하는 데이터 없음 (이 아티스트만 단일로 팔로우 중인 팬 표본이 없습니다)")
else:
    bucket_df = bucket_df.set_index("gap_bucket").reindex(bucket_order).reset_index()

    fig2 = go.Figure()
    fig2.add_trace(go.Bar(x=bucket_df["gap_bucket"], y=bucket_df["at_risk_pct"],
                          name="14일 이탈위험률(%)", marker_color=PALETTE[0]))
    fig2.add_trace(go.Bar(x=bucket_df["gap_bucket"], y=bucket_df["dormant_pct"],
                          name="30일 휴면율(%)", marker_color=PALETTE[1]))
    fig2_theme = get_plotly_theme()
    fig2_theme["title"]["text"] = "소통 공백 구간별 14일 이탈위험률·30일 휴면율 (단일 팔로우 팬 기준)"
    fig2.update_layout(**fig2_theme, barmode="group")
    st.plotly_chart(fig2, width="stretch")

    display_bucket = pd.DataFrame({
        "소통 공백 구간": bucket_df["gap_bucket"],
        "표본(n)": bucket_df["n"].apply(lambda v: "-" if pd.isna(v) else f"{int(v):,}"),
        "14일 이탈위험(분자/분모)": bucket_df.apply(
            lambda r: "-" if pd.isna(r["n"]) else f"{int(r['at_risk_count']):,} / {int(r['n']):,}", axis=1),
        "14일 이탈위험률": bucket_df["at_risk_pct"].apply(lambda v: "-" if pd.isna(v) else f"{v}%"),
        "30일 휴면(분자/분모)": bucket_df.apply(
            lambda r: "-" if pd.isna(r["n"]) else f"{int(r['dormant_count']):,} / {int(r['n']):,}", axis=1),
        "30일 휴면율": bucket_df["dormant_pct"].apply(lambda v: "-" if pd.isna(v) else f"{v}%"),
    })
    st.dataframe(display_bucket, width="stretch", hide_index=True)
    st.caption(
        "정확히 이 아티스트 하나만 팔로우 중인 팬만 대상으로 한 결과다(다중 팔로우 팬을 포함한 "
        "전체 팬 기준 최솟값 공백 분석은 `docs/analysis_report.md` 발견 1 참고, 이 페이지 범위 밖). "
        "표본(n)이 '-'인 구간은 그 공백 길이에 해당하는 단일 팔로우 팬이 이 기간에 없었다는 뜻이다."
    )

st.markdown("---")

# ------------------------------------------------------------------
# 3. 소통 빈도와 팬 활동의 상관관계
# ------------------------------------------------------------------
st.markdown("## 3. 소통 빈도와 팬 활동의 상관관계")

corr = get_communication_wau_correlation(selected_artist_id, start_date, end_date)
concurrent, lag = corr["concurrent"], corr["lag"]

ccol1, ccol2 = st.columns(2)
with ccol1:
    with st.container(border=True):
        st.markdown("**동시(같은 주) 상관** — 소통 활동일수 vs WAU")
        if concurrent["available"]:
            st.markdown(f"r = **{concurrent['r']}**  ·  p = {concurrent['p']}  ·  n = {concurrent['n']}")
            st.markdown(f"95% CI: [{concurrent['ci_low']}, {concurrent['ci_high']}]")
        else:
            st.markdown("이 기간에는 상관계수를 계산하기에 표본이 부족합니다.")
with ccol2:
    with st.container(border=True):
        st.markdown("**1주 시차 상관** — 이번 주 소통일수 vs 다음 주 WAU")
        if lag["available"]:
            st.markdown(f"r = **{lag['r']}**  ·  p = {lag['p']}  ·  n = {lag['n']}")
            st.markdown(f"95% CI: [{lag['ci_low']}, {lag['ci_high']}]")
        else:
            st.markdown("이 기간에는 상관계수를 계산하기에 표본이 부족합니다.")

st.caption(
    "Spearman 순위 상관, 95% 신뢰구간은 Fisher z 변환 기준. 완전한 주(7일이 모두 관측된 주)만 "
    "사용했다. 표본이 작을 때(n<15)는 신뢰구간이 넓어질 수 있어 점추정치 r만으로 판단하지 않는다"
    "(`docs/decisions_log.md` 11.1절). 상관관계이며 인과관계로 해석하지 않는다."
)

st.markdown("### 누적 가입자 수를 통제하면?")
partial = get_partial_correlation_controlling_signups(selected_artist_id, start_date, end_date)

if not partial["available"]:
    st.info(f"이 기간에는 상관계수를 계산하기에 표본이 부족합니다 ({partial.get('reason', '')}).")
else:
    orig_sign = partial["r_original"] >= 0
    partial_sign = partial["r_partial"] >= 0
    if orig_sign != partial_sign:
        flip_msg = (
            "<b>부호가 반전되었습니다</b> — 이는 시간 추세 등 교란 변수가 착시를 만들었을 "
            "가능성을 시사합니다."
        )
    else:
        flip_msg = "통제 후에도 방향이 유지되었습니다."

    p_partial_display = "-" if partial["p_partial"] is None else partial["p_partial"]
    card_html = textwrap.dedent(
        f"""\
    <div style="border-radius:14px; padding:2px; margin:8px 0;
                background: linear-gradient(90deg, {COLORS['brand_violet']}, {COLORS['brand_pink']});">
    <div style="background:{COLORS['surface']}; border-radius:12px; padding:18px 20px;">
    <div style="color:{COLORS['text_muted']}; font-size:0.82rem; margin-bottom:12px;">
    그 주 마지막 날 기준 누적 가입자 수를 통제 변수로 넣은 1차 편(partial) Spearman 상관계수
    (`docs/decisions_log.md` 11.7절 로직)
    </div>
    <div style="display:flex; gap:40px; margin-bottom:10px;">
    <div>
    <div style="font-size:0.78rem; color:{COLORS['text_muted']};">원본 상관</div>
    <div style="font-size:1.5rem; font-weight:800; color:{COLORS['text_primary']};">r = {partial['r_original']}</div>
    </div>
    <div>
    <div style="font-size:0.78rem; color:{COLORS['text_muted']};">편상관(통제 후)</div>
    <div style="font-size:1.5rem; font-weight:800; color:{COLORS['brand_pink']};">r = {partial['r_partial']}</div>
    </div>
    </div>
    <div style="font-size:0.85rem; color:{COLORS['text_muted']};">
    p = {p_partial_display} · n = {partial['n']} · 95% CI: [{partial['ci_low']}, {partial['ci_high']}]
    </div>
    <div style="margin-top:12px; font-size:0.92rem; color:{COLORS['text_primary']};">{flip_msg}</div>
    </div>
    </div>
    """
    )
    st.markdown(card_html, unsafe_allow_html=True)

st.markdown("---")

# ------------------------------------------------------------------
# 4. 인과관계 해석 시 유의할 점
# ------------------------------------------------------------------
st.markdown("## 4. 인과관계 해석 시 유의할 점")
st.info(
    "이 페이지의 모든 상관계수와 비율은 가상 데이터를 대상으로 한 것이며, 상관관계를 인과관계로 "
    "표현하지 않는다(PRD 14.6절). 컴백·공연 등 동시 영향, 표본 크기, 선택 편향(활동성 높은 팬이 "
    "원래 소통에 더 자주 노출) 가능성을 배제하지 못하며, 실제 서비스에 적용하려면 별도의 실제 "
    "데이터 분석과 실험이 필요하다(PRD 13.4절)."
)
