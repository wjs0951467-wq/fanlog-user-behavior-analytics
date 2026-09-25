-- ============================================================
-- FANLOG 분석 마트 4/4: mart_commerce_funnel
-- 기준 문서: docs/PRD.md 10.3절(마트 목록), 8.3절(커머스 퍼널 정의: view_item→add_to_cart→
--           begin_checkout→purchase, 동일 팬·상품, 첫 조회 후 7일 이내)
-- 한 행의 기준: 팬 1명 × 상품 1개 × 그 조합에 대한 "첫 관심(first touch)" 시점
--
-- 주의: 이 마트는 (user_id, product_id) 쌍당 "첫 관심" 시점만 추적하며
-- 재구매를 다루지 않는다. 총매출·환불 등 재무 지표의 정답 소스는
-- 항상 fact_order/fact_order_item이며, 이 마트에서 매출을 집계해서
-- 사용하지 않는다. 이 마트는 퍼널 단계별 전환율·이탈 분석 전용이다.
--
-- 설계 메모(구현 세부사항, 문서에 명시되지 않아 다음 기준으로 판단):
-- - add_to_cart_at_utc는 스펙대로 "이 (user_id, product_id)의 add_to_cart 중 가장 이른 시각"이다.
--   하지만 실제로 checkout까지 이어진 주문은 그 이후에 다시 담은 add_to_cart에서 나온 것일 수 있다
--   (예: 1차 담기는 장바구니에서 이탈, 나중에 재차 담아서 결제까지 감). 이런 경우를 위해
--   reached_checkout/checkout_at_utc/transaction_id는 "이 상품이 포함되어 있고 begin_checkout
--   시각이 add_to_cart_at_utc 이후인 주문 중 가장 이른 것"을 찾는다. 즉 add_to_cart_at_utc(최초 시도)와
--   checkout_at_utc(실제로 성사된 시도)가 서로 다른 담기 사건을 가리킬 수 있다 — 퍼널의 "시작"과
--   "실제 진행 상황"을 각각 정확히 보여주기 위한 의도적 설계다.
-- - fact_user_event에는 add_to_cart 이벤트와 그 결과 만들어질 주문(transaction_id)을 직접 잇는
--   컬럼이 없다(add_to_cart는 product_id만, begin_checkout/purchase는 transaction_id만 가진다).
--   그래서 fact_order_item(어느 주문에 어느 상품이 담겼는지의 최종 사실)을 거쳐 역추적한다.
--
-- VIEW로 만든 이유: 원본 fact 테이블이 갱신될 때마다 항상 최신 값을 반영하기 위해서다.
-- 나중에 조회 성능이 문제가 되면(대시보드에서 반복 조회 등) CREATE MATERIALIZED VIEW로
-- 바꾸고 REFRESH MATERIALIZED VIEW로 갱신하는 방식으로 전환할 수 있다.
--
-- 실행 방법: psql -f sql/marts/004_mart_commerce_funnel.sql
-- ============================================================

DROP VIEW IF EXISTS mart_commerce_funnel;

