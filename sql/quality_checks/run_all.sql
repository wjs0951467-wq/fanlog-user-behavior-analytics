-- ============================================================
-- FANLOG 데이터 품질검사 전체 통합 실행 스크립트
-- 001~005번 파일(기본키·외래키·결측 / 시간순서 / 허용값·카테고리 / 구매·환불 정합성 /
-- UTC-KST 타임존 일치) 전체 규칙을 한 번에 돌리기 위한 스크립트다.
--
-- 구성:
--   1) [통합 요약] 5개 그룹, 87개 세부 항목을 하나의 표로 합쳐서 보여준다(전부 0이어야 정상).
--   2) [참고용] ET-DQ-28 pending 주문 집계 (위반 아님, 별도 표시).
--   3) \i 로 001~005 파일 전체를 순서대로 실행한다(각 파일 자체의 요약·개별·상세조회용
--      쿼리까지 그대로 재실행되며, 감사 추적·개별 규칙 재확인용으로 남겨둔다).
--
-- 실행 방법: psql -f sql/quality_checks/run_all.sql
-- (또는 psql 세션 안에서 \i sql/quality_checks/run_all.sql)
-- ============================================================


-- ============================================================
-- 1) [통합 요약] 001~005 전체 규칙 87개 세부 항목을 하나의 표로 출력한다.
--    group_no 1~5는 각각 001~005 파일에 대응한다.
-- ============================================================
SELECT group_no, source_file, rule_id, target, violation_count
FROM (

    -- ======== group 1: 001_keys_and_referential_integrity.sql (51개 항목) ========
    SELECT 1 AS group_no, '001_keys_and_referential_integrity.sql' AS source_file, 'DQ-01' AS rule_id, 'dim_artist' AS target, COUNT(*) AS violation_count
    FROM (SELECT artist_id FROM dim_artist GROUP BY artist_id HAVING COUNT(*) > 1) d
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-01', 'dim_user', COUNT(*)
    FROM (SELECT user_id FROM dim_user GROUP BY user_id HAVING COUNT(*) > 1) d
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-01', 'dim_content', COUNT(*)
    FROM (SELECT content_id FROM dim_content GROUP BY content_id HAVING COUNT(*) > 1) d
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-01', 'dim_product', COUNT(*)
    FROM (SELECT product_id FROM dim_product GROUP BY product_id HAVING COUNT(*) > 1) d
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-01', 'dim_activity_phase', COUNT(*)
    FROM (SELECT phase_id FROM dim_activity_phase GROUP BY phase_id HAVING COUNT(*) > 1) d
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-01', 'bridge_user_artist_follow', COUNT(*)
    FROM (SELECT follow_id FROM bridge_user_artist_follow GROUP BY follow_id HAVING COUNT(*) > 1) d
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-01', 'fact_message_subscription', COUNT(*)
    FROM (SELECT subscription_id FROM fact_message_subscription GROUP BY subscription_id HAVING COUNT(*) > 1) d
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-01', 'fact_artist_activity', COUNT(*)
    FROM (SELECT activity_id FROM fact_artist_activity GROUP BY activity_id HAVING COUNT(*) > 1) d
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-01', 'fact_order', COUNT(*)
    FROM (SELECT transaction_id FROM fact_order GROUP BY transaction_id HAVING COUNT(*) > 1) d
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-01', 'fact_order_item', COUNT(*)
    FROM (SELECT order_item_id FROM fact_order_item GROUP BY order_item_id HAVING COUNT(*) > 1) d
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-01', 'fact_user_event', COUNT(*)
    FROM (SELECT event_id FROM fact_user_event GROUP BY event_id HAVING COUNT(*) > 1) d
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-02', 'dim_artist', COUNT(*)
    FROM dim_artist
    WHERE artist_id ~ '^[[:space:]]*$' OR artist_name ~ '^[[:space:]]*$' OR artist_type ~ '^[[:space:]]*$'
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-02', 'dim_user', COUNT(*)
    FROM dim_user
    WHERE user_id ~ '^[[:space:]]*$' OR country_group ~ '^[[:space:]]*$'
       OR acquisition_channel ~ '^[[:space:]]*$' OR primary_device_type ~ '^[[:space:]]*$'
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-02', 'dim_content', COUNT(*)
    FROM dim_content
    WHERE content_id ~ '^[[:space:]]*$' OR artist_id ~ '^[[:space:]]*$'
       OR content_type ~ '^[[:space:]]*$' OR title ~ '^[[:space:]]*$'
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-02', 'dim_product', COUNT(*)
    FROM dim_product
    WHERE product_id ~ '^[[:space:]]*$' OR artist_id ~ '^[[:space:]]*$'
       OR product_name ~ '^[[:space:]]*$' OR product_type ~ '^[[:space:]]*$'
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-02', 'dim_activity_phase', COUNT(*)
    FROM dim_activity_phase
    WHERE phase_id ~ '^[[:space:]]*$' OR artist_id ~ '^[[:space:]]*$' OR phase_type ~ '^[[:space:]]*$'
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-02', 'bridge_user_artist_follow', COUNT(*)
    FROM bridge_user_artist_follow
    WHERE follow_id ~ '^[[:space:]]*$' OR user_id ~ '^[[:space:]]*$' OR artist_id ~ '^[[:space:]]*$'
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-02', 'fact_message_subscription', COUNT(*)
    FROM fact_message_subscription
    WHERE subscription_id ~ '^[[:space:]]*$' OR user_id ~ '^[[:space:]]*$'
       OR artist_id ~ '^[[:space:]]*$' OR plan_type ~ '^[[:space:]]*$'
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-02', 'fact_artist_activity', COUNT(*)
    FROM fact_artist_activity
    WHERE activity_id ~ '^[[:space:]]*$' OR artist_id ~ '^[[:space:]]*$' OR activity_type ~ '^[[:space:]]*$'
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-02', 'fact_order', COUNT(*)
    FROM fact_order
    WHERE transaction_id ~ '^[[:space:]]*$' OR user_id ~ '^[[:space:]]*$' OR status ~ '^[[:space:]]*$'
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-02', 'fact_order_item', COUNT(*)
    FROM fact_order_item
    WHERE order_item_id ~ '^[[:space:]]*$' OR transaction_id ~ '^[[:space:]]*$' OR product_id ~ '^[[:space:]]*$'
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-02', 'fact_user_event', COUNT(*)
    FROM fact_user_event
    WHERE event_id ~ '^[[:space:]]*$' OR event_name ~ '^[[:space:]]*$'
       OR user_id ~ '^[[:space:]]*$' OR device_type ~ '^[[:space:]]*$'
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-03', 'bridge_user_artist_follow.user_id -> dim_user', COUNT(*)
    FROM bridge_user_artist_follow b
    WHERE NOT EXISTS (SELECT 1 FROM dim_user u WHERE u.user_id = b.user_id)
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-03', 'fact_message_subscription.user_id -> dim_user', COUNT(*)
    FROM fact_message_subscription s
    WHERE NOT EXISTS (SELECT 1 FROM dim_user u WHERE u.user_id = s.user_id)
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-03', 'fact_order.user_id -> dim_user', COUNT(*)
    FROM fact_order o
    WHERE NOT EXISTS (SELECT 1 FROM dim_user u WHERE u.user_id = o.user_id)
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-03', 'fact_user_event.user_id -> dim_user', COUNT(*)
    FROM fact_user_event e
    WHERE NOT EXISTS (SELECT 1 FROM dim_user u WHERE u.user_id = e.user_id)
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-03', 'dim_content.artist_id -> dim_artist', COUNT(*)
    FROM dim_content c
    WHERE NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = c.artist_id)
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-03', 'dim_product.artist_id -> dim_artist', COUNT(*)
    FROM dim_product p
    WHERE NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = p.artist_id)
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-03', 'dim_activity_phase.artist_id -> dim_artist', COUNT(*)
    FROM dim_activity_phase ph
    WHERE NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = ph.artist_id)
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-03', 'bridge_user_artist_follow.artist_id -> dim_artist', COUNT(*)
    FROM bridge_user_artist_follow b
    WHERE NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = b.artist_id)
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-03', 'fact_message_subscription.artist_id -> dim_artist', COUNT(*)
    FROM fact_message_subscription s
    WHERE NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = s.artist_id)
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-03', 'fact_artist_activity.artist_id -> dim_artist', COUNT(*)
    FROM fact_artist_activity fa
    WHERE NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = fa.artist_id)
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-03', 'fact_user_event.artist_id -> dim_artist', COUNT(*)
    FROM fact_user_event e
    WHERE e.artist_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = e.artist_id)
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-03', 'fact_artist_activity.content_id -> dim_content', COUNT(*)
    FROM fact_artist_activity fa
    WHERE fa.content_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM dim_content c WHERE c.content_id = fa.content_id)
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-03', 'fact_user_event.content_id -> dim_content', COUNT(*)
    FROM fact_user_event e
    WHERE e.content_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM dim_content c WHERE c.content_id = e.content_id)
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-03', 'fact_order_item.product_id -> dim_product', COUNT(*)
    FROM fact_order_item oi
    WHERE NOT EXISTS (SELECT 1 FROM dim_product p WHERE p.product_id = oi.product_id)
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-03', 'fact_user_event.product_id -> dim_product', COUNT(*)
    FROM fact_user_event e
    WHERE e.product_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM dim_product p WHERE p.product_id = e.product_id)
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-03', 'fact_user_event.activity_id -> fact_artist_activity', COUNT(*)
    FROM fact_user_event e
    WHERE e.activity_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM fact_artist_activity fa WHERE fa.activity_id = e.activity_id)
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-03', 'fact_order_item.transaction_id -> fact_order', COUNT(*)
    FROM fact_order_item oi
    WHERE NOT EXISTS (SELECT 1 FROM fact_order o WHERE o.transaction_id = oi.transaction_id)
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'DQ-03', 'fact_user_event.transaction_id -> fact_order', COUNT(*)
    FROM fact_user_event e
    WHERE e.transaction_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM fact_order o WHERE o.transaction_id = e.transaction_id)
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'ET-DQ-01', 'fact_user_event.event_id', COUNT(*)
    FROM (SELECT event_id FROM fact_user_event GROUP BY event_id HAVING COUNT(*) > 1) d
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'ET-DQ-02', 'fact_artist_activity.activity_id', COUNT(*)
    FROM (SELECT activity_id FROM fact_artist_activity GROUP BY activity_id HAVING COUNT(*) > 1) d
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'ET-DQ-03', 'fact_user_event.event_name', COUNT(*)
    FROM fact_user_event
    WHERE event_name NOT IN (
        'sign_up', 'session_start', 'artist_view', 'artist_follow', 'artist_unfollow',
        'message_subscription_start', 'message_subscription_cancel', 'artist_post_view',
        'message_open', 'live_view_start', 'content_view', 'content_like', 'comment_create',
        'view_item', 'add_to_cart', 'begin_checkout', 'purchase', 'refund'
    )
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'ET-DQ-04', 'fact_artist_activity.activity_type', COUNT(*)
    FROM fact_artist_activity
    WHERE activity_type NOT IN ('post', 'message', 'live')
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'ET-DQ-05', 'fact_user_event.user_id IS NULL', COUNT(*)
    FROM fact_user_event
    WHERE user_id IS NULL
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'ET-DQ-06', 'fact_user_event.user_id -> dim_user', COUNT(*)
    FROM fact_user_event e
    WHERE NOT EXISTS (SELECT 1 FROM dim_user u WHERE u.user_id = e.user_id)
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'ET-DQ-06', 'fact_user_event.artist_id -> dim_artist', COUNT(*)
    FROM fact_user_event e
    WHERE e.artist_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM dim_artist a WHERE a.artist_id = e.artist_id)
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'ET-DQ-06', 'fact_user_event.content_id -> dim_content', COUNT(*)
    FROM fact_user_event e
    WHERE e.content_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM dim_content c WHERE c.content_id = e.content_id)
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'ET-DQ-06', 'fact_user_event.activity_id -> fact_artist_activity', COUNT(*)
    FROM fact_user_event e
    WHERE e.activity_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM fact_artist_activity fa WHERE fa.activity_id = e.activity_id)
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'ET-DQ-06', 'fact_user_event.product_id -> dim_product', COUNT(*)
    FROM fact_user_event e
    WHERE e.product_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM dim_product p WHERE p.product_id = e.product_id)
    UNION ALL
    SELECT 1, '001_keys_and_referential_integrity.sql', 'ET-DQ-06', 'fact_user_event.transaction_id -> fact_order', COUNT(*)
    FROM fact_user_event e
    WHERE e.transaction_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM fact_order o WHERE o.transaction_id = e.transaction_id)

    UNION ALL

    -- ======== group 2: 002_temporal_order.sql (15개 항목) ========
    SELECT 2, '002_temporal_order.sql', 'DQ-04', 'fact_user_event.event_timestamp_utc < dim_user.signup_timestamp_utc', COUNT(*)
    FROM fact_user_event e
    JOIN dim_user u ON u.user_id = e.user_id
    WHERE e.event_timestamp_utc < u.signup_timestamp_utc
    UNION ALL
    SELECT 2, '002_temporal_order.sql', 'DQ-05', 'message_open (활성 구독 없음)', COUNT(*)
    FROM fact_user_event e
    WHERE e.event_name = 'message_open'
      AND NOT EXISTS (
          SELECT 1 FROM fact_message_subscription s
          WHERE s.user_id = e.user_id AND s.artist_id = e.artist_id
            AND s.started_at_utc <= e.event_timestamp_utc
            AND (s.ended_at_utc IS NULL OR e.event_timestamp_utc < s.ended_at_utc)
      )
    UNION ALL
    SELECT 2, '002_temporal_order.sql', 'DQ-06', 'view_item/add_to_cart (product_id 직접)', COUNT(*)
    FROM fact_user_event e
    JOIN dim_product p ON p.product_id = e.product_id
    WHERE e.event_name IN ('view_item', 'add_to_cart')
      AND e.event_timestamp_utc < p.release_timestamp_utc
    UNION ALL
    SELECT 2, '002_temporal_order.sql', 'DQ-06', 'begin_checkout/purchase (fact_order_item 경유)', COUNT(*)
    FROM (
        SELECT DISTINCT e.event_id
        FROM fact_user_event e
        JOIN fact_order_item oi ON oi.transaction_id = e.transaction_id
        JOIN dim_product p ON p.product_id = oi.product_id
        WHERE e.event_name IN ('begin_checkout', 'purchase')
          AND e.event_timestamp_utc < p.release_timestamp_utc
    ) t
    UNION ALL
    SELECT 2, '002_temporal_order.sql', 'ET-DQ-07', '(DQ-04와 동일) fact_user_event.event_timestamp_utc < dim_user.signup_timestamp_utc', COUNT(*)
    FROM fact_user_event e
    JOIN dim_user u ON u.user_id = e.user_id
    WHERE e.event_timestamp_utc < u.signup_timestamp_utc
    UNION ALL
    SELECT 2, '002_temporal_order.sql', 'ET-DQ-09', 'fact_user_event(event_name=purchase).transaction_id 중복', COUNT(*)
    FROM (
        SELECT transaction_id FROM fact_user_event
        WHERE event_name = 'purchase'
        GROUP BY transaction_id HAVING COUNT(*) > 1
    ) d
    UNION ALL
    SELECT 2, '002_temporal_order.sql', 'ET-DQ-11', '(DQ-06과 동일) view_item/add_to_cart (product_id 직접)', COUNT(*)
    FROM fact_user_event e
    JOIN dim_product p ON p.product_id = e.product_id
    WHERE e.event_name IN ('view_item', 'add_to_cart')
      AND e.event_timestamp_utc < p.release_timestamp_utc
    UNION ALL
    SELECT 2, '002_temporal_order.sql', 'ET-DQ-11', '(DQ-06과 동일) begin_checkout/purchase (fact_order_item 경유)', COUNT(*)
    FROM (
        SELECT DISTINCT e.event_id
        FROM fact_user_event e
        JOIN fact_order_item oi ON oi.transaction_id = e.transaction_id
        JOIN dim_product p ON p.product_id = oi.product_id
        WHERE e.event_name IN ('begin_checkout', 'purchase')
          AND e.event_timestamp_utc < p.release_timestamp_utc
    ) t
    UNION ALL
    SELECT 2, '002_temporal_order.sql', 'ET-DQ-14', 'fact_user_event', COUNT(*)
    FROM fact_user_event
    WHERE event_timestamp_utc < '2025-12-31T15:00:00Z'::timestamptz
       OR event_timestamp_utc > '2026-03-31T14:59:59Z'::timestamptz
    UNION ALL
    SELECT 2, '002_temporal_order.sql', 'ET-DQ-14', 'fact_artist_activity', COUNT(*)
    FROM fact_artist_activity
    WHERE activity_timestamp_utc < '2025-12-31T15:00:00Z'::timestamptz
       OR activity_timestamp_utc > '2026-03-31T14:59:59Z'::timestamptz
    UNION ALL
    SELECT 2, '002_temporal_order.sql', 'ET-DQ-16', 'session_start.parameters.session_number 순차성', COUNT(*)
    FROM (
        SELECT
            (parameters ->> 'session_number')::int AS session_number,
            ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY event_timestamp_utc) AS expected_number
        FROM fact_user_event
        WHERE event_name = 'session_start'
    ) s
    WHERE s.session_number <> s.expected_number
    UNION ALL
    SELECT 2, '002_temporal_order.sql', 'ET-DQ-17', 'sign_up 팬당 2건 이상', COUNT(*)
    FROM (
        SELECT user_id FROM fact_user_event
        WHERE event_name = 'sign_up'
        GROUP BY user_id HAVING COUNT(*) > 1
    ) d
    UNION ALL
    SELECT 2, '002_temporal_order.sql', 'ET-DQ-18', 'artist_unfollow (활성 팔로우 없음)', COUNT(*)
    FROM fact_user_event e
    WHERE e.event_name = 'artist_unfollow'
      AND NOT EXISTS (
          SELECT 1 FROM bridge_user_artist_follow b
          WHERE b.user_id = e.user_id AND b.artist_id = e.artist_id
            AND b.followed_at_utc <= e.event_timestamp_utc
            AND (b.unfollowed_at_utc IS NULL OR b.unfollowed_at_utc >= e.event_timestamp_utc)
      )
    UNION ALL
    SELECT 2, '002_temporal_order.sql', 'ET-DQ-19', 'bridge_user_artist_follow (활성 팔로우 중복)', COUNT(*)
    FROM (
        SELECT user_id, artist_id FROM bridge_user_artist_follow
        WHERE unfollowed_at_utc IS NULL
        GROUP BY user_id, artist_id HAVING COUNT(*) > 1
    ) d
    UNION ALL
    SELECT 2, '002_temporal_order.sql', 'ET-DQ-21', 'message_subscription_cancel (활성 구독 없음)', COUNT(*)
    FROM fact_user_event e
    WHERE e.event_name = 'message_subscription_cancel'
      AND NOT EXISTS (
          SELECT 1 FROM fact_message_subscription s
          WHERE s.user_id = e.user_id AND s.artist_id = e.artist_id
            AND s.started_at_utc <= e.event_timestamp_utc
            AND (s.ended_at_utc IS NULL OR s.ended_at_utc >= e.event_timestamp_utc)
      )

    UNION ALL

    -- ======== group 3: 003_allowed_values.sql (6개 항목) ========
    SELECT 3, '003_allowed_values.sql', 'ET-DQ-03', 'fact_user_event.event_name', COUNT(*)
    FROM fact_user_event
    WHERE event_name NOT IN (
        'sign_up', 'session_start', 'artist_view', 'artist_follow', 'artist_unfollow',
        'message_subscription_start', 'message_subscription_cancel', 'artist_post_view',
        'message_open', 'live_view_start', 'content_view', 'content_like', 'comment_create',
        'view_item', 'add_to_cart', 'begin_checkout', 'purchase', 'refund'
    )
    UNION ALL
    SELECT 3, '003_allowed_values.sql', 'ET-DQ-04', 'fact_artist_activity.activity_type', COUNT(*)
    FROM fact_artist_activity
    WHERE activity_type NOT IN ('post', 'message', 'live')
    UNION ALL
    SELECT 3, '003_allowed_values.sql', 'ET-DQ-15', 'dim_content.content_type', COUNT(*)
    FROM dim_content
    WHERE content_type NOT IN ('notice', 'photo', 'video', 'music_video', 'live_replay')
    UNION ALL
    SELECT 3, '003_allowed_values.sql', 'ET-DQ-20', 'fact_user_event(cancel).parameters.cancel_reason_category', COUNT(*)
    FROM fact_user_event
    WHERE event_name = 'message_subscription_cancel'
      AND (parameters ->> 'cancel_reason_category') NOT IN ('user_cancel', 'expired_no_renewal')
    UNION ALL
    SELECT 3, '003_allowed_values.sql', '추가검사 A', 'dim_product.product_type', COUNT(*)
    FROM dim_product
    WHERE product_type NOT IN ('album', 'lightstick', 'apparel', 'collab')
    UNION ALL
    SELECT 3, '003_allowed_values.sql', '추가검사 B', 'fact_order.status', COUNT(*)
    FROM fact_order
    WHERE status NOT IN ('pending', 'completed', 'refunded', 'partially_refunded')

    UNION ALL

    -- ======== group 4: 004_commerce_integrity.sql (10개 항목, ET-DQ-28 참고용 집계는 제외) ========
    SELECT 4, '004_commerce_integrity.sql', 'DQ-07', 'fact_order (성공 상태) transaction_id 중복', COUNT(*)
    FROM (
        SELECT transaction_id FROM fact_order
        WHERE status IN ('completed', 'refunded', 'partially_refunded')
        GROUP BY transaction_id HAVING COUNT(*) > 1
    ) d
    UNION ALL
    SELECT 4, '004_commerce_integrity.sql', 'DQ-08', 'fact_order.order_amount vs fact_order_item 합계', COUNT(*)
    FROM fact_order o
    LEFT JOIN (
        SELECT transaction_id, SUM(unit_price * quantity - discount_amount) AS item_total
        FROM fact_order_item GROUP BY transaction_id
    ) i ON i.transaction_id = o.transaction_id
    WHERE o.order_amount <> COALESCE(i.item_total, 0)
    UNION ALL
    SELECT 4, '004_commerce_integrity.sql', 'DQ-09', 'dim_product.price', COUNT(*)
    FROM dim_product WHERE price < 0
    UNION ALL
    SELECT 4, '004_commerce_integrity.sql', 'DQ-09', 'fact_order_item.unit_price/quantity/discount_amount', COUNT(*)
    FROM fact_order_item
    WHERE unit_price < 0 OR quantity < 0 OR discount_amount < 0
    UNION ALL
    SELECT 4, '004_commerce_integrity.sql', 'DQ-09', 'fact_user_event(live_view_start).parameters.watch_seconds', COUNT(*)
    FROM fact_user_event
    WHERE event_name = 'live_view_start'
      AND (parameters ->> 'watch_seconds')::numeric < 0
    UNION ALL
    SELECT 4, '004_commerce_integrity.sql', 'DQ-09', 'fact_user_event(5종 이벤트).parameters.value', COUNT(*)
    FROM fact_user_event
    WHERE event_name IN ('view_item', 'add_to_cart', 'begin_checkout', 'purchase', 'refund')
      AND (parameters ->> 'value')::numeric < 0
    UNION ALL
    SELECT 4, '004_commerce_integrity.sql', 'ET-DQ-25', 'fact_user_event(purchase).parameters.value vs fact_order_item 합계', COUNT(*)
    FROM fact_user_event e
    LEFT JOIN (
        SELECT transaction_id, SUM(unit_price * quantity - discount_amount) AS item_total
        FROM fact_order_item GROUP BY transaction_id
    ) i ON i.transaction_id = e.transaction_id
    WHERE e.event_name = 'purchase'
      AND (e.parameters ->> 'value')::numeric <> COALESCE(i.item_total, 0)
    UNION ALL
    SELECT 4, '004_commerce_integrity.sql', 'ET-DQ-26', 'fact_user_event(refund).parameters.value > fact_order.order_amount', COUNT(*)
    FROM fact_user_event e
    JOIN fact_order o ON o.transaction_id = e.transaction_id
    WHERE e.event_name = 'refund'
      AND (e.parameters ->> 'value')::numeric > o.order_amount
    UNION ALL
    SELECT 4, '004_commerce_integrity.sql', 'ET-DQ-27', 'fact_order(status=completed) without purchase event', COUNT(*)
    FROM fact_order o
    WHERE o.status = 'completed'
      AND NOT EXISTS (
          SELECT 1 FROM fact_user_event e
          WHERE e.event_name = 'purchase' AND e.transaction_id = o.transaction_id
      )
    UNION ALL
    SELECT 4, '004_commerce_integrity.sql', '추가검사 C', 'fact_order.refund_amount > order_amount', COUNT(*)
    FROM fact_order
    WHERE refund_amount > order_amount

    UNION ALL

    -- ======== group 5: 005_timezone_consistency.sql (5개 항목) ========
    SELECT 5, '005_timezone_consistency.sql', 'DQ-10/ET-DQ-13', 'dim_user.signup_timestamp_utc vs signup_date_kst', COUNT(*)
    FROM dim_user
    WHERE (signup_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date <> signup_date_kst
    UNION ALL
    SELECT 5, '005_timezone_consistency.sql', 'DQ-10/ET-DQ-13', 'dim_content.published_timestamp_utc vs published_date_kst', COUNT(*)
    FROM dim_content
    WHERE (published_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date <> published_date_kst
    UNION ALL
    SELECT 5, '005_timezone_consistency.sql', 'DQ-10/ET-DQ-13', 'dim_product.release_timestamp_utc vs release_date_kst', COUNT(*)
    FROM dim_product
    WHERE (release_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date <> release_date_kst
    UNION ALL
    SELECT 5, '005_timezone_consistency.sql', 'DQ-10/ET-DQ-13', 'fact_artist_activity.activity_timestamp_utc vs activity_date_kst', COUNT(*)
    FROM fact_artist_activity
    WHERE (activity_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date <> activity_date_kst
    UNION ALL
    SELECT 5, '005_timezone_consistency.sql', 'DQ-10/ET-DQ-13', 'fact_user_event.event_timestamp_utc vs event_date_kst', COUNT(*)
    FROM fact_user_event
    WHERE (event_timestamp_utc AT TIME ZONE 'Asia/Seoul')::date <> event_date_kst

) all_groups
ORDER BY group_no, rule_id, target;


-- ============================================================
-- 2) [참고용, 위반 아님] ET-DQ-28: 분석 기간 종료 시점에 pending 상태로 남은 주문 수
-- 위 통합 표(87개 항목)에는 포함하지 않는다 — pending은 오류가 아니라 정상적인 열린 퍼널 결과다.
-- ============================================================
SELECT COUNT(*) AS pending_order_count_reference_only
FROM fact_order
WHERE status = 'pending';


-- ============================================================
-- 3) 001~005 파일 전체를 순서대로 실행 (각 파일 자체의 요약·개별·상세조회용 쿼리까지 재실행)
--    감사 추적(NFR-10) 및 개별 규칙 재확인용으로 남겨둔다.
-- ============================================================
\i sql/quality_checks/001_keys_and_referential_integrity.sql
\i sql/quality_checks/002_temporal_order.sql
\i sql/quality_checks/003_allowed_values.sql
\i sql/quality_checks/004_commerce_integrity.sql
\i sql/quality_checks/005_timezone_consistency.sql
