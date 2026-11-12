"""자연어 질문 -> SQL 생성 -> 검증 -> 실행 -> (실패하면 에러를 돌려주고 재시도) -> 요약.

흐름: ask()
  1) complete()      : LLM 이 JSON {"sql", "assumptions"} 또는 거절 {"cannot_answer", "missing"} 을 만든다
  2) validate_sql()  : 가드레일
  3) run_query()     : 읽기 전용 DB 실행
  4) 실패하면 "이전 SQL + 에러 원문"을 대화에 덧붙여 다시 1)로 (SQL 호출은 최대 3회)
  5) summarize()     : 결과를 한국어 2~3문장으로 요약 (별도 호출 1회)
질문 1개당 LLM 호출은 최대 4회(SQL 3 + 요약 1)다.
"""
import json
import re
import sys
from functools import lru_cache
from pathlib import Path

from .db import run_query
from .llm import complete
from .sql_guard import ALLOWED_TABLES, SQLGuardError, validate_sql

ROOT = Path(__file__).resolve().parent.parent
MAX_SQL_CALLS = 3      # SQL 생성 호출 상한. 요약 1회를 더해 질문당 최대 4회
SUMMARY_ROWS = 20      # 요약 모델에게 보여줄 행 수 (토큰 절약)
ERROR_TEXT_LIMIT = 500  # 모델에게 돌려주는 에러 원문 길이 상한

NO_ASSUMPTION_NOTE = "모델이 가정을 반환하지 않음 (JSON 형식이 아니라 SQL 블록에서 추출함)"
NO_DATA_SUMMARY = "조건에 해당하는 데이터가 없습니다."

SYSTEM_RULES = """You are a PostgreSQL analyst for FANLOG, a K-entertainment fan platform.
Convert the user's question (usually Korean) into ONE read-only PostgreSQL query.

Output format:
- Respond with a single JSON object and nothing else (no markdown, no code fence).
- If you can answer:
  {"sql": "<one PostgreSQL SELECT query>", "assumptions": ["<계산 기준, 한국어>", ...]}
- If you truly cannot answer:
  {"sql": null, "cannot_answer": "<short reason in Korean>", "missing": ["<table>" or "<table>.<column>", ...]}
  "missing" lists the exact table or column names you needed but could not find.

Rules:
- SELECT only. Use only the tables/views listed under AVAILABLE TABLES. Do not qualify with a schema name.
- Follow the SEMANTIC LAYER definitions and conventions strictly; they override your own assumptions.
- Use only column values that appear in the schema profile (e.g. for status columns).
- For date logic use the *_kst columns, never *_utc.
- Always add a sensible ORDER BY and LIMIT for list-type results.
- "assumptions": 1 to 3 short Korean sentences stating the calculation basis the reader must know
  (e.g. whether deleted users are excluded, which date is used as "today").
- For questions about user activity status (active / at_risk / dormant), exclude deleted users
  (dim_user.is_deleted IS NOT TRUE) by default and say so in "assumptions".
- cannot_answer is a last resort. Before using it, re-check AVAILABLE TABLES and the schema profile.
  Use it only when a required table or column truly does not appear there.
"""

SUMMARY_RULES = """You explain a SQL query result to a FANLOG operations manager who does not know SQL.
The user message is a JSON object with: question, assumptions, columns, row_count, rows (top rows only).
Write 2-3 sentences in Korean, plain text.
- Use only numbers that appear in the input. Do not calculate or invent new numbers.
- Do not assert causes. Describe only what the data shows.
- If row_count is larger than the number of rows shown, say that only the top rows were considered.
"""


