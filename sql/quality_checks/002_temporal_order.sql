-- ============================================================
-- FANLOG 데이터 품질검사 2/5: 시간 순서
-- 기준 문서: docs/PRD.md 10.4절·15.1절(DQ-04~06), docs/event_tracking_plan.md 9.2절·11.1.1·11.2.1(ET-DQ-07,09,11,14,16~19,21)
-- 대상 규칙: DQ-04, DQ-05, DQ-06, ET-DQ-07, ET-DQ-09, ET-DQ-11, ET-DQ-14,
--            ET-DQ-16, ET-DQ-17, ET-DQ-18, ET-DQ-19, ET-DQ-21
-- ET-DQ-07은 DQ-04와, ET-DQ-11은 DQ-06과 각각 동일한 로직을 재사용한다(주석에 명시).
-- 나머지 규칙(DQ-07~10, ET-DQ-08,10,12,13,15,20,22~28)은 다음 그룹(3/5 이후)에서 다룬다.
--
-- 모든 위반 건수 쿼리는 0이어야 정상이다.
-- 위반이 있을 경우 참고할 "위반 상세 조회용" 쿼리를 각 규칙 바로 아래 주석으로 남겨뒀다(필요할 때만 주석 해제).
--
-- 실행 방법: psql -f sql/quality_checks/002_temporal_order.sql
-- (또는 psql 세션 안에서 \i sql/quality_checks/002_temporal_order.sql)
-- ============================================================


