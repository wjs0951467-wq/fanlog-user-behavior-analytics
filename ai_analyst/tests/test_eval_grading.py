"""eval/grading.py 테스트: 값 비교, 실패 분류, 결과에 행 값이 남지 않는 것."""
import json
from datetime import date
from decimal import Decimal

import pytest

from eval import grading as G
from eval.questions import Question


def q(kind="scalar", **over):
    base = dict(id="X01", question="질문", category="단순 집계", split="heldout", expected_kind=kind, source="test",
                verified=True, reference_sql=None if kind == "refusal" else "SELECT 1", tolerance={})
    base.update(over)
    return Question(**base)


def answered(rows, columns=("n",), **over):
    out = {"question": "질문", "sql": "SELECT 1 LIMIT 1000", "columns": list(columns), "rows": rows, "row_count": len(rows),
           "attempts": [{"sql": "SELECT 1", "error_type": "none", "error_message": None}], "error": None,
           "truncated": False, "row_cap_note": None, "usage": {"llm_calls": 1, "tokens": 50}}
    out.update(over)
    return out


def failed(error, last_type, calls=3):
    return {"question": "질문", "sql": None, "columns": [], "rows": [], "row_count": 0,
            "attempts": [{"sql": None, "error_type": last_type, "error_message": "x"}], "error": error,
            "usage": {"llm_calls": calls, "tokens": 10}}


def ref(rows, columns=("n",)):
    return list(columns), rows


# ---------- scalar ----------
def test_scalar_exact_match_passes():
    r = G.grade(q(), answered([[879]]), ref([[879]]))
    assert r["passed"] is True and r["failure"] is None and r["detail"] == "single_cell"


def test_scalar_decimal_and_float_are_the_same_number():
    assert G.grade(q(), answered([[Decimal("879")]]), ref([[879.0]]))["passed"]


def test_scalar_mismatch_is_a_value_failure():
    r = G.grade(q(), answered([[880]]), ref([[879]]))
    assert r["passed"] is False and r["failure"] == G.FAIL_VALUE


@pytest.mark.parametrize("value, tol, ok", [
    (0.1643, {"abs": 0.0001}, True), (0.1644, {"abs": 0.0001}, False),
    (101, {"rel": 0.01}, True), (102, {"rel": 0.01}, False),
    (16.42, {"abs": 0.0001, "accept_percent_or_ratio": True}, True),   # 퍼센트로 답함
    (16.42, {"abs": 0.0001}, False),                                    # 문항이 허용하지 않으면 다른 값
])
def test_scalar_tolerance(value, tol, ok):
    reference = 0.1642 if value < 50 else 100
    assert G.grade(q(tolerance=tol), answered([[value]]), ref([[reference]]))["passed"] is ok


def test_ratio_answer_matches_a_percent_reference_when_allowed():
    assert G.grade(q(tolerance={"abs": 0.01, "accept_percent_or_ratio": True}), answered([[0.1642]]), ref([[16.42]]))["passed"]


def test_scalar_in_a_row_with_numerator_and_denominator_passes_and_says_how():
    r = G.grade(q(tolerance={"abs": 0.0001}), answered([[791, 4817, 0.1642]], columns=("a", "b", "rate")), ref([[0.1642]]))
    assert r["passed"] and r["detail"] == "one_of_cells"


@pytest.mark.parametrize("rows, word", [([], "행 수"), ([[1], [2]], "행 수"), ([["많음"]], "숫자 칸"), ([[None]], "숫자 칸"),
                                        ([[True]], "숫자 칸"), ([["879"]], "숫자 칸")])
def test_scalar_wrong_shapes_fail(rows, word):
    r = G.grade(q(), answered(rows), ref([[879]]))
    assert r["passed"] is False and r["failure"] == G.FAIL_VALUE and word in r["detail"]


@pytest.mark.parametrize("bad_ref", [[], [[1], [2]], [[1, 2]], [["글자"]], [[None]]])
def test_scalar_reference_with_a_wrong_shape_is_an_eval_set_problem(bad_ref):
    r = G.grade(q(), answered([[1]]), ref(bad_ref))
    assert r["passed"] is False and r["failure"] == G.FAIL_REFERENCE


