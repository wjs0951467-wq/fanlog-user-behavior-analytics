import pytest

from app.sql_guard import SQLGuardError, validate_sql


# ---------- 통과해야 하는 SQL ----------
def test_simple_select_gets_limit():
    out = validate_sql("SELECT user_id FROM dim_user")
    assert "LIMIT 1000" in out


def test_trailing_semicolon_ok():
    assert validate_sql("SELECT 1 FROM dim_user;")


def test_cte_ok():
    sql = "WITH f AS (SELECT user_id FROM bridge_user_artist_follow WHERE unfollowed_at_utc IS NULL) SELECT COUNT(*) FROM f"
    assert "LIMIT" in validate_sql(sql)


def test_join_and_union_ok():
    assert validate_sql("SELECT a.artist_id FROM dim_artist a JOIN dim_content c ON c.artist_id = a.artist_id")
    assert validate_sql("SELECT user_id FROM dim_user UNION SELECT user_id FROM fact_order")


def test_generate_series_ok():
    assert validate_sql("SELECT d::date FROM generate_series('2025-01-01'::date, '2025-01-10'::date, '1 day') d")


def test_big_limit_is_reduced():
    assert "LIMIT 1000" in validate_sql("SELECT * FROM dim_user LIMIT 999999")


def test_small_limit_kept():
    assert "LIMIT 5" in validate_sql("SELECT * FROM dim_user LIMIT 5")


# ---------- 막아야 하는 SQL ----------
@pytest.mark.parametrize("sql", [
    "DROP TABLE dim_user",
    "DELETE FROM dim_user",
    "UPDATE dim_user SET is_deleted = true",
    "INSERT INTO dim_user (user_id) VALUES ('x')",
    "TRUNCATE dim_user",
    "SELECT 1; DROP TABLE dim_user",
    "WITH d AS (DELETE FROM dim_user RETURNING *) SELECT * FROM d",
    "SELECT * INTO backup_user FROM dim_user",
    "SELECT * FROM dim_user FOR UPDATE",
    "SELECT pg_sleep(30)",
    "SELECT * FROM pg_catalog.pg_tables",
    "SELECT * FROM information_schema.columns",
    "SELECT * FROM meta_generation_run",
    "SELECT * FROM some_unknown_table",
    "COPY dim_user TO '/tmp/x.csv'",
])
def test_dangerous_sql_blocked(sql):
    with pytest.raises(SQLGuardError):
        validate_sql(sql)


def test_garbage_blocked():
    with pytest.raises(SQLGuardError):
        validate_sql("이건 SQL이 아니다")
