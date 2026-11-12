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


# =====================================================================
# 보안 점검(1-1, 1-2, 1-3, 1-5)에서 찾은 우회 사례. 모두 막혀야 한다.
# =====================================================================

# ---------- 1-1. CTE 이름으로 실제 테이블을 가리는 우회 ----------
# CTE 는 "그 자리에서 보이는 것"만 인정한다. 다른 범위의 CTE 와 이름이 같다고 실제 테이블을 통과시키면 안 된다.
CTE_BYPASSES = {
    "보고서 재현: 안쪽 CTE 이름으로 바깥의 시스템 뷰를 읽는다":
        "SELECT * FROM (WITH pg_user AS (SELECT 1) SELECT * FROM pg_user) a, pg_user",
    "안쪽 CTE 이름으로 바깥의 비허용 테이블을 읽는다":
        "SELECT * FROM (WITH meta_generation_run AS (SELECT 1 AS x) SELECT x FROM meta_generation_run) a, meta_generation_run",
    "허용 목록에도 시스템 이름에도 없는 테이블을 같은 방식으로 읽는다":
        "SELECT * FROM (WITH secret_t AS (SELECT 1 AS x) SELECT x FROM secret_t) a, secret_t",
    "같은 WITH 에서 나중에 정의한 CTE 는 앞의 CTE 안에서 보이지 않는다":
        "WITH a AS (SELECT * FROM secret_t), secret_t AS (SELECT 1) SELECT * FROM a",
    "재귀가 아닌 CTE 는 자기 본문 안에서 자기 이름이 보이지 않는다":
        "WITH secret_t AS (SELECT * FROM secret_t) SELECT * FROM secret_t",
    "스키마를 붙인 이름은 CTE 가 아니라 실제 테이블이다":
        "WITH meta_generation_run AS (SELECT 1) SELECT * FROM public.meta_generation_run",
    "UNION 의 한쪽 안에서 정의한 CTE 는 다른 쪽에서 보이지 않는다":
        "SELECT x FROM (WITH secret_t AS (SELECT 1 AS x) SELECT x FROM secret_t) q UNION SELECT 1 FROM secret_t",
    "두 겹 중첩: 가장 안쪽 CTE 는 바깥 서브쿼리의 형제에서 보이지 않는다":
        "SELECT * FROM (SELECT * FROM (WITH secret_t AS (SELECT 1 AS x) SELECT x FROM secret_t) i) o JOIN secret_t ON true",
    "따옴표로 대소문자를 지킨 CTE 는 소문자 이름의 실제 테이블과 다른 것이다":
        'WITH "Secret_T" AS (SELECT 1) SELECT * FROM secret_t',
    "WHERE 절 서브쿼리 안의 CTE 는 바깥 FROM 에서 보이지 않는다":
        "SELECT * FROM secret_t WHERE EXISTS (WITH secret_t AS (SELECT 1) SELECT * FROM secret_t)",
}


@pytest.mark.parametrize("sql", CTE_BYPASSES.values(), ids=CTE_BYPASSES.keys())
def test_cte_name_cannot_hide_a_real_table_in_another_scope(sql):
    with pytest.raises(SQLGuardError):
        validate_sql(sql)


@pytest.mark.parametrize("sql", [
    "WITH dim_user AS (SELECT 1 AS user_id) SELECT * FROM dim_user",           # 허용 테이블 이름을 가린다
    "WITH DIM_USER AS (SELECT 1 AS user_id) SELECT * FROM DIM_USER",           # 대소문자만 다른 경우
    "WITH pg_user AS (SELECT 1) SELECT * FROM pg_user",                         # 시스템 관계 이름
    "WITH pg_anything AS (SELECT 1) SELECT * FROM pg_anything",
    "WITH information_schema AS (SELECT 1) SELECT * FROM information_schema",
    "WITH ok AS (SELECT 1), mart_user_daily AS (SELECT 2) SELECT * FROM ok",    # 쓰지 않아도 이름만으로 거부
])
def test_cte_named_like_an_allowed_or_system_relation_is_rejected(sql):
    with pytest.raises(SQLGuardError, match="CTE"):
        validate_sql(sql)


