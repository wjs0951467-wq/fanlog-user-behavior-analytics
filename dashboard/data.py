"""FANLOG 대시보드 데이터 접근 계층.

PostgreSQL 접속은 `src/analysis/db.py`의 `get_engine()`을 그대로 재사용한다
(`src/ingestion/load_to_postgres.py`와 동일한 `.env` 접속 정보를 쓰는 SQLAlchemy 엔진).
모든 조회 함수는 `@st.cache_data(ttl=300)`로 캐싱한다.

## 설계 메모(문서에 명시되지 않아 이 모듈에서 판단한 부분)

- **아티스트 필터의 의미**: PRD FR-002는 "기간과 아티스트 전역 필터"라고만 명시하고,
  DAU·WAU·W1재방문율·14일이탈위험률처럼 아티스트에 직접 귀속되지 않는 팬 단위 지표를
  아티스트로 어떻게 필터링할지는 정의하지 않는다. 여기서는 "그 아티스트에 귀속되는
  이벤트만 집계"가 아니라 **"그 아티스트를 팔로우 중인 팬 집단으로 모집단을 제한"**하는
  방식을 택했다(`_population_user_ids`). 콘텐츠 참여율·구매 전환율은 콘텐츠/상품에
  artist_id가 직접 있으므로 이벤트 자체를 아티스트로 필터링한다.
- **DAU/WAU 표시값**: 특정 하루·한 주의 스냅샷이 아니라, 선택한 기간 내 **일평균 DAU /
  주평균 WAU**로 정의했다(기간 필터와 자연스럽게 맞물리도록).
- **W1 참여 재방문율**: `notebooks/03_commerce_funnel.ipynb`(`docs/decisions_log.md` 11.10절)의
  방식을 그대로 재사용한다 — 선택 기간 내 핵심 활동일마다 그 후 1~7일 이내 재활동이 있었는지
  날짜 단위로 집계한 인스턴스 기반 비율이며, 관측 가능한 7일 창이 없는 기간 끝 7일은 제외한다.
- **상품 조회→구매 전환율**: `mart_commerce_funnel.is_closed_funnel_complete`(PRD 8.3절
  "동일 팬·상품, 첫 조회 후 7일 이내" 순서 기반 닫힌 퍼널) 기준이다. 분모는 그 기간 첫 관심
  (조회 또는 장바구니 담기) 전체이며, "조회자만" 별도로 좁히지는 않았다(PRD 8.3절이 요구하는
  "현재 계산 방식 표시"는 페이지의 캡션으로 제공한다).
"""

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from analysis.db import get_engine  # noqa: E402

# 데이터 생성 스크립트가 고정한 분석 기간 (sql/marts/*.sql의 date_spine과 동일)
ANALYSIS_START = dt.date(2026, 1, 1)
ANALYSIS_END = dt.date(2026, 3, 31)

PARTICIPATION_EVENTS = ["content_like", "comment_create", "message_open", "live_view_start"]


def _sql_in_list(values) -> str:
    """문자열 값 목록을 SQL IN 절에 쓸 수 있는 `('a','b')` 형태로 만든다.
    값은 전부 내부 ID(artist_id/user_id)라 자유 텍스트 인젝션 위험이 없다."""
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


@st.cache_data(ttl=300)
def get_data_generation_meta() -> dict | None:
    """meta_generation_run에서 가장 최근 실행 기록 1건을 가져온다."""
    engine = get_engine()
    df = pd.read_sql(
        "SELECT config_version, random_seed, scenario, generated_at_utc "
        "FROM meta_generation_run ORDER BY generated_at_utc DESC LIMIT 1;",
        engine,
    )
    if df.empty:
        return None
    return df.iloc[0].to_dict()


@st.cache_data(ttl=300)
def get_artist_list() -> pd.DataFrame:
    engine = get_engine()
    return pd.read_sql(
        "SELECT artist_id, artist_name, artist_type, debut_year FROM dim_artist ORDER BY artist_id;",
        engine,
    )


def _population_user_ids(artist_ids: list[str] | None, start_date: dt.date, end_date: dt.date) -> list[str] | None:
    """artist_ids가 없거나 전체 아티스트를 포함하면 None(모집단 제한 없음)을 반환한다.
    부분집합이면 그 기간 동안 하나라도 활성 팔로우 상태였던 팬 user_id 리스트를 반환한다."""
    all_artist_ids = set(get_artist_list()["artist_id"].tolist())
    if not artist_ids or set(artist_ids) >= all_artist_ids:
        return None
    engine = get_engine()
    query = f"""
        SELECT DISTINCT user_id FROM bridge_user_artist_follow
        WHERE artist_id IN {_sql_in_list(artist_ids)}
          AND (followed_at_utc AT TIME ZONE 'Asia/Seoul')::date <= '{end_date}'::date
          AND (unfollowed_at_utc IS NULL OR (unfollowed_at_utc AT TIME ZONE 'Asia/Seoul')::date >= '{start_date}'::date)
    """
    return pd.read_sql(query, engine)["user_id"].tolist()


