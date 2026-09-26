"""FANLOG 대시보드 공통 디자인 시스템.

색상·폰트 토큰과 Streamlit 기본 스타일을 덮어쓰는 CSS 주입 함수,
KPI·배지 렌더링 헬퍼, Plotly 다크 테마를 모아둔다.
모든 페이지는 이 모듈의 `inject_theme()`을 최상단에서 한 번 호출한다.
"""

import textwrap

import streamlit as st

# ============================================================
# 디자인 토큰 (임의로 값을 바꾸지 않는다)
# ============================================================

COLORS = {
    "deep_violet": "#14111F",
    "surface": "#1E1A2E",
    "brand_violet": "#8B5CF6",
    "brand_pink": "#EC4899",
    "signal_cyan": "#22D3EE",
    "text_primary": "#F2EFFA",
    "text_muted": "#9C93B5",
    "positive": "#34D399",
    "warning": "#FB7185",
}

FONT_FAMILY = "'Pretendard', -apple-system, BlinkMacSystemFont, sans-serif"
FONT_CDN_URL = "https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css"

# 기본 4색 + 세그먼트 도넛처럼 5개 구분색이 필요한 차트를 위한 5번째 색(positive, 연한 민트 그린).
# 카테고리가 4개 이하인 차트(예: 아티스트 3팀 막대 차트)는 앞 3~4색만 순서대로 쓰이므로 영향 없다.
_CATEGORY_PALETTE = [
    COLORS["brand_violet"],
    COLORS["brand_pink"],
    COLORS["signal_cyan"],
    "#F59E0B",
    COLORS["positive"],
]


def inject_theme() -> None:
    """Streamlit 기본 흰 배경·기본 카드 스타일을 FANLOG 다크 테마로 덮어쓴다."""
    c = COLORS
    # 주의: 이 문자열은 반드시 textwrap.dedent()로 공통 들여쓰기를 제거해야 한다.
    # st.markdown()은 내부적으로 CommonMark 파서를 쓰는데, 한 줄이라도 4칸 이상
    # 들여써져 있으면(이 함수 코드의 들여쓰기가 f-string 안으로 그대로 들어가면 8칸+)
    # "들여쓰기된 코드 블록"으로 해석돼 <style> 태그가 파싱되지 않고 화면에 그대로
    # 이스케이프된 텍스트로 노출된다(실제로 발생했던 버그, docs/decisions_log.md 참고).
    st.markdown(
        textwrap.dedent(
            f"""\
        <link rel="stylesheet" href="{FONT_CDN_URL}" />
        <style>
        html, body, [class*="css"], [class*="st-"] {{
            font-family: {FONT_FAMILY} !important;
        }}
        /* 위 전역 규칙이 Streamlit의 Material Symbols 아이콘(사이드바 접기 화살표 등)까지
           덮어써서 "keyboard_double_arrow_left" 같은 리게이처 텍스트가 아이콘 대신 그대로
           노출되는 버그가 있었다. 아이콘 요소(data-testid="stIconMaterial")는 원래
           아이콘 폰트(Material Symbols Rounded, Streamlit 자체 번들 폰트)를 그대로 쓰도록
           뒤에서 다시 지정해 덮어쓴다. */
        [data-testid="stIconMaterial"] {{
            font-family: "Material Symbols Rounded" !important;
        }}
        .stApp {{
            background-color: {c["deep_violet"]};
            color: {c["text_primary"]};
        }}
        /* 사이드바 */
        section[data-testid="stSidebar"] {{
            background-color: {c["surface"]};
            border-right: 1px solid rgba(255,255,255,0.06);
        }}
        section[data-testid="stSidebar"] * {{
            color: {c["text_primary"]};
        }}
        /* 기본 텍스트 요소 */
        h1, h2, h3, h4, h5, h6, p, span, label, div {{
            color: {c["text_primary"]};
        }}
        .stCaption, [data-testid="stCaptionContainer"] {{
            color: {c["text_muted"]} !important;
        }}
        /* st.metric 카드 — Streamlit 기본 SaaS 카드 느낌(둥근 테두리·그림자) 제거 */
        div[data-testid="stMetric"] {{
            background-color: transparent;
            border: none;
            box-shadow: none;
            border-radius: 0;
            padding: 0;
        }}
        div[data-testid="stMetricValue"] {{
            color: {c["text_primary"]};
            font-weight: 800;
        }}
        div[data-testid="stMetricLabel"] {{
            color: {c["text_muted"]};
            font-weight: 500;
        }}
        /* 일반 컨테이너·expander·dataframe의 카드형 그림자 최소화 */
        div[data-testid="stVerticalBlockBorderWrapper"],
        div[data-testid="stExpander"],
        .stDataFrame, .stTable {{
            background-color: {c["surface"]} !important;
            border: 1px solid rgba(255,255,255,0.06) !important;
            box-shadow: none !important;
            border-radius: 10px !important;
        }}
        /* 버튼·셀렉트박스 등 입력 위젯 */
        .stButton > button, .stDownloadButton > button {{
            background-color: {c["surface"]};
            color: {c["text_primary"]};
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 8px;
        }}
        div[data-baseweb="select"] > div, div[data-baseweb="input"] > div {{
            background-color: {c["surface"]};
            border-color: rgba(255,255,255,0.12);
            color: {c["text_primary"]};
        }}
        /* 구분선 */
        hr {{
            border-color: rgba(255,255,255,0.08);
        }}
        /* 상단 헤더 바 투명화 (배경과 이질감 없도록) */
        header[data-testid="stHeader"] {{
            background-color: {c["deep_violet"]};
        }}
        </style>
        """
        ),
        unsafe_allow_html=True,
    )