@pytest.mark.parametrize("sql", [
    "WITH a AS (SELECT user_id FROM dim_user), b AS (SELECT user_id FROM a) SELECT COUNT(*) FROM b",  # 앞에서 정의한 CTE
    "WITH a AS (SELECT user_id FROM dim_user) SELECT * FROM (SELECT user_id FROM a) s",               # 서브쿼리 안에서도 보인다
    "WITH a AS (SELECT user_id FROM dim_user) SELECT * FROM dim_user u WHERE u.user_id IN (SELECT user_id FROM a)",
    "WITH a AS (SELECT 1 AS x) SELECT * FROM a UNION ALL SELECT * FROM a",                             # UNION 양쪽에서 보인다
    "SELECT * FROM (WITH a AS (SELECT user_id FROM dim_user) SELECT * FROM a) s",                      # 안쪽에서 정의하고 안쪽에서 쓴다
    "WITH RECURSIVE n AS (SELECT 1 AS x UNION ALL SELECT x + 1 FROM n WHERE x < 5) SELECT * FROM n",   # 재귀 CTE 는 자기 이름이 보인다
    "WITH a AS (WITH b AS (SELECT user_id FROM dim_user) SELECT * FROM b) SELECT * FROM a",            # CTE 안의 CTE
    "WITH A AS (SELECT user_id FROM dim_user) SELECT * FROM a",                                        # 따옴표 없는 이름은 대소문자 무시
])
def test_cte_visible_in_its_own_scope_still_passes(sql):
    assert "LIMIT" in validate_sql(sql)


# ---------- 1-2. 함수: 모르는 함수는 허용 목록에 있을 때만 ----------
FUNCTION_BYPASSES = {
    "query_to_xml": "SELECT query_to_xml('select * from meta_generation_run', true, false, '')",
    "query_to_xml_and_xmlschema": "SELECT query_to_xml_and_xmlschema('select 1', true, false, '')",
    "query_to_xmlschema": "SELECT query_to_xmlschema('select 1', true, false, '')",
    "table_to_xml": "SELECT table_to_xml('pg_user'::regclass, true, false, '')",
    "cursor_to_xml": "SELECT cursor_to_xml('c'::refcursor, 10, true, false, '')",
    "schema_to_xml": "SELECT schema_to_xml('public', true, false, '')",
    "database_to_xml": "SELECT database_to_xml(true, false, '')",
    "pg_advisory_lock": "SELECT pg_advisory_lock(1)",
    "pg_advisory_xact_lock": "SELECT pg_advisory_xact_lock(1)",
    "pg_try_advisory_lock": "SELECT pg_try_advisory_lock(1)",
    "pg_sleep_for": "SELECT pg_sleep_for('10 seconds')",
    "pg_sleep_until": "SELECT pg_sleep_until('2030-01-01')",
    "pg_stat_file": "SELECT pg_stat_file('/etc/passwd')",
    "lo_get": "SELECT lo_get(1)",
    "nextval": "SELECT nextval('s')",
    "inet_server_addr": "SELECT inet_server_addr()",
    "pg_backend_pid": "SELECT pg_backend_pid()",
    "has_table_privilege": "SELECT has_table_privilege('dim_user', 'select')",
    "모르는 함수": "SELECT some_unknown_function(user_id) FROM dim_user",
    "WHERE 절 안": "SELECT 1 FROM dim_user WHERE pg_sleep_for('1s') IS NULL",
    "함수 인자 안": "SELECT lower(query_to_xml('select 1', true, false, '')::text) FROM dim_user",
    "CTE 안": "WITH a AS (SELECT pg_advisory_lock(1) AS x) SELECT * FROM a",
    "스키마를 붙인 금지 함수": "SELECT pg_catalog.pg_sleep_for('1s')",
    "스키마를 붙인 허용 이름 (다른 스키마의 같은 이름 함수)": "SELECT evil.age(signup_date_kst) FROM dim_user",
    "대문자": "SELECT QUERY_TO_XML('select 1', true, false, '')",
}


@pytest.mark.parametrize("sql", FUNCTION_BYPASSES.values(), ids=FUNCTION_BYPASSES.keys())
def test_function_not_on_the_allow_list_is_blocked(sql):
    with pytest.raises(SQLGuardError):
        validate_sql(sql)