-- ============================================================
-- [요약 쿼리] 아래 12개 규칙 항목의 위반 건수를 한 번에 표로 출력한다.
-- 이 문서 하단의 개별 쿼리들과 로직은 동일하되, rule_id/target/violation_count 형태로 합쳐서 보여준다.
-- ============================================================
SELECT rule_id, target, violation_count
FROM (
    -- ---------- DQ-04: 가입 전 사용자 이벤트 ----------
    SELECT 'DQ-04' AS rule_id, 'fact_user_event.event_timestamp_utc < dim_user.signup_timestamp_utc' AS target, COUNT(*) AS violation_count
    FROM fact_user_event e
    JOIN dim_user u ON u.user_id = e.user_id
    WHERE e.event_timestamp_utc < u.signup_timestamp_utc

    UNION ALL

    -- ---------- DQ-05: 구독 자격 없는 메시지 열람 ----------
    SELECT 'DQ-05', 'message_open (활성 구독 없음)', COUNT(*)
    FROM fact_user_event e
    WHERE e.event_name = 'message_open'
      AND NOT EXISTS (
          SELECT 1 FROM fact_message_subscription s
          WHERE s.user_id = e.user_id AND s.artist_id = e.artist_id
            AND s.started_at_utc <= e.event_timestamp_utc
            AND (s.ended_at_utc IS NULL OR e.event_timestamp_utc < s.ended_at_utc)
      )

    UNION ALL

    -- ---------- DQ-06: 상품 출시 전 구매 ----------
    SELECT 'DQ-06', 'view_item/add_to_cart (product_id 직접)', COUNT(*)
    FROM fact_user_event e
    JOIN dim_product p ON p.product_id = e.product_id
    WHERE e.event_name IN ('view_item', 'add_to_cart')
      AND e.event_timestamp_utc < p.release_timestamp_utc
    UNION ALL
    SELECT 'DQ-06', 'begin_checkout/purchase (fact_order_item 경유)', COUNT(*)
    FROM (
        SELECT DISTINCT e.event_id
        FROM fact_user_event e
        JOIN fact_order_item oi ON oi.transaction_id = e.transaction_id
        JOIN dim_product p ON p.product_id = oi.product_id
        WHERE e.event_name IN ('begin_checkout', 'purchase')
          AND e.event_timestamp_utc < p.release_timestamp_utc
    ) t

    UNION ALL

    -- ---------- ET-DQ-07: 사용자 가입 시각보다 빠른 팬 이벤트 (DQ-04와 동일, 재사용) ----------
    SELECT 'ET-DQ-07', '(DQ-04와 동일) fact_user_event.event_timestamp_utc < dim_user.signup_timestamp_utc', COUNT(*)
    FROM fact_user_event e
    JOIN dim_user u ON u.user_id = e.user_id
    WHERE e.event_timestamp_utc < u.signup_timestamp_utc

    UNION ALL

    -- ---------- ET-DQ-09: 중복된 purchase.transaction_id ----------
    SELECT 'ET-DQ-09', 'fact_user_event(event_name=purchase).transaction_id 중복', COUNT(*)
    FROM (
        SELECT transaction_id
        FROM fact_user_event
        WHERE event_name = 'purchase'
        GROUP BY transaction_id
        HAVING COUNT(*) > 1
    ) d

    UNION ALL

    -- ---------- ET-DQ-11: 상품 출시 시각보다 빠른 상품 이벤트 (DQ-06과 동일, 재사용) ----------
    SELECT 'ET-DQ-11', '(DQ-06과 동일) view_item/add_to_cart (product_id 직접)', COUNT(*)
    FROM fact_user_event e
    JOIN dim_product p ON p.product_id = e.product_id
    WHERE e.event_name IN ('view_item', 'add_to_cart')
      AND e.event_timestamp_utc < p.release_timestamp_utc
    UNION ALL
    SELECT 'ET-DQ-11', '(DQ-06과 동일) begin_checkout/purchase (fact_order_item 경유)', COUNT(*)
    FROM (
        SELECT DISTINCT e.event_id
        FROM fact_user_event e
        JOIN fact_order_item oi ON oi.transaction_id = e.transaction_id
        JOIN dim_product p ON p.product_id = oi.product_id
        WHERE e.event_name IN ('begin_checkout', 'purchase')
          AND e.event_timestamp_utc < p.release_timestamp_utc
    ) t

    UNION ALL

    -- ---------- ET-DQ-14: 분석 기간을 벗어난 이벤트·활동 ----------
    -- 분석 기간: 2026-01-01 00:00:00 KST ~ 2026-03-31 23:59:59 KST
    --          = UTC 2025-12-31T15:00:00Z ~ 2026-03-31T14:59:59Z
    SELECT 'ET-DQ-14', 'fact_user_event', COUNT(*)
    FROM fact_user_event
    WHERE event_timestamp_utc < '2025-12-31T15:00:00Z'::timestamptz
       OR event_timestamp_utc > '2026-03-31T14:59:59Z'::timestamptz
    UNION ALL
    SELECT 'ET-DQ-14', 'fact_artist_activity', COUNT(*)
    FROM fact_artist_activity
    WHERE activity_timestamp_utc < '2025-12-31T15:00:00Z'::timestamptz
       OR activity_timestamp_utc > '2026-03-31T14:59:59Z'::timestamptz

    UNION ALL

    -- ---------- ET-DQ-16: user_id별 session_number 1부터 순차 증가 ----------
    SELECT 'ET-DQ-16', 'session_start.parameters.session_number 순차성', COUNT(*)
    FROM (
        SELECT
            (parameters ->> 'session_number')::int AS session_number,
            ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY event_timestamp_utc) AS expected_number
        FROM fact_user_event
        WHERE event_name = 'session_start'
    ) s
    WHERE s.session_number <> s.expected_number

    UNION ALL

    -- ---------- ET-DQ-17: 팬당 sign_up 2건 이상 ----------
    SELECT 'ET-DQ-17', 'sign_up 팬당 2건 이상', COUNT(*)
    FROM (
        SELECT user_id
        FROM fact_user_event
        WHERE event_name = 'sign_up'
        GROUP BY user_id
        HAVING COUNT(*) > 1
    ) d

    UNION ALL

    -- ---------- ET-DQ-18: 활성 팔로우 없는 artist_unfollow ----------
    SELECT 'ET-DQ-18', 'artist_unfollow (활성 팔로우 없음)', COUNT(*)
    FROM fact_user_event e
    WHERE e.event_name = 'artist_unfollow'
      AND NOT EXISTS (
          SELECT 1 FROM bridge_user_artist_follow b
          WHERE b.user_id = e.user_id AND b.artist_id = e.artist_id
            AND b.followed_at_utc <= e.event_timestamp_utc
            AND (b.unfollowed_at_utc IS NULL OR b.unfollowed_at_utc >= e.event_timestamp_utc)
      )

    UNION ALL

    -- ---------- ET-DQ-19: 동일 팬·아티스트 조합 활성 팔로우 2개 이상 동시 존재 ----------
    SELECT 'ET-DQ-19', 'bridge_user_artist_follow (활성 팔로우 중복)', COUNT(*)
    FROM (
        SELECT user_id, artist_id
        FROM bridge_user_artist_follow
        WHERE unfollowed_at_utc IS NULL
        GROUP BY user_id, artist_id
        HAVING COUNT(*) > 1
    ) d

    UNION ALL

    -- ---------- ET-DQ-21: 활성 구독 없는 message_subscription_cancel ----------
    SELECT 'ET-DQ-21', 'message_subscription_cancel (활성 구독 없음)', COUNT(*)
    FROM fact_user_event e
    WHERE e.event_name = 'message_subscription_cancel'
      AND NOT EXISTS (
          SELECT 1 FROM fact_message_subscription s
          WHERE s.user_id = e.user_id AND s.artist_id = e.artist_id
            AND s.started_at_utc <= e.event_timestamp_utc
            AND (s.ended_at_utc IS NULL OR s.ended_at_utc >= e.event_timestamp_utc)
      )
) summary
ORDER BY rule_id, target;