def render_kpi(label: str, value: str, delta: str | None = None, gradient: bool = True) -> None:
    """st.metric 대신 커스텀 HTML로 KPI 숫자를 렌더링한다.

    value의 굵기는 ExtraBold(800)이며, gradient=True면 brand_violet -> brand_pink
    그라데이션 텍스트(background-clip: text)를 적용한다. delta가 주어지면 부호에 따라
    positive/warning 색상과 화살표를 붙인다.
    """
    c = COLORS
    if gradient:
        value_style = (
            f"background: linear-gradient(90deg, {c['brand_violet']}, {c['brand_pink']});"
            "-webkit-background-clip: text; -webkit-text-fill-color: transparent;"
            "background-clip: text;"
        )
    else:
        value_style = f"color: {c['text_primary']};"

    delta_html = ""
    if delta is not None and delta != "":
        is_negative = delta.strip().startswith("-")
        delta_color = c["warning"] if is_negative else c["positive"]
        arrow = "▼" if is_negative else "▲"
        delta_text = delta.strip().lstrip("+-")
        delta_html = (
            f'<div style="font-size:0.85rem; font-weight:500; color:{delta_color}; margin-top:2px;">'
            f"{arrow} {delta_text}</div>"
        )

    st.markdown(
        textwrap.dedent(
            f"""\
        <div style="padding:4px 0;">
            <div style="font-size:0.8rem; font-weight:500; color:{c['text_muted']};
                        text-transform:uppercase; letter-spacing:0.04em;">{label}</div>
            <div style="font-size:2.1rem; font-weight:800; line-height:1.3; {value_style}">{value}</div>
            {delta_html}
        </div>
        """
        ),
        unsafe_allow_html=True,
    )


def render_virtual_data_badge() -> None:
    """"가상 데이터 프로젝트" 배지를 보라-핑크 그라데이션 알약 모양으로 렌더링한다 (FR-001)."""
    c = COLORS
    st.markdown(
        textwrap.dedent(
            f"""\
        <div style="
            display:inline-block; padding:5px 14px; border-radius:999px; margin-bottom:12px;
            background: linear-gradient(90deg, {c['brand_violet']}, {c['brand_pink']});
            color: #FFFFFF; font-size:0.78rem; font-weight:700; letter-spacing:0.02em;">
            가상 데이터 프로젝트
        </div>
        """
        ),
        unsafe_allow_html=True,
    )


def get_plotly_theme() -> dict:
    """Plotly 차트용 다크 템플릿(레이아웃) 딕셔너리.

    사용: fig.update_layout(**get_plotly_theme())
    카테고리 색상은 [brand_violet, brand_pink, signal_cyan, "#F59E0B", positive] 5색 순환
    (5개 구분색이 필요한 세그먼트 도넛 차트 등을 위해 positive를 5번째 색으로 추가했다).
    """
    c = COLORS
    grid_color = "rgba(242,239,250,0.08)"
    return {
        "colorway": _CATEGORY_PALETTE,
        "paper_bgcolor": c["surface"],
        "plot_bgcolor": c["surface"],
        "font": {"family": FONT_FAMILY, "color": c["text_primary"], "size": 13},
        "title": {"font": {"family": FONT_FAMILY, "color": c["text_primary"], "size": 16}},
        "legend": {
            "bgcolor": "rgba(0,0,0,0)",
            "font": {"color": c["text_muted"]},
        },
        "xaxis": {
            "gridcolor": grid_color,
            "zerolinecolor": grid_color,
            "linecolor": grid_color,
            "color": c["text_muted"],
        },
        "yaxis": {
            "gridcolor": grid_color,
            "zerolinecolor": grid_color,
            "linecolor": grid_color,
            "color": c["text_muted"],
        },
        "margin": {"l": 40, "r": 20, "t": 40, "b": 40},
    }
