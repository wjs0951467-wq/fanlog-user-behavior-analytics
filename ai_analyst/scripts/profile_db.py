"""DB를 훑어서 semantic/schema_profile.json 을 만든다.

왜 필요한가: 컬럼 이름만으로는 'status' 에 어떤 값이 들어 있는지, 데이터가 언제부터 언제까지인지 알 수 없다.
모델이 존재하지 않는 값(예: status = 'done')으로 WHERE 를 걸어 "결과 0건"을 내는 게
Text-to-SQL 에서 가장 흔한 오답이라서, 실제 값 목록을 프롬프트에 넣어 준다.

실행: python -m scripts.profile_db   (관리자 계정 DATABASE_URL_ADMIN 사용)
"""
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
OUT = Path(__file__).resolve().parent.parent / "semantic" / "schema_profile.json"
MAX_ENUM = 30  # 서로 다른 값이 이 개수 이하면 "값 목록"으로 취급


def q(ident: str) -> str:
    """식별자 따옴표 처리 (information_schema 에서 읽은 이름만 넣으므로 안전)."""
    return '"' + ident.replace('"', '""') + '"'


def main():
    engine = create_engine(os.environ["DATABASE_URL_ADMIN"])
    profile = {}
    with engine.connect() as conn:
        tables = [r[0] for r in conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY 1"))]

        for t in tables:
            cols = conn.execute(text(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=:t ORDER BY ordinal_position"),
                {"t": t}).fetchall()
            n = conn.execute(text(f"SELECT COUNT(*) FROM public.{q(t)}")).scalar()
            info = {"row_count": n, "columns": {}}
            print(f"[{t}] {n:,} rows")

            for name, dtype in cols:
                col = {"type": dtype}
                try:
                    if dtype in ("character varying", "text", "boolean") and not name.endswith("_id"):
                        rows = conn.execute(text(
                            f"SELECT {q(name)}, COUNT(*) FROM public.{q(t)} "
                            f"GROUP BY 1 ORDER BY 2 DESC LIMIT {MAX_ENUM + 1}")).fetchall()
                        if len(rows) <= MAX_ENUM:
                            col["values"] = {("NULL" if v is None else str(v)): c for v, c in rows}
                        else:
                            col["high_cardinality"] = True
                    elif dtype == "date" or dtype.startswith("timestamp"):
                        mn, mx = conn.execute(text(
                            f"SELECT MIN({q(name)}), MAX({q(name)}) FROM public.{q(t)}")).one()
                        col["min"], col["max"] = str(mn), str(mx)
                    elif dtype == "jsonb":
                        rows = conn.execute(text(
                            f"SELECT k, COUNT(*) FROM (SELECT jsonb_object_keys({q(name)}) AS k FROM "
                            f"(SELECT {q(name)} FROM public.{q(t)} WHERE jsonb_typeof({q(name)})='object' "
                            f"LIMIT 50000) s) x GROUP BY k ORDER BY 2 DESC LIMIT 30")).fetchall()
                        col["keys"] = [k for k, _ in rows]
                except Exception as e:  # 한 컬럼 실패가 전체를 멈추지 않게
                    conn.rollback()
                    col["profile_error"] = str(e).splitlines()[0]
                info["columns"][name] = col
            profile[t] = info

    OUT.write_text(json.dumps(profile, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n저장 완료: {OUT}")


if __name__ == "__main__":
    main()
