-- FANLOG 평가 후보 질문의 정답 SQL 초안 (eval/candidates.yaml 과 같은 SQL)
--
-- 이 초안은 정답이 아니다. 사람이 DBeaver 로 직접 확인해야 verified 가 된다.
-- 사용법: 읽기 전용 계정(fanlog_ro)으로 접속해서 한 문항씩 선택해 실행하고, 결과를 VERIFY_CHECKLIST.md 에 적는다.
-- 모든 문장은 SELECT 다. Claude Code 는 이 파일을 실행하지 않았다 (가드레일 파싱 검사만 했다).
-- 거절 문항(Q36~Q40)은 실행할 SQL 이 없다. 해당 정보가 정말 데이터에 없는지만 확인한다.

-- [Q01] 지금까지 가입한 사용자는 모두 몇 명이야?
SELECT COUNT(*) AS signup_users
FROM dim_user;

-- [Q02] 탈퇴 처리된 사용자는 몇 명이야?
SELECT COUNT(*) AS deleted_users
FROM dim_user
WHERE is_deleted;

-- [Q03] 판매 등록된 상품은 총 몇 개야?
SELECT COUNT(*) AS products
FROM dim_product;

-- [Q04] 콘텐츠 유형별로 콘텐츠가 몇 개씩 있어?
SELECT content_type, COUNT(*) AS contents
FROM dim_content
GROUP BY content_type
ORDER BY contents DESC;

-- [Q05] 환불이 발생한 주문은 몇 건이야? 부분 환불도 포함해서.
SELECT COUNT(*) AS refunded_orders
FROM fact_order
WHERE status IN ('refunded', 'partially_refunded');

-- [Q06] 주로 쓰는 기기별 가입자 수를 알려줘.
SELECT primary_device_type, COUNT(*) AS users
FROM dim_user
GROUP BY primary_device_type
ORDER BY users DESC;

-- [Q07] 아티스트 쪽에서 올린 소통 활동은 종류별로 몇 건이야?
SELECT activity_type, COUNT(*) AS activities
FROM fact_artist_activity
GROUP BY activity_type
ORDER BY activities DESC;

-- [Q08] 결제를 시작만 하고 끝내지 않은 주문은 몇 건이야?
SELECT COUNT(*) AS pending_orders
FROM fact_order
WHERE status = 'pending';

-- [Q09] 아티스트별로 등록된 상품이 몇 개인지 이름과 같이 보여줘.
SELECT a.artist_name, COUNT(*) AS products
FROM dim_product p
JOIN dim_artist a ON a.artist_id = p.artist_id
GROUP BY a.artist_name
ORDER BY products DESC;

-- [Q10] 상품 종류별로 몇 개나 팔렸어? 결제가 끝나지 않은 주문은 빼고.
SELECT p.product_type, SUM(i.quantity) AS quantity
FROM fact_order_item i
JOIN fact_order o ON o.transaction_id = i.transaction_id
JOIN dim_product p ON p.product_id = i.product_id
WHERE o.status <> 'pending'
GROUP BY p.product_type
ORDER BY quantity DESC;

-- [Q11] 지금 유지되고 있는 메시지 구독이 아티스트별로 몇 건이야?
SELECT a.artist_name, COUNT(*) AS active_subscriptions
FROM fact_message_subscription s
JOIN dim_artist a ON a.artist_id = s.artist_id
WHERE s.ended_at_utc IS NULL
GROUP BY a.artist_name
ORDER BY active_subscriptions DESC;

-- [Q12] 아티스트별 콘텐츠 누적 조회수를 알려줘.
SELECT a.artist_name, SUM(c.total_views) AS total_views
FROM mart_content_performance c
JOIN dim_artist a ON a.artist_id = c.artist_id
GROUP BY a.artist_name
ORDER BY total_views DESC;

-- [Q13] 국가 그룹별 구매 건수는 어떻게 돼?
SELECT u.country_group, COUNT(*) AS purchases
FROM fact_order o
JOIN dim_user u ON u.user_id = o.user_id
WHERE o.status <> 'pending'
GROUP BY u.country_group
ORDER BY purchases DESC;

-- [Q14] 앨범 상품이 들어 있는 구매 주문은 몇 건이야?
SELECT COUNT(DISTINCT o.transaction_id) AS album_orders
FROM fact_order o
JOIN fact_order_item i ON i.transaction_id = o.transaction_id
JOIN dim_product p ON p.product_id = i.product_id
WHERE o.status <> 'pending'
  AND p.product_type = 'album';

