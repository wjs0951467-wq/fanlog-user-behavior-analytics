-- ============================================================
-- FANLOG 데이터 품질검사 4/5: 구매·환불 금액 정합성
-- 기준 문서: docs/PRD.md 10.4절·15.1절(DQ-07~09), docs/event_tracking_plan.md 9.3절(ET-DQ-25~28)
-- 대상 규칙: DQ-07, DQ-08, DQ-09, ET-DQ-25, ET-DQ-26, ET-DQ-27, ET-DQ-28 + 추가검사 C(refund_amount)
-- ET-DQ-28은 위반 검사가 아니라 참고용 집계 쿼리이므로 요약 쿼리에는 포함하지 않고 별도 섹션으로 둔다.
-- 나머지 규칙(DQ-10, ET-DQ-08,10,12,13,22~24)은 다음 그룹(5/5)에서 다룬다.
--
-- 모든 위반 건수 쿼리는 0이어야 정상이다(ET-DQ-28 제외).
-- 위반이 있을 경우 참고할 "위반 상세 조회용" 쿼리를 각 규칙 바로 아래 주석으로 남겨뒀다(필요할 때만 주석 해제).
--
-- 실행 방법: psql -f sql/quality_checks/004_commerce_integrity.sql
-- (또는 psql 세션 안에서 \i sql/quality_checks/004_commerce_integrity.sql)
-- ============================================================


-- ============================================================
-- [요약 쿼리] 아래 7개 규칙 항목(ET-DQ-28 제외)의 위반 건수를 한 번에 표로 출력한다.
-- 이 문서 하단의 개별 쿼리들과 로직은 동일하되, rule_id/target/violation_count 형태로 합쳐서 보여준다.
-- ============================================================
SELECT rule_id, target, violation_count
FROM (
    -- ---------- DQ-07: 중복 purchase.transaction_id (fact_order 기준) ----------
    SELECT 'DQ-07' AS rule_id, 'fact_order (성공 상태) transaction_id 중복' AS target, COUNT(*) AS violation_count
    FROM (
        SELECT transaction_id
        FROM fact_order
        WHERE status IN ('completed', 'refunded', 'partially_refunded')
        GROUP BY transaction_id
        HAVING COUNT(*) > 1
    ) d

    UNION ALL

    -- ---------- DQ-08: 주문과 주문 상품 합계 불일치 ----------
    SELECT 'DQ-08', 'fact_order.order_amount vs fact_order_item 합계', COUNT(*)
    FROM fact_order o
    LEFT JOIN (
        SELECT transaction_id, SUM(unit_price * quantity - discount_amount) AS item_total
        FROM fact_order_item
        GROUP BY transaction_id
    ) i ON i.transaction_id = o.transaction_id
    WHERE o.order_amount <> COALESCE(i.item_total, 0)

    UNION ALL

    -- ---------- DQ-09: 음수 가격·수량·시청시간 ----------
    SELECT 'DQ-09', 'dim_product.price', COUNT(*)
    FROM dim_product
    WHERE price < 0
    UNION ALL
    SELECT 'DQ-09', 'fact_order_item.unit_price/quantity/discount_amount', COUNT(*)
    FROM fact_order_item
    WHERE unit_price < 0 OR quantity < 0 OR discount_amount < 0
    UNION ALL
    SELECT 'DQ-09', 'fact_user_event(live_view_start).parameters.watch_seconds', COUNT(*)
    FROM fact_user_event
    WHERE event_name = 'live_view_start'
      AND (parameters ->> 'watch_seconds')::numeric < 0
    UNION ALL
    SELECT 'DQ-09', 'fact_user_event(view_item/add_to_cart/begin_checkout/purchase/refund).parameters.value', COUNT(*)
    FROM fact_user_event
    WHERE event_name IN ('view_item', 'add_to_cart', 'begin_checkout', 'purchase', 'refund')
      AND (parameters ->> 'value')::numeric < 0

    UNION ALL

    -- ---------- ET-DQ-25: purchase.parameters.value가 fact_order_item 금액 합계와 불일치 ----------
    -- DQ-08과 대상은 유사하지만, DQ-08은 fact_order.order_amount 기준이고
    -- 이 규칙은 fact_user_event의 purchase 이벤트 parameters.value 기준으로 event 레벨에서 재검증한다.
    SELECT 'ET-DQ-25', 'fact_user_event(purchase).parameters.value vs fact_order_item 합계', COUNT(*)
    FROM fact_user_event e
    LEFT JOIN (
        SELECT transaction_id, SUM(unit_price * quantity - discount_amount) AS item_total
        FROM fact_order_item
        GROUP BY transaction_id
    ) i ON i.transaction_id = e.transaction_id
    WHERE e.event_name = 'purchase'
      AND (e.parameters ->> 'value')::numeric <> COALESCE(i.item_total, 0)

    UNION ALL

    -- ---------- ET-DQ-26: refund.parameters.value가 원 주문 금액을 초과 ----------
    SELECT 'ET-DQ-26', 'fact_user_event(refund).parameters.value > fact_order.order_amount', COUNT(*)
    FROM fact_user_event e
    JOIN fact_order o ON o.transaction_id = e.transaction_id
    WHERE e.event_name = 'refund'
      AND (e.parameters ->> 'value')::numeric > o.order_amount

    UNION ALL

    -- ---------- ET-DQ-27: status='completed'인데 대응 purchase 이벤트가 없음 ----------
    SELECT 'ET-DQ-27', 'fact_order(status=completed) without purchase event', COUNT(*)
    FROM fact_order o
    WHERE o.status = 'completed'
      AND NOT EXISTS (
          SELECT 1 FROM fact_user_event e
          WHERE e.event_name = 'purchase' AND e.transaction_id = o.transaction_id
      )

    UNION ALL

    -- ---------- 추가검사 C: refund_amount가 order_amount를 초과 ----------
    SELECT '추가검사 C', 'fact_order.refund_amount > order_amount', COUNT(*)
    FROM fact_order
    WHERE refund_amount > order_amount
) summary
ORDER BY rule_id, target;