@pytest.mark.parametrize("sql, name", [
    ("SELECT some_unknown_function(user_id) FROM dim_user", "some_unknown_function"),
    ("SELECT query_to_xml('select 1', true, false, '')", "query_to_xml"),
    ("SELECT pg_advisory_lock(1)", "pg_advisory_lock"),
    ("SELECT PG_SLEEP_FOR('1s')", "pg_sleep_for"),
    ("SELECT pg_sleep(30)", "pg_sleep"),
])
def test_blocked_function_message_names_the_function(sql, name):
    # 재시도 루프와 로그가 이 문장을 그대로 쓴다. 함수 이름이 소문자로 그대로 들어 있어야 모델이 고칠 수 있다.
    with pytest.raises(SQLGuardError, match=f"허용되지 않는 함수: {name}"):
        validate_sql(sql)


@pytest.mark.parametrize("sql", [
    "SELECT current_user", "SELECT session_user", "SELECT version()",
    "SELECT current_database()", "SELECT current_schema",
])
def test_server_information_functions_are_blocked(sql):
    with pytest.raises(SQLGuardError, match="허용되지 않는 함수"):
        validate_sql(sql)


def test_explicit_block_list_wins_over_the_allow_list(monkeypatch):
    """이중 방어: 누군가 허용 목록에 위험한 함수를 잘못 넣어도 블랙리스트가 먼저 막는다."""
    from app import sql_guard
    monkeypatch.setattr(sql_guard, "ALLOWED_FUNCTIONS", sql_guard.ALLOWED_FUNCTIONS | {"query_to_xml", "pg_advisory_lock"})
    for sql in ("SELECT query_to_xml('select 1', true, false, '')", "SELECT pg_advisory_lock(1)"):
        with pytest.raises(SQLGuardError, match="허용되지 않는 함수"):
            validate_sql(sql)


@pytest.mark.parametrize("name", ["pg_advisory_future_lock", "pg_try_advisory_future", "pg_sleep_longer", "pg_read_anything",
                                  "pg_ls_anything", "lo_anything", "dblink_anything"])
def test_forbidden_prefix_wins_over_the_allow_list(monkeypatch, name):
    """같은 계열의 새 함수(목록에 없는 이름)를 누가 허용 목록에 넣어도, 이름의 앞부분으로 막는다."""
    from app import sql_guard
    assert name not in sql_guard.FORBIDDEN_FUNCTIONS  # 명시 목록에는 없는 이름이다 (접두사 검사만 시험한다)
    monkeypatch.setattr(sql_guard, "ALLOWED_FUNCTIONS", sql_guard.ALLOWED_FUNCTIONS | {name})
    with pytest.raises(SQLGuardError, match=f"허용되지 않는 함수: {name}"):
        validate_sql(f"SELECT {name}(1)")


def test_allow_list_is_one_constant_and_adding_a_name_opens_only_that_function(monkeypatch):
    from app import sql_guard
    sql = "SELECT my_new_analysis_function(user_id) FROM dim_user"
    with pytest.raises(SQLGuardError):
        validate_sql(sql)
    monkeypatch.setattr(sql_guard, "ALLOWED_FUNCTIONS", sql_guard.ALLOWED_FUNCTIONS | {"my_new_analysis_function"})
    assert validate_sql(sql)


# ---------- 1-3. 행 수 제한 ----------
LIMIT_BYPASSES = {
    "LIMIT ALL": "SELECT * FROM dim_user LIMIT ALL",
    "LIMIT NULL": "SELECT * FROM dim_user LIMIT NULL",
    "LIMIT 서브쿼리": "SELECT * FROM dim_user LIMIT (SELECT 99999999)",
    "LIMIT 계산식": "SELECT * FROM dim_user LIMIT 500 * 500",
    "LIMIT 문자열": "SELECT * FROM dim_user LIMIT '99999999'",
    "LIMIT 큰 수": "SELECT * FROM dim_user LIMIT 99999999",
    "LIMIT ALL + OFFSET": "SELECT * FROM dim_user LIMIT ALL OFFSET 5",
    "UNION + LIMIT ALL": "SELECT user_id FROM dim_user UNION ALL SELECT user_id FROM fact_order LIMIT ALL",
    "UNION + LIMIT 서브쿼리": "SELECT user_id FROM dim_user UNION SELECT user_id FROM fact_order LIMIT (SELECT 99999999)",
    "UNION, 가지 안에만 LIMIT": "(SELECT user_id FROM dim_user LIMIT ALL) UNION ALL (SELECT user_id FROM fact_order LIMIT ALL)",
    "LIMIT 없음": "SELECT * FROM dim_user",
}


