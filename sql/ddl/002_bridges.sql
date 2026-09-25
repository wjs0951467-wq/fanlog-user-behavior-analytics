-- FANLOG 관계·연결 테이블 DDL
-- 기준 문서: docs/data_dictionary.md 3절
-- dim_user, dim_artist(001_dimensions.sql)가 먼저 생성되어 있어야 한다.

CREATE TABLE bridge_user_artist_follow (
    follow_id         VARCHAR PRIMARY KEY,
    user_id           VARCHAR NOT NULL REFERENCES dim_user (user_id),
    artist_id         VARCHAR NOT NULL REFERENCES dim_artist (artist_id),
    followed_at_utc   TIMESTAMPTZ NOT NULL,
    unfollowed_at_utc TIMESTAMPTZ
);

CREATE TABLE fact_message_subscription (
    subscription_id         VARCHAR PRIMARY KEY,
    user_id                 VARCHAR NOT NULL REFERENCES dim_user (user_id),
    artist_id               VARCHAR NOT NULL REFERENCES dim_artist (artist_id),
    plan_type               VARCHAR NOT NULL CHECK (plan_type IN ('monthly')),
    started_at_utc          TIMESTAMPTZ NOT NULL,
    ended_at_utc            TIMESTAMPTZ,
    cancel_reason_category  VARCHAR CHECK (cancel_reason_category IN ('user_cancel', 'expired_no_renewal'))
);
