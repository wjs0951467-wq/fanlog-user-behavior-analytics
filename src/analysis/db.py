"""분석 노트북·스크립트가 공용으로 쓰는 PostgreSQL 연결 헬퍼.

src/ingestion/load_to_postgres.py의 get_connection()과 같은 .env 값을 읽지만,
여기서는 pandas.read_sql과 바로 호환되는 SQLAlchemy Engine을 반환한다.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_engine() -> Engine:
    load_dotenv(PROJECT_ROOT / ".env")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ["POSTGRES_PORT"]
    dbname = os.environ["POSTGRES_DB"]
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    url = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{dbname}"
    return create_engine(url)