def _kpis_for_range(engine, start_date: dt.date, end_date: dt.date, pop_ids, artist_ids) -> dict:
    """선택된 하나의 기간(현재 또는 이전 동일 기간)에 대해 6개 KPI를 계산한다."""
    pop_filter = f"AND user_id IN {_sql_in_list(pop_ids)}" if pop_ids is not None else ""
    n_days = (end_date - start_date).days + 1

    # 1) 일평균 DAU
    daily = pd.read_sql(
        f"""
        SELECT activity_date_kst,
               COUNT(DISTINCT CASE WHEN had_core_activity THEN user_id END) AS dau
        FROM mart_user_daily
        WHERE activity_date_kst BETWEEN '{start_date}' AND '{end_date}' {pop_filter}
        GROUP BY activity_date_kst;
        """,
        engine,
    )
    dau = round(daily["dau"].mean(), 1) if len(daily) else None

    # 2) 주평균 WAU (KST 월~일 주 단위)
    weekly = pd.read_sql(
        f"""
        SELECT date_trunc('week', activity_date_kst)::date AS week_start,
               COUNT(DISTINCT CASE WHEN had_core_activity THEN user_id END) AS wau
        FROM mart_user_daily
        WHERE activity_date_kst BETWEEN '{start_date}' AND '{end_date}' {pop_filter}
        GROUP BY 1;
        """,
        engine,
    )
    wau = round(weekly["wau"].mean(), 1) if len(weekly) else None

    # 3) W1 참여 재방문율 (인스턴스 기반, 03_commerce_funnel.ipynb 11.10절과 동일 방식)
    core_daily = pd.read_sql(
        f"""
        SELECT user_id, activity_date_kst, had_core_activity
        FROM mart_user_daily
        WHERE activity_date_kst BETWEEN '{start_date}' AND '{end_date}' {pop_filter};
        """,
        engine,
    )
    w1_eligible = w1_returned = 0
    if len(core_daily):
        core_daily["activity_date_kst"] = pd.to_datetime(core_daily["activity_date_kst"])
        last_observable_baseline = pd.Timestamp(end_date) - pd.Timedelta(days=7)
        for _, g in core_daily.groupby("user_id"):
            active_dates = set(g.loc[g["had_core_activity"], "activity_date_kst"])
            for d in active_dates:
                if d > last_observable_baseline:
                    continue
                w1_eligible += 1
                if any((d + pd.Timedelta(days=k)) in active_dates for k in range(1, 8)):
                    w1_returned += 1
    w1_return_rate_pct = round(100 * w1_returned / w1_eligible, 1) if w1_eligible > 0 else None

    # 4) 14일 이탈위험률 (기준일 = end_date)
    status_counts = pd.read_sql(
        f"""
        SELECT activity_status, COUNT(*) AS n
        FROM mart_user_daily
        WHERE activity_date_kst = '{end_date}' {pop_filter}
        GROUP BY activity_status;
        """,
        engine,
    )
    status_map = dict(zip(status_counts["activity_status"], status_counts["n"]))
    at_risk_n = int(status_map.get("at_risk", 0))
    at_risk_denom = at_risk_n + int(status_map.get("active", 0))
    at_risk_pct = round(100 * at_risk_n / at_risk_denom, 1) if at_risk_denom > 0 else None

    # 5) 콘텐츠 참여율 (콘텐츠 artist_id로 직접 필터, 모집단 필터와 별개)
    artist_filter = f"AND c.artist_id IN {_sql_in_list(artist_ids)}" if artist_ids and pop_ids is not None else ""
    content_stats = pd.read_sql(
        f"""
        WITH viewers AS (
            SELECT DISTINCT e.user_id FROM fact_user_event e
            JOIN dim_content c ON c.content_id = e.content_id
            WHERE e.event_name = 'content_view'
              AND e.event_date_kst BETWEEN '{start_date}' AND '{end_date}' {artist_filter}
        ),
        engagers AS (
            SELECT DISTINCT e.user_id FROM fact_user_event e
            JOIN dim_content c ON c.content_id = e.content_id
            WHERE e.event_name IN ('content_like', 'comment_create')
              AND e.event_date_kst BETWEEN '{start_date}' AND '{end_date}' {artist_filter}
        )
        SELECT
            (SELECT COUNT(*) FROM viewers) AS unique_viewers,
            (SELECT COUNT(*) FROM viewers v JOIN engagers en ON en.user_id = v.user_id) AS unique_engagers;
        """,
        engine,
    ).iloc[0]
    content_viewers_n = int(content_stats["unique_viewers"])
    content_engagers_n = int(content_stats["unique_engagers"])
    content_engagement_pct = (
        round(100 * content_engagers_n / content_viewers_n, 1) if content_viewers_n > 0 else None
    )

    # 6) 상품 조회->구매 전환율 (mart_commerce_funnel, 닫힌 퍼널 기준)
    funnel_artist_filter = f"AND artist_id IN {_sql_in_list(artist_ids)}" if artist_ids and pop_ids is not None else ""
    funnel_stats = pd.read_sql(
        f"""
        SELECT COUNT(*) AS total_n,
               COUNT(*) FILTER (WHERE is_closed_funnel_complete) AS closed_n
        FROM mart_commerce_funnel
        WHERE first_touch_date_kst BETWEEN '{start_date}' AND '{end_date}' {funnel_artist_filter};
        """,
        engine,
    ).iloc[0]
    purchase_denom = int(funnel_stats["total_n"])
    purchase_n = int(funnel_stats["closed_n"])
    purchase_conversion_pct = round(100 * purchase_n / purchase_denom, 1) if purchase_denom > 0 else None

    return {
        "n_days": n_days,
        "dau": dau,
        "wau": wau,
        "w1_return_rate_pct": w1_return_rate_pct,
        "w1_eligible_days": w1_eligible,
        "w1_return_days": w1_returned,
        "at_risk_14d_pct": at_risk_pct,
        "at_risk_n": at_risk_n,
        "at_risk_denom": at_risk_denom,
        "content_engagement_pct": content_engagement_pct,
        "content_viewers_n": content_viewers_n,
        "content_engagers_n": content_engagers_n,
        "purchase_conversion_pct": purchase_conversion_pct,
        "purchase_n": purchase_n,
        "purchase_denom": purchase_denom,
    }


