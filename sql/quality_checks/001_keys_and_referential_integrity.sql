-- ============================================================
-- FANLOG 데이터 품질검사 1/5: 기본키·외래키·결측
-- 기준 문서: docs/PRD.md 15.1절(DQ-01~03), docs/event_tracking_plan.md 9절(ET-DQ-01~06, 9.1절 참조 규칙)
-- 대상 규칙: DQ-01, DQ-02, DQ-03, ET-DQ-01, ET-DQ-02, ET-DQ-03, ET-DQ-04, ET-DQ-05, ET-DQ-06 (총 9개)
-- 나머지 규칙(DQ-04~10, ET-DQ-07~28)은 다음 그룹(2/5 이후)에서 다룬다.
--
-- 모든 위반 건수 쿼리는 0이어야 정상이다.
-- 위반이 있을 경우 참고할 "위반 상세 조회용" 쿼리를 각 규칙 바로 아래 주석으로 남겨뒀다(필요할 때만 주석 해제).
--
-- 실행 방법: psql -f sql/quality_checks/001_keys_and_referential_integrity.sql
-- (또는 psql 세션 안에서 \i sql/quality_checks/001_keys_and_referential_integrity.sql)
-- ============================================================


-- ============================================================
-- [요약 쿼리] 아래 9개 규칙(52개 세부 항목)의 위반 건수를 한 번에 표로 출력한다.
-- 이 문서 하단의 개별 쿼리들과 로직은 동일하되, rule_id/target/violation_count 형태로 합쳐서 보여준다.
-- ============================================================
SELECT rule_id, target, violation_count
FROM (
    -- ---------- DQ-01: 기본키 중복 (11개 테이블) ----------
    SELECT 'DQ-01' AS rule_id, 'dim_artist' AS target, COUNT(*) AS violation_count
    FROM (SELECT artist_id FROM dim_artist GROUP BY artist_id HAVING COUNT(*) > 1) d
    UNION ALL
    SELECT 'DQ-01', 'dim_user', COUNT(*)
    FROM (SELECT user_id FROM dim_user GROUP BY user_id HAVING COUNT(*) > 1) d
    UNION ALL
    SELECT 'DQ-01', 'dim_content', COUNT(*)
    FROM (SELECT content_id FROM dim_content GROUP BY content_id HAVING COUNT(*) > 1) d
    UNION ALL
    SELECT 'DQ-01', 'dim_product', COUNT(*)
    FROM (SELECT product_id FROM dim_product GROUP BY product_id HAVING COUNT(*) > 1) d
    UNION ALL
    SELECT 'DQ-01', 'dim_activity_phase', COUNT(*)
    FROM (SELECT phase_id FROM dim_activity_phase GROUP BY phase_id HAVING COUNT(*) > 1) d
    UNION ALL
    SELECT 'DQ-01', 'bridge_user_artist_follow', COUNT(*)
    FROM (SELECT follow_id FROM bridge_user_artist_follow GROUP BY follow_id HAVING COUNT(*) > 1) d
    UNION ALL
    SELECT 'DQ-01', 'fact_message_subscription', COUNT(*)
    FROM (SELECT subscription_id FROM fact_message_subscription GROUP BY subscription_id HAVING COUNT(*) > 1) d
    UNION ALL
    SELECT 'DQ-01', 'fact_artist_activity', COUNT(*)
    FROM (SELECT activity_id FROM fact_artist_activity GROUP BY activity_id HAVING COUNT(*) > 1) d
    UNION ALL
    SELECT 'DQ-01', 'fact_order', COUNT(*)
    FROM (SELECT transaction_id FROM fact_order GROUP BY transaction_id HAVING COUNT(*) > 1) d
    UNION ALL
    SELECT 'DQ-01', 'fact_order_item', COUNT(*)
    FROM (SELECT order_item_id FROM fact_order_item GROUP BY order_item_id HAVING COUNT(*) > 1) d
    UNION ALL
    SELECT 'DQ-01', 'fact_user_event', COUNT(*)
    FROM (SELECT event_id FROM fact_user_event GROUP BY event_id HAVING COUNT(*) > 1) d

    UNION ALL

    -- ---------- DQ-02: NOT NULL 문자열 컬럼의 빈 문자열/공백 (11개 테이블) ----------
    SELECT 'DQ-02', 'dim_artist', COUNT(*)
    FROM dim_artist
    WHERE artist_id ~ '^[[:space:]]*$' OR artist_name ~ '^[[:space:]]*$' OR artist_type ~ '^[[:space:]]*$'
    UNION ALL
    SELECT 'DQ-02', 'dim_user', COUNT(*)
    FROM dim_user
    WHERE user_id ~ '^[[:space:]]*$' OR country_group ~ '^[[:space:]]*$'
       OR acquisition_channel ~ '^[[:space:]]*$' OR primary_device_type ~ '^[[:space:]]*$'
    UNION ALL
    SELECT 'DQ-02', 'dim_content', COUNT(*)
    FROM dim_content
    WHERE content_id ~ '^[[:space:]]*$' OR artist_id ~ '^[[:space:]]*$'
       OR content_type ~ '^[[:space:]]*$' OR title ~ '^[[:space:]]*$'
    UNION ALL
    SELECT 'DQ-02', 'dim_product', COUNT(*)
    FROM dim_product
    WHERE product_id ~ '^[[:space:]]*$' OR artist_id ~ '^[[:space:]]*$'
       OR product_name ~ '^[[:space:]]*$' OR product_type ~ '^[[:space:]]*$'
    UNION ALL
    SELECT 'DQ-02', 'dim_activity_phase', COUNT(*)
    FROM dim_activity_phase
    WHERE phase_id ~ '^[[:space:]]*$' OR artist_id ~ '^[[:space:]]*$' OR phase_type ~ '^[[:space:]]*$'
    UNION ALL
    SELECT 'DQ-02', 'bridge_user_artist_follow', COUNT(*)
    FROM bridge_user_artist_follow
    WHERE follow_id ~ '^[[:space:]]*$' OR user_id ~ '^[[:space:]]*$' OR artist_id ~ '^[[:space:]]*$'
    UNION ALL
    SELECT 'DQ-02', 'fact_message_subscription', COUNT(*)
    FROM fact_message_subscription
    WHERE subscription_id ~ '^[[:space:]]*$' OR user_id ~ '^[[:space:]]*$'
       OR artist_id ~ '^[[:space:]]*$' OR plan_type ~ '^[[:space:]]*$'
    UNION ALL
    SELECT 'DQ-02', 'fact_artist_activity', COUNT(*)
    FROM fact_artist_activity
    WHERE activity_id ~ '^[[:space:]]*$' OR artist_id ~ '^[[:space:]]*$' OR activity_type ~ '^[[:space:]]*$'
    UNION ALL
    SELECT 'DQ-02', 'fact_order', COUNT(*)
    FROM fact_order
    WHERE transaction_id ~ '^[[:space:]]*$' OR user_id ~ '^[[:space:]]*$' OR status ~ '^[[:space:]]*$'
    UNION ALL
    SELECT 'DQ-02', 'fact_order_item', COUNT(*)
    FROM fact_order_item
    WHERE order_item_id ~ '^[[:space:]]*$' OR transaction_id ~ '^[[:space:]]*$' OR product_id ~ '^[[:space:]]*$'
    UNION ALL
    SELECT 'DQ-02', 'fact_user_event', COUNT(*)
    FROM fact_user_event
    WHERE event_id ~ '^[[:space:]]*$' OR event_name ~ '^[[:space:]]*$'
       OR user_id ~ '^[[:space:]]*$' OR device_type ~ '^[[:space:]]*$'

    UNION ALL

    -- ---------- DQ-03: 외래키 고아 행 (18개 FK 관계 전수 확인) ----------
    -- dim_user 참조
    SELECT 'DQ-03', 'bridge_user_artist_follow.user_id -> dim_user', COUNT(*)
    FROM bridge_user_artist_follow b
    WHERE NOT EXISTS (SELECT 1 FROM dim_user u WHERE u.user_id = b.user_id)
    UNION ALL
    SELECT 'DQ-03', 'fact_message_subscription.user_id -> dim_user', COUNT(*)
    FROM fact_message_subscription s
    WHERE NOT EXISTS (SELECT 1 FROM dim_user u WHERE u.user_id = s.user_id)
    UNION ALL
    SELECT 'DQ-03', 'fact_order.user_id -> dim_user', COUNT(*)
    FROM fact_order o
    WHERE NOT EXISTS (SELECT 1 FROM dim_user u WHERE u.user_id = o.user_id)
    UNION ALL
    SELECT 'DQ-03', 'fact_user_event.user_id -> dim_user', COUNT(*)
    FROM fact_user_event e
    WHERE NOT EXISTS (SELECT 1 FROM dim_user u WHERE u.user_id = e.user_id)
    -- dim_artist 참조
    UNION ALL
    SELECT 'DQ-03', 'dim_content.artist_id -> dim_artist', COUNT(*)
    FROM dim_content c
    WHERE NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = c.artist_id)
    UNION ALL
    SELECT 'DQ-03', 'dim_product.artist_id -> dim_artist', COUNT(*)
    FROM dim_product p
    WHERE NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = p.artist_id)
    UNION ALL
    SELECT 'DQ-03', 'dim_activity_phase.artist_id -> dim_artist', COUNT(*)
    FROM dim_activity_phase ph
    WHERE NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = ph.artist_id)
    UNION ALL
    SELECT 'DQ-03', 'bridge_user_artist_follow.artist_id -> dim_artist', COUNT(*)
    FROM bridge_user_artist_follow b
    WHERE NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = b.artist_id)
    UNION ALL
    SELECT 'DQ-03', 'fact_message_subscription.artist_id -> dim_artist', COUNT(*)
    FROM fact_message_subscription s
    WHERE NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = s.artist_id)
    UNION ALL
    SELECT 'DQ-03', 'fact_artist_activity.artist_id -> dim_artist', COUNT(*)
    FROM fact_artist_activity fa
    WHERE NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = fa.artist_id)
    UNION ALL
    SELECT 'DQ-03', 'fact_user_event.artist_id -> dim_artist', COUNT(*)
    FROM fact_user_event e
    WHERE e.artist_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = e.artist_id)
    -- dim_content 참조
    UNION ALL
    SELECT 'DQ-03', 'fact_artist_activity.content_id -> dim_content', COUNT(*)
    FROM fact_artist_activity fa
    WHERE fa.content_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM dim_content c WHERE c.content_id = fa.content_id)
    UNION ALL
    SELECT 'DQ-03', 'fact_user_event.content_id -> dim_content', COUNT(*)
    FROM fact_user_event e
    WHERE e.content_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM dim_content c WHERE c.content_id = e.content_id)
    -- dim_product 참조
    UNION ALL
    SELECT 'DQ-03', 'fact_order_item.product_id -> dim_product', COUNT(*)
    FROM fact_order_item oi
    WHERE NOT EXISTS (SELECT 1 FROM dim_product p WHERE p.product_id = oi.product_id)
    UNION ALL
    SELECT 'DQ-03', 'fact_user_event.product_id -> dim_product', COUNT(*)
    FROM fact_user_event e
    WHERE e.product_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM dim_product p WHERE p.product_id = e.product_id)
    -- fact_artist_activity 참조
    UNION ALL
    SELECT 'DQ-03', 'fact_user_event.activity_id -> fact_artist_activity', COUNT(*)
    FROM fact_user_event e
    WHERE e.activity_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM fact_artist_activity fa WHERE fa.activity_id = e.activity_id)
    -- fact_order 참조
    UNION ALL
    SELECT 'DQ-03', 'fact_order_item.transaction_id -> fact_order', COUNT(*)
    FROM fact_order_item oi
    WHERE NOT EXISTS (SELECT 1 FROM fact_order o WHERE o.transaction_id = oi.transaction_id)
    UNION ALL
    SELECT 'DQ-03', 'fact_user_event.transaction_id -> fact_order', COUNT(*)
    FROM fact_user_event e
    WHERE e.transaction_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM fact_order o WHERE o.transaction_id = e.transaction_id)

    UNION ALL

    -- ---------- ET-DQ-01: fact_user_event.event_id 중복 ----------
    SELECT 'ET-DQ-01', 'fact_user_event.event_id', COUNT(*)
    FROM (SELECT event_id FROM fact_user_event GROUP BY event_id HAVING COUNT(*) > 1) d

    UNION ALL

    -- ---------- ET-DQ-02: fact_artist_activity.activity_id 중복 ----------
    SELECT 'ET-DQ-02', 'fact_artist_activity.activity_id', COUNT(*)
    FROM (SELECT activity_id FROM fact_artist_activity GROUP BY activity_id HAVING COUNT(*) > 1) d

    UNION ALL

    -- ---------- ET-DQ-03: 허용 목록 밖 event_name ----------
    SELECT 'ET-DQ-03', 'fact_user_event.event_name', COUNT(*)
    FROM fact_user_event
    WHERE event_name NOT IN (
        'sign_up', 'session_start', 'artist_view', 'artist_follow', 'artist_unfollow',
        'message_subscription_start', 'message_subscription_cancel', 'artist_post_view',
        'message_open', 'live_view_start', 'content_view', 'content_like', 'comment_create',
        'view_item', 'add_to_cart', 'begin_checkout', 'purchase', 'refund'
    )

    UNION ALL

    -- ---------- ET-DQ-04: 허용 목록 밖 activity_type ----------
    SELECT 'ET-DQ-04', 'fact_artist_activity.activity_type', COUNT(*)
    FROM fact_artist_activity
    WHERE activity_type NOT IN ('post', 'message', 'live')

    UNION ALL

    -- ---------- ET-DQ-05: fact_user_event.user_id 결측 ----------
    SELECT 'ET-DQ-05', 'fact_user_event.user_id IS NULL', COUNT(*)
    FROM fact_user_event
    WHERE user_id IS NULL

    UNION ALL

    -- ---------- ET-DQ-06: 참조 대상 없는 외래키 (event_tracking_plan.md 9.1절, DQ-03 로직 재사용) ----------
    SELECT 'ET-DQ-06', 'fact_user_event.user_id -> dim_user', COUNT(*)
    FROM fact_user_event e
    WHERE NOT EXISTS (SELECT 1 FROM dim_user u WHERE u.user_id = e.user_id)
    UNION ALL
    SELECT 'ET-DQ-06', 'fact_user_event.artist_id -> dim_artist', COUNT(*)
    FROM fact_user_event e
    WHERE e.artist_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = e.artist_id)
    UNION ALL
    SELECT 'ET-DQ-06', 'fact_user_event.content_id -> dim_content', COUNT(*)
    FROM fact_user_event e
    WHERE e.content_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM dim_content c WHERE c.content_id = e.content_id)
    UNION ALL
    SELECT 'ET-DQ-06', 'fact_user_event.activity_id -> fact_artist_activity', COUNT(*)
    FROM fact_user_event e
    WHERE e.activity_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM fact_artist_activity fa WHERE fa.activity_id = e.activity_id)
    UNION ALL
    SELECT 'ET-DQ-06', 'fact_user_event.product_id -> dim_product', COUNT(*)
    FROM fact_user_event e
    WHERE e.product_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM dim_product p WHERE p.product_id = e.product_id)
    UNION ALL
    SELECT 'ET-DQ-06', 'fact_user_event.transaction_id -> fact_order', COUNT(*)
    FROM fact_user_event e
    WHERE e.transaction_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM fact_order o WHERE o.transaction_id = e.transaction_id)
) summary
ORDER BY rule_id, target;


