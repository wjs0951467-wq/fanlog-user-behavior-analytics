-- ============================================================
-- FANLOG 분석 마트 2/4: mart_user_daily
-- 기준 문서: docs/PRD.md 10.3절(마트 목록), 8.1절(핵심 활동·이탈위험·휴면·재활성 정의),
--           8.2절(활동 상태 정의), docs/event_tracking_plan.md 8절(핵심 활동 12종·활동 상태 계산)
-- 한 행의 기준: 팬 × 일 (Page 1·2·3 전체의 핵심 재료)
--
-- 날짜 범위 결정(사용자 확인 완료): 기존 가입자(분석 시작일 이전 가입, decisions_log 5.10절)의
-- signup_timestamp_utc는 최대 2년 전까지 거슬러 올라갈 수 있다. 이 마트는 분석 기간
-- (2026-01-01~2026-03-31) 밖의 날짜는 만들지 않고, 각 팬의 첫 행을
-- GREATEST(signup_date_kst, 분석 시작일)로 제한한다. 실제 이벤트 데이터 자체가
-- 분석 기간 밖에는 없으므로(ET-DQ-14) 이 쪽이 001번 마트(mart_artist_daily)와도 일관되고,
-- 불필요하게 수백만 건의 빈 행이 생기는 것도 막는다.
--
-- VIEW로 만든 이유: 원본 fact 테이블이 갱신될 때마다 항상 최신 값을 반영하기 위해서다.
-- 나중에 조회 성능이 문제가 되면(대시보드에서 반복 조회 등) CREATE MATERIALIZED VIEW로
-- 바꾸고 REFRESH MATERIALIZED VIEW로 갱신하는 방식으로 전환할 수 있다.
--
-- 실행 방법: psql -f sql/marts/002_mart_user_daily.sql
-- ============================================================

DROP VIEW IF EXISTS mart_user_daily;

