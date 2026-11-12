"""SQL 가드레일 (2차 방어선).

1차 방어선: DB 읽기 전용 계정 (sql/01_readonly_role.sql)
2차 방어선: 이 파일 - 실행 전에 SQL을 파싱해서 "SELECT 한 문장만, 허용된 테이블만, 허용된 함수만" 통과시킨다.
방어를 겹쳐 두는 이유: 한 층이 뚫려도 다음 층이 막아준다 (defense in depth).

원칙은 "닫는 방향(fail closed)"이다. 확실히 안전하다고 판단할 수 없으면 막는다.
- 테이블: 허용 목록에 있거나, "그 자리에서 보이는" CTE 일 때만 통과한다.
- 함수: sqlglot 이 모르는 함수는 허용 목록(ALLOWED_FUNCTIONS)에 있을 때만 통과한다.
- 행 수: 맨 바깥 LIMIT 은 항상 max_rows 이하의 정수 리터럴이다.
"""
import sqlglot
from sqlglot import exp

MAX_ROWS = 1000

# 에이전트가 조회해도 되는 테이블 (meta_generation_run 은 제외)
ALLOWED_TABLES = {
    "bridge_user_artist_follow", "dim_activity_phase", "dim_artist", "dim_content",
    "dim_product", "dim_user", "fact_artist_activity", "fact_message_subscription",
    "fact_order", "fact_order_item", "fact_user_event", "mart_artist_daily",
    "mart_commerce_funnel", "mart_content_performance", "mart_user_daily",
}

# ---------- 함수 ----------
# 허용 함수 목록 (화이트리스트). 함수를 더 열어야 하면 여기 한 곳에만 이름(소문자)을 추가한다.
# sqlglot 이 "모르는 함수"(exp.Anonymous)로 읽은 것은 이 목록에 있을 때만 통과한다.
# sqlglot 이 아는 표준 함수(COUNT, SUM, ROUND, DATE_TRUNC 등)는 전용 노드로 읽히므로 이 목록과 무관하게 통과하지만,
# 어떤 함수를 쓰기로 했는지 한눈에 보이도록 여기에도 적어 둔다.
ALLOWED_FUNCTIONS = frozenset({
    # 날짜와 시간
    "date_trunc", "extract", "date_part", "to_char", "to_date", "to_timestamp", "age", "make_date", "timezone",
    "now", "generate_series", "isfinite",
    # 숫자
    "round", "abs", "floor", "ceil", "ceiling", "trunc", "mod", "power", "sqrt", "greatest", "least",
    # 문자열
    "lower", "upper", "length", "substr", "substring", "trim", "replace", "concat", "split_part", "left", "right",
    # NULL 처리
    "coalesce", "nullif",
    # 집계
    "count", "sum", "avg", "min", "max", "string_agg", "percentile_cont", "percentile_disc", "stddev", "variance",
    "bool_and", "bool_or", "every",
    # 윈도
    "row_number", "rank", "dense_rank", "lag", "lead", "ntile", "first_value", "last_value",
    # JSON 컬럼 읽기 (fact_user_event 등의 jsonb 컬럼)
    "jsonb_extract_path_text", "jsonb_typeof", "jsonb_array_length",
})