-- ============================================================
-- 이하 개별 쿼리 (규칙별로 다시 실행하고 싶을 때 이 아래부터 필요한 부분만 발췌해서 쓴다)
-- ============================================================


-- ============================================================
-- DQ-01: 각 테이블(11개) 기본키 중복 건수
-- 정의: docs/PRD.md 15.1절
-- 참고: 각 테이블 PK는 PRIMARY KEY 제약으로 이미 DB가 중복을 막고 있다.
--       이 쿼리는 문서화 목적 및 제약이 우회된 적재(예: COPY 중 제약 임시 해제)가 없었는지 재확인하는 용도다.
-- ============================================================
SELECT 'dim_artist' AS table_name, COUNT(*) AS duplicate_key_count
FROM (SELECT artist_id FROM dim_artist GROUP BY artist_id HAVING COUNT(*) > 1) d
UNION ALL
SELECT 'dim_user', COUNT(*)
FROM (SELECT user_id FROM dim_user GROUP BY user_id HAVING COUNT(*) > 1) d
UNION ALL
SELECT 'dim_content', COUNT(*)
FROM (SELECT content_id FROM dim_content GROUP BY content_id HAVING COUNT(*) > 1) d
UNION ALL
SELECT 'dim_product', COUNT(*)
FROM (SELECT product_id FROM dim_product GROUP BY product_id HAVING COUNT(*) > 1) d
UNION ALL
SELECT 'dim_activity_phase', COUNT(*)
FROM (SELECT phase_id FROM dim_activity_phase GROUP BY phase_id HAVING COUNT(*) > 1) d
UNION ALL
SELECT 'bridge_user_artist_follow', COUNT(*)
FROM (SELECT follow_id FROM bridge_user_artist_follow GROUP BY follow_id HAVING COUNT(*) > 1) d
UNION ALL
SELECT 'fact_message_subscription', COUNT(*)
FROM (SELECT subscription_id FROM fact_message_subscription GROUP BY subscription_id HAVING COUNT(*) > 1) d
UNION ALL
SELECT 'fact_artist_activity', COUNT(*)
FROM (SELECT activity_id FROM fact_artist_activity GROUP BY activity_id HAVING COUNT(*) > 1) d
UNION ALL
SELECT 'fact_order', COUNT(*)
FROM (SELECT transaction_id FROM fact_order GROUP BY transaction_id HAVING COUNT(*) > 1) d
UNION ALL
SELECT 'fact_order_item', COUNT(*)
FROM (SELECT order_item_id FROM fact_order_item GROUP BY order_item_id HAVING COUNT(*) > 1) d
UNION ALL
SELECT 'fact_user_event', COUNT(*)
FROM (SELECT event_id FROM fact_user_event GROUP BY event_id HAVING COUNT(*) > 1) d;