-- [Q15] 그룹 아티스트와 솔로 아티스트 중 어느 쪽이 콘텐츠를 더 많이 올렸어? 각각 몇 개인지 알려줘.
SELECT a.artist_type, COUNT(*) AS contents
FROM dim_content c
JOIN dim_artist a ON a.artist_id = c.artist_id
GROUP BY a.artist_type
ORDER BY contents DESC;

-- [Q16] 유입 채널별로 현재 메시지 구독을 유지 중인 팬이 몇 명인지 알려줘. 탈퇴한 사용자는 빼고.
SELECT u.acquisition_channel, COUNT(DISTINCT s.user_id) AS subscribers
FROM fact_message_subscription s
JOIN dim_user u ON u.user_id = s.user_id
WHERE s.ended_at_utc IS NULL
  AND u.is_deleted IS NOT TRUE
GROUP BY u.acquisition_channel
ORDER BY subscribers DESC;

-- [Q17] 분석 기간 전체 순매출은 얼마야?
-- (정의 미확정: 대시보드 Page 3 의 매출 정의와 같은지 먼저 확인)
SELECT SUM(order_amount - refund_amount) AS net_revenue
FROM fact_order
WHERE status <> 'pending';

-- [Q18] 지금까지 환불해 준 금액은 다 합쳐서 얼마야?
SELECT SUM(refund_amount) AS refund_total
FROM fact_order;

-- [Q19] 현재 유지 중인 메시지 구독은 총 몇 건이야?
SELECT COUNT(*) AS active_subscriptions
FROM fact_message_subscription
WHERE ended_at_utc IS NULL;

-- [Q20] 결제를 시작한 주문은 전부 몇 건이야? 구매 완료 여부와 상관없이.
SELECT COUNT(*) AS checkout_started_orders
FROM fact_order;

-- [Q21] W1 참여 재방문율을 하나의 값으로만 알려줘.
-- (정의 미확정: 아래 SQL 은 임의의 가정으로 쓴 자리 채움이다. PRD 의 공식 W1 정의를 먼저 정한다)
SELECT ROUND(COUNT(DISTINCT w1.user_id)::numeric / COUNT(DISTINCT w0.user_id), 4) AS w1_retention
FROM mart_user_daily w0
LEFT JOIN mart_user_daily w1
  ON w1.user_id = w0.user_id
 AND w1.had_core_activity
 AND w1.activity_date_kst BETWEEN DATE '2026-01-08' AND DATE '2026-01-14'
WHERE w0.had_core_activity
  AND w0.activity_date_kst BETWEEN DATE '2026-01-01' AND DATE '2026-01-07';

-- [Q22] 마지막 날짜 기준으로 이탈 위험(at_risk)이거나 휴면(dormant)인 팬은 합쳐서 몇 명이야?
SELECT COUNT(DISTINCT m.user_id) AS fans
FROM mart_user_daily m
JOIN dim_user u ON u.user_id = m.user_id
WHERE m.activity_date_kst = (SELECT MAX(activity_date_kst) FROM mart_user_daily)
  AND m.activity_status IN ('at_risk', 'dormant')
  AND u.is_deleted IS NOT TRUE;

-- [Q23] 구매 건수 중에서 환불(부분 환불 포함)된 주문의 비율을 하나의 값으로만 알려줘.
SELECT ROUND(COUNT(*) FILTER (WHERE status IN ('refunded', 'partially_refunded'))::numeric / COUNT(*), 4) AS refund_rate
FROM fact_order
WHERE status <> 'pending';

-- [Q24] 2026년 2월 한 달 동안 구매 건수는 몇 건이었어?
SELECT COUNT(*) AS purchases
FROM fact_order
WHERE status <> 'pending'
  AND (completed_at_utc AT TIME ZONE 'Asia/Seoul')::date BETWEEN DATE '2026-02-01' AND DATE '2026-02-28';

-- [Q25] 최근 7일 동안 구매 건수는 몇 건이야? 데이터의 마지막 날을 포함해서 7일로 세어줘.
SELECT COUNT(*) AS purchases
FROM fact_order
WHERE status <> 'pending'
  AND (completed_at_utc AT TIME ZONE 'Asia/Seoul')::date >=
      (SELECT MAX((completed_at_utc AT TIME ZONE 'Asia/Seoul')::date) FROM fact_order WHERE status <> 'pending') - 6;

