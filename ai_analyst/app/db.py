"""DB 연결. 앱은 반드시 읽기 전용 계정(DATABASE_URL_RO)만 사용한다."""
import os
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()


@lru_cache(maxsize=1)
def get_engine():
    return create_engine(
        os.environ["DATABASE_URL_RO"],
        # 3차 방어선: 계정 설정과 별개로 연결 단위에서도 읽기 전용 + 5초 제한
        connect_args={"options": "-c default_transaction_read_only=on -c statement_timeout=5000"},
        pool_pre_ping=True,
    )


def run_query(sql: str):
    """(컬럼명 리스트, 행 리스트) 반환. 호출 전에 반드시 sql_guard.validate_sql 을 거칠 것."""
    with get_engine().connect() as conn:
        result = conn.execute(text(sql))
        columns = list(result.keys())
        rows = [list(r) for r in result.fetchall()]
    return columns, rows