# ---------- rows ----------
ROWS = [["search", 0.172], ["direct", 0.166], ["social", 0.164]]


def test_rows_same_set_in_another_order_passes():
    r = G.grade(q("rows"), answered(list(reversed(ROWS))), ref(ROWS))
    assert r["passed"] and r["detail"] == "positional"


def test_rows_order_matters_only_when_the_question_asks_for_it():
    ordered = q("rows", ordered=True)
    assert G.grade(ordered, answered(ROWS), ref(ROWS))["passed"]
    r = G.grade(ordered, answered(list(reversed(ROWS))), ref(ROWS))
    assert r["passed"] is False and r["failure"] == G.FAIL_VALUE


def test_rows_with_swapped_columns_pass_and_say_so():
    swapped = [[v, name] for name, v in ROWS]
    r = G.grade(q("rows"), answered(swapped), ref(ROWS))
    assert r["passed"] and r["detail"] == "column_permuted"


def test_rows_numeric_tolerance_and_percent():
    close = [["search", 0.1721], ["direct", 0.1661], ["social", 0.1641]]
    assert G.grade(q("rows", tolerance={"abs": 0.001}), answered(close), ref(ROWS))["passed"]
    assert not G.grade(q("rows"), answered(close), ref(ROWS))["passed"]
    percent = [["search", 17.2], ["direct", 16.6], ["social", 16.4]]
    assert G.grade(q("rows", tolerance={"abs": 0.001, "accept_percent_or_ratio": True}), answered(percent), ref(ROWS))["passed"]


@pytest.mark.parametrize("rows, word", [
    (ROWS[:2], "행 수"),
    ([r + [1] for r in ROWS], "열 수"),
    ([["search", 0.172], ["direct", 0.166], ["push", 0.164]], "값이 다름"),
    ([["search", 0.172], ["direct", 0.166], ["direct", 0.166]], "값이 다름"),   # 중복 행으로 개수만 맞춘 경우
])
def test_rows_mismatches_fail(rows, word):
    r = G.grade(q("rows"), answered(rows), ref(ROWS))
    assert r["passed"] is False and r["failure"] == G.FAIL_VALUE and word in r["detail"]


def test_rows_both_empty_pass_and_dates_and_nulls_compare():
    assert G.grade(q("rows"), answered([]), ref([]))["passed"]
    a = [[date(2026, 1, 1), None, 3]]
    assert G.grade(q("rows"), answered(a), ref([[date(2026, 1, 1), None, 3]]))["passed"]
    assert not G.grade(q("rows"), answered(a), ref([[date(2026, 1, 2), None, 3]]))["passed"]


def test_user_ids_are_masked_on_both_sides_before_comparing():
    """ask() 는 결과의 사용자 ID 를 [ID] 로 가려서 준다. 정답 쪽도 같은 방식으로 가려야 비교가 공평하다."""
    generated = answered([["[ID]", 3]])          # ask() 가 이미 가린 결과
    reference = ref([["user_000123", 3]])         # 정답 SQL 을 직접 실행한 결과
    assert G.grade(q("rows"), generated, reference)["passed"]


# ---------- 거절 문항 ----------
def test_refusal_question_passes_only_when_the_last_attempt_is_a_refusal():
    r = G.grade(q("refusal"), failed("CANNOT_ANSWER: 성별 컬럼이 없음", "refusal", calls=1))
    assert r["passed"] is True and r["failure"] is None


def test_refusal_question_fails_when_the_model_answers_with_numbers():
    r = G.grade(q("refusal"), answered([[42]]))
    assert r["passed"] is False and r["failure"] == G.FAIL_ANSWERED


@pytest.mark.parametrize("error, last, expected", [
    ("[거짓 거절] 1회 시도 후 실패: x", "false_refusal", G.FAIL_FALSE_REFUSAL),
    ("[가드레일 차단] 3회 시도 후 실패: x", "guard", G.FAIL_GUARD),
    ("[LLM 오류] RateLimitError", None, G.FAIL_LLM),
])
def test_refusal_question_other_endings_fail_with_their_class(error, last, expected):
    r = G.grade(q("refusal"), failed(error, last))
    assert r["passed"] is False and r["failure"] == expected


