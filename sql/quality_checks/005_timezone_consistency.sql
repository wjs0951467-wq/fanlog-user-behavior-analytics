-- ============================================================
-- FANLOG 데이터 품질검사 5/5: UTC/KST 파생 일자 일치 (마지막 그룹)
-- 기준 문서: docs/PRD.md 15.1절(DQ-10), docs/event_tracking_plan.md 9절(ET-DQ-13)
-- 대상 규칙: DQ-10, ET-DQ-13 (두 규칙 모두 같은 검사를 가리키므로 하나의 쿼리 세트로 함께 다룬다)
--
-- 검사 대상 5개 테이블·컬럼 쌍:
--   dim_user:              signup_timestamp_utc    vs signup_date_kst
--   dim_content:           published_timestamp_utc vs published_date_kst
--   dim_product:           release_timestamp_utc   vs release_date_kst
--   fact_artist_activity:  activity_timestamp_utc  vs activity_date_kst
--   fact_user_event:       event_timestamp_utc     vs event_date_kst
--
-- 검증 방법: UTC 타임스탬프를 (utc_col AT TIME ZONE 'UTC') AT TIME ZONE 'Asia/Seoul'로
-- KST 벽시계 시각으로 변환한 뒤 ::date로 날짜만 뽑아, 저장된 kst_date 컬럼과 비교한다.
-- (TIMESTAMPTZ 컬럼에 AT TIME ZONE 'Asia/Seoul'을 한 번만 적용하면 PostgreSQL이 그 시각을
--  Asia/Seoul 기준 벽시계 시각으로 변환한 timestamp(타임존 없음)를 반환하므로 이 방식으로 충분하다.)
--
-- 참고: decisions_log.md 5.10절·5.14절에서 두 차례 발견된 KST→UTC 정규화 누락 버그
-- (naive datetime이 KST 벽시계 시각인데 "Z"(UTC) 접미사로 잘못 문자열화되는 문제)가
-- 이번에도 재발했는지 최종적으로 재확인하는 목적을 겸한다.
--
-- 모든 불일치 건수 쿼리는 0이어야 정상이다.
-- 위반이 있을 경우 참고할 "위반 상세 조회용" 쿼리를 각 규칙 바로 아래 주석으로 남겨뒀다(필요할 때만 주석 해제).
--
-- 실행 방법: psql -f sql/quality_checks/005_timezone_consistency.sql
-- (또는 psql 세션 안에서 \i sql/quality_checks/005_timezone_consistency.sql)
-- ============================================================


-- ============================================================
-- [요약 쿼리] 5개 테이블의 UTC→KST 파생 일자 불일치 건수를 한 번에 표로 출력한다.
-- 이 문서 하단의 개별 쿼리들과 로직은 동일하되, rule_id/target/violation_count 형태로 합쳐서 보여준다.
-- ============================================================
SELECT rule_id, target, violation_count
FROM (
    SELECT 'DQ-10/ET-DQ-13' AS rule_id, 'dim_user.signup_timestamp_utc vs signup_date_kst' AS target, COUNT(*) AS violation_count
    FROM dim_user
    WHERE (signup_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date <> signup_date_kst

    UNION ALL

    SELECT 'DQ-10/ET-DQ-13', 'dim_content.published_timestamp_utc vs published_date_kst', COUNT(*)
    FROM dim_content
    WHERE (published_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date <> published_date_kst

    UNION ALL

    SELECT 'DQ-10/ET-DQ-13', 'dim_product.release_timestamp_utc vs release_date_kst', COUNT(*)
    FROM dim_product
    WHERE (release_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date <> release_date_kst

    UNION ALL

    SELECT 'DQ-10/ET-DQ-13', 'fact_artist_activity.activity_timestamp_utc vs activity_date_kst', COUNT(*)
    FROM fact_artist_activity
    WHERE (activity_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date <> activity_date_kst

    UNION ALL

    SELECT 'DQ-10/ET-DQ-13', 'fact_user_event.event_timestamp_utc vs event_date_kst', COUNT(*)
    FROM fact_user_event
    WHERE (event_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date <> event_date_kst
) summary
ORDER BY target;


-- ============================================================
-- 이하 개별 쿼리 (테이블별로 다시 실행하고 싶을 때 이 아래부터 필요한 부분만 발췌해서 쓴다)
-- ============================================================


-- ============================================================
-- DQ-10 / ET-DQ-13: dim_user (signup_timestamp_utc vs signup_date_kst)
-- ============================================================
SELECT COUNT(*) AS mismatch_count
FROM dim_user
WHERE (signup_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date <> signup_date_kst;

-- 위반 상세 조회용
-- SELECT user_id, signup_timestamp_utc,
--        (signup_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date AS expected_kst_date,
--        signup_date_kst AS stored_kst_date
-- FROM dim_user
-- WHERE (signup_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date <> signup_date_kst
-- ORDER BY user_id;


-- ============================================================
-- DQ-10 / ET-DQ-13: dim_content (published_timestamp_utc vs published_date_kst)
-- ============================================================
SELECT COUNT(*) AS mismatch_count
FROM dim_content
WHERE (published_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date <> published_date_kst;

-- 위반 상세 조회용
-- SELECT content_id, published_timestamp_utc,
--        (published_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date AS expected_kst_date,
--        published_date_kst AS stored_kst_date
-- FROM dim_content
-- WHERE (published_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date <> published_date_kst
-- ORDER BY content_id;


-- ============================================================
-- DQ-10 / ET-DQ-13: dim_product (release_timestamp_utc vs release_date_kst)
-- ============================================================
SELECT COUNT(*) AS mismatch_count
FROM dim_product
WHERE (release_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date <> release_date_kst;

-- 위반 상세 조회용
-- SELECT product_id, release_timestamp_utc,
--        (release_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date AS expected_kst_date,
--        release_date_kst AS stored_kst_date
-- FROM dim_product
-- WHERE (release_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date <> release_date_kst
-- ORDER BY product_id;


-- ============================================================
-- DQ-10 / ET-DQ-13: fact_artist_activity (activity_timestamp_utc vs activity_date_kst)
-- ============================================================
SELECT COUNT(*) AS mismatch_count
FROM fact_artist_activity
WHERE (activity_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date <> activity_date_kst;

-- 위반 상세 조회용
-- SELECT activity_id, activity_timestamp_utc,
--        (activity_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date AS expected_kst_date,
--        activity_date_kst AS stored_kst_date
-- FROM fact_artist_activity
-- WHERE (activity_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date <> activity_date_kst
-- ORDER BY activity_id;


-- ============================================================
-- DQ-10 / ET-DQ-13: fact_user_event (event_timestamp_utc vs event_date_kst)
-- ============================================================
SELECT COUNT(*) AS mismatch_count
FROM fact_user_event
WHERE (event_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date <> event_date_kst;

-- 위반 상세 조회용
-- SELECT event_id, event_timestamp_utc,
--        (event_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date AS expected_kst_date,
--        event_date_kst AS stored_kst_date
-- FROM fact_user_event
-- WHERE (event_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date <> event_date_kst
-- ORDER BY event_id;