-- 위반 상세 조회용 (실제 중복된 키 값과 중복 횟수를 보여준다)
-- SELECT 'dim_artist' AS table_name, artist_id AS duplicate_key, COUNT(*) AS occurrence_count
-- FROM dim_artist GROUP BY artist_id HAVING COUNT(*) > 1
-- UNION ALL
-- SELECT 'dim_user', user_id, COUNT(*) FROM dim_user GROUP BY user_id HAVING COUNT(*) > 1
-- UNION ALL
-- SELECT 'dim_content', content_id, COUNT(*) FROM dim_content GROUP BY content_id HAVING COUNT(*) > 1
-- UNION ALL
-- SELECT 'dim_product', product_id, COUNT(*) FROM dim_product GROUP BY product_id HAVING COUNT(*) > 1
-- UNION ALL
-- SELECT 'dim_activity_phase', phase_id, COUNT(*) FROM dim_activity_phase GROUP BY phase_id HAVING COUNT(*) > 1
-- UNION ALL
-- SELECT 'bridge_user_artist_follow', follow_id, COUNT(*) FROM bridge_user_artist_follow GROUP BY follow_id HAVING COUNT(*) > 1
-- UNION ALL
-- SELECT 'fact_message_subscription', subscription_id, COUNT(*) FROM fact_message_subscription GROUP BY subscription_id HAVING COUNT(*) > 1
-- UNION ALL
-- SELECT 'fact_artist_activity', activity_id, COUNT(*) FROM fact_artist_activity GROUP BY activity_id HAVING COUNT(*) > 1
-- UNION ALL
-- SELECT 'fact_order', transaction_id, COUNT(*) FROM fact_order GROUP BY transaction_id HAVING COUNT(*) > 1
-- UNION ALL
-- SELECT 'fact_order_item', order_item_id, COUNT(*) FROM fact_order_item GROUP BY order_item_id HAVING COUNT(*) > 1
-- UNION ALL
-- SELECT 'fact_user_event', event_id, COUNT(*) FROM fact_user_event GROUP BY event_id HAVING COUNT(*) > 1;


