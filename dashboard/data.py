"""FANLOG 대시보드 데이터 접근 계층.

모든 SQL은 `dashboard/db_backend.py`의 `run_query()`로 실행한다. 환경변수 `DEPLOY_MODE`에 따라
로컬 PostgreSQL(`postgres`, 기본값 — `src/analysis/db.py` 엔진 재사용) 또는 `data/processed/*.parquet`을
읽는 DuckDB(`duckdb`, 배포용)에서 같은 SQL 문자열이 그대로 실행된다.
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
from scipy.stats import norm, spearmanr
from scipy.stats import t as t_dist

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_backend import run_query  # noqa: E402  (DEPLOY_MODE에 따라 PostgreSQL/DuckDB 전환)

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
    """meta_generation_run에서 가장 최근 실행 기록 1건을 가져온다.
    db_backend.run_query()로 전환한 첫 파일럿 함수(PostgreSQL/DuckDB 두 모드 결과 일치 확인)."""
    df = run_query(
        "SELECT config_version, random_seed, scenario, generated_at_utc "
        "FROM meta_generation_run ORDER BY generated_at_utc DESC LIMIT 1;"
    )
    if df.empty:
        return None
    return df.iloc[0].to_dict()


@st.cache_data(ttl=300)
def get_artist_list() -> pd.DataFrame:
    return run_query(
        "SELECT artist_id, artist_name, artist_type, debut_year FROM dim_artist ORDER BY artist_id;"
    )


def _population_user_ids(artist_ids: list[str] | None, start_date: dt.date, end_date: dt.date) -> list[str] | None:
    """artist_ids가 없거나 전체 아티스트를 포함하면 None(모집단 제한 없음)을 반환한다.
    부분집합이면 그 기간 동안 하나라도 활성 팔로우 상태였던 팬 user_id 리스트를 반환한다."""
    all_artist_ids = set(get_artist_list()["artist_id"].tolist())
    if not artist_ids or set(artist_ids) >= all_artist_ids:
        return None
    query = f"""
        SELECT DISTINCT user_id FROM bridge_user_artist_follow
        WHERE artist_id IN {_sql_in_list(artist_ids)}
          AND (followed_at_utc AT TIME ZONE 'Asia/Seoul')::date <= '{end_date}'::date
          AND (unfollowed_at_utc IS NULL OR (unfollowed_at_utc AT TIME ZONE 'Asia/Seoul')::date >= '{start_date}'::date)
    """
    return run_query(query)["user_id"].tolist()


def _kpis_for_range(start_date: dt.date, end_date: dt.date, pop_ids, artist_ids) -> dict:
    """선택된 하나의 기간(현재 또는 이전 동일 기간)에 대해 6개 KPI를 계산한다."""
    pop_filter = f"AND user_id IN {_sql_in_list(pop_ids)}" if pop_ids is not None else ""
    n_days = (end_date - start_date).days + 1

    # 1) 일평균 DAU
    daily = run_query(
        f"""
        SELECT activity_date_kst,
               COUNT(DISTINCT CASE WHEN had_core_activity THEN user_id END) AS dau
        FROM mart_user_daily
        WHERE activity_date_kst BETWEEN '{start_date}' AND '{end_date}' {pop_filter}
        GROUP BY activity_date_kst;
        """
    )
    dau = round(daily["dau"].mean(), 1) if len(daily) else None

    # 2) 주평균 WAU (KST 월~일 주 단위)
    weekly = run_query(
        f"""
        SELECT date_trunc('week', activity_date_kst)::date AS week_start,
               COUNT(DISTINCT CASE WHEN had_core_activity THEN user_id END) AS wau
        FROM mart_user_daily
        WHERE activity_date_kst BETWEEN '{start_date}' AND '{end_date}' {pop_filter}
        GROUP BY 1;
        """
    )
    wau = round(weekly["wau"].mean(), 1) if len(weekly) else None

    # 3) W1 참여 재방문율 (인스턴스 기반, 03_commerce_funnel.ipynb 11.10절과 동일 방식)
    core_daily = run_query(
        f"""
        SELECT user_id, activity_date_kst, had_core_activity
        FROM mart_user_daily
        WHERE activity_date_kst BETWEEN '{start_date}' AND '{end_date}' {pop_filter};
        """
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
    status_counts = run_query(
        f"""
        SELECT activity_status, COUNT(*) AS n
        FROM mart_user_daily
        WHERE activity_date_kst = '{end_date}' {pop_filter}
        GROUP BY activity_status;
        """
    )
    status_map = dict(zip(status_counts["activity_status"], status_counts["n"]))
    at_risk_n = int(status_map.get("at_risk", 0))
    at_risk_denom = at_risk_n + int(status_map.get("active", 0))
    at_risk_pct = round(100 * at_risk_n / at_risk_denom, 1) if at_risk_denom > 0 else None

    # 5) 콘텐츠 참여율 (콘텐츠 artist_id로 직접 필터, 모집단 필터와 별개)
    artist_filter = f"AND c.artist_id IN {_sql_in_list(artist_ids)}" if artist_ids and pop_ids is not None else ""
    content_stats = run_query(
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
        """
    ).iloc[0]
    content_viewers_n = int(content_stats["unique_viewers"])
    content_engagers_n = int(content_stats["unique_engagers"])
    content_engagement_pct = (
        round(100 * content_engagers_n / content_viewers_n, 1) if content_viewers_n > 0 else None
    )

    # 6) 상품 조회->구매 전환율 (mart_commerce_funnel, 닫힌 퍼널 기준)
    funnel_artist_filter = f"AND artist_id IN {_sql_in_list(artist_ids)}" if artist_ids and pop_ids is not None else ""
    funnel_stats = run_query(
        f"""
        SELECT COUNT(*) AS total_n,
               COUNT(*) FILTER (WHERE is_closed_funnel_complete) AS closed_n
        FROM mart_commerce_funnel
        WHERE first_touch_date_kst BETWEEN '{start_date}' AND '{end_date}' {funnel_artist_filter};
        """
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
    pop_ids = _population_user_ids(artist_ids, start_date, end_date)
    n_fans_in_scope = len(pop_ids) if pop_ids is not None else int(
        run_query("SELECT COUNT(*) AS n FROM dim_user;").iloc[0]["n"]
    )

    current = _kpis_for_range(start_date, end_date, pop_ids, artist_ids)

    period_len = (end_date - start_date).days + 1
    prev_end = start_date - dt.timedelta(days=1)
    prev_start = prev_end - dt.timedelta(days=period_len - 1)
    prev_available = prev_start >= ANALYSIS_START
    previous = None
    if prev_available:
        previous = _kpis_for_range(prev_start, prev_end, pop_ids, artist_ids)

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
    return run_query(
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
        """
    )


@st.cache_data(ttl=300)
def get_low_engagement_content(
    start_date: dt.date, end_date: dt.date, artist_ids: list[str] | None, min_viewers: int = 5
) -> pd.DataFrame:
    """조회수는 높지만 참여율은 낮은 콘텐츠 상위 10개 (published_date_kst 기준 기간 필터)."""
    all_artist_ids = set(get_artist_list()["artist_id"].tolist())
    artist_filter = ""
    if artist_ids and not set(artist_ids) >= all_artist_ids:
        artist_filter = f"AND artist_id IN {_sql_in_list(artist_ids)}"
    return run_query(
        f"""
        SELECT content_id, artist_id, content_type, title, unique_viewers, unique_engagers,
               engagement_rate, published_date_kst
        FROM mart_content_performance
        WHERE published_date_kst BETWEEN '{start_date}' AND '{end_date}'
          AND unique_viewers >= {int(min_viewers)}
          {artist_filter}
        ORDER BY unique_viewers DESC, engagement_rate ASC NULLS LAST
        LIMIT 10;
        """
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
    df = run_query(query)
    if df.empty:
        return pd.DataFrame(columns=["segment", "n"])
    df["signup_date_kst"] = pd.to_datetime(df["signup_date_kst"])
    df["tenure_days"] = (pd.Timestamp(as_of_date) - df["signup_date_kst"]).dt.days
    df["segment"] = df.apply(_classify_segment, axis=1)
    counts = df["segment"].value_counts().rename_axis("segment").reset_index(name="n")
    return counts


# ============================================================
# Page 2 (아티스트 소통·리텐션) 전용 함수
# ============================================================
# 상관계수 관련 함수(get_communication_wau_correlation,
# get_partial_correlation_controlling_signups)는 notebooks/02_communication_retention.ipynb의
# H-01·11.7절 로직(Fisher z 신뢰구간, 1차 편상관 공식)을 단일 아티스트·선택 기간 기준으로 그대로
# 이식한 것이다. 노트북과 달리 표본이 너무 작은 경우(n<8) 대시보드에서는 계산 자체를 생략한다
# (노트북은 상관 n<5, 편상관 n<6 기준을 썼지만, 실사용자에게 노출되는 화면이라 더 보수적으로 잡았다).
_MIN_CORRELATION_N = 8


@st.cache_data(ttl=300)
def get_communication_timeline(artist_id: str, start_date: dt.date, end_date: dt.date) -> pd.DataFrame:
    """mart_artist_daily 기준 단일 아티스트의 일별 소통 현황."""
    return run_query(
        f"""
        SELECT activity_date_kst, post_count, message_count, live_count,
               had_communication, days_since_last_communication
        FROM mart_artist_daily
        WHERE artist_id = '{artist_id}' AND activity_date_kst BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY activity_date_kst;
        """
    )


def _week_start(dates: pd.Series) -> pd.Series:
    """KST 월~일 주 경계(월요일 시작)로 날짜를 그 주의 월요일로 변환한다(PRD 8.2절 WAU 정의와 동일).
    `_weekly_communication_wau_panel`(섹션 3 상관계수 계산의 기반)과 `get_communication_timeline_weekly`
    (섹션 1 차트)가 이 헬퍼 하나로 주 경계를 공유해, 같은 페이지 안에서 시계열 차트와 상관계수 분석이
    서로 다른 주 정의를 쓰는 모순이 생기지 않게 한다."""
    dates = pd.to_datetime(dates)
    return dates - pd.to_timedelta(dates.dt.weekday, unit="D")


@st.cache_data(ttl=300)
def get_communication_timeline_weekly(artist_id: str, start_date: dt.date, end_date: dt.date) -> pd.DataFrame:
    """단일 아티스트의 주별(KST 월~일, `_week_start()` 기준) 게시글/메시지/라이브 합계.
    반환 컬럼: week_start, post_count, message_count, live_count, days_observed(그 주에 실제
    관측된 날짜 수), is_partial_week(선택 기간 경계에 걸려 7일을 다 채우지 못한 주)."""
    daily = get_communication_timeline(artist_id, start_date, end_date)
    empty_cols = ["week_start", "post_count", "message_count", "live_count", "days_observed", "is_partial_week"]
    if daily.empty:
        return pd.DataFrame(columns=empty_cols)

    daily = daily.copy()
    daily["week_start"] = _week_start(daily["activity_date_kst"])
    weekly = daily.groupby("week_start").agg(
        post_count=("post_count", "sum"),
        message_count=("message_count", "sum"),
        live_count=("live_count", "sum"),
        days_observed=("activity_date_kst", "size"),
    ).reset_index()
    weekly["is_partial_week"] = weekly["days_observed"] < 7
    return weekly.sort_values("week_start").reset_index(drop=True)


def _fisher_z_ci(r: float, n: int, n_control_vars: int = 0, confidence: float = 0.95):
    """Fisher z 변환 기반 상관계수 신뢰구간 (02_communication_retention.ipynb와 동일 공식)."""
    dof = n - 3 - n_control_vars
    if dof <= 0 or pd.isna(r) or abs(r) >= 1:
        return (None, None)
    z = np.arctanh(r)
    se = 1 / np.sqrt(dof)
    z_crit = norm.ppf(1 - (1 - confidence) / 2)
    lo, hi = np.tanh(z - z_crit * se), np.tanh(z + z_crit * se)
    return (round(lo, 3), round(hi, 3))


def _weekly_communication_wau_panel(artist_id: str, start_date: dt.date, end_date: dt.date) -> pd.DataFrame:
    """단일 아티스트의 주별 소통 활동일수·WAU·참여 팬 수·참여율 패널.
    반환 컬럼: week_start, days_observed(그 주에 관측된 날짜 수), communication_days_per_week,
    wau, engaged_fans, engagement_rate(주간 아티스트 참여율, docs/decisions_log.md 11.2절 정의)."""
    comm_daily = run_query(
        f"""
        SELECT activity_date_kst, had_communication
        FROM mart_artist_daily
        WHERE artist_id = '{artist_id}' AND activity_date_kst BETWEEN '{start_date}' AND '{end_date}';
        """
    )
    empty_cols = ["week_start", "days_observed", "communication_days_per_week", "wau", "engaged_fans", "engagement_rate"]
    if comm_daily.empty:
        return pd.DataFrame(columns=empty_cols)

    comm_daily["activity_date_kst"] = pd.to_datetime(comm_daily["activity_date_kst"])
    comm_daily["week_start"] = comm_daily["activity_date_kst"] - pd.to_timedelta(
        comm_daily["activity_date_kst"].dt.weekday, unit="D"
    )
    weekly_comm = comm_daily.groupby("week_start").agg(
        days_observed=("had_communication", "size"),
        communication_days_per_week=("had_communication", "sum"),
    ).reset_index()

    weekly_wau = run_query(
        f"""
        WITH core_activity_by_artist AS (
            SELECT user_id, event_date_kst, event_name
            FROM fact_user_event
            WHERE artist_id = '{artist_id}'
              AND event_name IN ('artist_follow', 'message_subscription_start', 'artist_post_view', 'message_open',
                                  'live_view_start', 'content_view', 'content_like', 'comment_create')
            UNION ALL
            SELECT e.user_id, e.event_date_kst, e.event_name
            FROM fact_user_event e JOIN dim_content c ON c.content_id = e.content_id
            WHERE c.artist_id = '{artist_id}' AND e.event_name IN ('content_view', 'content_like', 'comment_create')
            UNION ALL
            SELECT e.user_id, e.event_date_kst, e.event_name
            FROM fact_user_event e JOIN dim_product p ON p.product_id = e.product_id
            WHERE p.artist_id = '{artist_id}' AND e.event_name IN ('view_item', 'add_to_cart')
            UNION ALL
            SELECT e.user_id, e.event_date_kst, e.event_name
            FROM fact_user_event e
            JOIN fact_order_item oi ON oi.transaction_id = e.transaction_id
            JOIN dim_product p ON p.product_id = oi.product_id
            WHERE p.artist_id = '{artist_id}' AND e.event_name IN ('begin_checkout', 'purchase')
        )
        SELECT
            date_trunc('week', event_date_kst)::date AS week_start,
            COUNT(DISTINCT user_id) AS wau,
            COUNT(DISTINCT CASE WHEN event_name IN ('content_like','comment_create','message_open','live_view_start')
                                THEN user_id END) AS engaged_fans
        FROM core_activity_by_artist
        WHERE event_date_kst BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY date_trunc('week', event_date_kst);
        """
    )
    weekly_wau["week_start"] = pd.to_datetime(weekly_wau["week_start"])

    panel = weekly_comm.merge(weekly_wau, on="week_start", how="left")
    panel[["wau", "engaged_fans"]] = panel[["wau", "engaged_fans"]].fillna(0)
    panel["engagement_rate"] = np.where(panel["wau"] > 0, panel["engaged_fans"] / panel["wau"], np.nan)
    return panel.sort_values("week_start").reset_index(drop=True)


@st.cache_data(ttl=300)
def get_retention_timeline(artist_id: str, start_date: dt.date, end_date: dt.date) -> dict:
    """주별 WAU·주간 아티스트 참여율 시계열과, 선택 기간 전체에 대한 W1 참여 재방문율(인스턴스
    기반, 03_commerce_funnel.ipynb 11.10절 방식)을 반환한다. 모집단은 이 아티스트를 팔로우하는
    팬 집단(dashboard/data.py 상단 설계 메모의 '아티스트 필터=팔로우 팬 집단' 방침과 동일)."""
    panel = _weekly_communication_wau_panel(artist_id, start_date, end_date)
    weekly = panel[["week_start", "wau", "engagement_rate"]].copy()

    pop_ids = _population_user_ids([artist_id], start_date, end_date)
    kpis = _kpis_for_range(start_date, end_date, pop_ids, [artist_id])

    return {
        "weekly": weekly,
        "w1_return_rate_pct": kpis["w1_return_rate_pct"],
        "w1_eligible_days": kpis["w1_eligible_days"],
        "w1_return_days": kpis["w1_return_days"],
    }


@st.cache_data(ttl=300)
def get_status_snapshot(artist_id: str, as_of_date: dt.date) -> dict:
    """이 아티스트를 팔로우하는 팬 집단의 as_of_date 기준 활동 상태 스냅샷
    (14일 이탈위험률·30일 휴면율, PRD 8.2절 정의)."""
    pop_ids = _population_user_ids([artist_id], as_of_date, as_of_date)
    pop_filter = f"AND user_id IN {_sql_in_list(pop_ids)}" if pop_ids is not None else ""
    status_counts = run_query(
        f"""
        SELECT activity_status, COUNT(*) AS n
        FROM mart_user_daily
        WHERE activity_date_kst = '{as_of_date}' {pop_filter}
        GROUP BY activity_status;
        """
    )
    status_map = dict(zip(status_counts["activity_status"], status_counts["n"]))
    active_n = int(status_map.get("active", 0))
    at_risk_n = int(status_map.get("at_risk", 0))
    dormant_n = int(status_map.get("dormant", 0))
    total_n = active_n + at_risk_n + dormant_n
    at_risk_denom = active_n + at_risk_n  # PRD 8.1절: "이전 30일 내 활동 있었던 팬 중"(dormant 제외)
    return {
        "as_of_date": as_of_date,
        "total_n": total_n,
        "active_n": active_n,
        "at_risk_n": at_risk_n,
        "dormant_n": dormant_n,
        "at_risk_pct": round(100 * at_risk_n / at_risk_denom, 1) if at_risk_denom > 0 else None,
        "at_risk_denom": at_risk_denom,
        "dormant_pct": round(100 * dormant_n / total_n, 1) if total_n > 0 else None,
    }


@st.cache_data(ttl=300)
def get_risk_dormancy_by_gap_bucket(artist_id: str, start_date: dt.date, end_date: dt.date) -> pd.DataFrame:
    """단일 아티스트 팔로우 팬(정확히 이 아티스트 하나만 팔로우 중인 팬) 기준, 소통 공백
    구간별 14일 이탈위험률·30일 휴면율 (notebooks/02_communication_retention.ipynb H-02 로직
    재사용). 다중 팔로우 팬을 포함한 전체 팬 기준 최솟값 공백 분석은 docs/analysis_report.md
    발견 1을 참고 — 이 페이지에서는 범위 밖이라 생략했다."""
    query = f"""
        WITH date_spine AS (
            SELECT DISTINCT activity_date_kst FROM mart_user_daily
            WHERE activity_date_kst BETWEEN '{start_date}' AND '{end_date}'
        ),
        active_follows AS (
            SELECT b.user_id, d.activity_date_kst, b.artist_id
            FROM bridge_user_artist_follow b
            CROSS JOIN date_spine d
            WHERE (b.followed_at_utc AT TIME ZONE 'Asia/Seoul')::date <= d.activity_date_kst
              AND (b.unfollowed_at_utc IS NULL OR (b.unfollowed_at_utc AT TIME ZONE 'Asia/Seoul')::date >= d.activity_date_kst)
        ),
        follow_counts AS (
            SELECT user_id, activity_date_kst, COUNT(DISTINCT artist_id) AS n_followed, MAX(artist_id) AS the_artist_id
            FROM active_follows
            GROUP BY user_id, activity_date_kst
        ),
        single_follow AS (
            SELECT user_id, activity_date_kst
            FROM follow_counts
            WHERE n_followed = 1 AND the_artist_id = '{artist_id}'
        )
        SELECT u.user_id, u.activity_date_kst, u.activity_status, a.days_since_last_communication
        FROM mart_user_daily u
        JOIN single_follow sf ON sf.user_id = u.user_id AND sf.activity_date_kst = u.activity_date_kst
        JOIN mart_artist_daily a ON a.artist_id = '{artist_id}' AND a.activity_date_kst = u.activity_date_kst;
    """
    df = run_query(query)
    empty_cols = ["gap_bucket", "n", "at_risk_count", "dormant_count", "at_risk_pct", "dormant_pct"]
    if df.empty:
        return pd.DataFrame(columns=empty_cols)

    bins = [-1, 0, 3, 7, 100]
    labels = ["0일(당일 소통)", "1-3일", "4-7일", "8일 이상"]
    df["gap_bucket"] = pd.cut(df["days_since_last_communication"], bins=bins, labels=labels)
    summary = df.groupby("gap_bucket", observed=True).agg(
        n=("user_id", "size"),
        at_risk_count=("activity_status", lambda s: (s == "at_risk").sum()),
        dormant_count=("activity_status", lambda s: (s == "dormant").sum()),
    ).reset_index()
    summary["at_risk_pct"] = round(100 * summary["at_risk_count"] / summary["n"], 2)
    summary["dormant_pct"] = round(100 * summary["dormant_count"] / summary["n"], 2)
    return summary


@st.cache_data(ttl=300)
def get_reactivation_rate(artist_id: str, start_date: dt.date, end_date: dt.date) -> dict:
    """이 아티스트를 팔로우하는 팬 집단의 (팬,날짜) 행 중 was_reactivated_today=true인 날의 비율.
    PRD 8.2절 공식 "재활성률"(분석 시작 시점 휴면 팬 중 재활성한 "팬" 비율, 팬 단위 코호트
    지표)과는 분모가 다른 간이 운영 지표(날짜 단위 스냅샷 비율)라는 점에 유의해야 한다."""
    pop_ids = _population_user_ids([artist_id], start_date, end_date)
    pop_filter = f"AND user_id IN {_sql_in_list(pop_ids)}" if pop_ids is not None else ""
    row = run_query(
        f"""
        SELECT COUNT(*) FILTER (WHERE was_reactivated_today) AS reactivated_days, COUNT(*) AS total_days
        FROM mart_user_daily
        WHERE activity_date_kst BETWEEN '{start_date}' AND '{end_date}' {pop_filter};
        """
    ).iloc[0]
    total_days = int(row["total_days"])
    reactivated_days = int(row["reactivated_days"])
    return {
        "rate_pct": round(100 * reactivated_days / total_days, 2) if total_days > 0 else None,
        "reactivated_days": reactivated_days,
        "total_days": total_days,
    }


def _correlation_report(x: pd.Series, y: pd.Series, min_n: int = _MIN_CORRELATION_N) -> dict:
    paired = pd.concat([x, y], axis=1).dropna()
    n = len(paired)
    if n < min_n:
        return {"available": False, "n": n, "reason": f"표본 부족(n={n}<{min_n})"}
    r, p = spearmanr(paired.iloc[:, 0], paired.iloc[:, 1])
    ci_low, ci_high = _fisher_z_ci(r, n)
    return {"available": True, "r": round(r, 3), "p": round(p, 4), "n": n, "ci_low": ci_low, "ci_high": ci_high}


@st.cache_data(ttl=300)
def get_communication_wau_correlation(artist_id: str, start_date: dt.date, end_date: dt.date) -> dict:
    """주별 소통 활동일수 vs WAU의 동시·1주 시차 Spearman 상관 (완전한 주(7일 전부 관측)만 사용,
    notebooks/02_communication_retention.ipynb H-01 로직 재사용). n<8이면 계산하지 않는다."""
    panel = _weekly_communication_wau_panel(artist_id, start_date, end_date)
    full = panel[panel["days_observed"] == 7].reset_index(drop=True)

    concurrent = _correlation_report(full["communication_days_per_week"], full["wau"])

    lagged = full.copy()
    lagged["week_start_next"] = lagged["week_start"] + pd.Timedelta(days=7)
    next_wau = full[["week_start", "wau"]].rename(columns={"week_start": "week_start_next", "wau": "wau_next"})
    lagged = lagged.merge(next_wau, on="week_start_next", how="inner")
    lag = _correlation_report(lagged["communication_days_per_week"], lagged["wau_next"])

    return {"concurrent": concurrent, "lag": lag, "n_full_weeks": len(full)}


@st.cache_data(ttl=300)
def get_partial_correlation_controlling_signups(artist_id: str, start_date: dt.date, end_date: dt.date) -> dict:
    """그 주 마지막 날 기준 누적 가입자 수를 통제 변수로 한 1차 편(partial) Spearman 상관계수
    (notebooks/02_communication_retention.ipynb 11.7절 로직 그대로 이식). n<8이면 계산하지 않는다."""
    min_n = _MIN_CORRELATION_N
    panel = _weekly_communication_wau_panel(artist_id, start_date, end_date)
    full = panel[panel["days_observed"] == 7].reset_index(drop=True)
    if len(full) < min_n:
        return {"available": False, "n": len(full), "reason": f"표본 부족(n={len(full)}<{min_n})"}

    signup_dates = pd.to_datetime(run_query("SELECT signup_date_kst FROM dim_user;")["signup_date_kst"])
    full = full.copy()
    full["week_end"] = full["week_start"] + pd.Timedelta(days=6)
    full["cumulative_signups"] = full["week_end"].apply(lambda d: int((signup_dates <= d).sum()))

    df = full[["communication_days_per_week", "wau", "cumulative_signups"]].dropna()
    n = len(df)
    if n < min_n:
        return {"available": False, "n": n, "reason": f"표본 부족(n={n}<{min_n})"}

    x, y, z = df["communication_days_per_week"], df["wau"], df["cumulative_signups"]
    r_xy, _ = spearmanr(x, y)
    r_xz, _ = spearmanr(x, z)
    r_yz, _ = spearmanr(y, z)
    denom = np.sqrt((1 - r_xz**2) * (1 - r_yz**2))
    if denom == 0:
        return {"available": False, "n": n, "reason": "통제 변수와 완전 상관이라 계산 불가"}
    r_partial = (r_xy - r_xz * r_yz) / denom
    dof = n - 3
    if dof > 0 and abs(r_partial) < 1:
        t_stat = r_partial * np.sqrt(dof / (1 - r_partial**2))
        p_partial = 2 * (1 - t_dist.cdf(abs(t_stat), dof))
    else:
        p_partial = np.nan
    ci_low, ci_high = _fisher_z_ci(r_partial, n, n_control_vars=1)
    return {
        "available": True,
        "r_original": round(r_xy, 3),
        "r_partial": round(r_partial, 3),
        "p_partial": round(p_partial, 4) if pd.notna(p_partial) else None,
        "n": n,
        "ci_low": ci_low,
        "ci_high": ci_high,
    }


# ============================================================
# Page 3 (팬 행동·커머스 퍼널) 전용 함수
# ============================================================
# 화면 구현은 다음 세션에서 진행하고, 이번에는 데이터 함수 4개만 추가한다(docs/decisions_log.md 참고).


@st.cache_data(ttl=300)
def get_commerce_funnel_summary(
    start_date: dt.date, end_date: dt.date, artist_ids: list[str] | None = None
) -> pd.DataFrame:
    """mart_commerce_funnel 기준 열린 퍼널(첫 관심(조회 또는 장바구니 담기)→장바구니 담기→결제
    시작→구매 완료) 단계별 인원과 단계 간 전환율. artist_ids가 주어지면 마트의 artist_id
    (=dim_product.artist_id, 상품 소속 아티스트) 컬럼으로 필터링한다.

    '열린 퍼널'이므로 view_item 없이 add_to_cart로 시작한 경로도 포함하고(reached_* 플래그 그대로
    사용), 순서·7일 이내 조건까지 요구하는 닫힌 퍼널(is_closed_funnel_complete)과는 다르다
    (PRD 14.2절 "열린 퍼널과 순서 기반 닫힌 퍼널 분리" 원칙)."""
    all_artist_ids = set(get_artist_list()["artist_id"].tolist())
    artist_filter = ""
    if artist_ids and not set(artist_ids) >= all_artist_ids:
        artist_filter = f"AND artist_id IN {_sql_in_list(artist_ids)}"

    stats = run_query(
        f"""
        SELECT
            COUNT(*) AS n_first_touch,
            COUNT(*) FILTER (WHERE reached_add_to_cart) AS n_add_to_cart,
            COUNT(*) FILTER (WHERE reached_checkout) AS n_checkout,
            COUNT(*) FILTER (WHERE reached_purchase) AS n_purchase
        FROM mart_commerce_funnel
        WHERE first_touch_date_kst BETWEEN '{start_date}' AND '{end_date}' {artist_filter};
        """
    ).iloc[0]

    stages = [
        ("첫 관심(조회 또는 장바구니 담기)", int(stats["n_first_touch"])),
        ("장바구니 담기", int(stats["n_add_to_cart"])),
        ("결제 시작", int(stats["n_checkout"])),
        ("구매 완료", int(stats["n_purchase"])),
    ]
    total_n = stages[0][1]
    prev_n = None
    rows = []
    for label, n in stages:
        rows.append({
            "stage": label,
            "n": n,
            "pct_of_total": round(100 * n / total_n, 1) if total_n > 0 else None,
            "pct_of_previous": round(100 * n / prev_n, 1) if prev_n else None,
        })
        prev_n = n
    return pd.DataFrame(rows)


def _classify_segment_variant(row, core_definition: str) -> str:
    """`_classify_segment`와 동일한 규칙이되, 코어 판정 조건을 core_definition으로 바꿀 수 있다
    (03_commerce_funnel.ipynb 11.12절 반사실 재검증 로직)."""
    if row["tenure_days"] <= 14:
        return "신규"
    is_engaged = row["participation_type_count"] >= 2
    if core_definition == "subscription_only":
        is_core = is_engaged and row["has_active_subscription_in_window"]
    else:
        is_core = is_engaged and (row["has_active_subscription_in_window"] or row["has_purchase_in_window"])
    if is_core:
        return "코어"
    if is_engaged:
        return "참여"
    if row["has_view_activity"]:
        return "조회중심"
    return "미분류"


@st.cache_data(ttl=300)
def get_segment_conversion(
    as_of_date: dt.date, artist_ids: list[str] | None = None, core_definition: str = "with_purchase"
) -> pd.DataFrame:
    """PRD 11.1절 세그먼트 규칙(as_of_date 기준 최근 30일 윈도우)으로 세그먼트별 구매 전환율을 계산한다.

    core_definition:
    - `"with_purchase"`(공식): 코어 = 참여 기준(2종 이상) 충족 AND (최근 30일 유효 구독 OR 최근 30일 구매)
    - `"subscription_only"`(반사실, 03_commerce_funnel.ipynb 11.12절 재정의): 코어 = 참여 기준 충족 AND
      최근 30일 유효 구독만(구매 이력 조건 제거). "참여" 세그먼트가 코어 판정의 구매 이력 조건 때문에
      고전환 인원을 먼저 빼앗기는 정의상 순환성을 확인하기 위한 반사실 재계산이며, 노트북에서
      전체 팬(artist_ids 없음) 기준으로 참여 전환율이 27.4%(원래) -> 40.6%(재정의)로 바뀌는 것을 확인했다.

    구매 전환율의 분자(구매 팬 수)는 세그먼트 분류에 쓰인 30일 윈도우가 아니라
    ANALYSIS_START~as_of_date 전체 기간의 purchase 이벤트 유무로 계산한다(03_commerce_funnel.ipynb
    5절과 동일 — 분류에 쓰인 것과 같은 창으로 전환율을 재면 정의를 확인하는 순환 계산이 된다)."""
    if core_definition not in ("with_purchase", "subscription_only"):
        raise ValueError("core_definition은 'with_purchase' 또는 'subscription_only'여야 한다")

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
        ),
        full_period_purchase AS (
            SELECT DISTINCT user_id FROM fact_user_event
            WHERE event_name = 'purchase'
              AND (event_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date BETWEEN '{ANALYSIS_START}' AND '{as_of_date}'
        )
        SELECT
            u.user_id, u.signup_date_kst,
            COALESCE(w.has_view_activity, false) AS has_view_activity,
            COALESCE(w.participation_type_count, 0) AS participation_type_count,
            COALESCE(w.has_purchase_in_window, false) AS has_purchase_in_window,
            (asub.user_id IS NOT NULL) AS has_active_subscription_in_window,
            (fpp.user_id IS NOT NULL) AS has_purchase_full_period
        FROM dim_user u
        LEFT JOIN user_window_agg w ON w.user_id = u.user_id
        LEFT JOIN active_subscription asub ON asub.user_id = u.user_id
        LEFT JOIN full_period_purchase fpp ON fpp.user_id = u.user_id
        WHERE 1=1 {pop_filter};
    """
    df = run_query(query)
    empty_cols = ["segment", "n", "n_buyers", "purchase_conversion_pct"]
    if df.empty:
        return pd.DataFrame(columns=empty_cols)

    df["signup_date_kst"] = pd.to_datetime(df["signup_date_kst"])
    df["tenure_days"] = (pd.Timestamp(as_of_date) - df["signup_date_kst"]).dt.days
    df["segment"] = df.apply(lambda row: _classify_segment_variant(row, core_definition), axis=1)

    summary = df.groupby("segment").agg(
        n=("user_id", "size"),
        n_buyers=("has_purchase_full_period", "sum"),
    ).reset_index()
    summary["purchase_conversion_pct"] = round(100 * summary["n_buyers"] / summary["n"], 1)
    return summary


@st.cache_data(ttl=300)
def get_revenue_summary(
    start_date: dt.date, end_date: dt.date, artist_ids: list[str] | None = None
) -> dict:
    """fact_order/fact_order_item 기준(마트 아님, `docs/decisions_log.md` 5.13절·`sql/marts/004_...` 원칙
    그대로 — 재무 지표는 항상 fact 테이블에서 직접 계산) 총매출·환불액·환불률. 기간 필터는
    created_at_utc(결제 시작 시각, 상태와 무관하게 항상 존재)의 KST 날짜로 적용한다.

    artist_ids가 주어지면 매출은 주문 전체 금액이 아니라 **상품 단위**
    (`fact_order_item.quantity*unit_price - discount_amount`)로 그 아티스트 상품에 귀속되는 금액만
    합산한다 — 한 주문에 여러 아티스트 상품이 묶인 경우(전체 완료 주문 821건 중 11건, 직접 확인함)
    주문 전체 금액을 쓰면 다른 아티스트 매출까지 끌어오기 때문이다. 환불액은 주문 단위로만 기록되어
    있어(상품별로 나뉘지 않음) 그 주문의 환불액을 아티스트별 상품 매출 비중으로 비례 배분한다
    (근사치 — 영향받는 주문이 11건뿐이라 실질적 영향은 작다)."""
    all_artist_ids = set(get_artist_list()["artist_id"].tolist())
    filter_by_artist = bool(artist_ids) and not set(artist_ids) >= all_artist_ids

    if not filter_by_artist:
        revenue_df = run_query(
            f"""
            SELECT status, COUNT(*) AS order_count, SUM(order_amount) AS total_order_amount,
                   SUM(refund_amount) AS total_refund_amount
            FROM fact_order
            WHERE (created_at_utc AT TIME ZONE 'Asia/Seoul')::date BETWEEN '{start_date}' AND '{end_date}'
            GROUP BY status;
            """
        )
        completed_like = revenue_df[revenue_df["status"].isin(["completed", "refunded", "partially_refunded"])]
        total_completed_orders = int(completed_like["order_count"].sum())
        refunded_orders = int(
            revenue_df[revenue_df["status"].isin(["refunded", "partially_refunded"])]["order_count"].sum()
        )
        total_revenue = int(revenue_df[revenue_df["status"] == "completed"]["total_order_amount"].sum())
        total_refund = int(revenue_df["total_refund_amount"].sum())
    else:
        rows = run_query(
            f"""
            WITH artist_item_revenue AS (
                SELECT oi.transaction_id, SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS artist_revenue
                FROM fact_order_item oi
                JOIN dim_product p ON p.product_id = oi.product_id
                WHERE p.artist_id IN {_sql_in_list(artist_ids)}
                GROUP BY oi.transaction_id
            ),
            order_item_revenue AS (
                SELECT transaction_id, SUM(quantity * unit_price - discount_amount) AS order_revenue
                FROM fact_order_item
                GROUP BY transaction_id
            )
            SELECT o.status, o.order_amount, o.refund_amount,
                   air.artist_revenue, oir.order_revenue
            FROM fact_order o
            JOIN artist_item_revenue air ON air.transaction_id = o.transaction_id
            JOIN order_item_revenue oir ON oir.transaction_id = o.transaction_id
            WHERE (o.created_at_utc AT TIME ZONE 'Asia/Seoul')::date BETWEEN '{start_date}' AND '{end_date}';
            """
        )
        if rows.empty:
            total_completed_orders = refunded_orders = total_revenue = total_refund = 0
        else:
            rows["refund_share"] = rows["refund_amount"] * (rows["artist_revenue"] / rows["order_revenue"])
            completed_like = rows[rows["status"].isin(["completed", "refunded", "partially_refunded"])]
            total_completed_orders = len(completed_like)
            refunded_orders = len(rows[rows["status"].isin(["refunded", "partially_refunded"])])
            total_revenue = int(round(rows.loc[rows["status"] == "completed", "artist_revenue"].sum()))
            total_refund = int(round(rows["refund_share"].sum()))

    refund_rate_pct = (
        round(100 * refunded_orders / total_completed_orders, 2) if total_completed_orders > 0 else None
    )
    return {
        "total_revenue": total_revenue,
        "total_refund": total_refund,
        "refund_rate_pct": refund_rate_pct,
        "refunded_orders": refunded_orders,
        "total_completed_orders": total_completed_orders,
    }


@st.cache_data(ttl=300)
def get_purchase_timing(start_date: dt.date, end_date: dt.date) -> pd.DataFrame:
    """mart_commerce_funnel의 첫 관심(조회/장바구니)부터 구매까지 소요 일수(days_to_purchase) 분포.
    구매가 실제로 완료된(reached_purchase=true) 인스턴스만 포함하며, first_touch_date_kst 기준으로
    기간을 필터링한다. 구간화(히스토그램 버킷)는 화면 구현 단계에서 결정한다."""
    return run_query(
        f"""
        SELECT days_to_purchase
        FROM mart_commerce_funnel
        WHERE reached_purchase AND days_to_purchase IS NOT NULL
          AND first_touch_date_kst BETWEEN '{start_date}' AND '{end_date}';
        """
    )
