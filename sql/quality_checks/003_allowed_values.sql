-- ============================================================
-- FANLOG 데이터 품질검사 3/5: 허용값·카테고리
-- 기준 문서: docs/event_tracking_plan.md 9절(ET-DQ-03, 04, 15, 20)
-- 대상 규칙: ET-DQ-03, ET-DQ-04, ET-DQ-15, ET-DQ-20 + 추가검사 A, B(문서 규칙 ID는 없으나
--            같은 성격의 CHECK 제약 재확인 검사라 이 파일에 함께 포함)
--
-- 참고: 여기서 다루는 값들은 전부 sql/ddl/*.sql의 CHECK 제약이 이미 DB 차원에서 막고 있다.
--       즉 이 파일의 쿼리는 전부 0건이 나올 가능성이 높다. 그럼에도 별도 SQL로 만들어두는 이유는
--       (1) CHECK 제약이 실수로 빠지거나 우회된 적재가 없었는지 문서화된 형태로 재확인하고,
--       (2) PRD 16.1절 NFR-10(감사 가능성)에 맞춰 "허용값이 무엇이고 어떻게 검증했는지"를
--       코드로 남겨두기 위함이다.
-- 나머지 규칙(DQ-07~10, ET-DQ-08,10,12,13,22~28)은 다음 그룹(4/5 이후)에서 다룬다.
--
-- 모든 위반 건수 쿼리는 0이어야 정상이다.
-- 위반이 있을 경우 참고할 "위반 상세 조회용" 쿼리를 각 규칙 바로 아래 주석으로 남겨뒀다(필요할 때만 주석 해제).
--
-- 실행 방법: psql -f sql/quality_checks/003_allowed_values.sql
-- (또는 psql 세션 안에서 \i sql/quality_checks/003_allowed_values.sql)
-- ============================================================


-- ============================================================
-- [요약 쿼리] 아래 6개 규칙의 위반 건수를 한 번에 표로 출력한다.
-- 이 문서 하단의 개별 쿼리들과 로직은 동일하되, rule_id/target/violation_count 형태로 합쳐서 보여준다.
-- ============================================================
SELECT rule_id, target, violation_count
FROM (
    -- ---------- ET-DQ-03: 허용 목록(18개) 밖 event_name ----------
    -- 001번 파일(sql/quality_checks/001_keys_and_referential_integrity.sql)의 ET-DQ-03과 중복되지만,
    -- 허용값 검사만 모아둔 이 파일에서도 독립적으로 재검증한다.
    SELECT 'ET-DQ-03' AS rule_id, 'fact_user_event.event_name' AS target, COUNT(*) AS violation_count
    FROM fact_user_event
    WHERE event_name NOT IN (
        'sign_up', 'session_start', 'artist_view', 'artist_follow', 'artist_unfollow',
        'message_subscription_start', 'message_subscription_cancel', 'artist_post_view',
        'message_open', 'live_view_start', 'content_view', 'content_like', 'comment_create',
        'view_item', 'add_to_cart', 'begin_checkout', 'purchase', 'refund'
    )

    UNION ALL

    -- ---------- ET-DQ-04: 허용 목록(post, message, live) 밖 activity_type ----------
    SELECT 'ET-DQ-04', 'fact_artist_activity.activity_type', COUNT(*)
    FROM fact_artist_activity
    WHERE activity_type NOT IN ('post', 'message', 'live')

    UNION ALL

    -- ---------- ET-DQ-15: 허용 목록(notice, photo, video, music_video, live_replay) 밖 content_type ----------
    SELECT 'ET-DQ-15', 'dim_content.content_type', COUNT(*)
    FROM dim_content
    WHERE content_type NOT IN ('notice', 'photo', 'video', 'music_video', 'live_replay')

    UNION ALL

    -- ---------- ET-DQ-20: 허용 목록(user_cancel, expired_no_renewal) 밖 cancel_reason_category ----------
    SELECT 'ET-DQ-20', 'fact_user_event(event_name=message_subscription_cancel).parameters.cancel_reason_category', COUNT(*)
    FROM fact_user_event
    WHERE event_name = 'message_subscription_cancel'
      AND (parameters ->> 'cancel_reason_category') NOT IN ('user_cancel', 'expired_no_renewal')

    UNION ALL

    -- ---------- 추가검사 A: 허용 목록(album, lightstick, apparel, collab) 밖 product_type ----------
    SELECT '추가검사 A', 'dim_product.product_type', COUNT(*)
    FROM dim_product
    WHERE product_type NOT IN ('album', 'lightstick', 'apparel', 'collab')

    UNION ALL

    -- ---------- 추가검사 B: 허용 목록(pending, completed, refunded, partially_refunded) 밖 status ----------
    SELECT '추가검사 B', 'fact_order.status', COUNT(*)
    FROM fact_order
    WHERE status NOT IN ('pending', 'completed', 'refunded', 'partially_refunded')
) summary
ORDER BY rule_id, target;


-- ============================================================
-- 이하 개별 쿼리 (규칙별로 다시 실행하고 싶을 때 이 아래부터 필요한 부분만 발췌해서 쓴다)
-- ============================================================


-- ============================================================
-- ET-DQ-03: 허용 목록(18개)에 없는 fact_user_event.event_name
-- 정의: docs/event_tracking_plan.md 9절
-- 참고: sql/quality_checks/001_keys_and_referential_integrity.sql에 동일한 쿼리가 이미 있다.
--       허용값 검사만 모아두는 이 파일에서도 독립적으로 재검증하기 위해 그대로 포함한다.
--       sql/ddl/003_facts.sql의 CHECK 제약이 이미 이 18개 값으로 제한하고 있다.
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
-- ============================================================
SELECT COUNT(*) AS invalid_activity_type_count
FROM fact_artist_activity
WHERE activity_type NOT IN ('post', 'message', 'live');

-- 위반 상세 조회용
-- SELECT activity_id, activity_type
-- FROM fact_artist_activity
-- WHERE activity_type NOT IN ('post', 'message', 'live');


-- ============================================================
-- ET-DQ-15: 허용 목록에 없는 dim_content.content_type
-- 정의: docs/event_tracking_plan.md 9절, docs/PRD.md 6.1.1절(5개 유형 확정)
-- 참고: sql/ddl/001_dimensions.sql의 CHECK 제약이 이미 5개 값으로 제한하고 있다.
-- ============================================================
SELECT COUNT(*) AS invalid_content_type_count
FROM dim_content
WHERE content_type NOT IN ('notice', 'photo', 'video', 'music_video', 'live_replay');

-- 위반 상세 조회용
-- SELECT content_id, content_type
-- FROM dim_content
-- WHERE content_type NOT IN ('notice', 'photo', 'video', 'music_video', 'live_replay');


-- ============================================================
-- ET-DQ-20: 허용 목록에 없는 message_subscription_cancel.cancel_reason_category
-- 정의: docs/event_tracking_plan.md 11.2.1절
-- 참고: fact_message_subscription.cancel_reason_category에는 CHECK 제약이 있지만,
--       이 규칙은 fact_user_event.parameters(JSONB)에 실제로 기록된 값을 대상으로 한다
--       (JSONB는 CHECK 제약으로 값 형식을 강제할 수 없으므로, 여기서는 DB 제약이 아니라
--       이 쿼리 자체가 유일한 방어선이다).
-- ============================================================
SELECT COUNT(*) AS invalid_cancel_reason_count
FROM fact_user_event
WHERE event_name = 'message_subscription_cancel'
  AND (parameters ->> 'cancel_reason_category') NOT IN ('user_cancel', 'expired_no_renewal');

-- 위반 상세 조회용
-- SELECT event_id, user_id, artist_id, parameters ->> 'cancel_reason_category' AS cancel_reason_category
-- FROM fact_user_event
-- WHERE event_name = 'message_subscription_cancel'
--   AND (parameters ->> 'cancel_reason_category') NOT IN ('user_cancel', 'expired_no_renewal');


-- ============================================================
-- 추가검사 A: 허용 목록에 없는 dim_product.product_type
-- 정의: 문서에 별도 규칙 ID는 없으나(ET-DQ 목록 밖), 같은 성격의 CHECK 제약 재확인 검사
-- 참고: sql/ddl/001_dimensions.sql의 CHECK 제약이 이미 4개 값으로 제한하고 있다.
-- ============================================================
SELECT COUNT(*) AS invalid_product_type_count
FROM dim_product
WHERE product_type NOT IN ('album', 'lightstick', 'apparel', 'collab');

-- 위반 상세 조회용
-- SELECT product_id, product_type
-- FROM dim_product
-- WHERE product_type NOT IN ('album', 'lightstick', 'apparel', 'collab');


-- ============================================================
-- 추가검사 B: 허용 목록에 없는 fact_order.status
-- 정의: 문서에 별도 규칙 ID는 없으나(ET-DQ 목록 밖), 같은 성격의 CHECK 제약 재확인 검사
-- 참고: sql/ddl/003_facts.sql의 CHECK 제약이 이미 4개 값으로 제한하고 있다.
-- ============================================================
SELECT COUNT(*) AS invalid_order_status_count
FROM fact_order
WHERE status NOT IN ('pending', 'completed', 'refunded', 'partially_refunded');

-- 위반 상세 조회용
-- SELECT transaction_id, status
-- FROM fact_order
-- WHERE status NOT IN ('pending', 'completed', 'refunded', 'partially_refunded');
