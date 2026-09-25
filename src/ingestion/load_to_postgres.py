import argparse
import csv
import json
import os
from pathlib import Path

import psycopg
import yaml
from dotenv import load_dotenv
from psycopg.types.json import Json

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 적재 순서 (외래키 의존관계 순서, 매우 중요 — 뒤로 갈수록 앞의 테이블들을 참조한다)
TABLE_LOAD_ORDER = [
    "dim_artist",
    "dim_user",
    "dim_activity_phase",
    "dim_content",
    "dim_product",
    "bridge_user_artist_follow",
    "fact_message_subscription",
    "fact_artist_activity",
    "fact_order",
    "fact_order_item",
    "fact_user_event",
]

DDL_FILES = [
    "001_dimensions.sql",
    "002_bridges.sql",
    "003_facts.sql",
    "004_meta.sql",
    "005_indexes.sql",
]

# COPY로 적재할 때 특수 변환이 필요한 컬럼
BOOLEAN_COLUMNS = {"is_deleted"}
JSONB_COLUMNS = {"parameters"}


def get_connection() -> psycopg.Connection:
    load_dotenv(PROJECT_ROOT / ".env")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ["POSTGRES_PORT"]
    dbname = os.environ["POSTGRES_DB"]
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    return psycopg.connect(
        host=host, port=port, dbname=dbname, user=user, password=password, autocommit=False
    )


def run_ddl(conn: psycopg.Connection, reset: bool) -> None:
    ddl_dir = PROJECT_ROOT / "sql" / "ddl"

    with conn.cursor() as cur:
        if reset:
            print("--reset: 기존 테이블을 DROP TABLE ... CASCADE로 제거합니다.")
            for table in reversed(TABLE_LOAD_ORDER + ["meta_generation_run"]):
                cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
            conn.commit()

        for filename in DDL_FILES:
            path = ddl_dir / filename
            sql_text = path.read_text(encoding="utf-8")
            statements = [s.strip() for s in sql_text.split(";") if s.strip()]
            for stmt in statements:
                cur.execute(stmt)
            print(f"  실행: sql/ddl/{filename} ({len(statements)}개 statement)")
    conn.commit()
    print("DDL 실행 완료 (테이블 생성 성공)\n")


def _convert_value(column: str, value: str):
    if value == "":
        return None
    if column in BOOLEAN_COLUMNS:
        return value.strip().lower() == "true"
    if column in JSONB_COLUMNS:
        return Json(json.loads(value))
    return value


def load_csv_to_table(conn: psycopg.Connection, table: str, csv_path: Path) -> tuple:
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames
        rows = list(reader)

    cols_sql = ", ".join(columns)
    with conn.cursor() as cur:
        with cur.copy(f"COPY {table} ({cols_sql}) FROM STDIN") as copy:
            for row in rows:
                values = tuple(_convert_value(col, row[col]) for col in columns)
                copy.write_row(values)
    conn.commit()
    return len(rows), table


def verify_row_counts(conn: psycopg.Connection, csv_counts: dict) -> list:
    results = []
    with conn.cursor() as cur:
        for table in TABLE_LOAD_ORDER:
            cur.execute(f"SELECT count(*) FROM {table};")
            db_count = cur.fetchone()[0]
            csv_count = csv_counts[table]
            results.append((table, csv_count, db_count, csv_count == db_count))
    return results


def insert_meta_generation_run(conn: psycopg.Connection, config_version: str, random_seed: int, scenario: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO meta_generation_run (config_version, random_seed, scenario)
            VALUES (%s, %s, %s)
            RETURNING run_id;
            """,
            (str(config_version), random_seed, scenario),
        )
        run_id = cur.fetchone()[0]
    conn.commit()
    print(f"meta_generation_run에 run_id={run_id} 행 추가 완료 "
          f"(config_version={config_version}, random_seed={random_seed}, scenario={scenario})\n")


def run_fk_sanity_check(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM fact_user_event WHERE user_id NOT IN (SELECT user_id FROM dim_user);"
        )
        return cur.fetchone()[0]


def main():
    parser = argparse.ArgumentParser(
        description="sql/ddl/의 DDL을 실행해 테이블을 만들고 data/raw/*.csv를 PostgreSQL에 적재한다."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="기존 테이블을 DROP TABLE ... CASCADE로 제거한 뒤 다시 생성한다.",
    )
    parser.add_argument("--data-dir", type=str, default="data/raw")
    parser.add_argument("--config", type=str, default="config/data_generation.yaml")
    parser.add_argument("--scenario", type=str, default="baseline", choices=["baseline", "null_effect"])
    args = parser.parse_args()

    data_dir = PROJECT_ROOT / args.data_dir
    config_path = PROJECT_ROOT / args.config

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    config_version = config["meta"]["config_version"]
    random_seed = config["meta"]["random_seed"]

    conn = get_connection()
    try:
        print("=== 1. DDL 실행 (테이블 생성) ===")
        run_ddl(conn, reset=args.reset)

        print("=== 2. CSV 적재 (외래키 의존관계 순서) ===")
        csv_counts = {}
        for table in TABLE_LOAD_ORDER:
            csv_path = data_dir / f"{table}.csv"
            n_rows, _ = load_csv_to_table(conn, table, csv_path)
            csv_counts[table] = n_rows
            print(f"  {table}: {n_rows}행 적재")
        print()

        print("=== 3. 행 수 검증 (CSV vs DB) ===")
        results = verify_row_counts(conn, csv_counts)
        header = f"{'table':<32} {'csv_rows':>10} {'db_rows':>10} {'match':>6}"
        print(header)
        print("-" * len(header))
        all_match = True
        for table, csv_count, db_count, match in results:
            print(f"{table:<32} {csv_count:>10} {db_count:>10} {'OK' if match else 'FAIL':>6}")
            if not match:
                all_match = False
        print()

        if not all_match:
            raise RuntimeError(
                "CSV 행 수와 DB 행 수가 일치하지 않는 테이블이 있습니다. 적재를 중단합니다."
            )

        print("=== 4. meta_generation_run 기록 ===")
        insert_meta_generation_run(conn, config_version, random_seed, args.scenario)

        print("=== 5. 외래키 정합성 확인 (fact_user_event.user_id) ===")
        bad_count = run_fk_sanity_check(conn)
        print(
            f"SELECT count(*) FROM fact_user_event WHERE user_id NOT IN "
            f"(SELECT user_id FROM dim_user); -> {bad_count} "
            f"({'OK' if bad_count == 0 else 'FAIL'})"
        )

        print("\n모든 단계가 정상적으로 완료되었습니다.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