-- ============================================================
-- DQ-02: NOT NULL 문자열 컬럼에 빈 문자열/공백만 들어간 경우 (11개 테이블)
-- 정의: docs/PRD.md 15.1절
-- 참고: NOT NULL 제약은 이미 DB가 막고 있다. 이 쿼리는 "NULL은 아니지만 사실상 빈 값"인
--       빈 문자열('') 또는 공백만 있는 문자열이 문자열형 NOT NULL 컬럼에 들어갔는지 확인한다.
--       (숫자/날짜/불리언/JSONB/NULL 허용 컬럼은 대상이 아니다)
-- ============================================================
SELECT 'dim_artist' AS table_name, COUNT(*) AS blank_string_count
FROM dim_artist
WHERE artist_id ~ '^[[:space:]]*$' OR artist_name ~ '^[[:space:]]*$' OR artist_type ~ '^[[:space:]]*$'
UNION ALL
SELECT 'dim_user', COUNT(*)
FROM dim_user
WHERE user_id ~ '^[[:space:]]*$' OR country_group ~ '^[[:space:]]*$'
   OR acquisition_channel ~ '^[[:space:]]*$' OR primary_device_type ~ '^[[:space:]]*$'
UNION ALL
SELECT 'dim_content', COUNT(*)
FROM dim_content
WHERE content_id ~ '^[[:space:]]*$' OR artist_id ~ '^[[:space:]]*$'
   OR content_type ~ '^[[:space:]]*$' OR title ~ '^[[:space:]]*$'
