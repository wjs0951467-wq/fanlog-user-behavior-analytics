-- DBeaver에서 fanlog 연결(관리자 계정)로 실행하세요.
-- 목적: AI가 만든 SQL이 어떤 실수를 해도 데이터를 바꿀 수 없게 "DB 레벨"에서 막기 (1차 방어선)
-- ※ 'fanlog' 는 실제 DB 이름으로 바꾸세요. (확인: SELECT current_database();)

CREATE ROLE fanlog_ro LOGIN PASSWORD 'change_me';   -- 비밀번호는 바꾸고 .env 에도 반영

GRANT CONNECT ON DATABASE fanlog TO fanlog_ro;
GRANT USAGE ON SCHEMA public TO fanlog_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO fanlog_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO fanlog_ro;

-- 이 계정의 모든 세션에 자동 적용되는 안전 설정
ALTER ROLE fanlog_ro SET default_transaction_read_only = on;
ALTER ROLE fanlog_ro SET statement_timeout = '5s';

-- 에이전트에게 불필요한 메타 테이블은 막기
REVOKE ALL ON public.meta_generation_run FROM fanlog_ro;

-- 확인용: 아래가 에러(permission denied / read-only)가 나야 정상
-- SET ROLE fanlog_ro;  DELETE FROM dim_user;  RESET ROLE;