# 금지 함수 (블랙리스트). 허용 목록보다 먼저 검사한다: 누가 허용 목록에 잘못 넣어도 여기서 막힌다 (이중 방어).
FORBIDDEN_FUNCTIONS = frozenset({
    # 서버에 부담을 주거나 파일/설정에 접근하는 함수
    "pg_sleep", "pg_sleep_for", "pg_sleep_until", "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "pg_stat_file",
    "lo_import", "lo_export", "lo_get", "lo_put", "dblink", "dblink_exec", "set_config", "current_setting",
    "pg_terminate_backend", "pg_cancel_backend", "nextval", "setval",
    # 문자열로 받은 SQL 을 실행하는 함수: 허용 테이블 검사를 통째로 우회한다
    "query_to_xml", "query_to_xmlschema", "query_to_xml_and_xmlschema",
    "table_to_xml", "table_to_xmlschema", "table_to_xml_and_xmlschema",
    "cursor_to_xml", "cursor_to_xmlschema",
    "schema_to_xml", "schema_to_xmlschema", "schema_to_xml_and_xmlschema",
    "database_to_xml", "database_to_xmlschema", "database_to_xml_and_xmlschema",
    # 세션 락: 연결 풀에 락이 남을 수 있다
    "pg_advisory_lock", "pg_advisory_lock_shared", "pg_advisory_xact_lock", "pg_advisory_xact_lock_shared",
    "pg_try_advisory_lock", "pg_try_advisory_lock_shared", "pg_try_advisory_xact_lock",
    "pg_try_advisory_xact_lock_shared", "pg_advisory_unlock", "pg_advisory_unlock_all", "pg_advisory_unlock_shared",
    # 서버와 계정 정보 (sqlglot 이 전용 노드로 읽는 것 포함. 아래 이름은 sqlglot 의 내부 이름이다)
    "current_user", "session_user", "current_role", "current_database", "current_schema", "current_schemas",
    "current_catalog", "current_version", "version",
})
# 이름이 이렇게 시작하면 목록에 없어도 금지한다 (같은 계열의 새 함수 대비)
FORBIDDEN_FUNCTION_PREFIXES = ("pg_advisory", "pg_try_advisory", "pg_sleep", "pg_read_", "pg_ls_", "lo_", "dblink")

# 읽기 전용이 아닌 구문 노드 (WITH 안에 숨은 DELETE 같은 것도 잡기 위해 전체 트리를 검사)
FORBIDDEN_NODES = tuple(
    getattr(exp, name) for name in
    ("Insert", "Update", "Delete", "Drop", "Create", "Alter", "Merge",
     "Command", "TruncateTable", "Copy")
    if hasattr(exp, name)
)


class SQLGuardError(ValueError):
    """가드레일에 걸린 SQL. 메시지는 모델에게 되돌려 재시도에 쓸 수 있게 구체적으로 쓴다."""


def validate_sql(sql: str, max_rows: int = MAX_ROWS) -> str:
    """통과하면 LIMIT이 보장된 안전한 SQL 문자열을 돌려주고, 아니면 SQLGuardError.

    어떤 예외도 SQLGuardError 로 끝난다 (닫는 방향). sqlglot 의 TokenError(따옴표가 닫히지 않은 SQL 등)는 ParseError 가
    아니라서, 잡지 않으면 ask() 가 LLM 을 부른 뒤에 예외로 죽어 사용량을 잃고 재시도도 못 한다.
    """
    try:
        return _validate(sql, max_rows)
    except SQLGuardError:
        raise
    except sqlglot.errors.SqlglotError as e:
        raise SQLGuardError(f"SQL 문법 오류: {e}") from e
    except Exception as e:  # 검사 코드의 예상 못한 오류: 통과시키지 않는다
        raise SQLGuardError(f"SQL 검사 중 예상 못한 오류 ({type(e).__name__}). 다른 방식으로 쓰세요.") from e


def _validate(sql: str, max_rows: int) -> str:
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise SQLGuardError(f"SQL 문법 오류: {e}") from e

    if len(statements) != 1:
        raise SQLGuardError("SQL은 정확히 한 문장이어야 합니다 (세미콜론으로 여러 문장 금지).")
    root = statements[0]

    if not isinstance(root, (exp.Select, exp.Union)):
        raise SQLGuardError(f"SELECT 문만 허용됩니다. (받은 구문: {type(root).__name__})")
    if root.find(*FORBIDDEN_NODES):
        raise SQLGuardError("데이터를 변경하거나 구조를 바꾸는 구문이 포함되어 있습니다.")
    if root.args.get("into") or any(s.args.get("into") for s in root.find_all(exp.Select)):
        raise SQLGuardError("SELECT ... INTO 는 허용되지 않습니다.")
    if any(s.args.get("locks") for s in root.find_all(exp.Select)):
        raise SQLGuardError("FOR UPDATE 등 잠금 구문은 허용되지 않습니다.")

    _check_functions(root)
    _check_cte_names(root)
    _check_tables(root)
    return _enforce_limit(root, max_rows).sql(dialect="postgres")


