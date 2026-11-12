"""숫자 점검(app/numcheck.py) 테스트. 경고 전용 도구라서 "무엇을 잡고 무엇을 못 잡는지"를 테스트로 문서화한다.

분류 기준: 틀린 답을 통과시키면 "못 잡는 경우", 정상 답에 경고가 붙으면 "거짓 경보".

묶음:
  1) 허용 변환: 같은 숫자의 다른 표기는 통과시킨다 (정의 숫자는 변환 없이 있는 그대로만 통과)
  2) 못 잡는 경우 (놓침): 틀린 답인데 경고가 없다 -> 그래서 이 점검은 차단 수단이 아니다
  3) 거짓 경보: 정상 답인데 경고가 뜬다 -> 그래서 경고만 하고 답을 고치거나 재시도하지 않는다
"""
import pytest

from app import numcheck
from app.numcheck import extract_numbers, known_numbers, unverified_numbers


# ---------- 숫자 뽑기 ----------
@pytest.mark.parametrize("text, expected", [
    ("1,643명", ["1,643"]),
    ("16.42%", ["16.42"]),
    ("1,643, 그리고 7.5%.", ["1,643", "7.5"]),   # 문장 부호로 쓴 쉼표는 숫자에 붙이지 않는다
    ("14일, 30일", ["14", "30"]),
    ("숫자 없음", []),
    ("", []),
    (None, []),
])
def test_extract_numbers(text, expected):
    assert extract_numbers(text) == expected


def test_known_numbers_walks_nested_results_and_keys():
    source = {"rows": [[1643, "abc 75명"], [0.1642]], "meta": {"ok": True, "none": None, "120": "x"}}
    assert known_numbers(source) == {1643.0, 75.0, 0.1642, 120.0}  # bool 과 None 은 숫자로 세지 않는다


# ---------- 1) 허용 변환 ----------
def test_exact_numbers_in_tool_results_pass():
    assert unverified_numbers("활동 중인 팬은 1,643명입니다.", [{"rows": [[1643]]}]) == []


def test_comma_removal():
    assert unverified_numbers("1,643명과 12,345건", ["1643 그리고 12345"]) == []


@pytest.mark.parametrize("source, answer", [
    ({"ratio": 0.1642}, "비율은 16.42% 입니다"),   # 비율 -> 퍼센트
    ({"pct": 16.42}, "비율은 0.1642 입니다"),       # 퍼센트 -> 비율
])
def test_ratio_and_percent_conversion(source, answer):
    assert unverified_numbers(answer, [source]) == []


def test_rounding_to_the_digits_written_in_the_answer():
    assert unverified_numbers("약 7.5% 입니다", [{"rate": 7.46}]) == []   # 7.46 -> 7.5
    assert unverified_numbers("7.46% 입니다", [{"rate": 7.46}]) == []
    assert unverified_numbers("7.4% 입니다", [{"rate": 7.46}]) == ["7.4"]  # 반올림이 아니라 다른 값이다


def test_numbers_in_the_question_count_as_evidence():
    assert unverified_numbers("지난 90일 동안의 값입니다", ["최근 90일 구매는?"]) == []


def test_definition_numbers_always_pass():
    # 정의와 군 이름에 들어 있는 숫자(14~29일, 30일, 상위 10%군, 11~30%군)는 도구 결과에 없어도 자연스럽게 나온다
    answer = "이탈 위험은 14~29일, 휴면은 30일, 상위 10%군과 11~30%군을 말합니다."
    assert unverified_numbers(answer, []) == []


@pytest.mark.parametrize("token", ["1,000", "1,100", "1,400", "2,900", "3,000", "0.14", "0.3"])
def test_definition_numbers_are_not_converted_so_their_multiples_are_flagged(token):
    # 정의 숫자(10, 11, 14, 29, 30)는 있는 그대로만 통과한다. 비율<->퍼센트 변환(x100, /100)은
    # 도구 결과와 질문의 숫자에만 적용하므로, 정의 숫자의 100배나 100분의 1 은 근거가 없으면 "걸린다".
    # (예전에는 이 변환이 정의 숫자에도 적용되어 10 -> 1,000, 14 -> 1,400, 30 -> 3,000 이 통과하는 구멍이 있었다.)
    assert unverified_numbers(f"가입자는 {token}명입니다.", []) == [token]


