-- FANLOG 팩트 테이블 DDL
-- 기준 문서: docs/data_dictionary.md 4절
-- 생성 순서가 중요하다: fact_order_item은 fact_order를 참조하고,
-- fact_user_event는 거의 모든 테이블을 참조하므로 반드시 마지막에 생성한다.

CREATE TABLE fact_artist_activity (
    activity_id             VARCHAR PRIMARY KEY,
    artist_id               VARCHAR NOT NULL REFERENCES dim_artist (artist_id),
    activity_type           VARCHAR NOT NULL CHECK (activity_type IN ('post', 'message', 'live')),
    activity_timestamp_utc  TIMESTAMPTZ NOT NULL,
    activity_date_kst       DATE NOT NULL,
    content_id              VARCHAR REFERENCES dim_content (content_id),
    phase_id                VARCHAR REFERENCES dim_activity_phase (phase_id),
    parameters               JSONB
);

CREATE TABLE fact_order (
    transaction_id    VARCHAR PRIMARY KEY,
    user_id           VARCHAR NOT NULL REFERENCES dim_user (user_id),
    status            VARCHAR NOT NULL CHECK (status IN ('pending', 'completed', 'refunded', 'partially_refunded')),
    order_amount      NUMERIC(12, 0) NOT NULL,
    refund_amount     NUMERIC(12, 0) NOT NULL DEFAULT 0,
    created_at_utc    TIMESTAMPTZ NOT NULL,
    completed_at_utc  TIMESTAMPTZ
);

CREATE TABLE fact_order_item (
    order_item_id    VARCHAR PRIMARY KEY,
    transaction_id   VARCHAR NOT NULL REFERENCES fact_order (transaction_id),
    product_id       VARCHAR NOT NULL REFERENCES dim_product (product_id),
    quantity         INT NOT NULL,
    unit_price       NUMERIC(12, 0) NOT NULL,
    discount_amount  NUMERIC(12, 0) NOT NULL DEFAULT 0
);

CREATE TABLE fact_user_event (
    event_id             VARCHAR PRIMARY KEY,
    event_name           VARCHAR NOT NULL CHECK (event_name IN (
        'sign_up', 'session_start', 'artist_view', 'artist_follow', 'artist_unfollow',
        'message_subscription_start', 'message_subscription_cancel', 'artist_post_view',
        'message_open', 'live_view_start', 'content_view', 'content_like', 'comment_create',
        'view_item', 'add_to_cart', 'begin_checkout', 'purchase', 'refund'
    )),
    event_timestamp_utc  TIMESTAMPTZ NOT NULL,
    event_date_kst       DATE NOT NULL,
    user_id              VARCHAR NOT NULL REFERENCES dim_user (user_id),
    session_id           VARCHAR,
    artist_id            VARCHAR REFERENCES dim_artist (artist_id),
    content_id           VARCHAR REFERENCES dim_content (content_id),
    activity_id          VARCHAR REFERENCES fact_artist_activity (activity_id),
    product_id           VARCHAR REFERENCES dim_product (product_id),
    transaction_id       VARCHAR REFERENCES fact_order (transaction_id),
    device_type          VARCHAR NOT NULL CHECK (device_type IN ('mobile', 'desktop', 'tablet')),
    traffic_source       VARCHAR CHECK (traffic_source IN ('direct', 'push', 'social', 'search')),
    parameters            JSONB
);