-- ============================================================
-- 이하 개별 쿼리 (규칙별로 다시 실행하고 싶을 때 이 아래부터 필요한 부분만 발췌해서 쓴다)
-- ============================================================


-- ============================================================
-- DQ-04: 가입 전 사용자 이벤트
-- 정의: docs/PRD.md 10.4절·15.1절
-- ============================================================
SELECT COUNT(*) AS pre_signup_event_count
FROM fact_user_event e
JOIN dim_user u ON u.user_id = e.user_id
WHERE e.event_timestamp_utc < u.signup_timestamp_utc;

-- 위반 상세 조회용
-- SELECT e.event_id, e.user_id, e.event_name, e.event_timestamp_utc, u.signup_timestamp_utc
-- FROM fact_user_event e
-- JOIN dim_user u ON u.user_id = e.user_id
-- WHERE e.event_timestamp_utc < u.signup_timestamp_utc
-- ORDER BY e.user_id, e.event_timestamp_utc;


-- ============================================================
-- DQ-05: 구독 자격 없는 메시지 열람
-- 정의: docs/PRD.md 10.4절·15.1절, docs/event_tracking_plan.md 9.2절
-- 참고: message_open은 이벤트 발생 시점에 (user_id, artist_id) 조합의 활성 구독
--       (started_at_utc <= 이벤트 시각 < ended_at_utc, 또는 ended_at_utc가 NULL)이 있어야 한다.
-- ============================================================
SELECT COUNT(*) AS invalid_message_open_count
FROM fact_user_event e
WHERE e.event_name = 'message_open'
  AND NOT EXISTS (
      SELECT 1 FROM fact_message_subscription s
      WHERE s.user_id = e.user_id AND s.artist_id = e.artist_id
        AND s.started_at_utc <= e.event_timestamp_utc
        AND (s.ended_at_utc IS NULL OR e.event_timestamp_utc < s.ended_at_utc)
  );

-- 위반 상세 조회용
-- SELECT e.event_id, e.user_id, e.artist_id, e.event_timestamp_utc
-- FROM fact_user_event e
-- WHERE e.event_name = 'message_open'
--   AND NOT EXISTS (
--       SELECT 1 FROM fact_message_subscription s
--       WHERE s.user_id = e.user_id AND s.artist_id = e.artist_id
--         AND s.started_at_utc <= e.event_timestamp_utc
--         AND (s.ended_at_utc IS NULL OR e.event_timestamp_utc < s.ended_at_utc)
--   )
-- ORDER BY e.user_id, e.event_timestamp_utc;


-- ============================================================
-- DQ-06: 상품 출시 전 구매 (view_item/add_to_cart/begin_checkout/purchase)
-- 정의: docs/PRD.md 10.4절·15.1절
-- 참고: view_item/add_to_cart는 이벤트에 product_id가 직접 있고,
--       begin_checkout/purchase는 product_id 대신 transaction_id로 fact_order_item을 거쳐
--       상품을 확인한다(사용자 요청: docs/event_tracking_plan.md 11.4절 참고).
-- ============================================================
SELECT 'view_item/add_to_cart (product_id 직접)' AS target, COUNT(*) AS violation_count
FROM fact_user_event e
JOIN dim_product p ON p.product_id = e.product_id
WHERE e.event_name IN ('view_item', 'add_to_cart')
  AND e.event_timestamp_utc < p.release_timestamp_utc
UNION ALL
SELECT 'begin_checkout/purchase (fact_order_item 경유)', COUNT(*)
FROM (
    SELECT DISTINCT e.event_id
    FROM fact_user_event e
    JOIN fact_order_item oi ON oi.transaction_id = e.transaction_id
    JOIN dim_product p ON p.product_id = oi.product_id
    WHERE e.event_name IN ('begin_checkout', 'purchase')
      AND e.event_timestamp_utc < p.release_timestamp_utc
) t;

