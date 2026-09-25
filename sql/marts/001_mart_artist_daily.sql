-- ============================================================
-- FANLOG 분석 마트 1/4: mart_artist_daily
-- 기준 문서: docs/PRD.md 10.3절(마트 목록), 14.4절(소통과 팬 행동 관계 분석)
-- 한 행의 기준: 아티스트 × 일 (dim_artist 3팀 × 분석 기간 90일 = 270행 고정)
-- 용도: Page 2 대시보드, H-01/H-02(아티스트 소통이 줄면 팬 활동도 줄어드는가) 분석 재료
--
-- VIEW로 만든 이유: 원본 fact 테이블이 갱신될 때마다 항상 최신 값을 반영하기 위해서다.
-- 나중에 조회 성능이 문제가 되면(대시보드에서 반복 조회 등) 이 VIEW를 그대로
-- CREATE MATERIALIZED VIEW로 바꾸고 REFRESH MATERIALIZED VIEW로 갱신하는 방식으로 전환할 수 있다.
--
-- 실행 방법: psql -f sql/marts/001_mart_artist_daily.sql
-- ============================================================

DROP VIEW IF EXISTS mart_artist_daily;

CREATE VIEW mart_artist_daily AS
WITH date_spine AS (
    SELECT generate_series('2026-01-01'::date, '2026-03-31'::date, '1 day'::interval)::date AS activity_date_kst
),
artist_date_spine AS (
    -- 아티스트 × 전체 날짜 조합을 모두 만들어, 활동이 없는 날도 0으로 나오게 하는 날짜 스파인
    SELECT a.artist_id, d.activity_date_kst
    FROM dim_artist a
    CROSS JOIN date_spine d
),
activity_agg AS (
    -- fact_artist_activity는 이미 activity_date_kst(KST 파생 일자)를 갖고 있으므로 그대로 사용한다
    SELECT
        artist_id,
        activity_date_kst,
        COUNT(*) FILTER (WHERE activity_type = 'post') AS post_count,
        COUNT(*) FILTER (WHERE activity_type = 'message') AS message_count,
        COUNT(*) FILTER (WHERE activity_type = 'live') AS live_count
    FROM fact_artist_activity
    GROUP BY artist_id, activity_date_kst
),
exposure_agg AS (
    -- exposed_fans: artist_post_view/message_open/live_view_start는 fact_user_event.artist_id가 직접 채워져 있다
    SELECT
        artist_id,
        event_date_kst AS activity_date_kst,
        COUNT(DISTINCT user_id) AS exposed_fans
    FROM fact_user_event
    WHERE event_name IN ('artist_post_view', 'message_open', 'live_view_start')
    GROUP BY artist_id, event_date_kst
),
engagement_agg AS (
    -- engaged_fans: content_like/comment_create는 artist_id가 직접 없으므로 dim_content를 거쳐 판단한다
    SELECT
        c.artist_id,
        e.event_date_kst AS activity_date_kst,
        COUNT(DISTINCT e.user_id) AS engaged_fans
    FROM fact_user_event e
    JOIN dim_content c ON c.content_id = e.content_id
    WHERE e.event_name IN ('content_like', 'comment_create')
    GROUP BY c.artist_id, e.event_date_kst
),
core_activity_by_artist AS (
    -- event_tracking_plan.md 8.1절의 핵심 활동 12종을 "그 활동이 어느 아티스트와 관련됐는지"까지 붙여서 펼친 것.
    -- artist_id가 이벤트에 직접 있는 5종
    SELECT user_id, artist_id, event_date_kst
    FROM fact_user_event
    WHERE event_name IN ('artist_follow', 'message_subscription_start', 'artist_post_view', 'message_open', 'live_view_start')
    UNION
    -- content_id를 거쳐 artist_id를 아는 3종 (content_view/content_like/comment_create)
    SELECT e.user_id, c.artist_id, e.event_date_kst
    FROM fact_user_event e
    JOIN dim_content c ON c.content_id = e.content_id
    WHERE e.event_name IN ('content_view', 'content_like', 'comment_create')
    UNION
    -- product_id가 이벤트에 직접 있는 2종 (view_item/add_to_cart)
    SELECT e.user_id, p.artist_id, e.event_date_kst
    FROM fact_user_event e
    JOIN dim_product p ON p.product_id = e.product_id
    WHERE e.event_name IN ('view_item', 'add_to_cart')
    UNION
    -- transaction_id -> fact_order_item -> product_id를 거쳐 artist_id를 아는 2종 (begin_checkout/purchase)
    SELECT e.user_id, p.artist_id, e.event_date_kst
    FROM fact_user_event e
    JOIN fact_order_item oi ON oi.transaction_id = e.transaction_id
    JOIN dim_product p ON p.product_id = oi.product_id
    WHERE e.event_name IN ('begin_checkout', 'purchase')
),
active_follow_days AS (
    -- 각 (user_id, artist_id) 팔로우 기간을 날짜 스파인과 맞춰 "그 날짜에 활성 팔로우였는가"로 펼친다
    SELECT b.user_id, b.artist_id, d.activity_date_kst
    FROM bridge_user_artist_follow b
    JOIN date_spine d
      ON (b.followed_at_utc AT TIME ZONE 'Asia/Seoul')::date <= d.activity_date_kst
     AND (b.unfollowed_at_utc IS NULL OR (b.unfollowed_at_utc AT TIME ZONE 'Asia/Seoul')::date >= d.activity_date_kst)
),
active_followers_agg AS (
    -- active_followers: 그날 이 아티스트를 활성 팔로우 중이면서, 그 아티스트 관련 핵심 활동을 한 팬
    SELECT af.artist_id, af.activity_date_kst, COUNT(DISTINCT af.user_id) AS active_followers
    FROM active_follow_days af
    JOIN core_activity_by_artist ca
      ON ca.user_id = af.user_id
     AND ca.artist_id = af.artist_id
     AND ca.event_date_kst = af.activity_date_kst
    GROUP BY af.artist_id, af.activity_date_kst
),
follow_events_agg AS (
    SELECT
        artist_id,
        (followed_at_utc AT TIME ZONE 'Asia/Seoul')::date AS activity_date_kst,
        COUNT(*) AS new_follows
    FROM bridge_user_artist_follow
    GROUP BY artist_id, (followed_at_utc AT TIME ZONE 'Asia/Seoul')::date
),
unfollow_events_agg AS (
    SELECT
        artist_id,
        (unfollowed_at_utc AT TIME ZONE 'Asia/Seoul')::date AS activity_date_kst,
        COUNT(*) AS unfollows
    FROM bridge_user_artist_follow
    WHERE unfollowed_at_utc IS NOT NULL
    GROUP BY artist_id, (unfollowed_at_utc AT TIME ZONE 'Asia/Seoul')::date
),
base AS (
    SELECT
        s.artist_id,
        s.activity_date_kst,
        ph.phase_type,
        COALESCE(aa.post_count, 0) AS post_count,
        COALESCE(aa.message_count, 0) AS message_count,
        COALESCE(aa.live_count, 0) AS live_count,
        COALESCE(aa.post_count, 0) + COALESCE(aa.message_count, 0) + COALESCE(aa.live_count, 0) AS total_activity_count,
        (COALESCE(aa.post_count, 0) + COALESCE(aa.message_count, 0) + COALESCE(aa.live_count, 0)) > 0 AS had_communication,
        COALESCE(ea.exposed_fans, 0) AS exposed_fans,
        COALESCE(ega.engaged_fans, 0) AS engaged_fans,
        COALESCE(afa.active_followers, 0) AS active_followers,
        COALESCE(nfa.new_follows, 0) AS new_follows,
        COALESCE(ufa.unfollows, 0) AS unfollows
    FROM artist_date_spine s
    LEFT JOIN dim_activity_phase ph
      ON ph.artist_id = s.artist_id
     AND s.activity_date_kst BETWEEN ph.start_date_kst AND ph.end_date_kst
    LEFT JOIN activity_agg aa
      ON aa.artist_id = s.artist_id AND aa.activity_date_kst = s.activity_date_kst
    LEFT JOIN exposure_agg ea
      ON ea.artist_id = s.artist_id AND ea.activity_date_kst = s.activity_date_kst
    LEFT JOIN engagement_agg ega
      ON ega.artist_id = s.artist_id AND ega.activity_date_kst = s.activity_date_kst
    LEFT JOIN active_followers_agg afa
      ON afa.artist_id = s.artist_id AND afa.activity_date_kst = s.activity_date_kst
    LEFT JOIN follow_events_agg nfa
      ON nfa.artist_id = s.artist_id AND nfa.activity_date_kst = s.activity_date_kst
    LEFT JOIN unfollow_events_agg ufa
      ON ufa.artist_id = s.artist_id AND ufa.activity_date_kst = s.activity_date_kst
),
gap_calc AS (
    -- days_since_last_communication: 조건부 누적 MAX 트릭.
    -- had_communication=true인 날짜만 남기고 그 이전까지의 최댓값(=가장 최근 소통일)을
    -- 누적 윈도우로 계산한 뒤, 오늘 날짜에서 그 날짜를 빼면 "마지막 소통 이후 며칠"이 나온다.
    SELECT
        *,
        MAX(CASE WHEN had_communication THEN activity_date_kst END) OVER (
            PARTITION BY artist_id ORDER BY activity_date_kst
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS last_communication_date
    FROM base
)
SELECT
    artist_id,
    activity_date_kst,
    phase_type,
    post_count,
    message_count,
    live_count,
    total_activity_count,
    had_communication,
    -- 분석 기간 내 그 아티스트의 첫 소통일 이전 날짜는 last_communication_date가 NULL이라
    -- days_since_last_communication도 NULL로 남는다(정의상 "마지막 소통"이 아직 없었기 때문).
    CASE
        WHEN had_communication THEN 0
        ELSE (activity_date_kst - last_communication_date)
    END AS days_since_last_communication,
    exposed_fans,
    engaged_fans,
    active_followers,
    new_follows,
    unfollows
FROM gap_calc
ORDER BY artist_id, activity_date_kst;


-- ============================================================
-- 검증 쿼리
-- ============================================================

-- 1) 전체 행 수: 아티스트 3팀 × 90일 = 270행이어야 한다
SELECT COUNT(*) AS total_row_count FROM mart_artist_daily;

