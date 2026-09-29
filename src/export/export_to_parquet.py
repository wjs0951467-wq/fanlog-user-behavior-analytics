"""PostgreSQL의 테이블·분석 마트 VIEW를 data/processed/*.parquet으로 내보낸다.

배포 환경(Streamlit Community Cloud)은 로컬 PostgreSQL에 접근할 수 없으므로, 대시보드가 읽는
테이블·VIEW를 Parquet 스냅샷으로 떠서 DuckDB로 읽게 하기 위한 1단계 스크립트다
(docs/decisions_log.md 참고). 내보내기 대상은 dashboard/data.py의 모든 SQL(FROM/JOIN 절)을
전수 조사해 실제로 참조하는 14개로 한정했다.

실행: python src/export/export_to_parquet.py
"""

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from analysis.db import get_engine  # noqa: E402

# dashboard/data.py가 참조하는 테이블·VIEW 전체 (이름: 종류).
# dim_activity_phase, fact_artist_activity는 data.py에서 직접 읽지 않는다(마트 VIEW 안에서만 쓰이고,
# 마트는 계산 결과가 그대로 Parquet으로 저장되므로 배포 환경에서는 원본이 필요 없다).
EXPORT_TARGETS = {
    "dim_artist": "table",
    "dim_user": "table",
    "dim_content": "table",
    "dim_product": "table",
    "bridge_user_artist_follow": "table",
    "fact_message_subscription": "table",
    "fact_user_event": "table",
    "fact_order": "table",
    "fact_order_item": "table",
    "meta_generation_run": "table",
    "mart_artist_daily": "view",
    "mart_user_daily": "view",
    "mart_content_performance": "view",
    "mart_commerce_funnel": "view",
}

# JSONB 컬럼은 psycopg가 dict로 돌려주는데, 행마다 키 구성이 달라 pyarrow struct 추론이 불안정하다.
# JSON 문자열로 저장하고, 읽는 쪽(DuckDB)에서 필요하면 json 함수로 파싱한다.
JSON_COLUMNS = {"fact_user_event": ["parameters"], "fact_artist_activity": ["parameters"]}


def _integer_numeric_columns(engine, table: str) -> list[str]:
    """PostgreSQL에서 정수로 선언된 컬럼을 스키마 정보에서 직접 찾는다(하드코딩하지 않음).
    - NUMERIC(p, 0)(금액 등): read_sql이 항상 float64로 바꿔버린다.
    - smallint/integer/bigint: NULL이 하나라도 있으면 pandas가 float64로 바꿔 Parquet에 DOUBLE로 저장된다
      (예: mart_artist_daily.days_since_last_communication). 그러면 DuckDB 모드에서 NULL이 없는 조회 결과도
      float로 돌아와 PostgreSQL 모드(int64)와 타입이 달라진다.
    스케일이 없는 계산형 NUMERIC(마트의 비율 등)은 제외한다."""
    return pd.read_sql(
        "SELECT column_name FROM information_schema.columns "
        f"WHERE table_name = '{table}' AND ("
        "(data_type = 'numeric' AND numeric_scale = 0) OR data_type IN ('smallint', 'integer', 'bigint'));",
        engine,
    )["column_name"].tolist()


def _normalize_for_parquet(table: str, df: pd.DataFrame, integer_numeric_cols: list[str]) -> pd.DataFrame:
    # 정수 컬럼(금액 포함)을 부동소수점(DOUBLE)이 아닌 정확한 정수(nullable Int64)로 저장한다.
    for col in integer_numeric_cols:
        if col in df.columns:
            df[col] = df[col].round().astype("Int64")
    for col in JSON_COLUMNS.get(table, []):
        if col in df.columns:
            df[col] = df[col].map(lambda v: None if v is None else json.dumps(v, ensure_ascii=False))
    # TIMESTAMPTZ는 DB 세션 타임존으로 들어올 수 있으므로 저장 전에 항상 UTC로 통일한다
    # (프로젝트 원칙: 저장은 UTC, 표시는 KST — docs/decisions_log.md 5.10·5.15절).
    for col in df.columns:
        if isinstance(df[col].dtype, pd.DatetimeTZDtype):
            df[col] = df[col].dt.tz_convert("UTC")
    return df


def main():
    parser = argparse.ArgumentParser(description="PostgreSQL 테이블·마트를 data/processed/*.parquet으로 내보낸다.")
    parser.add_argument("--output-dir", type=str, default="data/processed")
    args = parser.parse_args()

    output_dir = PROJECT_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    engine = get_engine()

    results = []
    for table, kind in EXPORT_TARGETS.items():
        df = pd.read_sql(f"SELECT * FROM {table};", engine)
        df = _normalize_for_parquet(table, df, _integer_numeric_columns(engine, table))
        path = output_dir / f"{table}.parquet"
        df.to_parquet(path, engine="pyarrow", compression="snappy", index=False)

        source_rows = int(pd.read_sql(f"SELECT COUNT(*) AS n FROM {table};", engine).iloc[0]["n"])
        parquet_rows = pq.read_metadata(path).num_rows
        results.append({
            "table": table,
            "kind": kind,
            "source_rows": source_rows,
            "parquet_rows": parquet_rows,
            "match": source_rows == parquet_rows,
            "columns": len(df.columns),
            "size_bytes": path.stat().st_size,
        })

    report = pd.DataFrame(results)
    report["size_kb"] = (report["size_bytes"] / 1024).round(1)
    print(report[["table", "kind", "source_rows", "parquet_rows", "match", "columns", "size_kb"]].to_string(index=False))

    total_mb = report["size_bytes"].sum() / 1024 / 1024
    all_match = bool(report["match"].all())
    print(f"\n전체 {len(report)}개 파일, 총 {total_mb:.2f} MB, 행 수 일치: {'전부 일치' if all_match else '불일치 있음'}")

    meta = pd.read_sql(
        "SELECT config_version, random_seed, scenario, generated_at_utc "
        "FROM meta_generation_run ORDER BY generated_at_utc DESC LIMIT 1;",
        engine,
    )
    meta_row = meta.iloc[0] if not meta.empty else None
    manifest = {
        "exported_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "config_version": None if meta_row is None else str(meta_row["config_version"]),
        "random_seed": None if meta_row is None else int(meta_row["random_seed"]),
        "scenario": None if meta_row is None else str(meta_row["scenario"]),
        "data_generated_at_utc": None if meta_row is None else pd.Timestamp(meta_row["generated_at_utc"]).tz_convert("UTC").isoformat(),
        "tables": {
            r["table"]: {"kind": r["kind"], "rows": r["parquet_rows"], "columns": r["columns"], "size_bytes": r["size_bytes"]}
            for r in results
        },
    }
    manifest_path = output_dir / "_export_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"매니페스트 저장: {manifest_path.relative_to(PROJECT_ROOT)}")

    if not all_match:
        sys.exit(1)


if __name__ == "__main__":
    main()
