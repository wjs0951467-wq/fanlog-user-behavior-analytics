"""SQL 가드레일 (2차 방어선).

1차 방어선: DB 읽기 전용 계정 (sql/01_readonly_role.sql)
2차 방어선: 이 파일 - 실행 전에 SQL을 파싱해서 "SELECT 한 문장만, 허용된 테이블만" 통과시킨다.
방어를 겹쳐 두는 이유: 한 층이 뚫려도 다음 층이 막아준다 (defense in depth).
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

# 서버에 부담을 주거나 파일/설정에 접근할 수 있는 PostgreSQL 함수
FORBIDDEN_FUNCTIONS = {
    "pg_sleep", "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "lo_import",
    "lo_export", "dblink", "set_config", "current_setting",
    "pg_terminate_backend", "pg_cancel_backend",
}

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
    """통과하면 LIMIT이 보장된 안전한 SQL 문자열을 돌려주고, 아니면 SQLGuardError."""
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

    for func in root.find_all(exp.Anonymous, exp.Func):
        name = (func.name or "").lower()
        if name in FORBIDDEN_FUNCTIONS:
            raise SQLGuardError(f"허용되지 않는 함수입니다: {name}")

    cte_names = {cte.alias_or_name for cte in root.find_all(exp.CTE)}
    for table in root.find_all(exp.Table):
        if isinstance(table.this, exp.ExplodingGenerateSeries):
            continue  # generate_series (날짜 스파인용)는 허용
        if not table.name:
            raise SQLGuardError("허용되지 않는 테이블 함수입니다.")
        if table.db and table.db.lower() != "public":
            raise SQLGuardError(f"public 스키마 외 접근 금지: {table.db}.{table.name}")
        if table.name in cte_names:
            continue
        if table.name.lower() not in ALLOWED_TABLES:
            raise SQLGuardError(f"허용되지 않은 테이블: {table.name}")

    return _enforce_limit(root, max_rows).sql(dialect="postgres")


def _enforce_limit(root: exp.Expression, max_rows: int) -> exp.Expression:
    """LIMIT이 없으면 붙이고, 너무 크면 max_rows 로 줄인다 (결과 폭주 방지)."""
    limit = root.args.get("limit")
    if limit is None:
        return root.limit(max_rows)
    value = limit.expression
    if isinstance(value, exp.Literal) and value.is_int and int(value.name) > max_rows:
        return root.limit(max_rows)
    return root