-- 2) artist_001 최근 10일 샘플
SELECT *
FROM mart_artist_daily
WHERE artist_id = 'artist_001'
ORDER BY activity_date_kst DESC
LIMIT 10;

-- 3) had_communication=true 비율이 comeback_active/tour 구간에서 daily/inactive 구간보다 높은지 확인
SELECT
    phase_type,
    COUNT(*) AS day_count,
    SUM(CASE WHEN had_communication THEN 1 ELSE 0 END) AS communication_day_count,
    ROUND(100.0 * SUM(CASE WHEN had_communication THEN 1 ELSE 0 END) / COUNT(*), 1) AS communication_day_pct
FROM mart_artist_daily
GROUP BY phase_type
ORDER BY communication_day_pct DESC;

-- 4) days_since_last_communication이 inactive 구간에서 뚜렷이 높게 나오는지 확인
SELECT
    phase_type,
    ROUND(AVG(days_since_last_communication), 1) AS avg_days_since_last_communication,
    MAX(days_since_last_communication) AS max_days_since_last_communication
FROM mart_artist_daily
GROUP BY phase_type
ORDER BY avg_days_since_last_communication DESC NULLS LAST;

-- 5) 3)의 5개 phase_type을 두 묶음(comeback_active+tour vs daily+inactive)으로 합쳐서 직접 비교
--    (comeback_prep은 어느 쪽에도 속하지 않으므로 이 비교에서 제외)
SELECT
    CASE WHEN phase_type IN ('comeback_active', 'tour') THEN 'comeback_active+tour'
         ELSE 'daily+inactive' END AS phase_group,
    COUNT(*) AS day_count,
    SUM(CASE WHEN had_communication THEN 1 ELSE 0 END) AS communication_day_count,
    ROUND(100.0 * SUM(CASE WHEN had_communication THEN 1 ELSE 0 END) / COUNT(*), 1) AS communication_day_pct
FROM mart_artist_daily
WHERE phase_type IN ('comeback_active', 'tour', 'daily', 'inactive')
GROUP BY phase_group
ORDER BY communication_day_pct DESC;