CREATE VIEW mart_user_daily AS
WITH date_spine AS (
    SELECT generate_series('2026-01-01'::date, '2026-03-31'::date, '1 day'::interval)::date AS activity_date_kst
),
user_date_spine AS (
    -- 각 팬은 GREATEST(가입일, 분석 시작일)부터 분석 종료일까지만 행을 가진다(가입 전 날짜 제외)
    SELECT u.user_id, d.activity_date_kst
    FROM dim_user u
    CROSS JOIN date_spine d
    WHERE d.activity_date_kst >= GREATEST(u.signup_date_kst, '2026-01-01'::date)
),
core_activity_agg AS (
    -- event_tracking_plan.md 8.1절 핵심 활동 12종 중 하나라도 있었는지(had_core_activity),
    -- "참여 행동"(PRD 8.1) 4종 중 몇 종을 했는지(engagement_action_count), purchase 여부를 하루 단위로 집계
    SELECT
        user_id,
        event_date_kst AS activity_date_kst,
        bool_or(event_name IN (
            'artist_follow', 'message_subscription_start', 'artist_post_view', 'message_open',
            'live_view_start', 'content_view', 'content_like', 'comment_create',
            'view_item', 'add_to_cart', 'begin_checkout', 'purchase'
        )) AS had_core_activity,
        COUNT(DISTINCT CASE
            WHEN event_name IN ('content_like', 'comment_create', 'message_open', 'live_view_start')
            THEN event_name
        END) AS engagement_action_count,
        bool_or(event_name = 'purchase') AS had_purchase
    FROM fact_user_event
    GROUP BY user_id, event_date_kst
),
base AS (
    SELECT
        s.user_id,
        s.activity_date_kst,
        COALESCE(ca.had_core_activity, false) AS had_core_activity,
        COALESCE(ca.engagement_action_count, 0) AS engagement_action_count,
        COALESCE(ca.had_purchase, false) AS had_purchase
    FROM user_date_spine s
    LEFT JOIN core_activity_agg ca
      ON ca.user_id = s.user_id AND ca.activity_date_kst = s.activity_date_kst
),
gap_calc AS (
    -- days_since_last_core_activity 계산: 001번 마트(mart_artist_daily)의
    -- "조건부 누적 MAX" 트릭을 그대로 재사용하되, 이 마트는 "가입 첫날은 0으로 시작"해야 하므로
    -- 마지막 핵심활동일이 아직 없을 때(NULL) 대신 쓸 기준일로 각 팬의 마트 내 첫 날짜
    -- (first_tracked_date = GREATEST(가입일, 분석 시작일))를 함께 계산해둔다.
    SELECT
        *,
        FIRST_VALUE(activity_date_kst) OVER (PARTITION BY user_id ORDER BY activity_date_kst) AS first_tracked_date,
        MAX(CASE WHEN had_core_activity THEN activity_date_kst END) OVER (
            PARTITION BY user_id ORDER BY activity_date_kst
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS last_core_activity_date
    FROM base
),
gap_resolved AS (
    SELECT
        *,
        CASE
            WHEN had_core_activity THEN 0
            -- 아직 핵심활동이 한 번도 없었으면 첫 추적일(가입일 또는 분석 시작일) 기준으로 센다
            -- => 가입 첫날(=first_tracked_date)은 0에서 시작해서, 활동이 없으면 하루씩 늘어난다
            ELSE activity_date_kst - COALESCE(last_core_activity_date, first_tracked_date)
        END AS days_since_last_core_activity
    FROM gap_calc
),
status_calc AS (
    -- docs/event_tracking_plan.md 8.2절 그대로: 0~13일 active, 14~29일 at_risk, 30일 이상 dormant
    -- (at_risk 조건의 "이전 30일 내 핵심활동 있었음"은 gap<30이라는 사실 자체로 이미 보장된다)
    SELECT
        *,
        CASE
            WHEN days_since_last_core_activity <= 13 THEN 'active'
            WHEN days_since_last_core_activity <= 29 THEN 'at_risk'
            ELSE 'dormant'
        END AS activity_status
    FROM gap_resolved
)
SELECT
    user_id,
    activity_date_kst,
    had_core_activity,
    engagement_action_count,
    had_purchase,
    days_since_last_core_activity,
    activity_status,
    -- was_reactivated_today: 어제 dormant였다가 오늘 핵심활동이 발생한 경우(PRD 8.1 "재활성 팬")
    COALESCE(
        LAG(activity_status) OVER (PARTITION BY user_id ORDER BY activity_date_kst) = 'dormant'
        AND had_core_activity,
        false
    ) AS was_reactivated_today
FROM status_calc
ORDER BY user_id, activity_date_kst;


-- ============================================================
-- 검증 쿼리
-- ============================================================

-- 1) 전체 행 수 (1,750명이 각자 다른 날 시작하므로 정확한 예상치는 없으나, 대략적인 범위 확인용)
SELECT COUNT(*) AS total_row_count, COUNT(DISTINCT user_id) AS distinct_user_count
FROM mart_user_daily;

-- 2) 가장 초기에 가입한 팬의 최근 20일 샘플
SELECT m.*
FROM mart_user_daily m
WHERE m.user_id = (SELECT user_id FROM dim_user ORDER BY signup_timestamp_utc ASC LIMIT 1)
ORDER BY m.activity_date_kst DESC
LIMIT 20;

-- 3) activity_status별 전체 건수·비율 분포
SELECT
    activity_status,
    COUNT(*) AS row_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
FROM mart_user_daily
GROUP BY activity_status
ORDER BY row_count DESC;

-- 4) 교차검증: 2026-02-15 DAU가 마트 집계와 fact_user_event 직접 집계에서 정확히 일치하는지 확인
SELECT
    (SELECT COUNT(*) FROM mart_user_daily WHERE activity_date_kst = '2026-02-15' AND had_core_activity) AS dau_from_mart,
    (SELECT COUNT(DISTINCT user_id) FROM fact_user_event
     WHERE event_date_kst = '2026-02-15'
       AND event_name IN (
           'artist_follow', 'message_subscription_start', 'artist_post_view', 'message_open',
           'live_view_start', 'content_view', 'content_like', 'comment_create',
           'view_item', 'add_to_cart', 'begin_checkout', 'purchase'
       )
    ) AS dau_from_raw_events;

-- 5) was_reactivated_today가 실제로 발생하는지 확인
SELECT COUNT(*) AS reactivation_event_count
FROM mart_user_daily
WHERE was_reactivated_today;

-- 참고: 재활성 사례 샘플 (필요 시 주석 해제)
-- SELECT user_id, activity_date_kst, days_since_last_core_activity, activity_status, was_reactivated_today
-- FROM mart_user_daily
-- WHERE was_reactivated_today
-- ORDER BY activity_date_kst
-- LIMIT 20;