-- 위반 상세 조회용
-- SELECT 'view_item/add_to_cart' AS source, e.event_id, e.event_name, e.product_id, e.event_timestamp_utc, p.release_timestamp_utc
-- FROM fact_user_event e
-- JOIN dim_product p ON p.product_id = e.product_id
-- WHERE e.event_name IN ('view_item', 'add_to_cart')
--   AND e.event_timestamp_utc < p.release_timestamp_utc
-- UNION ALL
-- SELECT 'begin_checkout/purchase', e.event_id, e.event_name, oi.product_id, e.event_timestamp_utc, p.release_timestamp_utc
-- FROM fact_user_event e
-- JOIN fact_order_item oi ON oi.transaction_id = e.transaction_id
-- JOIN dim_product p ON p.product_id = oi.product_id
-- WHERE e.event_name IN ('begin_checkout', 'purchase')
--   AND e.event_timestamp_utc < p.release_timestamp_utc
-- ORDER BY 1, 5;


-- ============================================================
-- ET-DQ-07: 사용자 가입 시각보다 빠른 팬 이벤트
-- 정의: docs/event_tracking_plan.md 9.2절
-- 참고: DQ-04와 완전히 동일한 규칙·로직이므로 재사용한다.
-- ============================================================
SELECT COUNT(*) AS pre_signup_event_count
FROM fact_user_event e
JOIN dim_user u ON u.user_id = e.user_id
WHERE e.event_timestamp_utc < u.signup_timestamp_utc;

-- 위반 상세 조회용 (DQ-04와 동일)
-- SELECT e.event_id, e.user_id, e.event_name, e.event_timestamp_utc, u.signup_timestamp_utc
-- FROM fact_user_event e
-- JOIN dim_user u ON u.user_id = e.user_id
-- WHERE e.event_timestamp_utc < u.signup_timestamp_utc
-- ORDER BY e.user_id, e.event_timestamp_utc;


-- ============================================================
-- ET-DQ-09: 중복된 purchase.transaction_id
-- 정의: docs/event_tracking_plan.md 9절
-- 참고: fact_order의 PK 중복은 DQ-01에서 이미 확인했다. 이 규칙은
--       fact_user_event에서 event_name='purchase'인 행이 같은 transaction_id로
--       2건 이상 있는지(9.3절 "하나의 transaction_id에 성공한 purchase는 최대 한 건")를 본다.
-- ============================================================
SELECT COUNT(*) AS duplicate_purchase_transaction_count
FROM (
    SELECT transaction_id
    FROM fact_user_event
    WHERE event_name = 'purchase'
    GROUP BY transaction_id
    HAVING COUNT(*) > 1
) d;

-- 위반 상세 조회용
-- SELECT transaction_id, COUNT(*) AS occurrence_count
-- FROM fact_user_event
-- WHERE event_name = 'purchase'
-- GROUP BY transaction_id
-- HAVING COUNT(*) > 1;


-- ============================================================
-- ET-DQ-11: 상품 출시 시각보다 빠른 상품 이벤트
-- 정의: docs/event_tracking_plan.md 9.2절
-- 참고: DQ-06과 완전히 동일한 규칙·로직이므로 재사용한다.
-- ============================================================
SELECT 'view_item/add_to_cart (product_id 직접)' AS target, COUNT(*) AS violation_count
FROM fact_user_event e
JOIN dim_product p ON p.product_id = e.product_id
WHERE e.event_name IN ('view_item', 'add_to_cart')
  AND e.event_timestamp_utc < p.release_timestamp_utc
UNION ALL
SELECT 'begin_checkout/purchase (fact_order_item 경유)', COUNT(*)
FROM (
    SELECT DISTINCT e.event_id
    FROM fact_user_event e
    JOIN fact_order_item oi ON oi.transaction_id = e.transaction_id
    JOIN dim_product p ON p.product_id = oi.product_id
    WHERE e.event_name IN ('begin_checkout', 'purchase')
      AND e.event_timestamp_utc < p.release_timestamp_utc
) t;