UNION ALL
SELECT 'dim_product', COUNT(*)
FROM dim_product
WHERE product_id ~ '^[[:space:]]*$' OR artist_id ~ '^[[:space:]]*$'
   OR product_name ~ '^[[:space:]]*$' OR product_type ~ '^[[:space:]]*$'
UNION ALL
SELECT 'dim_activity_phase', COUNT(*)
FROM dim_activity_phase
WHERE phase_id ~ '^[[:space:]]*$' OR artist_id ~ '^[[:space:]]*$' OR phase_type ~ '^[[:space:]]*$'
UNION ALL
SELECT 'bridge_user_artist_follow', COUNT(*)
FROM bridge_user_artist_follow
WHERE follow_id ~ '^[[:space:]]*$' OR user_id ~ '^[[:space:]]*$' OR artist_id ~ '^[[:space:]]*$'
UNION ALL
SELECT 'fact_message_subscription', COUNT(*)
FROM fact_message_subscription
WHERE subscription_id ~ '^[[:space:]]*$' OR user_id ~ '^[[:space:]]*$'
   OR artist_id ~ '^[[:space:]]*$' OR plan_type ~ '^[[:space:]]*$'
UNION ALL
SELECT 'fact_artist_activity', COUNT(*)
FROM fact_artist_activity
WHERE activity_id ~ '^[[:space:]]*$' OR artist_id ~ '^[[:space:]]*$' OR activity_type ~ '^[[:space:]]*$'
UNION ALL
SELECT 'fact_order', COUNT(*)
FROM fact_order
WHERE transaction_id ~ '^[[:space:]]*$' OR user_id ~ '^[[:space:]]*$' OR status ~ '^[[:space:]]*$'
UNION ALL
SELECT 'fact_order_item', COUNT(*)
FROM fact_order_item
WHERE order_item_id ~ '^[[:space:]]*$' OR transaction_id ~ '^[[:space:]]*$' OR product_id ~ '^[[:space:]]*$'
UNION ALL
SELECT 'fact_user_event', COUNT(*)
FROM fact_user_event
WHERE event_id ~ '^[[:space:]]*$' OR event_name ~ '^[[:space:]]*$'
   OR user_id ~ '^[[:space:]]*$' OR device_type ~ '^[[:space:]]*$';

-- 위반 상세 조회용 (문제 행의 기본키를 보여준다. 이후 SELECT * FROM <table> WHERE <pk>='...' 로 전체 행 확인)
-- SELECT 'dim_artist' AS table_name, artist_id AS row_key
-- FROM dim_artist
-- WHERE artist_id ~ '^[[:space:]]*$' OR artist_name ~ '^[[:space:]]*$' OR artist_type ~ '^[[:space:]]*$'
-- UNION ALL
-- SELECT 'dim_user', user_id FROM dim_user
-- WHERE user_id ~ '^[[:space:]]*$' OR country_group ~ '^[[:space:]]*$'
--    OR acquisition_channel ~ '^[[:space:]]*$' OR primary_device_type ~ '^[[:space:]]*$'
-- UNION ALL
-- SELECT 'dim_content', content_id FROM dim_content
-- WHERE content_id ~ '^[[:space:]]*$' OR artist_id ~ '^[[:space:]]*$'
--    OR content_type ~ '^[[:space:]]*$' OR title ~ '^[[:space:]]*$'
-- UNION ALL
-- SELECT 'dim_product', product_id FROM dim_product
-- WHERE product_id ~ '^[[:space:]]*$' OR artist_id ~ '^[[:space:]]*$'
--    OR product_name ~ '^[[:space:]]*$' OR product_type ~ '^[[:space:]]*$'
-- UNION ALL
-- SELECT 'dim_activity_phase', phase_id FROM dim_activity_phase
-- WHERE phase_id ~ '^[[:space:]]*$' OR artist_id ~ '^[[:space:]]*$' OR phase_type ~ '^[[:space:]]*$'
-- UNION ALL
-- SELECT 'bridge_user_artist_follow', follow_id FROM bridge_user_artist_follow
-- WHERE follow_id ~ '^[[:space:]]*$' OR user_id ~ '^[[:space:]]*$' OR artist_id ~ '^[[:space:]]*$'
-- UNION ALL
-- SELECT 'fact_message_subscription', subscription_id FROM fact_message_subscription
-- WHERE subscription_id ~ '^[[:space:]]*$' OR user_id ~ '^[[:space:]]*$'
--    OR artist_id ~ '^[[:space:]]*$' OR plan_type ~ '^[[:space:]]*$'
-- UNION ALL
-- SELECT 'fact_artist_activity', activity_id FROM fact_artist_activity
-- WHERE activity_id ~ '^[[:space:]]*$' OR artist_id ~ '^[[:space:]]*$' OR activity_type ~ '^[[:space:]]*$'
-- UNION ALL
-- SELECT 'fact_order', transaction_id FROM fact_order
-- WHERE transaction_id ~ '^[[:space:]]*$' OR user_id ~ '^[[:space:]]*$' OR status ~ '^[[:space:]]*$'
-- UNION ALL
-- SELECT 'fact_order_item', order_item_id FROM fact_order_item
-- WHERE order_item_id ~ '^[[:space:]]*$' OR transaction_id ~ '^[[:space:]]*$' OR product_id ~ '^[[:space:]]*$'
-- UNION ALL
-- SELECT 'fact_user_event', event_id FROM fact_user_event
-- WHERE event_id ~ '^[[:space:]]*$' OR event_name ~ '^[[:space:]]*$'
--    OR user_id ~ '^[[:space:]]*$' OR device_type ~ '^[[:space:]]*$';