# ---------- 답해야 하는 문항의 실패 분류 ----------
@pytest.mark.parametrize("error, last, expected", [
    ("[가드레일 차단] 3회 시도 후 실패: 허용되지 않는 테이블", "guard", G.FAIL_GUARD),
    ("[DB 오류] 3회 시도 후 실패: column x does not exist", "db", G.FAIL_DB),
    ("[DB 오류] 데이터베이스 접속 문제로 실행하지 못했습니다.", "db", G.FAIL_DB),
    ("[출력 형식 오류] 3회 시도 후 실패: Could not find SQL", "parse", G.FAIL_PARSE),
    ("[거짓 거절] 1회 시도 후 실패: You said", "false_refusal", G.FAIL_FALSE_REFUSAL),
    ("CANNOT_ANSWER: 테이블이 없음", "refusal", G.FAIL_FALSE_REFUSAL),
    ("[LLM 오류] BadRequestError (param=reasoning_effort)", None, G.FAIL_LLM),
    ("[LLM 오류] 출력 상한 초과 (추론 토큰이 상한을 소진했을 수 있음)", None, G.FAIL_LLM),
    ("알 수 없는 오류", None, G.FAIL_OTHER),
])
def test_failure_classes_for_answerable_questions(error, last, expected):
    r = G.grade(q(), failed(error, last), ref([[1]]))
    assert r["passed"] is False and r["failure"] == expected
    assert r["failure"] in G.FAILURE_CLASSES


def test_missing_reference_result_is_reported_as_an_eval_set_problem():
    r = G.grade(q(), answered([[1]]), None, reference_error="SQLGuardError")
    assert r["failure"] == G.FAIL_REFERENCE and "SQLGuardError" in r["detail"]


def test_not_run_is_the_call_limit_class():
    r = G.not_run(q())
    assert r["passed"] is False and r["failure"] == G.FAIL_CALL_LIMIT and r["llm_calls"] == 0


def test_seven_required_failure_classes_exist():
    for name in ("값 불일치", "가드레일 차단", "DB 오류", "파싱 실패", "거짓 거절", "거절해야 하는데 답함", "호출 상한 초과"):
        assert name in G.FAILURE_CLASSES


# ---------- 결과에 행 값이 남지 않는다 ----------
def test_graded_result_contains_no_row_values():
    generated = answered([["user_000123", "비밀이름", 12345.678]], columns=("id", "name", "v"),
                         sql="SELECT 1 WHERE user_id = 'user_000999' LIMIT 1000")
    reference = ref([["user_000123", "비밀이름", 12345.678]], columns=("id", "name", "v"))
    r = G.grade(q("rows"), generated, reference)
    text = json.dumps(r, ensure_ascii=False)
    assert r["passed"]
    for secret in ("user_000123", "user_000999", "비밀이름", "12345.678"):
        assert secret not in text
    assert r["generated"]["row_count"] == 1 and r["generated"]["column_count"] == 3
    assert len(r["generated"]["sha256_16"]) == 16 and r["generated"] == r["reference"]


def test_digest_ignores_row_order_and_changes_with_values():
    a = G.result_digest(["n"], [[1], [2]])
    assert a == G.result_digest(["n"], [[2], [1]])
    assert a["sha256_16"] != G.result_digest(["n"], [[1], [3]])["sha256_16"]
    assert G.result_digest([], []) == {"row_count": 0, "column_count": 0, "sha256_16": G.result_digest(None, None)["sha256_16"]}


def test_digest_is_taken_after_masking():
    assert G.result_digest(["id"], [["user_000123"]]) == G.result_digest(["id"], [["user_000456"]])  # 둘 다 [ID]


def test_usage_and_attempts_are_carried_over():
    out = answered([[1]], usage={"llm_calls": 2, "tokens": 77})
    out["attempts"] = [{"error_type": "guard"}, {"error_type": "none"}]
    r = G.grade(q(), out, ref([[1]]))
    assert r["llm_calls"] == 2 and r["tokens"] == 77 and r["attempt_types"] == ["guard", "none"]


def test_row_cap_is_noted():
    r = G.grade(q("rows"), answered(ROWS, row_cap_note="결과가 정확히 1000행이라 더 있을 수 있음"), ref(ROWS))
    assert r["passed"] and "상한" in r["detail"]