@pytest.mark.parametrize("sql", LIMIT_BYPASSES.values(), ids=LIMIT_BYPASSES.keys())
def test_row_cap_is_always_a_literal_at_most_max_rows(sql):
    out = validate_sql(sql)
    assert out.rstrip().endswith("LIMIT 1000") or "LIMIT 1000 OFFSET" in out, out  # 맨 바깥의 LIMIT 이 1000 으로 강제된다
    assert "LIMIT ALL" not in out.split(")")[-1] and "99999999" not in out.split(")")[-1]


@pytest.mark.parametrize("sql", [
    "SELECT * FROM dim_user FETCH FIRST 99999999 ROWS ONLY",
    "SELECT * FROM dim_user FETCH FIRST 5 ROWS ONLY",
    "SELECT * FROM dim_user OFFSET 3 ROWS FETCH NEXT 99999999 ROWS ONLY",
    "SELECT user_id FROM dim_user UNION SELECT user_id FROM fact_order FETCH FIRST 99999999 ROWS ONLY",
    "SELECT * FROM (SELECT * FROM dim_user FETCH FIRST 99999999 ROWS ONLY) s",
])
def test_fetch_first_is_rejected_with_a_hint_to_use_limit(sql):
    with pytest.raises(SQLGuardError, match="LIMIT"):
        validate_sql(sql)


def test_custom_max_rows_is_enforced_the_same_way():
    assert validate_sql("SELECT * FROM dim_user LIMIT ALL", max_rows=7).endswith("LIMIT 7")
    assert validate_sql("SELECT * FROM dim_user LIMIT 3", max_rows=7).endswith("LIMIT 3")
    assert validate_sql("SELECT * FROM dim_user", max_rows=200_000).endswith("LIMIT 200000")


# ---------- 1-5. catalog 가 붙은 이름 ----------
@pytest.mark.parametrize("sql", [
    "SELECT * FROM otherdb.public.dim_user",
    "SELECT * FROM fanlog.public.dim_user",
    "SELECT * FROM dim_user u JOIN otherdb.public.fact_order o ON o.user_id = u.user_id",
])
def test_catalog_qualified_names_are_rejected(sql):
    with pytest.raises(SQLGuardError):
        validate_sql(sql)


def test_public_schema_prefix_is_still_allowed():
    assert validate_sql("SELECT user_id FROM public.dim_user")


# =====================================================================
# 회귀: 정상 SQL 은 막히면 안 된다
# =====================================================================
def _semantic_examples():
    import yaml
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent / "semantic" / "semantic_layer.yaml"
    return [e["sql"] for e in yaml.safe_load(path.read_text(encoding="utf-8"))["examples"]]


def test_semantic_layer_examples_exist_and_pass():
    examples = _semantic_examples()
    assert len(examples) >= 2
    for sql in examples:
        assert "LIMIT" in validate_sql(sql)


def test_churn_fixed_sql_passes_with_its_raised_row_cap():
    from app import churn
    assert len(churn.LOAD_SQL) == 5
    for sql in churn.LOAD_SQL.values():
        assert validate_sql(sql, max_rows=churn.LOAD_MAX_ROWS).endswith(f"LIMIT {churn.LOAD_MAX_ROWS}")