# ---------- 함수 검사 ----------
def _is_forbidden_function(name: str) -> bool:
    return name in FORBIDDEN_FUNCTIONS or name.startswith(FORBIDDEN_FUNCTION_PREFIXES)


def _check_functions(root: exp.Expression) -> None:
    """금지 함수는 무조건 막고, sqlglot 이 모르는 함수는 허용 목록에 있을 때만 통과시킨다.

    에러 문장은 항상 "허용되지 않는 함수: 이름" 으로 시작한다. 재시도 루프가 이 문장을 모델에게 그대로 돌려준다.
    """
    for func in root.find_all(exp.Func):
        if isinstance(func, exp.Anonymous):
            name = (func.name or "").lower()
            if _is_forbidden_function(name) or name not in ALLOWED_FUNCTIONS:
                raise SQLGuardError(f"허용되지 않는 함수: {name}")
            if isinstance(func.parent, exp.Dot):
                # 스키마를 붙이면 다른 스키마에 있는 같은 이름의 함수를 부를 수 있다. 이름만으로는 안전을 판단할 수 없다.
                raise SQLGuardError(f"허용되지 않는 함수: {name} (스키마를 붙인 함수 호출은 허용되지 않습니다)")
        else:
            name = func.sql_name().lower()  # sqlglot 이 아는 함수의 내부 이름 (예: CURRENT_USER -> current_user)
            if _is_forbidden_function(name):
                raise SQLGuardError(f"허용되지 않는 함수: {name}")


# ---------- 테이블과 CTE 검사 ----------
def _normalized(identifier) -> str:
    """PostgreSQL 이 이름을 읽는 방식: 따옴표가 없으면 소문자로 접고, 따옴표가 있으면 글자 그대로다."""
    name = identifier.name
    return name if getattr(identifier, "quoted", False) else name.lower()


def _cte_name(cte: exp.CTE) -> str:
    alias = cte.args.get("alias")
    return _normalized(alias.this) if alias is not None and alias.this is not None else ""


def _check_cte_names(root: exp.Expression) -> None:
    """허용 테이블이나 시스템 관계와 같은 이름의 CTE 는 쓰지 않아도 거부한다 (이중 방어).

    이런 이름의 CTE 는 "진짜 테이블을 읽는 것처럼 보이는 가짜"를 만들거나, 범위 검사에 빈틈이 있을 때
    진짜 테이블을 가리는 데 쓰인다. 정상 질의는 이런 이름을 쓸 이유가 없다.
    """
    for cte in root.find_all(exp.CTE):
        name = _cte_name(cte).lower()
        if not name:
            raise SQLGuardError("이름이 없는 CTE 는 허용되지 않습니다.")
        if name in ALLOWED_TABLES or name.startswith("pg_") or name == "information_schema":
            raise SQLGuardError(f"CTE 이름으로 쓸 수 없습니다: {name} (허용 테이블이나 시스템 관계와 같은 이름). 다른 이름을 쓰세요.")


def _with_of(node: exp.Expression):
    w = node.args.get("with_") or node.args.get("with")  # sqlglot 버전에 따라 키 이름이 다르다
    return w if isinstance(w, exp.With) else None


