"""Page 3 — 팬 행동·커머스 퍼널 (PRD 12.5절).

팬 활동 수준과 상품 구매 전환의 차이를 확인하는 페이지.
"""

import sys
import textwrap
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from theme import COLORS, inject_theme, render_kpi, render_virtual_data_badge, get_plotly_theme  # noqa: E402
from data import (  # noqa: E402
    ANALYSIS_START,
    ANALYSIS_END,
    get_artist_list,
    get_commerce_funnel_summary,
    get_segment_conversion,
    get_revenue_summary,
    get_purchase_timing,
)

st.set_page_config(page_title="팬 행동·커머스 퍼널 · FANLOG", page_icon="🎤", layout="wide")
inject_theme()
render_virtual_data_badge()

st.title("팬 행동·커머스 퍼널")
st.caption("팬 활동 수준과 상품 구매 전환의 차이를 확인합니다 (PRD 12.5절).")

PALETTE = get_plotly_theme()["colorway"]
SEGMENT_ORDER = ["신규", "조회중심", "참여", "코어", "미분류"]


def _fmt_pct(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "계산 불가"
    return f"{value}%"


def _segment_row(df: pd.DataFrame, segment: str):
    """세그먼트 결과표에서 한 세그먼트 행을 꺼낸다. 표본이 없으면 None."""
    matched = df[df["segment"] == segment]
    if matched.empty or int(matched.iloc[0]["n"]) == 0:
        return None
    return matched.iloc[0]


# ------------------------------------------------------------------
# 사이드바 필터 (FR-002) — Page 1과 동일한 기간 필터 + 아티스트 다중선택
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

if not selected_artist_ids:
    st.warning("조건에 해당하는 데이터 없음 (아티스트를 최소 1개 이상 선택하세요)")
    st.stop()

all_artist_selected = set(selected_artist_ids) == set(artist_df["artist_id"].tolist())
artist_filter_text = "전체 아티스트" if all_artist_selected else ", ".join(
    artist_label_map[aid] for aid in selected_artist_ids
)

st.markdown(
    f"**적용 중인 필터**: {start_date} ~ {end_date} ({(end_date - start_date).days + 1}일) · "
    f"아티스트: {artist_filter_text}"
)

st.markdown("---")

# ------------------------------------------------------------------
# 1. 커머스 퍼널
# ------------------------------------------------------------------
st.markdown("## 1. 커머스 퍼널")

funnel_df = get_commerce_funnel_summary(start_date, end_date, selected_artist_ids)
revenue = get_revenue_summary(start_date, end_date, selected_artist_ids)

fcol, kcol = st.columns([3, 2])
with fcol:
    if funnel_df.empty or int(funnel_df.iloc[0]["n"]) == 0:
        st.info("조건에 해당하는 데이터 없음 (이 기간에 첫 관심이 발생한 (팬, 상품) 쌍이 없습니다)")
    else:
        # 라벨: 첫 단계는 인원만, 이후 단계는 인원 + 전 단계 대비 전환율.
        funnel_labels = [
            f"{int(r['n']):,}명" if pd.isna(r["pct_of_previous"])
            else f"{int(r['n']):,}명 · 전 단계 대비 {r['pct_of_previous']}%"
            for _, r in funnel_df.iterrows()
        ]
        fig1 = go.Figure(go.Funnel(
            y=funnel_df["stage"],
            x=funnel_df["n"],
            text=funnel_labels,
            textinfo="text",
            textposition="inside",
            marker=dict(color=PALETTE[:len(funnel_df)]),
            connector=dict(line=dict(color=COLORS["text_muted"], width=1)),
        ))
        fig1_theme = get_plotly_theme()
        fig1_theme["title"]["text"] = "열린 퍼널: 첫 관심 → 장바구니 → 결제 시작 → 구매 완료"
        fig1_theme["margin"] = {**fig1_theme["margin"], "l": 200}
        fig1.update_layout(**fig1_theme, height=380)
        st.plotly_chart(fig1, width="stretch")

with kcol:
    render_kpi("총매출", f"{revenue['total_revenue']:,}원")
    render_kpi("환불액", f"{revenue['total_refund']:,}원", gradient=False)
    render_kpi("환불률", _fmt_pct(revenue["refund_rate_pct"]), gradient=False)
    st.caption(
        f"환불률 = 환불(전액·부분) 주문 {revenue['refunded_orders']:,} / "
        f"결제 완료 주문 {revenue['total_completed_orders']:,}건."
    )

st.caption(
    "**매출·환불은 fact_order/fact_order_item 기준(마트가 아님)**이다. 퍼널 마트(mart_commerce_funnel)는 "
    "(팬, 상품) 쌍의 첫 관심만 추적하고 재구매를 다루지 않아 재무 지표의 정답 소스로 쓰지 않는다"
    "(`docs/decisions_log.md` 9절 마트 4/4). 아티스트를 일부만 선택하면 매출은 그 아티스트 상품 금액만, "
    "환불액은 상품 매출 비중으로 비례 배분한 근사치로 합산한다."
)

if not funnel_df.empty and int(funnel_df.iloc[0]["n"]) > 0:
    with st.expander("퍼널 단계별 상세 집계"):
        detail = funnel_df.copy()
        detail["prev_n"] = detail["n"].shift(1)
        detail_display = pd.DataFrame({
            "단계": detail["stage"],
            "인원((팬,상품) 쌍)": detail["n"].map(lambda v: f"{int(v):,}"),
            "전 단계 대비 전환(분자/분모)": detail.apply(
                lambda r: "-" if pd.isna(r["prev_n"]) else f"{int(r['n']):,} / {int(r['prev_n']):,}", axis=1),
            "전 단계 대비 전환율": detail["pct_of_previous"].map(
                lambda v: "-" if pd.isna(v) else f"{v}%"),
            "전 단계 대비 이탈률": detail["pct_of_previous"].map(
                lambda v: "-" if pd.isna(v) else f"{round(100 - v, 1)}%"),
            "첫 관심 대비 비율": detail["pct_of_total"].map(_fmt_pct),
        })
        st.dataframe(detail_display, width="stretch", hide_index=True)
        st.caption(
            "열린 퍼널이므로 상품 조회 없이 장바구니 담기로 시작한 경로도 포함한다(PRD 14.2절, "
            "`docs/decisions_log.md` 5.6절). 순서·기간 조건까지 요구하는 닫힌 퍼널과는 다른 지표다. "
            "기간 필터는 첫 관심 발생일(KST) 기준."
        )

st.markdown("---")

# ------------------------------------------------------------------
# 2. 팬 세그먼트별 구매 전환
# ------------------------------------------------------------------
st.markdown("## 2. 팬 세그먼트별 구매 전환")

seg_official = get_segment_conversion(end_date, selected_artist_ids, core_definition="with_purchase")

if seg_official.empty:
    st.info("조건에 해당하는 데이터 없음")
else:
    seg_official = (
        seg_official.set_index("segment").reindex(SEGMENT_ORDER).dropna(subset=["n"]).reset_index()
    )

    fig2 = go.Figure(go.Bar(
        x=seg_official["segment"],
        y=seg_official["purchase_conversion_pct"],
        text=seg_official["purchase_conversion_pct"].map(lambda v: f"{v}%"),
        textposition="outside",
        marker_color=[PALETTE[SEGMENT_ORDER.index(s)] for s in seg_official["segment"]],
    ))
    fig2_theme = get_plotly_theme()
    fig2_theme["title"]["text"] = f"세그먼트별 구매 전환율 (기준일 {end_date}, 코어 = 공식 정의)"
    fig2.update_layout(**fig2_theme, showlegend=False, height=400)
    fig2.update_yaxes(title_text="구매 전환율(%)",
                      range=[0, max(float(seg_official["purchase_conversion_pct"].max()) * 1.2, 10)])
    st.plotly_chart(fig2, width="stretch")

    seg_display = pd.DataFrame({
        "세그먼트": seg_official["segment"],
        "팬 수(n)": seg_official["n"].map(lambda v: f"{int(v):,}"),
        "구매 전환(분자/분모)": seg_official.apply(
            lambda r: f"{int(r['n_buyers']):,} / {int(r['n']):,}", axis=1),
        "구매 전환율": seg_official["purchase_conversion_pct"].map(lambda v: f"{v}%"),
    })
    st.dataframe(seg_display, width="stretch", hide_index=True)
    st.caption(
        "세그먼트는 기준일(선택 기간 종료일) 직전 30일 행동으로 PRD 11.1절 규칙대로 분류한다. "
        "구매 전환율 = 분석 시작일~기준일 사이 구매 이벤트가 1건 이상 있는 팬 비율(분류에 쓴 30일 창과 "
        "다른 창을 써서 순환 계산을 피한다). 아티스트를 선택하면 그 아티스트를 팔로우한 팬으로 모집단을 "
        "제한한다. '미분류'는 PRD 4개 세그먼트 밖의 최근 30일 무활동 팬이다(`docs/decisions_log.md` 11.9절)."
    )

    engaged_row = _segment_row(seg_official, "참여")
    viewer_row = _segment_row(seg_official, "조회중심")
    if (
        engaged_row is not None and viewer_row is not None
        and engaged_row["purchase_conversion_pct"] < viewer_row["purchase_conversion_pct"]
    ):
        st.warning(
            f"⚠ 참여 세그먼트의 전환율({engaged_row['purchase_conversion_pct']}%)이 조회중심"
            f"({viewer_row['purchase_conversion_pct']}%)보다 낮게 나타났습니다 — 아래 섹션에서 원인을 확인하세요."
        )

st.markdown("---")

# ------------------------------------------------------------------
# 3. 코어 판정에서 구매 이력을 빼면? (docs/analysis_report.md 발견 3)
# ------------------------------------------------------------------
st.markdown("## 3. 코어 판정에서 구매 이력을 빼면?")

seg_counterfactual = get_segment_conversion(end_date, selected_artist_ids, core_definition="subscription_only")

official_engaged = _segment_row(seg_official, "참여") if not seg_official.empty else None
official_viewer = _segment_row(seg_official, "조회중심") if not seg_official.empty else None
cf_engaged = _segment_row(seg_counterfactual, "참여") if not seg_counterfactual.empty else None
cf_viewer = _segment_row(seg_counterfactual, "조회중심") if not seg_counterfactual.empty else None

if official_engaged is None or cf_engaged is None or official_viewer is None or cf_viewer is None:
    st.info("조건에 해당하는 데이터 없음 (이 조건에서는 '참여' 또는 '조회중심' 세그먼트 표본이 없어 비교할 수 없습니다)")
else:
    official_pct = float(official_engaged["purchase_conversion_pct"])
    cf_pct = float(cf_engaged["purchase_conversion_pct"])
    # 조회중심은 코어 정의와 무관하게 분류되므로 두 정의에서 값이 같아야 하지만, 비교는 재정의 결과 기준으로 한다.
    viewer_pct = float(cf_viewer["purchase_conversion_pct"])
    was_inverted = official_pct < float(official_viewer["purchase_conversion_pct"])
    moved_n = int(cf_engaged["n"]) - int(official_engaged["n"])

    if not was_inverted:
        verdict_msg = (
            "이 조건에서는 공식 정의에서도 '참여' 전환율이 '조회중심'보다 낮지 않아, 해소할 역전 자체가 "
            "없었습니다. 재정의 결과는 참고용으로만 봅니다."
        )
    elif cf_pct > viewer_pct:
        verdict_msg = (
            "<b>역전이 해소되었습니다</b> — 코어 판정의 구매 이력 조건이 참여 집단에서 고전환 인원을 "
            "미리 빼갔을 가능성을 시사합니다."
        )
    else:
        verdict_msg = (
            "<b>역전이 완전히 해소되지는 않았습니다</b> — 코어 판정의 구매 이력 조건만으로는 이 조건에서의 "
            "역전을 다 설명하지 못하며, 다른 요인(표본 크기, 기간·아티스트 구성 차이 등)이 함께 작용했을 수 있습니다."
        )

    card_html = textwrap.dedent(
        f"""\
    <div style="border-radius:14px; padding:2px; margin:8px 0;
                background: linear-gradient(90deg, {COLORS['brand_violet']}, {COLORS['brand_pink']});">
    <div style="background:{COLORS['surface']}; border-radius:12px; padding:18px 20px;">
    <div style="color:{COLORS['text_muted']}; font-size:0.82rem; margin-bottom:12px;">
    코어 판정을 "참여 기준 + (구독 또는 구매)"(공식)에서 "참여 기준 + 구독만"(재정의)으로 바꿔 '참여' 세그먼트를
    다시 계산한 반사실 비교 (`docs/decisions_log.md` 11.12절, `docs/analysis_report.md` 발견 3)
    </div>
    <div style="display:flex; flex-wrap:wrap; gap:40px; margin-bottom:10px;">
    <div>
    <div style="font-size:0.78rem; color:{COLORS['text_muted']};">참여 · 공식(구매 이력 포함)</div>
    <div style="font-size:1.5rem; font-weight:800; color:{COLORS['text_primary']};">{official_pct}%</div>
    <div style="font-size:0.85rem; color:{COLORS['text_muted']};">{int(official_engaged['n_buyers']):,} / {int(official_engaged['n']):,}명</div>
    </div>
    <div>
    <div style="font-size:0.78rem; color:{COLORS['text_muted']};">참여 · 재정의(구독만)</div>
    <div style="font-size:1.5rem; font-weight:800; color:{COLORS['brand_pink']};">{cf_pct}%</div>
    <div style="font-size:0.85rem; color:{COLORS['text_muted']};">{int(cf_engaged['n_buyers']):,} / {int(cf_engaged['n']):,}명</div>
    </div>
    <div>
    <div style="font-size:0.78rem; color:{COLORS['text_muted']};">비교 기준 · 조회중심</div>
    <div style="font-size:1.5rem; font-weight:800; color:{COLORS['text_muted']};">{viewer_pct}%</div>
    <div style="font-size:0.85rem; color:{COLORS['text_muted']};">{int(cf_viewer['n_buyers']):,} / {int(cf_viewer['n']):,}명</div>
    </div>
    </div>
    <div style="font-size:0.85rem; color:{COLORS['text_muted']};">
    재정의로 코어 → 참여로 이동한 팬: {moved_n:+,}명
    </div>
    <div style="margin-top:12px; font-size:0.92rem; color:{COLORS['text_primary']};">{verdict_msg}</div>
    </div>
    </div>
    """
    )
    st.markdown(card_html, unsafe_allow_html=True)
    st.caption(
        "재정의는 공식 지표를 대체하지 않는 반사실 확인용 계산이다. 공식 세그먼트 정의는 섹션 2의 결과를 따른다."
    )

st.markdown("---")

# ------------------------------------------------------------------
# 4. 구매까지 걸린 시간
# ------------------------------------------------------------------
st.markdown("## 4. 구매까지 걸린 시간")

timing_df = get_purchase_timing(start_date, end_date)

if timing_df.empty:
    st.info("조건에 해당하는 데이터 없음")
else:
    days = timing_df["days_to_purchase"].astype(float)
    total_n = len(days)

    # 24시간 이내 구매(전체의 약 79%)를 한 차트에 같이 넣으면 나머지 구간의 상대적 차이가 묻힌다.
    # 그래서 당일 구매는 KPI로만 보여주고, 차트는 1일 이상 걸린 구매만 대상으로 따로 그린다.
    within_24h_n = int((days < 1).sum())
    within_24h_pct = round(100 * within_24h_n / total_n, 1)
    late_days = days[days >= 1]
    late_n = len(late_days)

    tcol1, tcol2, tcol3 = st.columns(3)
    with tcol1:
        render_kpi("구매 완료 건수", f"{total_n:,}건", gradient=False)
    with tcol2:
        render_kpi("중앙값", f"{days.median():.1f}일")
    with tcol3:
        render_kpi("24시간 이내 구매 비율", f"{within_24h_pct}%", gradient=False)

    st.markdown("### 1일 이상 걸린 구매는 언제 이뤄졌나")

    if late_n == 0:
        st.info(f"이 기간의 구매 {total_n:,}건은 모두 24시간 이내에 이뤄졌습니다 (1일 이상 걸린 구매 없음).")
    else:
        # days_to_purchase는 소수점 일 단위라 [하한, 상한) 반열린 구간으로 자른다(예: 1~3일 = 1일 이상 4일 미만).
        late_buckets = [("1~3일", 1), ("4~7일", 4), ("8~14일", 8), ("15일 이상", 15)]
        bucket_labels = [label for label, _ in late_buckets]
        bucket_series = pd.cut(
            late_days,
            bins=[lo for _, lo in late_buckets] + [float("inf")],
            labels=bucket_labels,
            right=False,
        )
        # reindex로 0건인 구간도 행을 유지한다(막대 0 높이 + "0건" 라벨로 자연스럽게 표시).
        bucket_df = (
            bucket_series.value_counts().reindex(bucket_labels, fill_value=0)
            .rename_axis("bucket").reset_index(name="n")
        )
        # 분모는 전체 구매가 아니라 1일 이상 걸린 구매 수(late_n) — "늦게 구매한 건 안에서의 비율".
        bucket_df["pct"] = (100 * bucket_df["n"] / late_n).round(1)

        fig4 = go.Figure(go.Bar(
            x=bucket_df["bucket"],
            y=bucket_df["n"],
            text=bucket_df.apply(lambda r: f"{int(r['n']):,}건 ({r['pct']}%)", axis=1),
            textposition="outside",
            marker_color=PALETTE[0],
        ))
        fig4_theme = get_plotly_theme()
        fig4_theme["title"]["text"] = f"1일 이상 걸린 구매 {late_n:,}건의 소요 기간 구간별 분포"
        fig4.update_layout(**fig4_theme, height=380, showlegend=False)
        fig4.update_xaxes(title_text="소요 기간 구간")
        fig4.update_yaxes(title_text="구매 건수((팬,상품) 쌍)",
                          range=[0, max(float(bucket_df["n"].max()) * 1.2, 1)])
        st.plotly_chart(fig4, width="stretch")

        display_timing = pd.DataFrame({
            "소요 기간 구간": bucket_df["bucket"],
            "건수(분자/분모)": bucket_df["n"].map(lambda v: f"{int(v):,} / {late_n:,}"),
            "비율(1일 이상 구매 중)": bucket_df["pct"].map(lambda v: f"{v}%"),
        })
        st.dataframe(display_timing, width="stretch", hide_index=True)
        st.caption(
            f"이 차트는 24시간 이내 구매({within_24h_n:,}건, 전체의 {within_24h_pct}%)를 제외한 나머지 "
            f"{late_n:,}건만을 대상으로 한다 — 비율의 분모도 전체 {total_n:,}건이 아니라 {late_n:,}건이다. "
            "구간은 소수점 일 단위 소요 기간을 [하한, 상한)으로 자른 것이다(예: 1~3일 = 1일 이상 4일 미만)."
        )

    st.caption(
        "첫 관심 발생일로 기간을 필터링하며, **이 섹션은 아티스트 필터를 적용하지 않는다**"
        "(데이터 함수가 기간 필터만 지원 — 항상 전체 아티스트 기준)."
    )

st.markdown("---")

# ------------------------------------------------------------------
# 5. 인과관계 해석 시 유의할 점
# ------------------------------------------------------------------
st.markdown("## 5. 인과관계 해석 시 유의할 점")
st.info(
    "이 페이지의 모든 전환율과 매출 지표는 가상 데이터를 대상으로 한 것이며, 세그먼트 간 전환율 차이를 "
    "인과관계로 표현하지 않는다(PRD 14.6절). 참여 수준이 높은 팬이 원래 구매 성향도 높을 수 있는 선택 편향, "
    "상품 가격·출시 시기 등 동시 영향, 세그먼트 정의 자체가 만드는 순환성(섹션 3)을 배제하지 못하며, "
    "실제 서비스에 적용하려면 별도의 실제 데이터 분석과 실험이 필요하다(PRD 13.4절)."
)
