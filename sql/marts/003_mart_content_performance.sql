-- ============================================================
-- FANLOG 분석 마트 3/4: mart_content_performance
-- 기준 문서: docs/PRD.md 10.3절(마트 목록), 8.2절("콘텐츠 고유 조회자", "콘텐츠 참여율" 정의),
--           14.6절(분모가 0이면 "계산 불가"로 처리)
-- 한 행의 기준: 콘텐츠 1개 (dim_content 103행과 정확히 일치해야 한다)
--
-- VIEW로 만든 이유: 원본 fact 테이블이 갱신될 때마다 항상 최신 값을 반영하기 위해서다.
-- 나중에 조회 성능이 문제가 되면(대시보드에서 반복 조회 등) CREATE MATERIALIZED VIEW로
-- 바꾸고 REFRESH MATERIALIZED VIEW로 갱신하는 방식으로 전환할 수 있다.
--
-- 실행 방법: psql -f sql/marts/003_mart_content_performance.sql
-- ============================================================

DROP VIEW IF EXISTS mart_content_performance;

CREATE VIEW mart_content_performance AS
WITH view_agg AS (
    SELECT
        content_id,
        COUNT(DISTINCT user_id) AS unique_viewers,
        COUNT(*) AS total_views
    FROM fact_user_event
    WHERE event_name = 'content_view'
    GROUP BY content_id
),
engagement_agg AS (
    SELECT
        content_id,
        COUNT(DISTINCT user_id) AS unique_engagers,
        COUNT(*) FILTER (WHERE event_name = 'content_like') AS like_count,
        COUNT(*) FILTER (WHERE event_name = 'comment_create') AS comment_count
    FROM fact_user_event
    WHERE event_name IN ('content_like', 'comment_create')
    GROUP BY content_id
)
SELECT
    c.content_id,
    c.artist_id,
    c.content_type,
    c.title,
    c.published_timestamp_utc,
    c.published_date_kst,
    COALESCE(v.unique_viewers, 0) AS unique_viewers,
    COALESCE(v.total_views, 0) AS total_views,
    COALESCE(e.unique_engagers, 0) AS unique_engagers,
    -- PRD 14.6: 분모(unique_viewers)가 0이면 0%가 아니라 계산 불가(NULL)로 처리한다
    CASE
        WHEN COALESCE(v.unique_viewers, 0) = 0 THEN NULL
        ELSE ROUND(COALESCE(e.unique_engagers, 0)::numeric / v.unique_viewers, 4)
    END AS engagement_rate,
    COALESCE(e.like_count, 0) AS like_count,
    COALESCE(e.comment_count, 0) AS comment_count,
    ('2026-03-31'::date - c.published_date_kst) AS days_since_published
FROM dim_content c
LEFT JOIN view_agg v ON v.content_id = c.content_id
LEFT JOIN engagement_agg e ON e.content_id = c.content_id
ORDER BY c.content_id;


-- ============================================================
-- 검증 쿼리
-- ============================================================

-- 1) 전체 행 수가 dim_content(103개)와 정확히 일치하는지
SELECT COUNT(*) AS total_row_count FROM mart_content_performance;

-- 2) unique_viewers 상위 5개
SELECT content_id, artist_id, content_type, title, unique_viewers, total_views, unique_engagers, engagement_rate
FROM mart_content_performance
ORDER BY unique_viewers DESC
LIMIT 5;

-- 3) engagement_rate 하위 5개 (단 unique_viewers >= 5인 것 중에서)
--    => "조회는 높지만 참여율 낮은 콘텐츠" 후보 (Page 1 후보 리스트)
SELECT content_id, artist_id, content_type, title, unique_viewers, unique_engagers, engagement_rate
FROM mart_content_performance
WHERE unique_viewers >= 5
ORDER BY engagement_rate ASC NULLS LAST
LIMIT 5;

-- 4) unique_viewers가 0인 콘텐츠 확인 (한 번도 조회되지 않은 콘텐츠)
SELECT COUNT(*) AS never_viewed_content_count
FROM mart_content_performance
WHERE unique_viewers = 0;

-- 4-1) 실제로 0건이 있다면, 최근 발행이라 조회 기회가 적었던 것인지 확인
SELECT content_id, artist_id, content_type, published_date_kst, days_since_published
FROM mart_content_performance
WHERE unique_viewers = 0
ORDER BY days_since_published ASC;

-- 4-2) 비교 기준: 전체 콘텐츠의 days_since_published 분포(중앙값·최소값)와 대조
SELECT
    ROUND(AVG(days_since_published), 1) AS avg_days_since_published,
    MIN(days_since_published) AS min_days_since_published,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_since_published) AS median_days_since_published
FROM mart_content_performance;

-- 5) engagement_rate가 NULL로 정상 처리되는 행이 있는지 확인 (unique_viewers=0인 행과 정확히 같아야 함)
SELECT COUNT(*) AS null_engagement_rate_count
FROM mart_content_performance
WHERE engagement_rate IS NULL;