def _visible_cte_names(table: exp.Table) -> set:
    """이 테이블 참조가 놓인 자리에서 실제로 보이는 CTE 이름들.

    PostgreSQL 규칙: CTE 는 (1) 그 WITH 가 붙은 질의와 그 안쪽 서브쿼리에서 보이고,
    (2) 같은 WITH 안에서는 "앞에서 정의한" CTE 만 뒤의 CTE 본문에서 보이며,
    (3) 자기 본문 안에서 자기 이름은 WITH RECURSIVE 일 때만 보인다.
    다른 서브쿼리 안에서 정의한 CTE 는 보이지 않는다. 그 자리의 같은 이름은 진짜 테이블을 가리킨다.
    """
    visible = set()
    child, node = table, table.parent
    while node is not None:
        if isinstance(node, exp.With):
            # 참조가 이 WITH 의 CTE 본문 안에 있다: 앞에서 정의한 CTE 만 (재귀면 자기 자신도) 보인다
            ctes = list(node.expressions)
            index = next((i for i, cte in enumerate(ctes) if cte is child), None)
            if index is not None:
                visible |= {_cte_name(cte) for cte in ctes[:index]}
                if node.args.get("recursive"):
                    visible.add(_cte_name(ctes[index]))
            # index 를 찾지 못하면 아무것도 인정하지 않는다 (닫는 방향)
            owner = node.parent          # 이 WITH 가 붙은 질의. 그 질의의 CTE 전체를 인정하면 안 되므로 건너뛴다
            if owner is None:
                break
            child, node = owner, owner.parent
            continue
        with_clause = _with_of(node)
        if with_clause is not None:  # 참조가 이 질의의 본문(또는 그 안쪽)에 있다: 이 질의의 CTE 가 모두 보인다
            visible |= {_cte_name(cte) for cte in with_clause.expressions}
        child, node = node, node.parent
    visible.discard("")
    return visible


def _check_tables(root: exp.Expression) -> None:
    for table in root.find_all(exp.Table):
        if isinstance(table.this, exp.ExplodingGenerateSeries):
            continue  # generate_series (날짜 스파인용)는 허용
        if not table.name or not isinstance(table.this, exp.Identifier):
            raise SQLGuardError("허용되지 않는 테이블 함수입니다.")
        if table.catalog:
            raise SQLGuardError(f"데이터베이스 이름을 붙인 접근 금지: {table.catalog}.{table.db}.{table.name}")
        if table.db and table.db.lower() != "public":
            raise SQLGuardError(f"public 스키마 외 접근 금지: {table.db}.{table.name}")
        name = _normalized(table.this)
        # 스키마를 붙인 이름(public.x)은 CTE 가 아니라 실제 테이블이다. CTE 는 스키마 없는 이름으로만 인정한다.
        if not table.db and name in _visible_cte_names(table):
            continue
        if name not in ALLOWED_TABLES:
            raise SQLGuardError(f"허용되지 않은 테이블: {table.name}")


# ---------- 행 수 제한 ----------
def _enforce_limit(root: exp.Expression, max_rows: int) -> exp.Expression:
    """맨 바깥 LIMIT 을 "max_rows 이하의 정수 리터럴"로 강제한다 (결과 폭주 방지). UNION 에도 같게 적용된다.

    그대로 두는 경우는 하나뿐이다: LIMIT <정수 리터럴> 이고 그 값이 max_rows 이하일 때.
    LIMIT ALL, LIMIT NULL, LIMIT (SELECT ...), LIMIT 계산식, 너무 큰 수는 모두 max_rows 로 덮어쓴다.
    FETCH FIRST n ROWS ONLY 는 같은 일을 하는 다른 문법이라 통째로 거부한다 (LIMIT 한 가지만 검사하면 되게).
    """
    if root.find(exp.Fetch):
        raise SQLGuardError("FETCH FIRST ... ROWS ONLY 는 허용되지 않습니다. 대신 LIMIT 을 쓰세요.")
    limit = root.args.get("limit")
    if isinstance(limit, exp.Limit):
        value = limit.expression
        extras = [k for k, v in limit.args.items() if k not in ("this", "expression") and v]  # WITH TIES, PERCENT 등
        if (isinstance(value, exp.Literal) and value.is_int and not extras
                and 0 <= int(value.name) <= max_rows):
            return root
    return root.limit(max_rows)