-- ============================================================
-- [참고용 집계] ET-DQ-28: 분석 기간 종료 시점에 pending 상태로 남은 주문 수
-- 이것은 위반이 아니다 — PRD 8.3/decisions_log.md 5.13절의 "열린 퍼널" 원칙에 따라
-- cart_to_checkout_rate·checkout_to_purchase_rate를 통과하지 못한 주문이 'pending'으로
-- 남는 것은 정상적인 현상이다. 0건이 아니어도 문제 없다.
-- ============================================================
SELECT COUNT(*) AS pending_order_count_reference_only
FROM fact_order
WHERE status = 'pending';


-- ============================================================
-- 이하 개별 쿼리 (규칙별로 다시 실행하고 싶을 때 이 아래부터 필요한 부분만 발췌해서 쓴다)
-- ============================================================


-- ============================================================
-- DQ-07: 중복 purchase.transaction_id (fact_order 기준)
-- 정의: docs/PRD.md 10.4절·15.1절
-- 참고: transaction_id는 fact_order의 PK라 DB가 이미 전체 중복을 막고 있다(DQ-01에서도 확인).
--       이 쿼리는 "성공 상태(완료·환불·부분환불)인 주문"이라는 비즈니스 조건으로 좁혀서
--       독립적으로 재검증하는 용도다.
-- ============================================================
SELECT COUNT(*) AS duplicate_successful_transaction_count
FROM (
    SELECT transaction_id
    FROM fact_order
    WHERE status IN ('completed', 'refunded', 'partially_refunded')
    GROUP BY transaction_id
    HAVING COUNT(*) > 1
) d;

-- 위반 상세 조회용
-- SELECT transaction_id, COUNT(*) AS occurrence_count
-- FROM fact_order
-- WHERE status IN ('completed', 'refunded', 'partially_refunded')
-- GROUP BY transaction_id
-- HAVING COUNT(*) > 1;


-- ============================================================
-- DQ-08: 주문과 주문 상품 합계 불일치
-- 정의: docs/PRD.md 10.4절·15.1절
-- 참고: fact_order.order_amount는 해당 transaction_id의 fact_order_item에서
--       (unit_price * quantity - discount_amount)를 모두 더한 값과 같아야 한다.
--       주문 상품이 하나도 없는 경우(정상적으로는 발생하지 않아야 함)도 불일치로 잡히도록
--       LEFT JOIN + COALESCE(0)을 사용한다.
-- ============================================================
SELECT COUNT(*) AS order_amount_mismatch_count
FROM fact_order o
LEFT JOIN (
    SELECT transaction_id, SUM(unit_price * quantity - discount_amount) AS item_total
    FROM fact_order_item
    GROUP BY transaction_id
) i ON i.transaction_id = o.transaction_id
WHERE o.order_amount <> COALESCE(i.item_total, 0);

