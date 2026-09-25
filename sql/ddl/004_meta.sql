-- FANLOG 데이터 생성 실행 메타 테이블
-- 데이터 생성 스크립트를 실행/적재할 때마다 어떤 config_version, random_seed,
-- scenario로 만들어졌는지 기록해 재현성을 추적한다.

CREATE TABLE meta_generation_run (
    run_id           SERIAL PRIMARY KEY,
    config_version   VARCHAR,
    random_seed      BIGINT,
    scenario         VARCHAR CHECK (scenario IN ('baseline', 'null_effect')),
    generated_at_utc TIMESTAMPTZ NOT NULL DEFAULT now()
);