@st.cache_data(ttl=300)
def get_overview_kpis(start_date: dt.date, end_date: dt.date, artist_ids: list[str] | None) -> dict:
    """선택 기간·아티스트 필터로 Page 1 KPI 6종(+이전 동일 기간 대비)을 계산한다."""
    engine = get_engine()
    pop_ids = _population_user_ids(artist_ids, start_date, end_date)
    n_fans_in_scope = len(pop_ids) if pop_ids is not None else int(
        pd.read_sql("SELECT COUNT(*) AS n FROM dim_user;", engine).iloc[0]["n"]
    )

    current = _kpis_for_range(engine, start_date, end_date, pop_ids, artist_ids)

    period_len = (end_date - start_date).days + 1
    prev_end = start_date - dt.timedelta(days=1)
    prev_start = prev_end - dt.timedelta(days=period_len - 1)
    prev_available = prev_start >= ANALYSIS_START
    previous = None
    if prev_available:
        previous = _kpis_for_range(engine, prev_start, prev_end, pop_ids, artist_ids)

    return {
        "n_fans_in_scope": n_fans_in_scope,
        "current": current,
        "previous": previous,
        "prev_start": prev_start,
        "prev_end": prev_end,
        "prev_available": prev_available,
    }


@st.cache_data(ttl=300)
def get_artist_comparison(start_date: dt.date, end_date: dt.date) -> pd.DataFrame:
    """mart_artist_daily 기준 아티스트별 핵심 지표 비교."""
    engine = get_engine()
    return pd.read_sql(
        f"""
        SELECT
            a.artist_id,
            a.artist_name,
            SUM(CASE WHEN m.had_communication THEN 1 ELSE 0 END) AS communication_days,
            COUNT(*) AS total_days,
            ROUND(AVG(m.active_followers), 1) AS avg_active_followers,
            ROUND(AVG(m.engaged_fans), 1) AS avg_engaged_fans,
            ROUND(AVG(m.exposed_fans), 1) AS avg_exposed_fans,
            SUM(m.new_follows) AS total_new_follows,
            SUM(m.unfollows) AS total_unfollows
        FROM mart_artist_daily m
        JOIN dim_artist a ON a.artist_id = m.artist_id
        WHERE m.activity_date_kst BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY a.artist_id, a.artist_name
        ORDER BY a.artist_id;
        """,
        engine,
    )