-- ============================================================
-- DQ-03: 외래키 고아 행 — dim_user/dim_artist/dim_content/dim_product/
--         fact_artist_activity/fact_order를 참조하는 모든 FK 컬럼 (18개)
-- 정의: docs/PRD.md 15.1절, docs/event_tracking_plan.md 9.1절
-- 참고: 모든 FK는 REFERENCES 제약으로 이미 DB가 막고 있다. 이 쿼리는 문서화 및 재확인 목적이다.
-- ============================================================
SELECT 'bridge_user_artist_follow.user_id -> dim_user' AS fk_relationship, COUNT(*) AS orphan_count
FROM bridge_user_artist_follow b
WHERE NOT EXISTS (SELECT 1 FROM dim_user u WHERE u.user_id = b.user_id)
UNION ALL
SELECT 'fact_message_subscription.user_id -> dim_user', COUNT(*)
FROM fact_message_subscription s
WHERE NOT EXISTS (SELECT 1 FROM dim_user u WHERE u.user_id = s.user_id)
UNION ALL
SELECT 'fact_order.user_id -> dim_user', COUNT(*)
FROM fact_order o
WHERE NOT EXISTS (SELECT 1 FROM dim_user u WHERE u.user_id = o.user_id)
UNION ALL
SELECT 'fact_user_event.user_id -> dim_user', COUNT(*)
FROM fact_user_event e
WHERE NOT EXISTS (SELECT 1 FROM dim_user u WHERE u.user_id = e.user_id)
UNION ALL
SELECT 'dim_content.artist_id -> dim_artist', COUNT(*)
FROM dim_content c
WHERE NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = c.artist_id)
UNION ALL
SELECT 'dim_product.artist_id -> dim_artist', COUNT(*)
FROM dim_product p
WHERE NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = p.artist_id)
UNION ALL
SELECT 'dim_activity_phase.artist_id -> dim_artist', COUNT(*)
FROM dim_activity_phase ph
WHERE NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = ph.artist_id)
UNION ALL
SELECT 'bridge_user_artist_follow.artist_id -> dim_artist', COUNT(*)
FROM bridge_user_artist_follow b
WHERE NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = b.artist_id)
UNION ALL
SELECT 'fact_message_subscription.artist_id -> dim_artist', COUNT(*)
FROM fact_message_subscription s
WHERE NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = s.artist_id)
UNION ALL
SELECT 'fact_artist_activity.artist_id -> dim_artist', COUNT(*)
FROM fact_artist_activity fa
WHERE NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = fa.artist_id)
UNION ALL
SELECT 'fact_user_event.artist_id -> dim_artist', COUNT(*)
FROM fact_user_event e
WHERE e.artist_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = e.artist_id)
UNION ALL
SELECT 'fact_artist_activity.content_id -> dim_content', COUNT(*)
FROM fact_artist_activity fa
WHERE fa.content_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM dim_content c WHERE c.content_id = fa.content_id)
UNION ALL
SELECT 'fact_user_event.content_id -> dim_content', COUNT(*)
FROM fact_user_event e
WHERE e.content_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM dim_content c WHERE c.content_id = e.content_id)
UNION ALL
SELECT 'fact_order_item.product_id -> dim_product', COUNT(*)
FROM fact_order_item oi
WHERE NOT EXISTS (SELECT 1 FROM dim_product p WHERE p.product_id = oi.product_id)
UNION ALL
SELECT 'fact_user_event.product_id -> dim_product', COUNT(*)
FROM fact_user_event e
WHERE e.product_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM dim_product p WHERE p.product_id = e.product_id)
UNION ALL
SELECT 'fact_user_event.activity_id -> fact_artist_activity', COUNT(*)
FROM fact_user_event e
WHERE e.activity_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM fact_artist_activity fa WHERE fa.activity_id = e.activity_id)
UNION ALL
SELECT 'fact_order_item.transaction_id -> fact_order', COUNT(*)
FROM fact_order_item oi
WHERE NOT EXISTS (SELECT 1 FROM fact_order o WHERE o.transaction_id = oi.transaction_id)
UNION ALL
SELECT 'fact_user_event.transaction_id -> fact_order', COUNT(*)
FROM fact_user_event e
WHERE e.transaction_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM fact_order o WHERE o.transaction_id = e.transaction_id);

