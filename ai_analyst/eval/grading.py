"""채점: 모델이 만든 SQL 의 실행 결과를 정답 SQL 의 실행 결과와 비교한다.

원칙
- 정답은 "정답 SQL 을 실행한 결과"다. 모델이 쓴 SQL 문장이 정답 SQL 과 같은지는 보지 않는다 (같은 답을 내는 SQL 은 여러 가지다).
- 채점 결과에는 행 값을 저장하지 않는다. 행 수와 요약값(해시)만 남긴다. 결과 파일을 git 에 올려도 사용자 ID 같은 값이 새지 않게 하기 위해서다.
- 애매하면 실패 쪽으로 판정한다. 틀린 답을 통과시키는 것이 맞는 답을 떨어뜨리는 것보다 평가를 더 망가뜨린다.
  (그 대가로 "형식만 다른 정답"이 떨어질 수 있다. 통과 방식은 detail 에 남겨 사람이 확인할 수 있게 한다.)
"""
import hashlib
import itertools
import json
import math
from datetime import date, datetime, time
from decimal import Decimal

from app.safety import mask_ids, mask_rows

# 실패 분류 (리포트의 표에 이 이름 그대로 나온다)
FAIL_VALUE = "값 불일치"
FAIL_GUARD = "가드레일 차단"
FAIL_DB = "DB 오류"
FAIL_PARSE = "파싱 실패"
FAIL_FALSE_REFUSAL = "거짓 거절"
FAIL_ANSWERED = "거절해야 하는데 답함"
FAIL_CALL_LIMIT = "호출 상한 초과"
# 아래 셋은 지시에 없던 분류다. 위 일곱 가지에 억지로 넣으면 원인을 잘못 읽게 되어 따로 두었다.
FAIL_LLM = "LLM 오류"                    # API 오류, 출력 상한 소진 등 (SQL 품질과 무관)
FAIL_REFERENCE = "정답 SQL 실행 실패"     # 모델이 아니라 평가셋의 문제
FAIL_OTHER = "기타 오류"
FAILURE_CLASSES = (FAIL_VALUE, FAIL_GUARD, FAIL_DB, FAIL_PARSE, FAIL_FALSE_REFUSAL, FAIL_ANSWERED, FAIL_CALL_LIMIT,
                   FAIL_LLM, FAIL_REFERENCE, FAIL_OTHER)

# ask() 의 error 문자열 머리말 -> 실패 분류 (DESIGN.md 4장의 응답 계약)
ERROR_PREFIXES = (("[가드레일 차단]", FAIL_GUARD), ("[DB 오류]", FAIL_DB), ("[출력 형식 오류]", FAIL_PARSE),
                  ("[거짓 거절]", FAIL_FALSE_REFUSAL), ("[LLM 오류]", FAIL_LLM))

ANSWERED, REFUSED = "answered", "refused"
MAX_PERMUTE_COLUMNS = 6   # 열 순서를 바꿔 가며 맞춰 보는 최대 열 수 (6열이면 720가지)
FLOAT_EPSILON = 1e-9      # 허용 오차가 0 이어도 부동소수점 표현 차이는 같은 값으로 본다


class ReferenceShapeError(ValueError):
    """정답 SQL 의 결과가 문항의 expected_kind 와 맞지 않는다 (예: scalar 인데 여러 행)."""


