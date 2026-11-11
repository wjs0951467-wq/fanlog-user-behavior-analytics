"""에이전트가 부를 수 있는 도구 모음.

도구 하나는 dict 로 정의한다.
  spec             : 모델에게 보여주는 설명과 인자 형식 (OpenAI function calling 형식)
  run(args)        : 실제 실행 함수. 인자 값 검증도 여기서 한다 (모델이 준 값을 믿지 않는다)
  llm_cost         : 이 도구가 내부에서 쓸 수 있는 LLM 호출의 최대치 (예산 계산용)
  max_per_question : 질문 1개에서 이 도구를 부를 수 있는 횟수

run 의 반환값 (모든 도구 공통)
  status  : "ok" | "error" | "refusal" | "hold"
  for_llm : 모델에게 돌려줄 요약 (작게 자른다)
  for_ui  : 화면이 그릴 전체 결과 (표와 숫자는 모델을 거치지 않고 여기서 바로 그린다)
  usage   : {"llm_calls", "tokens"} 이 도구가 내부에서 쓴 LLM 사용량
"""
from .text2sql import MAX_SQL_CALLS, ask

MAX_QUESTION_CHARS = 300
ROWS_FOR_LLM = 20      # 모델에게는 상위 20행만 준다. 전체 표는 화면이 for_ui 로 그린다
CELL_CHARS_FOR_LLM = 200  # 긴 문자열 칸은 자른다 (토큰 절약 + 데이터 안에 숨은 지시문이 통째로 들어가는 것 방지)
NO_USAGE = {"llm_calls": 0, "tokens": 0}

# 모든 도구가 공통으로 받는 인자. 설계서의 "어떤 도구를, 왜, 무슨 인자로"에서 "왜"를 기록하기 위한 것이다.
REASON_PARAM = {"type": "string", "description": "이 도구를 왜 부르는지 한국어 한 문장"}


def error_result(message: str, **extra) -> dict:
    """도구가 실행되지 못했을 때의 결과. 예외를 던지지 않고 모델에게 이유를 돌려줘 스스로 고치게 한다."""
    return {"status": "error", "for_llm": {"error": message, **extra}, "for_ui": {"error": message, **extra},
            "usage": dict(NO_USAGE)}


def sanitize_error(error: str | None) -> str | None:
    """모델, 화면, 로그에 내보내도 되는 에러 문장으로 바꾼다.

    - LLM 오류: OpenAI 의 인증 오류 메시지에는 API 키 일부가 들어 있을 수 있다.
    - DB 접속/인증 오류: 호스트나 계정 이름이 들어 있을 수 있고, SQL 잘못이 아니라 모델이 알 필요도 없다.
    SQL 잘못으로 재시도 끝에 실패한 경우("...회 시도 후 실패")와 거절 사유는 그대로 둔다.
    """
    if not error:
        return error
    if error.startswith("[LLM 오류]"):
        return "[LLM 오류] LLM 호출에 실패했습니다."
    if error.startswith("[DB 오류]") and "시도 후 실패" not in error:
        return "[DB 오류] 데이터베이스 접속 문제로 실행하지 못했습니다."
    return error


def _trim_rows(rows: list) -> list:
    """모델에게 보낼 행: 상위 20행, 문자열 칸은 200자까지."""
    def cell(v):
        if isinstance(v, (int, float, bool)) or v is None:
            return v
        text = str(v)  # Decimal, date 등은 문자열로
        return text if len(text) <= CELL_CHARS_FOR_LLM else text[:CELL_CHARS_FOR_LLM] + "...(잘림)"
    return [[cell(v) for v in row] for row in rows[:ROWS_FOR_LLM]]


# ---------- ask_data ----------
def run_ask_data(args: dict) -> dict:
    """자연어 질문을 검증된 ask() 파이프라인에 넘긴다.

    에이전트가 SQL 을 직접 쓰지 않고 ask() 를 도구로 재사용하는 이유:
    가드레일(SELECT 전용, 허용 테이블)과 읽기 전용 계정을 우회할 길을 만들지 않기 위해서다.
    """
    question = args.get("question")
    if not isinstance(question, str) or not question.strip():
        return error_result("question 은 비어 있지 않은 문자열이어야 합니다.")
    if len(question) > MAX_QUESTION_CHARS:
        return error_result(f"question 은 {MAX_QUESTION_CHARS}자 이하여야 합니다.")

    # 요약은 끈다: 최종 문장은 에이전트가 쓰므로 요약 호출 1회가 중복이다.
    out = ask(question.strip(), summarize_result=False)
    out["error"] = sanitize_error(out["error"])
    status = "ok" if not out["error"] else "refusal" if out["error"].startswith("CANNOT_ANSWER") else "error"
    for_llm = {
        "sql": out["sql"], "columns": out["columns"], "row_count": out["row_count"],
        "rows": _trim_rows(out["rows"]),
        "rows_shown": min(out["row_count"], ROWS_FOR_LLM),
        "assumptions": out["assumptions"], "error": out["error"],
        # attempts(실패한 SQL 과 에러 원문)는 모델에게 주지 않는다. 화면과 로그에서만 본다.
    }
    return {"status": status, "for_llm": for_llm, "for_ui": out, "usage": out["usage"]}


ASK_DATA = {
    "spec": {"type": "function", "function": {
        "name": "ask_data",
        "description": ("FANLOG DB 에 대한 지표/집계 질문을 SQL 로 계산해 답한다. "
                        "예: 가입자 수, 구매 건수, 전환율, 현재 휴면/이탈 위험(at_risk 상태)/활동 중인 팬 수. "
                        "질문은 한국어 한 문장으로, 한 번에 하나의 지표만 묻는다."),
        "parameters": {"type": "object", "additionalProperties": False,
                       "properties": {"question": {"type": "string", "description": "DB 에 물을 한국어 질문"},
                                      "reason": REASON_PARAM},
                       "required": ["question", "reason"]}}},
    "run": run_ask_data,
    "llm_cost": MAX_SQL_CALLS,  # 요약을 껐으므로 SQL 생성 3회가 최대
    "max_per_question": 2,
}

TOOLS = {"ask_data": ASK_DATA}