-- 위반 상세 조회용 (문제 행의 기본키와 잘못된 FK 값을 보여준다)
-- SELECT 'bridge_user_artist_follow.user_id' AS fk_relationship, follow_id AS source_row_key, user_id AS bad_fk_value
-- FROM bridge_user_artist_follow b
-- WHERE NOT EXISTS (SELECT 1 FROM dim_user u WHERE u.user_id = b.user_id)
-- UNION ALL
-- SELECT 'fact_message_subscription.user_id', subscription_id, user_id
-- FROM fact_message_subscription s
-- WHERE NOT EXISTS (SELECT 1 FROM dim_user u WHERE u.user_id = s.user_id)
-- UNION ALL
-- SELECT 'fact_order.user_id', transaction_id, user_id
-- FROM fact_order o
-- WHERE NOT EXISTS (SELECT 1 FROM dim_user u WHERE u.user_id = o.user_id)
-- UNION ALL
-- SELECT 'fact_user_event.user_id', event_id, user_id
-- FROM fact_user_event e
-- WHERE NOT EXISTS (SELECT 1 FROM dim_user u WHERE u.user_id = e.user_id)
-- UNION ALL
-- SELECT 'dim_content.artist_id', content_id, artist_id
-- FROM dim_content c
-- WHERE NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = c.artist_id)
-- UNION ALL
-- SELECT 'dim_product.artist_id', product_id, artist_id
-- FROM dim_product p
-- WHERE NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = p.artist_id)
-- UNION ALL
-- SELECT 'dim_activity_phase.artist_id', phase_id, artist_id
-- FROM dim_activity_phase ph
-- WHERE NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = ph.artist_id)
-- UNION ALL
-- SELECT 'bridge_user_artist_follow.artist_id', follow_id, artist_id
-- FROM bridge_user_artist_follow b
-- WHERE NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = b.artist_id)
-- UNION ALL
-- SELECT 'fact_message_subscription.artist_id', subscription_id, artist_id
-- FROM fact_message_subscription s
-- WHERE NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = s.artist_id)
-- UNION ALL
-- SELECT 'fact_artist_activity.artist_id', activity_id, artist_id
-- FROM fact_artist_activity fa
-- WHERE NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = fa.artist_id)
-- UNION ALL
-- SELECT 'fact_user_event.artist_id', event_id, artist_id
-- FROM fact_user_event e
-- WHERE e.artist_id IS NOT NULL
--   AND NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = e.artist_id)
-- UNION ALL
-- SELECT 'fact_artist_activity.content_id', activity_id, content_id
-- FROM fact_artist_activity fa
-- WHERE fa.content_id IS NOT NULL
--   AND NOT EXISTS (SELECT 1 FROM dim_content c WHERE c.content_id = fa.content_id)
-- UNION ALL
-- SELECT 'fact_user_event.content_id', event_id, content_id
-- FROM fact_user_event e
-- WHERE e.content_id IS NOT NULL
--   AND NOT EXISTS (SELECT 1 FROM dim_content c WHERE c.content_id = e.content_id)
-- UNION ALL
-- SELECT 'fact_order_item.product_id', order_item_id, product_id
-- FROM fact_order_item oi
-- WHERE NOT EXISTS (SELECT 1 FROM dim_product p WHERE p.product_id = oi.product_id)
-- UNION ALL
-- SELECT 'fact_user_event.product_id', event_id, product_id
-- FROM fact_user_event e
-- WHERE e.product_id IS NOT NULL
--   AND NOT EXISTS (SELECT 1 FROM dim_product p WHERE p.product_id = e.product_id)
-- UNION ALL
-- SELECT 'fact_user_event.activity_id', event_id, activity_id
-- FROM fact_user_event e
-- WHERE e.activity_id IS NOT NULL
--   AND NOT EXISTS (SELECT 1 FROM fact_artist_activity fa WHERE fa.activity_id = e.activity_id)
-- UNION ALL
-- SELECT 'fact_order_item.transaction_id', order_item_id, transaction_id
-- FROM fact_order_item oi
-- WHERE NOT EXISTS (SELECT 1 FROM fact_order o WHERE o.transaction_id = oi.transaction_id)
-- UNION ALL
-- SELECT 'fact_user_event.transaction_id', event_id, transaction_id
-- FROM fact_user_event e
-- WHERE e.transaction_id IS NOT NULL
--   AND NOT EXISTS (SELECT 1 FROM fact_order o WHERE o.transaction_id = e.transaction_id);


-- ============================================================
-- ET-DQ-01: fact_user_event.event_id 중복
-- 정의: docs/event_tracking_plan.md 9절
-- ============================================================
SELECT COUNT(*) AS duplicate_event_id_count
FROM (SELECT event_id FROM fact_user_event GROUP BY event_id HAVING COUNT(*) > 1) d;

-- 위반 상세 조회용
-- SELECT event_id, COUNT(*) AS occurrence_count
-- FROM fact_user_event
-- GROUP BY event_id
-- HAVING COUNT(*) > 1;


-- ============================================================
-- ET-DQ-02: fact_artist_activity.activity_id 중복
-- 정의: docs/event_tracking_plan.md 9절
-- ============================================================
SELECT COUNT(*) AS duplicate_activity_id_count
FROM (SELECT activity_id FROM fact_artist_activity GROUP BY activity_id HAVING COUNT(*) > 1) d;

-- 위반 상세 조회용
-- SELECT activity_id, COUNT(*) AS occurrence_count
-- FROM fact_artist_activity
-- GROUP BY activity_id
-- HAVING COUNT(*) > 1;


-- ============================================================
-- ET-DQ-03: 허용 목록(18개)에 없는 fact_user_event.event_name
-- 정의: docs/event_tracking_plan.md 9절
-- 참고: sql/ddl/003_facts.sql의 CHECK 제약이 이미 이 18개 값으로만 제한하고 있다.
--       이 쿼리는 문서화 목적으로 만들어둔다.
-- ============================================================
SELECT COUNT(*) AS invalid_event_name_count
FROM fact_user_event
WHERE event_name NOT IN (
    'sign_up', 'session_start', 'artist_view', 'artist_follow', 'artist_unfollow',
    'message_subscription_start', 'message_subscription_cancel', 'artist_post_view',
    'message_open', 'live_view_start', 'content_view', 'content_like', 'comment_create',
    'view_item', 'add_to_cart', 'begin_checkout', 'purchase', 'refund'
);