# ---------- 값 정리 ----------
def normalize_cell(value):
    """DB 드라이버가 준 값을 비교할 수 있는 기본형으로 바꾼다 (Decimal 은 숫자로, 날짜는 ISO 글자로)."""
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return "nan" if math.isnan(value) else value
    if isinstance(value, Decimal):
        return "nan" if value.is_nan() else float(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return str(value)


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def normalize_rows(rows) -> list:
    """행 값을 가린 뒤(사용자 ID 모양 -> [ID]) 기본형으로 바꾼다.

    ask() 는 결과 행의 사용자 ID 를 가려서 돌려준다. 정답 SQL 의 결과도 같은 방식으로 가려야 두 결과를 공평하게 비교할 수 있고,
    요약값(해시)에도 ID 원문이 들어가지 않는다.
    """
    masked, _ = mask_rows(rows or [])
    return [[normalize_cell(c) for c in row] for row in masked]


def _sort_key(row) -> tuple:
    def one(c):
        if c is None:
            return (0, 0.0, "")
        if is_number(c):
            return (1, round(float(c), 6), "")
        return (2, 0.0, str(c))
    return tuple(one(c) for c in row)


def result_digest(columns, rows) -> dict:
    """결과의 요약: 행 수, 열 수, 요약값. 행 값 자체는 담지 않는다. 요약값은 행 순서와 무관하다."""
    norm = normalize_rows(rows)
    lines = sorted(json.dumps(r, ensure_ascii=False) for r in norm)
    digest = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()[:16]
    width = len(columns) if columns else (len(norm[0]) if norm else 0)
    return {"row_count": len(norm), "column_count": width, "sha256_16": digest}


# ---------- 비교 ----------
def numbers_close(generated, reference, tolerance: dict) -> bool:
    """허용 오차 안에서 같은 숫자인가. 오차는 정답 값의 단위로 잰다."""
    abs_tol = float(tolerance.get("abs", 0) or 0)
    rel_tol = float(tolerance.get("rel", 0) or 0)

    def close(x):
        return abs(x - reference) <= max(abs_tol, rel_tol * abs(reference), FLOAT_EPSILON)

    if close(generated):
        return True
    # 비율(0.1642)과 퍼센트(16.42)는 같은 답의 다른 표기다. 문항이 허용할 때만 서로 바꿔서 본다.
    return bool(tolerance.get("accept_percent_or_ratio")) and (close(generated * 100) or close(generated / 100))


def cells_equal(generated, reference, tolerance: dict) -> bool:
    if is_number(generated) and is_number(reference):
        return numbers_close(generated, reference, tolerance)
    if is_number(generated) or is_number(reference):
        return False  # 숫자와 글자("879")는 같은 값으로 보지 않는다 (보수적)
    return generated == reference


def compare_scalar(generated_rows, reference_rows, tolerance: dict) -> tuple:
    """(통과 여부, 설명). 정답은 숫자 하나여야 한다.

    모델의 결과는 정확히 1행이어야 하고, 그 행의 숫자 칸 중 하나가 정답과 같으면 통과다.
    한 행에 (분자, 분모, 비율)을 같이 내는 답이 흔해서 "칸이 정확히 하나"를 요구하지 않았다.
    그 대신 어떻게 통과했는지(single_cell / one_of_cells)를 남겨서, 우연히 다른 칸이 맞은 경우를 사람이 확인할 수 있게 한다.
    """
    ref = normalize_rows(reference_rows)
    if len(ref) != 1 or len(ref[0]) != 1 or not is_number(ref[0][0]):
        raise ReferenceShapeError("scalar 문항의 정답 SQL 은 숫자 한 칸(1행 1열)을 돌려줘야 한다")
    gen = normalize_rows(generated_rows)
    if len(gen) != 1:
        return False, f"행 수가 1이 아님 ({len(gen)}행)"
    numbers = [c for c in gen[0] if is_number(c)]
    if not numbers:
        return False, "숫자 칸이 없음"
    if any(numbers_close(n, ref[0][0], tolerance) for n in numbers):
        return True, "single_cell" if len(gen[0]) == 1 else "one_of_cells"
    return False, "값이 다름"


def _rows_match(gen, ref, tolerance, ordered) -> bool:
    if not ordered:
        gen, ref = sorted(gen, key=_sort_key), sorted(ref, key=_sort_key)
    return all(len(g) == len(r) and all(cells_equal(a, b, tolerance) for a, b in zip(g, r)) for g, r in zip(gen, ref))


def compare_rows(generated_rows, reference_rows, tolerance: dict, ordered: bool = False) -> tuple:
    """(통과 여부, 설명). 행 집합이 같은가. 기본은 순서 무시, ordered=True 면 순서까지 본다.

    열 순서는 모델마다 다를 수 있어서, 같은 열 수일 때 열 순서를 바꿔 가며 맞춰 본다 (6열까지).
    열 이름은 비교하지 않는다 (별칭은 모델마다 다르다). 열 수가 다르면 실패다 (모델이 열을 더 주거나 덜 준 경우).
    """
    gen, ref = normalize_rows(generated_rows), normalize_rows(reference_rows)
    if len(gen) != len(ref):
        return False, f"행 수가 다름 (모델 {len(gen)}행, 정답 {len(ref)}행)"
    if not ref:
        return True, "둘 다 0행"
    width = len(ref[0])
    if any(len(r) != width for r in ref) or any(len(g) != width for g in gen):
        return False, "열 수가 다름"
    if _rows_match(gen, ref, tolerance, ordered):
        return True, "positional"
    if width <= MAX_PERMUTE_COLUMNS:
        for perm in itertools.permutations(range(width)):
            if perm == tuple(range(width)):
                continue
            if _rows_match([[g[i] for i in perm] for g in gen], ref, tolerance, ordered):
                return True, "column_permuted"
    return False, "값이 다름"


# ---------- ask() 결과 분류 ----------
def classify(out: dict) -> str:
    """ask() 의 결과를 answered / refused / 실패 분류 중 하나로 바꾼다."""
    error = out.get("error")
    if not error:
        return ANSWERED if out.get("sql") else FAIL_OTHER
    if error.startswith("CANNOT_ANSWER"):
        return REFUSED
    for prefix, label in ERROR_PREFIXES:
        if error.startswith(prefix):
            return label
    return FAIL_OTHER


def _last_attempt_type(out: dict):
    attempts = out.get("attempts") or []
    return attempts[-1].get("error_type") if attempts else None


def grade(question, out: dict, reference=None, reference_error: str | None = None) -> dict:
    """문항 하나를 채점한다.

    question: eval.questions.Question / out: ask() 의 결과 / reference: 정답 SQL 의 (columns, rows) 또는 None
    reference_error: 정답 SQL 을 실행하지 못했을 때의 짧은 사유 (예외 종류 이름)
    돌려주는 dict 에는 행 값이 없다: 행 수와 요약값만 있다.
    """
    status = classify(out)
    usage = out.get("usage") or {}
    result = {"id": question.id, "split": question.split, "category": question.category,
              "expected_kind": question.expected_kind, "passed": False, "failure": None, "detail": "",
              "generated": None, "reference": None,
              "llm_calls": int(usage.get("llm_calls", 0)), "tokens": int(usage.get("tokens", 0)),
              "attempt_types": [a.get("error_type") for a in (out.get("attempts") or [])],
              # SQL 문장은 행 값이 아니지만 조건에 ID 를 쓴 경우가 있을 수 있어 같은 규칙으로 가린다
              "generated_sql": mask_ids(out["sql"]) if out.get("sql") else None}
    if status == ANSWERED:
        result["generated"] = result_digest(out.get("columns"), out.get("rows"))

    if question.expected_kind == "refusal":
        # DESIGN.md 4장: 거절이 정답인 문항은 "마지막 시도가 refusal 인가"로 채점한다
        if status == REFUSED and _last_attempt_type(out) == "refusal":
            result.update(passed=True, detail="정상 거절")
        elif status == ANSWERED:
            result.update(failure=FAIL_ANSWERED, detail="거절해야 하는 질문에 결과를 내놓음")
        else:
            result.update(failure=status if status in FAILURE_CLASSES else FAIL_OTHER, detail="거절로 끝나지 않음")
        return result

    if status == REFUSED:  # 답할 수 있는 질문을 거절했다 (missing 이 비어서 교정이 걸리지 않은 경우 포함)
        result.update(failure=FAIL_FALSE_REFUSAL, detail="답할 수 있는 질문을 거절함")
        return result
    if status != ANSWERED:
        result.update(failure=status, detail="SQL 실행 결과를 얻지 못함")
        return result
    if reference is None:
        result.update(failure=FAIL_REFERENCE, detail=reference_error or "정답 SQL 결과 없음")
        return result

    ref_columns, ref_rows = reference
    result["reference"] = result_digest(ref_columns, ref_rows)
    try:
        if question.expected_kind == "scalar":
            ok, detail = compare_scalar(out.get("rows"), ref_rows, question.tolerance)
        else:
            ok, detail = compare_rows(out.get("rows"), ref_rows, question.tolerance, question.ordered)
    except ReferenceShapeError as e:
        result.update(failure=FAIL_REFERENCE, detail=str(e))
        return result
    if out.get("truncated") or out.get("row_cap_note"):
        detail += " (결과가 행 수 상한에 닿음: 비교가 불완전할 수 있음)"
    result.update(passed=ok, failure=None if ok else FAIL_VALUE, detail=detail)
    return result


def not_run(question) -> dict:
    """호출 상한 때문에 실행하지 못한 문항의 기록."""
    return {"id": question.id, "split": question.split, "category": question.category,
            "expected_kind": question.expected_kind, "passed": False, "failure": FAIL_CALL_LIMIT,
            "detail": "호출 상한에 닿아 실행하지 않음", "generated": None, "reference": None,
            "llm_calls": 0, "tokens": 0, "attempt_types": [], "generated_sql": None}