# ---------- 프롬프트 만들기 ----------
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
def load_profile() -> dict:
    """schema_profile.json 을 읽는다. 프롬프트 생성과 거짓 거절 판별이 같은 사실을 보도록 한 곳에서 읽는다."""
    profile_path = ROOT / "semantic" / "schema_profile.json"
    if not profile_path.exists():
        raise RuntimeError("semantic/schema_profile.json 이 없습니다. 먼저 `python -m scripts.profile_db` 를 실행하세요.")
    return json.loads(profile_path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def build_system_prompt() -> str:
    # 시스템 프롬프트는 질문/재시도와 무관하게 항상 똑같은 문자열이다.
    # 재시도 때도 앞부분이 동일하므로 OpenAI 의 자동 프롬프트 캐싱이 적용되어 비용이 줄어든다.
    profile = load_profile()
    semantic = (ROOT / "semantic" / "semantic_layer.yaml").read_text(encoding="utf-8")

    available = [t for t in profile if t in ALLOWED_TABLES]
    missing = sorted(ALLOWED_TABLES - set(available))
    if missing:  # 프로파일에 없는 테이블이 있으면 조용히 넘어가지 않고 바로 알려준다
        raise RuntimeError(f"schema_profile.json 에 없는 테이블/뷰: {missing}. profile_db 를 다시 실행하세요.")

    return (f"{SYSTEM_RULES}\nAVAILABLE TABLES: {', '.join(available)}\n\n"
            f"=== SCHEMA PROFILE ===\n{render_schema(profile)}\n"
            f"=== SEMANTIC LAYER ===\n{semantic}")


# ---------- LLM 출력 해석 ----------
def _as_str_list(value) -> list[str]:
    """모델이 목록 대신 문자열 하나를 주거나 이상한 타입을 줘도 문자열 목록으로 맞춘다."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def parse_llm_output(text: str) -> dict:
    """LLM 응답을 {sql, assumptions, cannot_answer, missing} 으로 바꾼다.

    1순위는 JSON. JSON 이 아니면 예전 방식(```sql 블록)으로 SQL 만이라도 건진다(fallback).
    둘 다 실패하면 sql 이 None 이고, ask() 가 이를 parse 오류로 보고 재시도한다.
    """
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("JSON 객체가 아님")
    except ValueError:  # json.JSONDecodeError 도 ValueError 의 하위 클래스다
        m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
        sql = m.group(1).strip() if m else None
        return {"sql": sql or None,
                # SQL 은 건졌지만 가정은 알 수 없다. 조용히 비워 두지 않고 그 사실을 사용자에게 보여준다.
                "assumptions": [NO_ASSUMPTION_NOTE] if sql else [],
                "cannot_answer": None, "missing": []}

    sql = data.get("sql")
    reason = data.get("cannot_answer")
    return {"sql": sql.strip() if isinstance(sql, str) and sql.strip() else None,
            "assumptions": _as_str_list(data.get("assumptions")),
            "cannot_answer": str(reason).strip() if reason else None,
            "missing": _as_str_list(data.get("missing"))}


def find_existing(missing: list[str], profile: dict) -> list[str]:
    """모델이 "없다"고 한 이름 중 실제로는 존재하는 것을 돌려준다. 하나라도 있으면 거짓 거절이다.

    이름 형식은 "테이블" 또는 "테이블.컬럼". 허용 테이블 15개의 프로파일하고만 대조한다.
    (프로파일에는 meta_generation_run 도 있지만 허용 테이블이 아니므로 "없는 것"으로 본다.
     이것을 "있다"고 판정하면 재시도가 가드레일에 막힐 뿐이다.)
    """
    existing = []
    for name in missing:
        name = name.strip().lower().removeprefix("public.")
        table, _, column = name.partition(".")
        if table not in ALLOWED_TABLES or table not in profile:
            continue
        if not column or column in profile[table]["columns"]:
            existing.append(name)
    return existing


def _describe_existing(existing: list[str], profile: dict) -> str:
    """거짓 거절 재시도 때 모델에게 보여줄 근거. 테이블이면 컬럼 목록까지 알려줘야 바로 SQL 을 쓸 수 있다."""
    lines = []
    for name in existing:
        table, _, column = name.partition(".")
        if column:
            lines.append(f"- column {name} exists")
        else:
            lines.append(f"- table/view {table} exists (columns: {', '.join(profile[table]['columns'])})")
    return "\n".join(lines)


# ---------- 재시도 ----------
def is_retryable_db_error(e: Exception) -> bool:
    """SQL 을 고치면 해결되는 DB 오류인가.

    PostgreSQL 오류 코드(SQLSTATE) 앞 두 자리로 구분한다.
      42xxx = 문법 오류, 없는 테이블/컬럼   22xxx = 데이터 오류(0으로 나누기, 형 변환 등)   57014 = 타임아웃
    그 외(08xxx 접속 실패, 28xxx 인증 실패, 코드 없음 등)는 SQL 잘못이 아니므로
    모델에게 다시 물어봐도 호출만 낭비한다.
    """
    orig = getattr(e, "orig", None)  # SQLAlchemy 가 감싼 원래 드라이버 예외
    code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    return bool(code) and (code[:2] in ("42", "22") or code == "57014")


def db_error_text(e: Exception) -> str:
    """모델에게 돌려줄 DB 에러 원문.

    SQLAlchemy 의 str(e) 에는 SQL 전문과 안내 링크가 붙어 길어지므로 드라이버 원문(e.orig)만 쓴다.
    첫 줄만 자르지 않는 이유: PostgreSQL 의 HINT 줄("Perhaps you meant ...")이 수정에 가장 도움이 된다.
    """
    return str(getattr(e, "orig", None) or e).strip()[:ERROR_TEXT_LIMIT]


# ---------- 밖으로 내보내는 에러 문장 ----------
# 응답(/ask, CLI, 에이전트, 화면, 로그)에 에러 원문을 그대로 싣지 않는다.
# - OpenAI 의 인증 오류 메시지에는 API 키 일부가 들어 있을 수 있다.
# - DB 접속/인증 오류 메시지에는 호스트나 계정 이름이 들어 있을 수 있다.
# 이 두 가지는 여기 한 곳에서만 만들고, agent.py 와 tools.py 도 이것을 가져다 쓴다.
DB_CONNECTION_ERROR = "[DB 오류] 데이터베이스 접속 문제로 실행하지 못했습니다."


def llm_error_text(e: Exception) -> str:
    """LLM 호출 실패는 예외의 종류 이름만 알린다 (예: AuthenticationError, RateLimitError)."""
    return f"[LLM 오류] {type(e).__name__}"


def build_retry_message(error_type: str, sql: str | None, error_text: str) -> str:
    """재시도 때 대화에 덧붙이는 user 메시지: 이전 SQL + 에러 원문 + 같은 실수 반복 금지."""
    return (f"Your previous answer failed ({error_type}).\n"
            f"Previous SQL:\n{sql or '(none)'}\n\n"
            f"Error:\n{error_text}\n\n"
            "Fix the cause of this error and do not repeat the same mistake. "
            "Respond again with a single JSON object in the same format.")


def _call_llm(result: dict, system: str, messages: list[dict], json_mode: bool) -> str:
    """complete() 를 부르고 호출 수/토큰 수를 result["usage"] 에 누적한다 (공용 크레딧 관리용)."""
    result["usage"]["llm_calls"] += 1  # 호출이 실패해도 시도한 것은 센다
    reply = complete(system, messages, json_mode=json_mode)
    result["usage"]["tokens"] += reply["tokens"]
    return reply["text"]


# ---------- 요약 ----------
def summarize(result: dict) -> str | None:
    """실행 결과를 한국어 2~3문장으로 요약한다. 실패해도 답변 전체를 실패시키지 않고 None 을 돌려준다."""
    payload = json.dumps({
        "question": result["question"],
        "assumptions": result["assumptions"],
        "columns": result["columns"],
        "row_count": result["row_count"],  # 상위 20행만 보고 "총 20건"이라고 쓰지 않게 전체 행 수를 함께 준다
        "rows": result["rows"][:SUMMARY_ROWS],
    }, ensure_ascii=False, default=str)  # Decimal/date 는 문자열로
    try:
        text = _call_llm(result, SUMMARY_RULES, [{"role": "user", "content": payload}], json_mode=False)
    except Exception:  # 숫자(SQL 결과)는 이미 확보했으므로 요약 실패는 치명적이지 않다
        return None
    return text.strip() or None


# ---------- 파이프라인 ----------
def ask(question: str, summarize_result: bool = True) -> dict:
    """질문 하나를 처리해 응답 계약(DESIGN.md 4장) 형식의 dict 를 돌려준다.

    summarize_result=False 면 요약 호출을 생략한다 (평가처럼 숫자만 필요할 때 호출을 아끼기 위해).
    """
    result = {"question": question, "sql": None, "columns": [], "rows": [], "row_count": 0,
              "assumptions": [], "summary": None, "attempts": [], "error": None,
              "truncated": False,  # run_query 가 상한에서 행을 잘랐는가 (가드레일의 LIMIT 과 별개인 2차 안전장치)
              "usage": {"llm_calls": 0, "tokens": 0}}
    system = build_system_prompt()
    profile = load_profile()
    # 재시도할 때마다 [이전 응답, 에러 피드백]을 뒤에 덧붙인다.
    # 이력을 누적해야 3번째 시도가 1번째 시도의 실수로 되돌아가지 않는다.
    messages = [{"role": "user", "content": question}]
    refusal_retried = False  # 거짓 거절 교정은 질문당 1회만

    for _ in range(MAX_SQL_CALLS):
        try:
            reply = _call_llm(result, system, messages, json_mode=True)
        except Exception as e:  # API 오류(인증, 한도 등)는 SQL 문제가 아니므로 재시도하지 않는다
            result["error"] = llm_error_text(e)
            return result

        parsed = parse_llm_output(reply)
        attempt = {"sql": parsed["sql"], "error_type": "none", "error_message": None}
        result["attempts"].append(attempt)

        if parsed["cannot_answer"]:
            existing = find_existing(parsed["missing"], profile)
            if not existing or refusal_retried:
                # 정상 거절: 없다고 한 이름이 정말 없거나, 이미 한 번 교정했는데도 다시 거절한 경우
                attempt.update(error_type="refusal", error_message=parsed["cannot_answer"])
                result["error"] = f"CANNOT_ANSWER: {parsed['cannot_answer']}"
                return result
            refusal_retried = True
            label = "거짓 거절"
            attempt.update(error_type="false_refusal", error_message=(
                f"You said these are missing, but they DO exist in the schema profile:\n"
                f"{_describe_existing(existing, profile)}\n"
                f"Re-check the schema profile and answer with SQL."))
        elif not parsed["sql"]:
            label = "출력 형식 오류"
            attempt.update(error_type="parse", error_message=(
                "Could not find SQL in your answer. It must be a JSON object with a non-empty \"sql\" string."))
        else:
            try:
                safe_sql = validate_sql(parsed["sql"])
            except SQLGuardError as e:
                label = "가드레일 차단"
                attempt.update(error_type="guard", error_message=str(e))
            else:
                try:
                    columns, rows = run_query(safe_sql)
                except Exception as e:
                    label = "DB 오류"
                    if not is_retryable_db_error(e):
                        # 접속/인증 오류 등: 에러 원문을 모델에게도, 응답(error, attempts)에도 싣지 않고 즉시 중단한다
                        attempt.update(error_type="db", error_message=DB_CONNECTION_ERROR)
                        result["error"] = DB_CONNECTION_ERROR
                        return result
                    attempt.update(error_type="db", error_message=db_error_text(e))
                else:
                    # 성공. 0행도 성공이다: 재시도하면 모델이 조건을 억지로 바꿔 "틀린 답"을 만들 수 있다.
                    result.update(sql=safe_sql, columns=columns, rows=rows, row_count=len(rows),
                                  assumptions=parsed["assumptions"],
                                  truncated=bool(getattr(rows, "truncated", False)))
                    if not rows:
                        result["summary"] = NO_DATA_SUMMARY  # LLM 을 부르지 않는다 (호출 절약, 숫자 지어낼 여지 없음)
                    elif summarize_result:
                        result["summary"] = summarize(result)
                    return result

        # 여기까지 왔으면 재시도 대상 실패다. 이전 응답과 에러를 대화에 덧붙인다.
        messages.append({"role": "assistant", "content": reply})
        messages.append({"role": "user", "content": build_retry_message(
            attempt["error_type"], parsed["sql"], attempt["error_message"])})

    result["error"] = f"[{label}] {MAX_SQL_CALLS}회 시도 후 실패: {attempt['error_message'].splitlines()[0]}"
    return result


if __name__ == "__main__":  # 터미널 테스트: python -m app.text2sql "질문"
    out = ask(" ".join(sys.argv[1:]) or "아티스트별 현재 팔로워 수 상위 5명은?")
    for i, a in enumerate(out["attempts"], 1):
        if a["error_type"] != "none":
            print(f"[시도 {i} 실패: {a['error_type']}] {a['error_message']}\n  SQL: {a['sql']}\n")
    print("SQL:\n", out["sql"], "\n")
    if out["error"]:
        print("ERROR:", out["error"])
    else:
        print(out["columns"], *out["rows"][:10], sep="\n")
        print("\n가정:", *out["assumptions"], sep="\n- ")
        print("\n요약:", out["summary"])
    print("\n사용량:", out["usage"])