-- 위반 상세 조회용 (DQ-06과 동일)
-- SELECT 'view_item/add_to_cart' AS source, e.event_id, e.event_name, e.product_id, e.event_timestamp_utc, p.release_timestamp_utc
-- FROM fact_user_event e
-- JOIN dim_product p ON p.product_id = e.product_id
-- WHERE e.event_name IN ('view_item', 'add_to_cart')
--   AND e.event_timestamp_utc < p.release_timestamp_utc
-- UNION ALL
-- SELECT 'begin_checkout/purchase', e.event_id, e.event_name, oi.product_id, e.event_timestamp_utc, p.release_timestamp_utc
-- FROM fact_user_event e
-- JOIN fact_order_item oi ON oi.transaction_id = e.transaction_id
-- JOIN dim_product p ON p.product_id = oi.product_id
-- WHERE e.event_name IN ('begin_checkout', 'purchase')
--   AND e.event_timestamp_utc < p.release_timestamp_utc
-- ORDER BY 1, 5;


-- ============================================================
-- ET-DQ-14: 분석 기간을 벗어난 fact_user_event·fact_artist_activity 행
-- 정의: docs/event_tracking_plan.md 9절
-- 분석 기간: 2026-01-01 00:00:00 KST ~ 2026-03-31 23:59:59 KST
--          = UTC 2025-12-31T15:00:00Z ~ 2026-03-31T14:59:59Z
-- ============================================================
SELECT 'fact_user_event' AS target, COUNT(*) AS violation_count
FROM fact_user_event
WHERE event_timestamp_utc < '2025-12-31T15:00:00Z'::timestamptz
   OR event_timestamp_utc > '2026-03-31T14:59:59Z'::timestamptz
UNION ALL
SELECT 'fact_artist_activity', COUNT(*)
FROM fact_artist_activity
WHERE activity_timestamp_utc < '2025-12-31T15:00:00Z'::timestamptz
   OR activity_timestamp_utc > '2026-03-31T14:59:59Z'::timestamptz;

-- 위반 상세 조회용
-- SELECT 'fact_user_event' AS source, event_id AS row_key, event_timestamp_utc AS bad_timestamp
-- FROM fact_user_event
-- WHERE event_timestamp_utc < '2025-12-31T15:00:00Z'::timestamptz
--    OR event_timestamp_utc > '2026-03-31T14:59:59Z'::timestamptz
-- UNION ALL
-- SELECT 'fact_artist_activity', activity_id, activity_timestamp_utc
-- FROM fact_artist_activity
-- WHERE activity_timestamp_utc < '2025-12-31T15:00:00Z'::timestamptz
--    OR activity_timestamp_utc > '2026-03-31T14:59:59Z'::timestamptz
-- ORDER BY 1, 3;


-- ============================================================
-- ET-DQ-16: 동일 user_id의 session_number가 1부터 중복 없이 순차 증가하는지
-- 정의: docs/event_tracking_plan.md 11.1.1절
-- 참고: session_start 이벤트를 user_id별로 event_timestamp_utc 순으로 정렬한 뒤,
--       parameters.session_number가 그 순번(1부터 시작하는 ROW_NUMBER)과 일치하는지 확인한다.
--       일치하지 않으면 중복·건너뜀·역전 중 하나가 있다는 뜻이다.
-- ============================================================
SELECT COUNT(*) AS session_number_mismatch_count
FROM (
    SELECT
        user_id,
        event_id,
        event_timestamp_utc,
        (parameters ->> 'session_number')::int AS session_number,
        ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY event_timestamp_utc) AS expected_number
    FROM fact_user_event
    WHERE event_name = 'session_start'
) s
WHERE s.session_number <> s.expected_number;

-- 위반 상세 조회용
-- SELECT user_id, event_id, event_timestamp_utc, session_number, expected_number
-- FROM (
--     SELECT
--         user_id,
--         event_id,
--         event_timestamp_utc,
--         (parameters ->> 'session_number')::int AS session_number,
--         ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY event_timestamp_utc) AS expected_number
--     FROM fact_user_event
--     WHERE event_name = 'session_start'
-- ) s
-- WHERE s.session_number <> s.expected_number
-- ORDER BY user_id, event_timestamp_utc;


-- ============================================================
-- ET-DQ-17: sign_up이 팬당 2건 이상 존재하는 경우
-- 정의: docs/event_tracking_plan.md 11.1.1절
-- ============================================================
SELECT COUNT(*) AS duplicate_signup_user_count
FROM (
    SELECT user_id
    FROM fact_user_event
    WHERE event_name = 'sign_up'
    GROUP BY user_id
    HAVING COUNT(*) > 1
) d;

-- 위반 상세 조회용
-- SELECT user_id, COUNT(*) AS signup_count
-- FROM fact_user_event
-- WHERE event_name = 'sign_up'
-- GROUP BY user_id
-- HAVING COUNT(*) > 1;