CREATE VIEW mart_commerce_funnel AS
WITH view_item_agg AS (
    SELECT user_id, product_id, MIN(event_timestamp_utc) AS view_item_at_utc
    FROM fact_user_event
    WHERE event_name = 'view_item' AND product_id IS NOT NULL
    GROUP BY user_id, product_id
),
add_to_cart_agg AS (
    SELECT user_id, product_id, MIN(event_timestamp_utc) AS add_to_cart_at_utc
    FROM fact_user_event
    WHERE event_name = 'add_to_cart' AND product_id IS NOT NULL
    GROUP BY user_id, product_id
),
funnel_base AS (
    -- view_item 또는 add_to_cart 중 더 이른 시각을 first_touch_utc로 (열린 퍼널 우회 케이스 포함)
    SELECT
        COALESCE(v.user_id, a.user_id) AS user_id,
        COALESCE(v.product_id, a.product_id) AS product_id,
        LEAST(v.view_item_at_utc, a.add_to_cart_at_utc) AS first_touch_utc
    FROM view_item_agg v
    FULL OUTER JOIN add_to_cart_agg a
      ON a.user_id = v.user_id AND a.product_id = v.product_id
),
order_for_product AS (
    -- 이 상품이 포함된 모든 주문과 그 주문의 begin_checkout/purchase 시각
    SELECT
        o.user_id,
        oi.product_id,
        o.transaction_id,
        o.status,
        bc.event_timestamp_utc AS checkout_at_utc,
        pu.event_timestamp_utc AS purchase_at_utc
    FROM fact_order_item oi
    JOIN fact_order o ON o.transaction_id = oi.transaction_id
    JOIN fact_user_event bc ON bc.transaction_id = o.transaction_id AND bc.event_name = 'begin_checkout'
    LEFT JOIN fact_user_event pu ON pu.transaction_id = o.transaction_id AND pu.event_name = 'purchase'
),
matched_order AS (
    -- 그 상품에 대한 add_to_cart 이후 실제로 checkout까지 이어진 주문 중 가장 이른 것 하나만 선택
    SELECT DISTINCT ON (ofp.user_id, ofp.product_id)
        ofp.user_id,
        ofp.product_id,
        ofp.transaction_id,
        ofp.status,
        ofp.checkout_at_utc,
        ofp.purchase_at_utc
    FROM order_for_product ofp
    JOIN add_to_cart_agg ac
      ON ac.user_id = ofp.user_id AND ac.product_id = ofp.product_id
    WHERE ofp.checkout_at_utc >= ac.add_to_cart_at_utc
    ORDER BY ofp.user_id, ofp.product_id, ofp.checkout_at_utc ASC
)
SELECT
    fb.user_id,
    fb.product_id,
    p.artist_id,
    fb.first_touch_utc,
    (fb.first_touch_utc AT TIME ZONE 'Asia/Seoul')::date AS first_touch_date_kst,
    (ac.add_to_cart_at_utc IS NOT NULL) AS reached_add_to_cart,
    ac.add_to_cart_at_utc,
    (mo.checkout_at_utc IS NOT NULL) AS reached_checkout,
    mo.checkout_at_utc,
    mo.transaction_id,
    COALESCE(mo.status = 'completed', false) AS reached_purchase,
    mo.purchase_at_utc,
    (
        vi.view_item_at_utc IS NOT NULL
        AND ac.add_to_cart_at_utc IS NOT NULL AND ac.add_to_cart_at_utc >= vi.view_item_at_utc
        AND mo.checkout_at_utc IS NOT NULL AND mo.checkout_at_utc >= ac.add_to_cart_at_utc
        AND mo.purchase_at_utc IS NOT NULL AND mo.purchase_at_utc >= mo.checkout_at_utc
        AND mo.status = 'completed'
        AND mo.purchase_at_utc <= fb.first_touch_utc + INTERVAL '7 days'
    ) AS is_closed_funnel_complete,
    CASE
        WHEN mo.purchase_at_utc IS NOT NULL
        THEN ROUND(EXTRACT(EPOCH FROM (mo.purchase_at_utc - fb.first_touch_utc)) / 86400.0, 2)
    END AS days_to_purchase
FROM funnel_base fb
JOIN dim_product p ON p.product_id = fb.product_id
LEFT JOIN view_item_agg vi ON vi.user_id = fb.user_id AND vi.product_id = fb.product_id
LEFT JOIN add_to_cart_agg ac ON ac.user_id = fb.user_id AND ac.product_id = fb.product_id
LEFT JOIN matched_order mo ON mo.user_id = fb.user_id AND mo.product_id = fb.product_id
ORDER BY fb.user_id, fb.product_id;


-- ============================================================
-- 검증 쿼리
-- ============================================================

-- 1) 전체 행 수 = (user_id, product_id) 고유 조합 수(view_item 또는 add_to_cart가 있었던 것)와 일치하는지
SELECT
    (SELECT COUNT(*) FROM mart_commerce_funnel) AS mart_row_count,
    (SELECT COUNT(*) FROM (
        SELECT DISTINCT user_id, product_id
        FROM fact_user_event
        WHERE event_name IN ('view_item', 'add_to_cart') AND product_id IS NOT NULL
    ) t) AS distinct_user_product_pair_count;

-- 2) 단계별 깔때기: 인스턴스 수 -> add_to_cart -> checkout -> purchase (각 단계 전환율 포함)
SELECT
    COUNT(*) AS funnel_instance_count,
    SUM(CASE WHEN reached_add_to_cart THEN 1 ELSE 0 END) AS reached_add_to_cart_count,
    SUM(CASE WHEN reached_checkout THEN 1 ELSE 0 END) AS reached_checkout_count,
    SUM(CASE WHEN reached_purchase THEN 1 ELSE 0 END) AS reached_purchase_count,
    ROUND(100.0 * SUM(CASE WHEN reached_add_to_cart THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_to_add_to_cart,
    ROUND(100.0 * SUM(CASE WHEN reached_checkout THEN 1 ELSE 0 END)
        / NULLIF(SUM(CASE WHEN reached_add_to_cart THEN 1 ELSE 0 END), 0), 1) AS pct_add_to_cart_to_checkout,
    ROUND(100.0 * SUM(CASE WHEN reached_purchase THEN 1 ELSE 0 END)
        / NULLIF(SUM(CASE WHEN reached_checkout THEN 1 ELSE 0 END), 0), 1) AS pct_checkout_to_purchase
FROM mart_commerce_funnel;

-- 3) add_to_cart 도달 건 중 view_item 없이 시작한(열린 퍼널 우회) 비율 -- 파이썬 검증치(18.24%)와 대조
SELECT
    SUM(CASE WHEN reached_add_to_cart THEN 1 ELSE 0 END) AS reached_add_to_cart_count,
    SUM(CASE WHEN reached_add_to_cart AND first_touch_utc = add_to_cart_at_utc THEN 1 ELSE 0 END) AS bypassed_view_item_count,
    ROUND(100.0 * SUM(CASE WHEN reached_add_to_cart AND first_touch_utc = add_to_cart_at_utc THEN 1 ELSE 0 END)
        / NULLIF(SUM(CASE WHEN reached_add_to_cart THEN 1 ELSE 0 END), 0), 2) AS bypass_pct
FROM mart_commerce_funnel;

-- 4) is_closed_funnel_complete=true 건수와 fact_order(status=completed) 건수의 관계 확인
--    (완전히 같을 필요 없음 -- 묶음 주문 1건에 상품이 여러 개면 그만큼 인스턴스도 여러 개 complete일 수 있다)
SELECT
    (SELECT COUNT(*) FROM mart_commerce_funnel WHERE is_closed_funnel_complete) AS closed_funnel_complete_instance_count,
    (SELECT COUNT(*) FROM fact_order WHERE status = 'completed') AS completed_order_count,
    (SELECT COUNT(DISTINCT transaction_id) FROM mart_commerce_funnel WHERE is_closed_funnel_complete) AS distinct_orders_behind_complete_instances;