-- 위반 상세 조회용
-- SELECT event_id, event_name
-- FROM fact_user_event
-- WHERE event_name NOT IN (
--     'sign_up', 'session_start', 'artist_view', 'artist_follow', 'artist_unfollow',
--     'message_subscription_start', 'message_subscription_cancel', 'artist_post_view',
--     'message_open', 'live_view_start', 'content_view', 'content_like', 'comment_create',
--     'view_item', 'add_to_cart', 'begin_checkout', 'purchase', 'refund'
-- );


-- ============================================================
-- ET-DQ-04: 허용 목록에 없는 fact_artist_activity.activity_type
-- 정의: docs/event_tracking_plan.md 9절
-- 참고: sql/ddl/003_facts.sql의 CHECK 제약이 이미 ('post','message','live')로 제한하고 있다.
--       이 쿼리는 문서화 목적으로 만들어둔다.
-- ============================================================
SELECT COUNT(*) AS invalid_activity_type_count
FROM fact_artist_activity
WHERE activity_type NOT IN ('post', 'message', 'live');

-- 위반 상세 조회용
-- SELECT activity_id, activity_type
-- FROM fact_artist_activity
-- WHERE activity_type NOT IN ('post', 'message', 'live');


-- ============================================================
-- ET-DQ-05: fact_user_event에서 user_id가 NULL인 행
-- 정의: docs/event_tracking_plan.md 9절
-- 참고: sql/ddl/003_facts.sql에서 user_id는 이미 NOT NULL이다. 이 쿼리는 재확인 목적이다.
-- ============================================================
SELECT COUNT(*) AS null_user_id_count
FROM fact_user_event
WHERE user_id IS NULL;

-- 위반 상세 조회용
-- SELECT event_id, event_name, event_timestamp_utc
-- FROM fact_user_event
-- WHERE user_id IS NULL;


-- ============================================================
-- ET-DQ-06: 참조 대상이 없는 외래키 — event_tracking_plan.md 9.1절에 명시된
--           fact_user_event의 6개 참조 관계(user_id/artist_id/content_id/
--           activity_id/product_id/transaction_id) 전수 확인
-- 정의: docs/event_tracking_plan.md 9절, 9.1절
-- 참고: DQ-03에서 이미 같은 6개 관계를 확인했으므로 로직을 그대로 재사용한다.
-- ============================================================
SELECT 'user_id -> dim_user' AS fk_relationship, COUNT(*) AS orphan_count
FROM fact_user_event e
WHERE NOT EXISTS (SELECT 1 FROM dim_user u WHERE u.user_id = e.user_id)
UNION ALL
SELECT 'artist_id -> dim_artist', COUNT(*)
FROM fact_user_event e
WHERE e.artist_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = e.artist_id)
UNION ALL
SELECT 'content_id -> dim_content', COUNT(*)
FROM fact_user_event e
WHERE e.content_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM dim_content c WHERE c.content_id = e.content_id)
UNION ALL
SELECT 'activity_id -> fact_artist_activity', COUNT(*)
FROM fact_user_event e
WHERE e.activity_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM fact_artist_activity fa WHERE fa.activity_id = e.activity_id)
UNION ALL
SELECT 'product_id -> dim_product', COUNT(*)
FROM fact_user_event e
WHERE e.product_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM dim_product p WHERE p.product_id = e.product_id)
UNION ALL
SELECT 'transaction_id -> fact_order', COUNT(*)
FROM fact_user_event e
WHERE e.transaction_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM fact_order o WHERE o.transaction_id = e.transaction_id);

-- 위반 상세 조회용
-- SELECT 'user_id' AS fk_column, event_id, user_id AS bad_fk_value
-- FROM fact_user_event e
-- WHERE NOT EXISTS (SELECT 1 FROM dim_user u WHERE u.user_id = e.user_id)
-- UNION ALL
-- SELECT 'artist_id', event_id, artist_id
-- FROM fact_user_event e
-- WHERE e.artist_id IS NOT NULL
--   AND NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = e.artist_id)
-- UNION ALL
-- SELECT 'content_id', event_id, content_id
-- FROM fact_user_event e
-- WHERE e.content_id IS NOT NULL
--   AND NOT EXISTS (SELECT 1 FROM dim_content c WHERE c.content_id = e.content_id)
-- UNION ALL
-- SELECT 'activity_id', event_id, activity_id
-- FROM fact_user_event e
-- WHERE e.activity_id IS NOT NULL
--   AND NOT EXISTS (SELECT 1 FROM fact_artist_activity fa WHERE fa.activity_id = e.activity_id)
-- UNION ALL
-- SELECT 'product_id', event_id, product_id
-- FROM fact_user_event e
-- WHERE e.product_id IS NOT NULL
--   AND NOT EXISTS (SELECT 1 FROM dim_product p WHERE p.product_id = e.product_id)
-- UNION ALL
-- SELECT 'transaction_id', event_id, transaction_id
-- FROM fact_user_event e
-- WHERE e.transaction_id IS NOT NULL
--   AND NOT EXISTS (SELECT 1 FROM fact_order o WHERE o.transaction_id = e.transaction_id);