-- 위반 상세 조회용
-- SELECT o.transaction_id, o.order_amount, COALESCE(i.item_total, 0) AS item_total
-- FROM fact_order o
-- LEFT JOIN (
--     SELECT transaction_id, SUM(unit_price * quantity - discount_amount) AS item_total
--     FROM fact_order_item
--     GROUP BY transaction_id
-- ) i ON i.transaction_id = o.transaction_id
-- WHERE o.order_amount <> COALESCE(i.item_total, 0)
-- ORDER BY o.transaction_id;


-- ============================================================
-- DQ-09: 음수 가격·수량·시청시간
-- 정의: docs/PRD.md 10.4절·15.1절
-- 참고: 숫자형 컬럼(price/unit_price/quantity/discount_amount)은 NUMERIC/INT라 CHECK 제약이
--       없으면 음수도 저장 가능하다. parameters(JSONB)의 watch_seconds/value는 애초에
--       DB 제약 대상이 아니므로 이 쿼리가 유일한 방어선이다.
-- ============================================================
SELECT 'dim_product.price' AS target, COUNT(*) AS violation_count
FROM dim_product
WHERE price < 0
UNION ALL
SELECT 'fact_order_item.unit_price/quantity/discount_amount', COUNT(*)
FROM fact_order_item
WHERE unit_price < 0 OR quantity < 0 OR discount_amount < 0
UNION ALL
SELECT 'fact_user_event(live_view_start).parameters.watch_seconds', COUNT(*)
FROM fact_user_event
WHERE event_name = 'live_view_start'
  AND (parameters ->> 'watch_seconds')::numeric < 0
UNION ALL
SELECT 'fact_user_event(view_item/add_to_cart/begin_checkout/purchase/refund).parameters.value', COUNT(*)
FROM fact_user_event
WHERE event_name IN ('view_item', 'add_to_cart', 'begin_checkout', 'purchase', 'refund')
  AND (parameters ->> 'value')::numeric < 0;

-- 위반 상세 조회용
-- SELECT 'dim_product.price' AS source, product_id AS row_key, price::text AS bad_value
-- FROM dim_product WHERE price < 0
-- UNION ALL
-- SELECT 'fact_order_item', order_item_id, unit_price::text
-- FROM fact_order_item WHERE unit_price < 0
-- UNION ALL
-- SELECT 'fact_order_item', order_item_id, quantity::text
-- FROM fact_order_item WHERE quantity < 0
-- UNION ALL
-- SELECT 'fact_order_item', order_item_id, discount_amount::text
-- FROM fact_order_item WHERE discount_amount < 0
-- UNION ALL
-- SELECT 'fact_user_event.watch_seconds', event_id, parameters ->> 'watch_seconds'
-- FROM fact_user_event
-- WHERE event_name = 'live_view_start' AND (parameters ->> 'watch_seconds')::numeric < 0
-- UNION ALL
-- SELECT 'fact_user_event.value', event_id, parameters ->> 'value'
-- FROM fact_user_event
-- WHERE event_name IN ('view_item', 'add_to_cart', 'begin_checkout', 'purchase', 'refund')
--   AND (parameters ->> 'value')::numeric < 0
-- ORDER BY 1, 2;


-- ============================================================
-- ET-DQ-25: purchase.parameters.value가 fact_order_item 금액 합계와 불일치
-- 정의: docs/event_tracking_plan.md 9.3절, 11.4절
-- 참고: DQ-08과 검증 대상(주문 금액 vs 주문 상품 합계)은 유사하지만, DQ-08은
--       fact_order.order_amount 기준이고 이 규칙은 fact_user_event의 purchase 이벤트
--       parameters.value 기준으로 이벤트 레벨에서 별도로 재검증한다.
-- ============================================================
SELECT COUNT(*) AS purchase_value_mismatch_count
FROM fact_user_event e
LEFT JOIN (
    SELECT transaction_id, SUM(unit_price * quantity - discount_amount) AS item_total
    FROM fact_order_item
    GROUP BY transaction_id
) i ON i.transaction_id = e.transaction_id
WHERE e.event_name = 'purchase'
  AND (e.parameters ->> 'value')::numeric <> COALESCE(i.item_total, 0);