@st.cache_data(ttl=300)
def get_low_engagement_content(
    start_date: dt.date, end_date: dt.date, artist_ids: list[str] | None, min_viewers: int = 5
) -> pd.DataFrame:
    """조회수는 높지만 참여율은 낮은 콘텐츠 상위 10개 (published_date_kst 기준 기간 필터)."""
    engine = get_engine()
    all_artist_ids = set(get_artist_list()["artist_id"].tolist())
    artist_filter = ""
    if artist_ids and not set(artist_ids) >= all_artist_ids:
        artist_filter = f"AND artist_id IN {_sql_in_list(artist_ids)}"
    return pd.read_sql(
        f"""
        SELECT content_id, artist_id, content_type, title, unique_viewers, unique_engagers,
               engagement_rate, published_date_kst
        FROM mart_content_performance
        WHERE published_date_kst BETWEEN '{start_date}' AND '{end_date}'
          AND unique_viewers >= {int(min_viewers)}
          {artist_filter}
        ORDER BY unique_viewers DESC, engagement_rate ASC NULLS LAST
        LIMIT 10;
        """,
        engine,
    )


def _classify_segment(row) -> str:
    """PRD 11.1절 세그먼트 규칙 (03_commerce_funnel.ipynb 4절 로직 재사용)."""
    if row["tenure_days"] <= 14:
        return "신규"
    is_engaged = row["participation_type_count"] >= 2
    if is_engaged and (row["has_active_subscription_in_window"] or row["has_purchase_in_window"]):
        return "코어"
    if is_engaged:
        return "참여"
    if row["has_view_activity"]:
        return "조회중심"
    return "미분류"


@st.cache_data(ttl=300)
def get_segment_distribution(as_of_date: dt.date, artist_ids: list[str] | None = None) -> pd.DataFrame:
    """PRD 11.1절 규칙으로 as_of_date 기준(최근 30일 윈도우) 세그먼트 분포를 계산한다."""
    engine = get_engine()
    window_start = as_of_date - dt.timedelta(days=29)
    pop_ids = _population_user_ids(artist_ids, window_start, as_of_date)
    pop_filter = f"AND u.user_id IN {_sql_in_list(pop_ids)}" if pop_ids is not None else ""

    query = f"""
        WITH window_events AS (
            SELECT user_id, event_name
            FROM fact_user_event
            WHERE (event_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date BETWEEN '{window_start}' AND '{as_of_date}'
              AND event_name IN ('content_view','artist_post_view','message_open',
                                  'content_like','comment_create','live_view_start','purchase')
        ),
        user_window_agg AS (
            SELECT user_id,
                bool_or(event_name IN ('content_view','artist_post_view','message_open')) AS has_view_activity,
                COUNT(DISTINCT CASE WHEN event_name IN ('content_like','comment_create','message_open','live_view_start')
                                    THEN event_name END) AS participation_type_count,
                bool_or(event_name = 'purchase') AS has_purchase_in_window
            FROM window_events
            GROUP BY user_id
        ),
        active_subscription AS (
            SELECT DISTINCT user_id
            FROM fact_message_subscription
            WHERE (started_at_utc AT TIME ZONE 'Asia/Seoul')::date <= '{as_of_date}'::date
              AND (ended_at_utc IS NULL OR (ended_at_utc AT TIME ZONE 'Asia/Seoul')::date >= '{window_start}'::date)
        )
        SELECT
            u.user_id, u.signup_date_kst,
            COALESCE(w.has_view_activity, false) AS has_view_activity,
            COALESCE(w.participation_type_count, 0) AS participation_type_count,
            COALESCE(w.has_purchase_in_window, false) AS has_purchase_in_window,
            (asub.user_id IS NOT NULL) AS has_active_subscription_in_window
        FROM dim_user u
        LEFT JOIN user_window_agg w ON w.user_id = u.user_id
        LEFT JOIN active_subscription asub ON asub.user_id = u.user_id
        WHERE 1=1 {pop_filter};
    """
    df = pd.read_sql(query, engine)
    if df.empty:
        return pd.DataFrame(columns=["segment", "n"])
    df["signup_date_kst"] = pd.to_datetime(df["signup_date_kst"])
    df["tenure_days"] = (pd.Timestamp(as_of_date) - df["signup_date_kst"]).dt.days
    df["segment"] = df.apply(_classify_segment, axis=1)
    counts = df["segment"].value_counts().rename_axis("segment").reset_index(name="n")
    return counts
