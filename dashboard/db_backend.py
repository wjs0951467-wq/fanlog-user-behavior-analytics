"""대시보드 데이터 백엔드 전환 계층 — PostgreSQL(로컬 개발)과 DuckDB+Parquet(배포)을 같은 인터페이스로 감싼다.

환경변수 DEPLOY_MODE로 모드를 고른다 (.env 또는 실행 환경 변수, 기본값 "postgres").
- "postgres": src/analysis/db.py의 SQLAlchemy 엔진으로 로컬 PostgreSQL에 쿼리한다.
- "duckdb":   data/processed/*.parquet(src/export/export_to_parquet.py로 생성)을 파일명과 같은 이름의
              VIEW로 등록한 인메모리 DuckDB에 쿼리한다. 배포 환경(Streamlit Community Cloud)용.

두 모드 모두 run_query(sql)이 pandas DataFrame을 돌려주므로, data.py의 SQL 문자열을 그대로 재사용할 수 있다.
DuckDB의 ICU(타임존) 확장은 pip 패키지에 정적 링크되어 있어 `AT TIME ZONE 'Asia/Seoul'`이 네트워크 없이 동작한다
(docs/decisions_log.md 참고).
"""

import os
import sys
import threading
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PARQUET_DIR = PROJECT_ROOT / "data" / "processed"
VALID_MODES = ("postgres", "duckdb")
sys.path.insert(0, str(PROJECT_ROOT / "src"))  # postgres 모드의 analysis.db import용 (data.py 없이 단독 사용 시에도)

# 이미 설정된 환경변수(예: 실행 시 DEPLOY_MODE=duckdb)는 .env가 덮어쓰지 않는다(load_dotenv 기본 동작).
load_dotenv(PROJECT_ROOT / ".env")

_duckdb_con = None
_duckdb_lock = threading.Lock()


def get_deploy_mode() -> str:
    mode = os.environ.get("DEPLOY_MODE", "postgres").strip().lower()
    if mode not in VALID_MODES:
        raise ValueError(f"DEPLOY_MODE는 {VALID_MODES} 중 하나여야 한다 (현재 값: {mode!r})")
    return mode


def _get_duckdb_connection():
    """Parquet 파일마다 VIEW를 하나씩 등록한 인메모리 DuckDB 연결(프로세스당 1개)을 만든다."""
    global _duckdb_con
    with _duckdb_lock:
        if _duckdb_con is None:
            import duckdb

            parquet_files = sorted(PARQUET_DIR.glob("*.parquet"))
            if not parquet_files:
                raise FileNotFoundError(
                    f"{PARQUET_DIR}에 Parquet 파일이 없다. 먼저 python src/export/export_to_parquet.py를 실행한다."
                )
            con = duckdb.connect(database=":memory:")
            # 세션 타임존을 UTC로 고정한다. PostgreSQL(Etc/UTC)과 같게 맞춰서, TIMESTAMPTZ 결과가 실행 환경의
            # 로컬 타임존에 따라 다르게 표시되지 않게 한다.
            con.execute("SET GLOBAL TimeZone = 'UTC'")  # GLOBAL: cursor()로 만든 복제 연결에도 적용되도록
            for path in parquet_files:
                # 파일 경로의 작은따옴표를 이스케이프해 SQL 문자열이 깨지지 않게 한다.
                file_literal = path.as_posix().replace("'", "''")
                con.execute(f'CREATE VIEW "{path.stem}" AS SELECT * FROM read_parquet(\'{file_literal}\')')
            _duckdb_con = con
        return _duckdb_con


def _match_postgres_dtypes(df: pd.DataFrame, columns: list[str], types: list) -> pd.DataFrame:
    """DuckDB `.df()`와 PostgreSQL(`pd.read_sql`)의 pandas 변환 규칙이 다른 두 가지를 PostgreSQL 쪽에 맞춘다.
    값은 바뀌지 않고 타입만 맞추며, 이 차이로 화면 표시가 달라지는 것(예: `12.0`, 날짜 뒤 `00:00:00`)을 막는다.
    - DATE: DuckDB는 datetime64로, psycopg는 파이썬 date 객체로 돌려준다 → date 객체로 변환.
    - HUGEINT: DuckDB의 SUM(정수)은 HUGEINT(128비트)라 .df()가 float64로 만든다(PostgreSQL SUM(int)은 bigint)
      → NULL이 없으면 int64로 변환. 단, PostgreSQL의 SUM(bigint)은 numeric이라 read_sql이 float64로 돌려주는데
      DuckDB 결과 타입만으로는 SUM(int)/SUM(bigint)을 구분할 수 없다. 합계는 정수가 맞으므로 int64로 통일한다
      (해당 컬럼은 get_artist_comparison의 total_new_follows·total_unfollows 2개뿐이고 화면에 표시되지 않으며 값은 같다).
    - NULL이 섞인 정수: DuckDB는 pandas nullable Int64(pd.NA)로, read_sql은 float64(NaN)로 돌려준다
      → read_sql과 같게 NULL이 있으면 float64, 없으면 int64로 변환."""
    for col, col_type in zip(columns, types):
        type_name = str(col_type).upper()
        if type_name == "DATE":
            df[col] = df[col].map(lambda v: None if pd.isna(v) else v.date()).astype(object)
        elif type_name == "HUGEINT" and not df[col].isna().any():
            df[col] = df[col].astype("int64")
        elif isinstance(df[col].dtype, pd.core.arrays.integer.IntegerDtype):
            df[col] = df[col].astype("float64") if df[col].isna().any() else df[col].astype("int64")
    return df


def run_query(sql: str) -> pd.DataFrame:
    """SQL 문자열을 현재 DEPLOY_MODE의 백엔드에서 실행해 DataFrame으로 돌려준다."""
    if get_deploy_mode() == "duckdb":
        # Streamlit은 여러 스레드에서 스크립트를 실행한다. DuckDB 연결 객체는 스레드 간 동시 사용이 안전하지 않아
        # 쿼리마다 cursor()(같은 인메모리 DB를 공유하는 복제 연결)를 새로 만들어 실행한다.
        cursor = _get_duckdb_connection().cursor()
        try:
            relation = cursor.sql(sql)
            return _match_postgres_dtypes(relation.df(), relation.columns, relation.types)
        finally:
            cursor.close()

    from analysis.db import get_engine  # postgres 모드에서만 import (배포 환경에서 DB 연결을 시도하지 않도록)

    return pd.read_sql(sql, get_engine())