-- 위반 상세 조회용
-- SELECT e.event_id, e.transaction_id, (e.parameters ->> 'value')::numeric AS purchase_value, COALESCE(i.item_total, 0) AS item_total
-- FROM fact_user_event e
-- LEFT JOIN (
--     SELECT transaction_id, SUM(unit_price * quantity - discount_amount) AS item_total
--     FROM fact_order_item
--     GROUP BY transaction_id
-- ) i ON i.transaction_id = e.transaction_id
-- WHERE e.event_name = 'purchase'
--   AND (e.parameters ->> 'value')::numeric <> COALESCE(i.item_total, 0)
-- ORDER BY e.transaction_id;


-- ============================================================
-- ET-DQ-26: refund.parameters.value가 원 주문 금액(fact_order.order_amount)을 초과
-- 정의: docs/event_tracking_plan.md 9.3절, 11.4절
-- ============================================================
SELECT COUNT(*) AS refund_value_exceeds_order_count
FROM fact_user_event e
JOIN fact_order o ON o.transaction_id = e.transaction_id
WHERE e.event_name = 'refund'
  AND (e.parameters ->> 'value')::numeric > o.order_amount;

-- 위반 상세 조회용
-- SELECT e.event_id, e.transaction_id, (e.parameters ->> 'value')::numeric AS refund_value, o.order_amount
-- FROM fact_user_event e
-- JOIN fact_order o ON o.transaction_id = e.transaction_id
-- WHERE e.event_name = 'refund'
--   AND (e.parameters ->> 'value')::numeric > o.order_amount
-- ORDER BY e.transaction_id;


-- ============================================================
-- ET-DQ-27: fact_order.status가 'completed'인데 대응하는 purchase 이벤트가 없음
-- 정의: docs/event_tracking_plan.md 9.3절, 11.4절
-- ============================================================
SELECT COUNT(*) AS completed_order_without_purchase_count
FROM fact_order o
WHERE o.status = 'completed'
  AND NOT EXISTS (
      SELECT 1 FROM fact_user_event e
      WHERE e.event_name = 'purchase' AND e.transaction_id = o.transaction_id
  );

-- 위반 상세 조회용
-- SELECT o.transaction_id, o.status, o.order_amount, o.completed_at_utc
-- FROM fact_order o
-- WHERE o.status = 'completed'
--   AND NOT EXISTS (
--       SELECT 1 FROM fact_user_event e
--       WHERE e.event_name = 'purchase' AND e.transaction_id = o.transaction_id
--   )
-- ORDER BY o.transaction_id;


-- ============================================================
-- ET-DQ-28: [참고용, 위반 검사 아님] pending 상태로 남은 주문 수
-- 정의: docs/event_tracking_plan.md 9.3절
-- 참고: PRD 8.3/decisions_log.md 5.13절의 "열린 퍼널" 원칙에 따라 cart_to_checkout_rate·
--       checkout_to_purchase_rate를 통과하지 못한 주문이 분석 기간 종료 시점에 'pending'으로
--       남는 것은 정상이다. 이 쿼리 결과가 0이 아니어도 오류가 아니다.
-- ============================================================
SELECT COUNT(*) AS pending_order_count_reference_only
FROM fact_order
WHERE status = 'pending';

-- 참고용 상세 조회 (필요 시 주석 해제 — 위반이 아니라 현황 확인용)
-- SELECT transaction_id, user_id, order_amount, created_at_utc
-- FROM fact_order
-- WHERE status = 'pending'
-- ORDER BY created_at_utc;


-- ============================================================
-- 추가검사 C: fact_order.refund_amount가 order_amount를 초과
-- 정의: 문서에 별도 규칙 ID는 없으나(ET-DQ 목록 밖), 9.3절 "refund 금액은 해당 주문의
--       구매 금액을 초과할 수 없다"와 동일한 취지를 fact_order 테이블 컬럼 레벨에서 재확인한다.
-- ============================================================
SELECT COUNT(*) AS refund_amount_exceeds_order_count
FROM fact_order
WHERE refund_amount > order_amount;

-- 위반 상세 조회용
-- SELECT transaction_id, order_amount, refund_amount, status
-- FROM fact_order
-- WHERE refund_amount > order_amount
-- ORDER BY transaction_id;