-- ============================================================
-- ET-DQ-18: 활성 팔로우 상태가 아닌 팬·아티스트 조합에서 발생한 artist_unfollow
-- 정의: docs/event_tracking_plan.md 11.2.1절
-- 참고: artist_unfollow는 bridge_user_artist_follow에서 역산 생성되므로 이 검사는
--       사실상 항상 0건이어야 하지만, 독립적인 재검증 차원에서 작성한다.
--       "활성"의 기준: followed_at_utc <= 이벤트 시각 AND (unfollowed_at_utc가 NULL이거나
--       이벤트 시각 이상)이다(이 이벤트 자체가 unfollowed_at_utc를 채운 경우도 활성으로 인정).
-- ============================================================
SELECT COUNT(*) AS invalid_unfollow_count
FROM fact_user_event e
WHERE e.event_name = 'artist_unfollow'
  AND NOT EXISTS (
      SELECT 1 FROM bridge_user_artist_follow b
      WHERE b.user_id = e.user_id AND b.artist_id = e.artist_id
        AND b.followed_at_utc <= e.event_timestamp_utc
        AND (b.unfollowed_at_utc IS NULL OR b.unfollowed_at_utc >= e.event_timestamp_utc)
  );

-- 위반 상세 조회용
-- SELECT e.event_id, e.user_id, e.artist_id, e.event_timestamp_utc
-- FROM fact_user_event e
-- WHERE e.event_name = 'artist_unfollow'
--   AND NOT EXISTS (
--       SELECT 1 FROM bridge_user_artist_follow b
--       WHERE b.user_id = e.user_id AND b.artist_id = e.artist_id
--         AND b.followed_at_utc <= e.event_timestamp_utc
--         AND (b.unfollowed_at_utc IS NULL OR b.unfollowed_at_utc >= e.event_timestamp_utc)
--   )
-- ORDER BY e.user_id, e.event_timestamp_utc;


-- ============================================================
-- ET-DQ-19: 동일 팬·아티스트 조합에서 종료되지 않은 활성 팔로우 행이 2개 이상 동시 존재
-- 정의: docs/event_tracking_plan.md 11.2.1절, docs/PRD.md 10.4절
-- ============================================================
SELECT COUNT(*) AS duplicate_active_follow_count
FROM (
    SELECT user_id, artist_id
    FROM bridge_user_artist_follow
    WHERE unfollowed_at_utc IS NULL
    GROUP BY user_id, artist_id
    HAVING COUNT(*) > 1
) d;

-- 위반 상세 조회용
-- SELECT user_id, artist_id, COUNT(*) AS active_follow_count
-- FROM bridge_user_artist_follow
-- WHERE unfollowed_at_utc IS NULL
-- GROUP BY user_id, artist_id
-- HAVING COUNT(*) > 1;


-- ============================================================
-- ET-DQ-21: 활성 구독이 없는 상태에서 발생한 message_subscription_cancel
-- 정의: docs/event_tracking_plan.md 11.2.1절
-- 참고: "활성"의 기준은 DQ-05와 동일하되, 이 이벤트 자체가 ended_at_utc를 채운
--       경우도 활성으로 인정하기 위해 이벤트 시각 이상까지 포함한다.
-- ============================================================
SELECT COUNT(*) AS invalid_cancel_count
FROM fact_user_event e
WHERE e.event_name = 'message_subscription_cancel'
  AND NOT EXISTS (
      SELECT 1 FROM fact_message_subscription s
      WHERE s.user_id = e.user_id AND s.artist_id = e.artist_id
        AND s.started_at_utc <= e.event_timestamp_utc
        AND (s.ended_at_utc IS NULL OR s.ended_at_utc >= e.event_timestamp_utc)
  );

-- 위반 상세 조회용
-- SELECT e.event_id, e.user_id, e.artist_id, e.event_timestamp_utc
-- FROM fact_user_event e
-- WHERE e.event_name = 'message_subscription_cancel'
--   AND NOT EXISTS (
--       SELECT 1 FROM fact_message_subscription s
--       WHERE s.user_id = e.user_id AND s.artist_id = e.artist_id
--         AND s.started_at_utc <= e.event_timestamp_utc
--         AND (s.ended_at_utc IS NULL OR s.ended_at_utc >= e.event_timestamp_utc)
--   )
-- ORDER BY e.user_id, e.event_timestamp_utc;
