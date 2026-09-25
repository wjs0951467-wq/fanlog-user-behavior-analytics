-- FANLOG 차원 테이블(dim_*) DDL
-- 기준 문서: docs/data_dictionary.md 2절
-- 생성 순서: dim_artist, dim_user는 독립적이라 먼저 생성하고,
-- dim_content/dim_product/dim_activity_phase는 dim_artist를 참조하므로 그 뒤에 생성한다.

CREATE TABLE dim_artist (
    artist_id   VARCHAR PRIMARY KEY,
    artist_name VARCHAR NOT NULL,
    artist_type VARCHAR NOT NULL CHECK (artist_type IN ('group', 'solo')),
    debut_year  INT
);

CREATE TABLE dim_user (
    user_id              VARCHAR PRIMARY KEY,
    signup_timestamp_utc TIMESTAMPTZ NOT NULL,
    signup_date_kst      DATE NOT NULL,
    country_group        VARCHAR NOT NULL CHECK (country_group IN ('domestic', 'overseas_asia', 'overseas_other')),
    acquisition_channel  VARCHAR NOT NULL CHECK (acquisition_channel IN ('direct', 'push', 'social', 'search')),
    primary_device_type  VARCHAR NOT NULL CHECK (primary_device_type IN ('mobile', 'desktop', 'tablet')),
    is_deleted           BOOLEAN NOT NULL DEFAULT false,
    deleted_at_utc        TIMESTAMPTZ
);

CREATE TABLE dim_content (
    content_id               VARCHAR PRIMARY KEY,
    artist_id                VARCHAR NOT NULL REFERENCES dim_artist (artist_id),
    content_type             VARCHAR NOT NULL CHECK (content_type IN ('notice', 'photo', 'video', 'music_video', 'live_replay')),
    title                    VARCHAR NOT NULL,
    published_timestamp_utc  TIMESTAMPTZ NOT NULL,
    published_date_kst       DATE NOT NULL
);

CREATE TABLE dim_product (
    product_id             VARCHAR PRIMARY KEY,
    artist_id              VARCHAR NOT NULL REFERENCES dim_artist (artist_id),
    product_name           VARCHAR NOT NULL,
    product_type           VARCHAR NOT NULL CHECK (product_type IN ('album', 'lightstick', 'apparel', 'collab')),
    price                  NUMERIC(12, 0) NOT NULL,
    release_timestamp_utc  TIMESTAMPTZ NOT NULL,
    release_date_kst       DATE NOT NULL
);

CREATE TABLE dim_activity_phase (
    phase_id       VARCHAR PRIMARY KEY,
    artist_id      VARCHAR NOT NULL REFERENCES dim_artist (artist_id),
    phase_type     VARCHAR NOT NULL CHECK (phase_type IN ('daily', 'comeback_prep', 'comeback_active', 'tour', 'inactive')),
    start_date_kst DATE NOT NULL,
    end_date_kst   DATE
);