-- [Q26] 2026년 3월에 새로 가입한 사용자는 몇 명이야?
SELECT COUNT(*) AS signups
FROM dim_user
WHERE signup_date_kst BETWEEN DATE '2026-03-01' AND DATE '2026-03-31';

-- [Q27] 월별 구매 건수 추이를 보여줘.
SELECT to_char(completed_at_utc AT TIME ZONE 'Asia/Seoul', 'YYYY-MM') AS month, COUNT(*) AS purchases
FROM fact_order
WHERE status <> 'pending'
GROUP BY 1
ORDER BY 1;

-- [Q28] 이번 달에 올라온 콘텐츠는 몇 개야?
SELECT COUNT(*) AS contents
FROM dim_content
WHERE date_trunc('month', published_date_kst) = (SELECT date_trunc('month', MAX(published_date_kst)) FROM dim_content);

-- [Q29] 2026년 1월에 새로 생긴 팔로우는 몇 건이야?
SELECT COUNT(*) AS follows
FROM bridge_user_artist_follow
WHERE (followed_at_utc AT TIME ZONE 'Asia/Seoul')::date BETWEEN DATE '2026-01-01' AND DATE '2026-01-31';

-- [Q30] 분석 기간(2026년 1월~3월) 동안 가입한 사용자는 몇 명이야?
SELECT COUNT(*) AS signups
FROM dim_user
WHERE signup_date_kst BETWEEN DATE '2026-01-01' AND DATE '2026-03-31';

-- [Q31] 장바구니에 담은 건 중에서 구매까지 이어진 비율을 하나의 값으로만 알려줘.
SELECT ROUND(COUNT(*) FILTER (WHERE reached_purchase)::numeric / COUNT(*), 4) AS cart_to_purchase_rate
FROM mart_commerce_funnel
WHERE reached_add_to_cart;

-- [Q32] 한 번이라도 구매한 적 있는 팬은 몇 명이야? 탈퇴한 사용자는 빼고.
SELECT COUNT(DISTINCT o.user_id) AS buyers
FROM fact_order o
JOIN dim_user u ON u.user_id = o.user_id
WHERE o.status <> 'pending'
  AND u.is_deleted IS NOT TRUE;

-- [Q33] 분석 기간 중에 하루라도 휴면 상태였던 팬은 몇 명이야?
SELECT COUNT(DISTINCT m.user_id) AS fans
FROM mart_user_daily m
JOIN dim_user u ON u.user_id = m.user_id
WHERE m.activity_status = 'dormant'
  AND u.is_deleted IS NOT TRUE;

-- [Q34] 현재 이탈 위험 상태인 팬을 유입 채널별로 나누면 각각 몇 명이야?
SELECT u.acquisition_channel, COUNT(DISTINCT m.user_id) AS fans
FROM mart_user_daily m
JOIN dim_user u ON u.user_id = m.user_id
WHERE m.activity_date_kst = (SELECT MAX(activity_date_kst) FROM mart_user_daily)
  AND m.activity_status = 'at_risk'
  AND u.is_deleted IS NOT TRUE
GROUP BY u.acquisition_channel
ORDER BY fans DESC;

-- [Q35] 2026년 1월 1일 하루 동안 구매 완료된 주문은 몇 건이야?
SELECT COUNT(*) AS purchases
FROM fact_order
WHERE status <> 'pending'
  AND (completed_at_utc AT TIME ZONE 'Asia/Seoul')::date = DATE '2026-01-01';

-- [Q36] 팬들의 성별 비율은 어떻게 돼?
-- (거절이 정답: 성별 컬럼이 어느 테이블에도 없는지 확인)

-- [Q37] 상품 리뷰 평점이 가장 높은 상품은 뭐야?
-- (거절이 정답: 리뷰나 평점 테이블/컬럼이 없는지 확인)

-- [Q38] 광고비 대비 매출(ROAS)은 채널별로 얼마야?
-- (거절이 정답: 광고비 데이터가 없는지 확인)

-- [Q39] 팬들이 사는 도시별로 가입자 수를 알려줘.
-- (거절이 정답: 도시 컬럼이 없고 country_group 뿐인지 확인)

-- [Q40] 쿠폰 코드별 사용 횟수는 몇 번이야?
-- (거절이 정답: 쿠폰 코드 컬럼이 없고 discount_amount 뿐인지 확인)