COMMON_PATTERNS = {
    "AT TIME ZONE + 날짜 캐스팅":
        "SELECT (followed_at_utc AT TIME ZONE 'Asia/Seoul')::date AS d, COUNT(*) FROM bridge_user_artist_follow GROUP BY 1",
    "FILTER (WHERE ...)":
        "SELECT COUNT(*) FILTER (WHERE reached_purchase) * 1.0 / COUNT(*) AS rate FROM mart_commerce_funnel",
    "COUNT(DISTINCT ...)":
        "SELECT COUNT(DISTINCT user_id) FROM mart_user_daily WHERE activity_status = 'dormant'",
    "윈도 함수":
        "SELECT user_id, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY activity_date_kst DESC) AS rn, "
        "RANK() OVER (ORDER BY activity_date_kst), DENSE_RANK() OVER (ORDER BY activity_date_kst), "
        "LAG(activity_date_kst) OVER (PARTITION BY user_id ORDER BY activity_date_kst), "
        "LEAD(activity_date_kst) OVER (PARTITION BY user_id ORDER BY activity_date_kst) FROM mart_user_daily",
    "날짜 함수":
        "SELECT date_trunc('month', signup_date_kst)::date AS m, EXTRACT(YEAR FROM signup_date_kst) AS y, "
        "to_char(signup_date_kst, 'YYYY-MM') AS ym, date_part('dow', signup_date_kst) AS dow, "
        "age(signup_date_kst) AS a, CAST(signup_timestamp_utc AS date) AS d FROM dim_user",
    "generate_series 날짜 스파인":
        "SELECT d::date FROM generate_series('2026-01-01'::date, '2026-01-31'::date, interval '1 day') d",
    "generate_series 와 조인":
        "SELECT g.d::date, COUNT(u.user_id) FROM generate_series('2026-01-01'::date, '2026-01-10'::date, '1 day') AS g(d) "
        "LEFT JOIN dim_user u ON u.signup_date_kst = g.d::date GROUP BY 1 ORDER BY 1",
    "수학과 문자열 함수":
        "SELECT ROUND(AVG(order_amount), 2), COALESCE(SUM(refund_amount), 0), NULLIF(COUNT(*), 0), ABS(-1), FLOOR(1.5), CEIL(1.5), "
        "GREATEST(1, 2), LEAST(1, 2), LOWER(status), UPPER(status), LENGTH(status), SUBSTR(status, 1, 3) FROM fact_order GROUP BY status",
    "percentile_cont 와 string_agg":
        "SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY order_amount) AS median, STRING_AGG(DISTINCT status, ',') FROM fact_order",
    "CASE, 서브쿼리, HAVING":
        "SELECT status, SUM(CASE WHEN refund_amount > 0 THEN 1 ELSE 0 END) FROM fact_order "
        "WHERE user_id IN (SELECT user_id FROM dim_user WHERE is_deleted IS NOT TRUE) GROUP BY status HAVING COUNT(*) > 1",
    "마지막 날짜 기준 현재 상태":
        "SELECT COUNT(DISTINCT user_id) FROM mart_user_daily "
        "WHERE activity_date_kst = (SELECT MAX(activity_date_kst) FROM mart_user_daily) AND activity_status = 'at_risk'",
    "CTE + 조인 + 정렬 + LIMIT":
        "WITH f AS (SELECT artist_id, COUNT(DISTINCT user_id) AS n FROM bridge_user_artist_follow "
        "WHERE unfollowed_at_utc IS NULL GROUP BY artist_id) "
        "SELECT a.artist_name, f.n FROM f JOIN dim_artist a ON a.artist_id = f.artist_id ORDER BY f.n DESC LIMIT 5",
    "UNION ALL + LIMIT":
        "SELECT user_id FROM dim_user UNION ALL SELECT user_id FROM fact_order LIMIT 10",
    "NOW 와 CURRENT_DATE":
        "SELECT CURRENT_DATE, NOW(), COUNT(*) FROM dim_user WHERE signup_date_kst <= CURRENT_DATE",
    "LIMIT + OFFSET":
        "SELECT user_id FROM dim_user ORDER BY user_id LIMIT 20 OFFSET 40",
}


@pytest.mark.parametrize("sql", COMMON_PATTERNS.values(), ids=COMMON_PATTERNS.keys())
def test_common_analysis_patterns_still_pass(sql):
    assert "LIMIT" in validate_sql(sql)


def test_small_limits_are_kept_exactly():
    assert validate_sql("SELECT user_id FROM dim_user ORDER BY user_id LIMIT 20 OFFSET 40").endswith("LIMIT 20 OFFSET 40")
    assert validate_sql("SELECT user_id FROM dim_user UNION ALL SELECT user_id FROM fact_order LIMIT 10").endswith("LIMIT 10")


USER_LISTED_FUNCTIONS = ("date_trunc", "extract", "round", "coalesce", "nullif", "generate_series", "to_char", "lower", "upper",
                         "length", "substr", "greatest", "least", "abs", "floor", "ceil", "row_number", "rank", "dense_rank",
                         "lag", "lead", "percentile_cont", "string_agg")


def test_allow_list_contains_the_agreed_starting_functions():
    from app import sql_guard
    assert set(USER_LISTED_FUNCTIONS) <= sql_guard.ALLOWED_FUNCTIONS
    assert not (sql_guard.ALLOWED_FUNCTIONS & sql_guard.FORBIDDEN_FUNCTIONS)  # 두 목록에 동시에 있는 이름은 없다
    assert all(name == name.lower() for name in sql_guard.ALLOWED_FUNCTIONS)