-- 4-1) 참고: 완료된 주문 중 상품이 2개 이상 묶인 주문 수(=인스턴스 수가 주문 수보다 많아지는 원인)
SELECT COUNT(*) AS multi_item_completed_order_count
FROM (
    SELECT transaction_id
    FROM fact_order_item
    GROUP BY transaction_id
    HAVING COUNT(*) > 1
) multi
JOIN fact_order o ON o.transaction_id = multi.transaction_id AND o.status = 'completed';

-- 5) 총 매출 일치 확인: mart_commerce_funnel(상품 단위, reached_purchase=true)로 집계한 합계
--    vs fact_order(status=completed)에서 직접 집계한 합계. 상품 단위 라인 금액을 써야
--    묶음 주문에서 이중 계산되지 않는다(각 인스턴스는 그 주문 전체 금액이 아니라 그 상품 몫만 갖는다).
--    참고: 두 합계는 정확히 일치하지 않는다(마트가 더 작음). 이중 계산이 아니라 아래 두 가지
--    설계상 이유로 "덜" 집계되는 것이며, 5-1/5-2에서 그 두 원인을 각각 정량화한다.
SELECT
    (
        SELECT SUM(oi.unit_price * oi.quantity - oi.discount_amount)
        FROM mart_commerce_funnel m
        JOIN fact_order_item oi
          ON oi.transaction_id = m.transaction_id AND oi.product_id = m.product_id
        WHERE m.reached_purchase
    ) AS revenue_from_mart_by_product_line,
    (
        SELECT SUM(order_amount) FROM fact_order WHERE status = 'completed'
    ) AS revenue_from_fact_order_completed;

-- 5-1) 원인 A(가장 큰 부분): 동일 (user_id, product_id)를 이 마트는 "첫 관심" 1건만 추적하므로,
--      같은 상품을 같은 팬이 또 구매한(재구매) 매출은 이 마트에 애초에 없다(설계상 의도된 범위 제외).
WITH completed_lines AS (
    SELECT
        o.user_id, oi.product_id, o.completed_at_utc,
        (oi.unit_price * oi.quantity - oi.discount_amount) AS line_amount,
        ROW_NUMBER() OVER (PARTITION BY o.user_id, oi.product_id ORDER BY o.completed_at_utc) AS rn
    FROM fact_order_item oi
    JOIN fact_order o ON o.transaction_id = oi.transaction_id
    WHERE o.status = 'completed'
)
SELECT
    SUM(line_amount) FILTER (WHERE rn = 1) AS first_purchase_per_pair_revenue,
    SUM(line_amount) FILTER (WHERE rn > 1) AS repeat_purchase_revenue_excluded_by_design,
    COUNT(*) FILTER (WHERE rn > 1) AS repeat_purchase_line_count
FROM completed_lines;

-- 5-2) 원인 B(소수 사례): "add_to_cart 이후 가장 이른 checkout"을 찾을 때 그 첫 checkout 시도가
--      완료되지 않고(pending 등) 더 나중의 별도 시도에서 완료된 경우, 이 마트는 먼저 발견한
--      (완료 안 된) 주문에 매칭해버려 나중의 성공 건을 놓친다. 몇 건이나 해당하는지 확인.
SELECT COUNT(*) AS pairs_matched_to_incomplete_order_despite_later_completed_order
FROM mart_commerce_funnel m
WHERE NOT m.reached_purchase
  AND EXISTS (
      SELECT 1
      FROM fact_order_item oi
      JOIN fact_order o ON o.transaction_id = oi.transaction_id
      WHERE oi.product_id = m.product_id
        AND o.user_id = m.user_id
        AND o.status = 'completed'
  );