def test_conversion_still_applies_to_numbers_from_tool_results():
    # 변환 자체는 그대로다: 도구 결과의 10 이면 1,000 도 통과한다 (10 의 100배가 결과 근거에서 나왔으므로)
    assert unverified_numbers("1,000", [{"rows": [[10]]}]) == []
    assert unverified_numbers("30%", [{"ratio": 0.3}]) == []


def test_number_without_evidence_is_reported_once():
    assert unverified_numbers("120명, 다시 120명, 그리고 1,643명", [{"rows": [[1643]]}]) == ["120"]


def test_checker_never_changes_or_blocks_the_answer():
    # 결과는 "의심되는 숫자 목록"뿐이다. 답 문자열은 건드리지 않는다.
    answer = "휴면은 999명입니다"
    assert unverified_numbers(answer, []) == ["999"] and answer == "휴면은 999명입니다"


# ---------- 2) 못 잡는 경우 (놓침): 틀렸는데 경고가 없다 ----------
def test_miss_number_attached_to_the_wrong_subject():
    # 도구 결과: at_risk 가 75명. 답: "휴면이 75명". 숫자 75 는 결과에 있으므로 통과한다.
    tool_result = {"activity_status": "at_risk", "n": 75}
    assert unverified_numbers("휴면 팬은 75명입니다.", [tool_result]) == []


def test_miss_number_written_in_words():
    # "절반", "두 배", "세 명" 같은 글자 숫자는 숫자로 읽지 않으므로 아무것도 검사하지 않는다
    answer = "구매 팬은 전체의 절반이고, 지난달보다 두 배로 늘었으며 세 명이 탈퇴했습니다."
    assert unverified_numbers(answer, [{"rows": [[1643, 3]]}]) == []


def test_miss_misused_definition_number():
    # 정의 숫자(14, 29, 30, 10, 11)는 항상 통과하므로, 그 숫자를 틀린 뜻으로 써도 모른다
    # (실제 정의: 휴면은 30일 이상 비활동. 아래 문장은 틀렸다.)
    assert unverified_numbers("휴면은 14일 이상 활동이 없는 팬입니다.", [{"rows": [[5]]}]) == []
    assert unverified_numbers("상위 30%군에 해당합니다.", []) == []  # 군 이름은 "상위 10%군"이다


def test_miss_wrong_number_that_happens_to_exist_elsewhere():
    # 결과에 있는 아무 숫자와 우연히 같으면 통과한다. 행이 많을수록 우연히 맞을 확률이 올라간다.
    rows = [[i] for i in range(1, 200)]
    assert unverified_numbers("가입자는 137명입니다.", [{"rows": rows}]) == []


# ---------- 3) 거짓 경보: 정상인데 경고가 뜬다 ----------
def test_false_alarm_sum_or_difference_computed_by_the_model():
    # 600 + 450 = 1,050 은 맞는 계산이지만 "1,050" 이 결과에 없으므로 경고가 뜬다
    sources = [{"rows": [["A", 600], ["B", 450]]}]
    assert unverified_numbers("두 곳을 합치면 1,050명입니다.", sources) == ["1,050"]
    assert unverified_numbers("두 곳의 차이는 150명입니다.", sources) == ["150"]


def test_false_alarm_approximation():
    # "약 1,600명" 은 1,643 을 어림한 정상 표현이지만 결과에 없는 숫자로 읽힌다
    assert unverified_numbers("활동 중인 팬은 약 1,600명입니다.", [{"rows": [[1643]]}]) == ["1,600"]


# 위 두 묶음이 "경고 전용"이어야 하는 이유: 2) 는 차단 수단으로 믿으면 안 되고, 3) 은 차단하면 정상 답을 막는다.
def test_module_doc_lists_the_known_limits():
    assert "잡지 못한다" in numcheck.__doc__ and "거짓 경보" in numcheck.__doc__
