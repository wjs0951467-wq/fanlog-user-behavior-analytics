"""자연어 질문 -> SQL 생성 -> 검증 -> 실행.

흐름: ask() -> generate_sql()(LLM) -> validate_sql()(가드레일) -> run_query()(읽기 전용 DB)
Day 2 에서 여기에 "실패하면 에러를 모델에게 돌려주고 재시도" 루프를 붙인다.
"""
import json
import os
import re
import sys
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from .db import run_query
from .sql_guard import ALLOWED_TABLES, SQLGuardError, validate_sql

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
MODEL = os.getenv("FANLOG_MODEL")

SYSTEM_RULES = """You are a PostgreSQL analyst for FANLOG, a K-entertainment fan platform.
Convert the user's question (usually Korean) into ONE read-only PostgreSQL query.

Rules:
- Output exactly one SQL query inside a ```sql fenced block. No explanation outside the block.
- SELECT only. Use only the tables/views listed under AVAILABLE TABLES. Do not qualify with a schema name.
- Follow the SEMANTIC LAYER definitions and conventions strictly; they override your own assumptions.
- Use only column values that appear in the schema profile (e.g. for status columns).
- For date logic use the *_kst columns, never *_utc.
- Always add a sensible ORDER BY and LIMIT for list-type results.
- CANNOT_ANSWER is a last resort. Before using it, re-check AVAILABLE TABLES and the schema profile.
  Use it only when a required table or column truly does not appear there. If you use it, output a single
  SQL comment: -- CANNOT_ANSWER: <short reason in Korean>
"""


def render_schema(profile: dict) -> str:
    lines = []
    for table, info in profile.items():
        if table not in ALLOWED_TABLES:
            continue
        kind = info.get("kind", "table").upper()
        lines.append(f"{kind} {table}  ({info['row_count']:,} rows)")
        for col, ci in info["columns"].items():
            extra = ""
            if "values" in ci:
                extra = "  values=" + json.dumps(ci["values"], ensure_ascii=False)
            elif "min" in ci:
                extra = f"  range={ci['min']} .. {ci['max']}"
            elif "keys" in ci:
                extra = "  json_keys=" + ",".join(ci["keys"])
            lines.append(f"  - {col}: {ci['type']}{extra}")
        lines.append("")
    return "\n".join(lines)


@lru_cache(maxsize=1)
def build_system_prompt() -> str:
    profile_path = ROOT / "semantic" / "schema_profile.json"
    if not profile_path.exists():
        raise RuntimeError("semantic/schema_profile.json 이 없습니다. 먼저 `python -m scripts.profile_db` 를 실행하세요.")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    semantic = (ROOT / "semantic" / "semantic_layer.yaml").read_text(encoding="utf-8")

    available = [t for t in profile if t in ALLOWED_TABLES]
    missing = sorted(ALLOWED_TABLES - set(available))
    if missing:  # 프로파일에 없는 테이블이 있으면 조용히 넘어가지 않고 바로 알려준다
        raise RuntimeError(f"schema_profile.json 에 없는 테이블/뷰: {missing}. profile_db 를 다시 실행하세요.")

    return (f"{SYSTEM_RULES}\nAVAILABLE TABLES: {', '.join(available)}\n\n"
            f"=== SCHEMA PROFILE ===\n{render_schema(profile)}\n"
            f"=== SEMANTIC LAYER ===\n{semantic}")


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    return OpenAI()  # OPENAI_API_KEY 환경변수 사용


def extract_sql(text: str) -> str:
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return (m.group(1) if m else text).strip()


def generate_sql(question: str) -> str:
    if not MODEL:
        raise RuntimeError(".env 에 FANLOG_MODEL (사용 가능한 모델명)을 설정하세요.")
    resp = _client().chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": question},
        ],
    )
    return extract_sql(resp.choices[0].message.content)


def ask(question: str) -> dict:
    result = {"question": question, "sql": None, "columns": [], "rows": [], "row_count": 0, "error": None}
    raw_sql = generate_sql(question)
    result["sql"] = raw_sql

    if "CANNOT_ANSWER" in raw_sql:
        result["error"] = raw_sql.replace("--", "").strip()
        return result
    try:
        safe_sql = validate_sql(raw_sql)
    except SQLGuardError as e:
        result["error"] = f"[가드레일 차단] {e}"
        return result

    result["sql"] = safe_sql
    try:
        columns, rows = run_query(safe_sql)
    except Exception as e:  # DB 에러(없는 컬럼, 타임아웃 등) -> Day 2 재시도 루프의 입력이 된다
        result["error"] = f"[DB 오류] {str(e).splitlines()[0]}"
        return result
    result.update(columns=columns, rows=rows, row_count=len(rows))
    return result


if __name__ == "__main__":  # 터미널 테스트: python -m app.text2sql "질문"
    out = ask(" ".join(sys.argv[1:]) or "아티스트별 현재 팔로워 수 상위 5명은?")
    print("SQL:\n", out["sql"], "\n")
    print("ERROR:", out["error"]) if out["error"] else print(out["columns"], *out["rows"][:10], sep="\n")