"""app/safety.py 테스트: 사용자 ID 가리기와 모델 입력 길이 자르기. 순수 함수라 DB 와 LLM 이 필요 없다."""
import copy

import pytest

from app import safety

# ---------- 사용자 ID 만 가린다 (dim_user.user_id 모양: "user_" + 숫자 6자리) ----------
MASKED = [
    ("user_000123", "[ID]"),
    ("고객 user_000123 님", "고객 [ID] 님"),
    ("user_000123의 주문", "[ID]의 주문"),               # 한글이 바로 붙어도 가린다
    ("(user_000123)", "([ID])"),
    ("user_000123, user_000456", "[ID], [ID]"),
    ("USER_000123", "[ID]"),                              # 모델이 대소문자를 바꿔 써도 가린다
    ("user_0001234", "[ID]"),                             # 7자리 이상도 가린다 (사용자가 늘어도 새지 않게)
    ('"user_000123"', '"[ID]"'),
    ("id=user_000123;", "id=[ID];"),
]


@pytest.mark.parametrize("text, expected", MASKED)
def test_user_ids_are_masked(text, expected):
    assert safety.mask_ids(text) == expected


# 사용자 ID 가 아닌 것은 건드리지 않는다. (주문번호, 상품, 콘텐츠, 이벤트, 팔로우, 구독 등 다른 ID 는 그대로 보인다)
NOT_MASKED = [
    "txn_000123", "orderitem_000001", "event_00000001", "follow_000001", "subscription_000001",
    "content_a1_0001", "product_a1_001", "activity_a1_00001", "phase_a1_01",
    "xuser_000123", "myuser_000123",                      # 앞에 글자가 붙은 다른 이름
    "users_000123",                                       # user_ 가 아니다
    "user_12345",                                         # 5자리는 사용자 ID 모양이 아니다
    "user_", "user_abc", "user 000123", "user-000123",   # 모양이 다른 것
    "user_000123abc",                                     # 뒤에 글자가 이어지면 다른 이름이다
    "휴면 팬은 1,643명입니다.", "",
]


@pytest.mark.parametrize("text", NOT_MASKED)
def test_other_values_are_left_alone(text):
    assert safety.mask_ids(text) == text


def test_known_false_positive_is_a_literal_that_looks_exactly_like_a_user_id():
    """오탐 가능성: 글자 그대로 user_ + 6자리인 문자열은, 사용자 ID 가 아니어도 가려진다 (닫는 방향의 선택)."""
    assert safety.mask_ids("상품 이름: user_123456") == "상품 이름: [ID]"


def test_mask_ids_handles_non_strings():
    assert safety.mask_ids(None) == "" and safety.mask_ids(123) == "123"


def test_mask_ids_counted_returns_how_many():
    assert safety.mask_ids_counted("user_000123 와 user_000456, txn_000001") == ("[ID] 와 [ID], txn_000001", 2)
    assert safety.mask_ids_counted("없음") == ("없음", 0)


def test_mask_deep_walks_containers_without_touching_the_input():
    original = {"rows": [["user_000123", 5, None, 1.5], ("user_000456", {"k": "user_000789 님"})], "n": 3,
                "user_000999": "키는 가리지 않는다"}
    before = copy.deepcopy(original)
    out = safety.mask_deep(original)
    assert out["rows"][0] == ["[ID]", 5, None, 1.5]
    assert out["rows"][1][0] == "[ID]" and out["rows"][1][1] == {"k": "[ID] 님"}
    assert out["n"] == 3 and out["user_000999"] == "키는 가리지 않는다"
    assert original == before  # 입력은 바뀌지 않는다


def test_mask_rows_returns_new_rows_and_the_count():
    rows = [["user_000123", "가"], ["user_000123", "user_000456"], [7, None]]
    masked, n = safety.mask_rows(rows)
    assert masked == [["[ID]", "가"], ["[ID]", "[ID]"], [7, None]] and n == 3
    assert rows[0][0] == "user_000123"


# ---------- 모델 입력 길이 ----------
def test_clip_text_boundary():
    assert safety.MODEL_TEXT_CHARS == 200
    exactly = "가" * 200
    assert safety.clip_text(exactly) == exactly
    clipped = safety.clip_text("가" * 201)
    assert clipped == "가" * 200 + "...(잘림)"


def test_clip_text_custom_limit_and_non_strings():
    assert safety.clip_text("abcdef", limit=3) == "abc...(잘림)"
    assert safety.clip_text(None) == "" and safety.clip_text(5) == "5"


def test_clip_deep_clips_every_string_but_not_numbers_or_keys():
    long = "x" * 500
    out = safety.clip_deep({"sql": long, "columns": [long, "a"], "n": 5, "nested": {"error": long, "ok": None}, long: 1})
    assert out["sql"].endswith("...(잘림)") and len(out["sql"]) < 220
    assert out["columns"][0].endswith("...(잘림)") and out["columns"][1] == "a"
    assert out["n"] == 5 and out["nested"]["ok"] is None and out["nested"]["error"].endswith("...(잘림)")
    assert long in out  # 키는 그대로
