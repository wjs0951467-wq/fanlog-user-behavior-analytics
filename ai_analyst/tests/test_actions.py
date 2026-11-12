"""recommend_actions 의 순수 함수(app/actions.py) 테스트: 개인정보 패턴, 금지어, 형식 검사, 표본 수.

LLM 도 DB 도 쓰지 않는다 (실제 OpenAI 호출 0회).
"""
import pytest

from app import actions


def draft(**over):
    """형식과 안전 규칙을 모두 지키는 초안. 테스트마다 바꿀 칸만 덮어쓴다."""
    base = {
        "segment_description": "지금 활동 중인 팬 중 이탈 위험 순위가 높은 군입니다.",
        "hypothesis": "새 소식을 알리면 다시 방문하는 팬이 늘 수 있다.",
        "message_draft": "새 콘텐츠가 올라왔어요. 구경 오세요!",
        "channel": "앱 푸시",
        "validation": {"metric": "14일 내 핵심 활동 비율", "comparison_group": "알림을 받지 않는 같은 군",
                       "period": "14일"},
        "cautions": ["가상 데이터의 결과이며 인과가 아니다."],
    }
    base.update(over)
    return base


def pii_labels(text):
    """message_draft 한 칸에 text 를 넣었을 때 잡히는 개인정보 종류들."""
    found = actions.safety_violations(draft(message_draft=text))
    return [v for v in found if "개인 식별 정보" in v]


# ---------- 개인정보 패턴 ----------
# 한글 조사가 바로 붙어도 잡혀야 한다. 예전 패턴은 끝의 \b 가 한글을 "단어 문자"로 봐서 이런 경우를 놓쳤다.
@pytest.mark.parametrize("text, label", [
    ("user_123", "사용자 ID"),
    ("user_123님", "사용자 ID"),
    ("user_123이 좋아해요", "사용자 ID"),
    ("팬user_123 에게", "사용자 ID"),          # 앞에 한글이 붙은 경우
    ("fan-4567을", "사용자 ID"),
    ("010-1234-5678", "전화번호"),
    ("010-1234-5678로 연락", "전화번호"),
    ("01012345678을 남겨 주세요", "전화번호"),
    ("abc@example.com", "이메일"),
    ("abc@example.com으로 보내 주세요", "이메일"),
])
def test_pii_is_caught_even_with_korean_particles(text, label):
    assert any(f"({label})" in v for v in pii_labels(text))


def test_pii_violation_does_not_repeat_the_text():
    # 위반 사유에 개인정보로 보이는 문자열 자체를 싣지 않는다 (다시 퍼뜨리지 않기 위해)
    found = actions.safety_violations(draft(message_draft="010-1234-5678로 연락, abc@example.com, user_123"))
    assert len(found) == 3
    joined = " ".join(found)
    assert "1234" not in joined and "abc@" not in joined and "user_123" not in joined


@pytest.mark.parametrize("text", [
    "14일 동안 1,643명 중 7.5% 입니다",     # 일반 숫자
    "user 님께 드리는 소식",                  # "user" 만 있는 단어
    "users 와 userland",                      # user 로 시작하지만 ID 모양이 아니다
    "2026-03-31 에 시작합니다",               # 날짜
    "문의는 앱 안에서 해 주세요",
])
def test_pii_does_not_flag_ordinary_text(text):
    assert pii_labels(text) == []


# ---------- 금지어 (결정 D1) ----------
TEXT_FIELDS = ["segment_description", "hypothesis", "message_draft", "channel",
               "validation.metric", "validation.comparison_group", "validation.period", "cautions[0]"]


def with_text(field, text):
    """초안의 한 칸만 text 로 바꾼다. field 는 safety_violations 가 쓰는 항목 이름이다."""
    rec = draft()
    if field.startswith("validation."):
        rec["validation"][field.split(".")[1]] = text
    elif field.startswith("cautions["):
        rec["cautions"] = [text]
    else:
        rec[field] = text
    return rec


def test_clean_draft_has_no_violations():
    assert actions.safety_violations(draft()) == []


@pytest.mark.parametrize("word", actions.BANNED_WORDS)
@pytest.mark.parametrize("field", TEXT_FIELDS)
def test_promise_words_are_banned_in_every_text_field(field, word):
    # 효과를 약속하는 말은 팬에게 가는 글뿐 아니라 모든 글 칸에 적용된다
    found = actions.safety_violations(with_text(field, f"이렇게 하면 {word} 좋아집니다"))
    assert any(v.startswith(f"{field}:") and word in v for v in found)


def test_must_be_promise_phrase_is_caught():
    assert actions.safety_violations(draft(hypothesis="이 알림을 보내면 반드시 방문이 늘어난다"))


@pytest.mark.parametrize("word", actions.MESSAGE_BANNED_WORDS)
def test_internal_class_words_are_banned_only_in_message_draft(word):
    assert actions.MESSAGE_BANNED_WORDS == ["이탈", "위험", "휴면"]
    found = actions.safety_violations(draft(message_draft=f"{word} 소식을 드려요"))
    assert [v.split(":")[0] for v in found] == ["message_draft"]
    # 같은 낱말이 운영자용 칸에 있으면 통과한다
    for field in ("segment_description", "hypothesis", "validation.metric", "cautions[0]"):
        assert actions.safety_violations(with_text(field, f"{word} 관련 설명")) == []


# ---------- 형식 검사 ----------
def test_valid_draft_passes_schema():
    assert actions.schema_errors(draft()) == []


@pytest.mark.parametrize("rec", [None, [], "text", 3])
def test_schema_rejects_non_objects(rec):
    assert actions.schema_errors(rec) == ["JSON 객체가 아니다"]


def test_schema_rejects_missing_and_extra_keys():
    missing = draft()
    del missing["hypothesis"]
    assert any("키가 정확히" in e for e in actions.schema_errors(missing))
    assert any("키가 정확히" in e for e in actions.schema_errors({**draft(), "send_time": "저녁"}))  # 결정 D2


@pytest.mark.parametrize("rec, fragment", [
    (draft(validation={"metric": "a", "comparison_group": "b"}), "validation"),
    (draft(validation="14일"), "validation"),
    (draft(cautions=[]), "cautions"),
    (draft(cautions=["a", "b", "c", "d"]), "cautions"),
    (draft(cautions="주의"), "cautions"),
    (draft(hypothesis="  "), "hypothesis"),
    (draft(message_draft=None), "message_draft"),
    (draft(hypothesis="가" * (actions.MAX_TEXT + 1)), "hypothesis"),
    (draft(channel="카카오톡"), "channel"),
])
def test_schema_reports_the_violation(rec, fragment):
    errors = actions.schema_errors(rec)
    assert errors and any(fragment in e for e in errors)


def test_schema_accepts_every_listed_channel():
    for channel in actions.CHANNELS:
        assert actions.schema_errors(draft(channel=channel)) == []


# ---------- 표본 수 ----------
# 아래 값은 "표에 적은 비율을 그대로" 넣은 계산이다. 도구는 반올림 전의 실제 비율(예: 0.07463...)을 쓰므로
# 화면에 나오는 인원은 이 값과 몇 명에서 수십 명까지 다를 수 있다 (손계산 590 / 1,850 과의 차이도 같은 이유다).
@pytest.mark.parametrize("rate, reduction, expected", [
    (0.075, 0.5, 589),     # 상위 10%군, 50% 감소  (손계산 약 590)
    (0.075, 0.3, 1847),    # 상위 10%군, 30% 감소  (손계산 약 1,850)
    (0.053, 0.5, 850),     # 11~30%군, 50% 감소
    (0.053, 0.3, 2668),    # 11~30%군, 30% 감소
])
def test_needed_per_group_matches_known_values(rate, reduction, expected):
    assert actions.needed_per_group(rate, reduction) == expected


def test_needed_per_group_moves_in_the_expected_direction():
    assert actions.needed_per_group(0.03, 0.5) > actions.needed_per_group(0.075, 0.5)   # 드문 사건일수록 많이 필요
    assert actions.needed_per_group(0.075, 0.3) > actions.needed_per_group(0.075, 0.5)  # 작은 효과일수록 많이 필요
    assert actions.needed_per_group(0.075, 0.5, power=0.9) > actions.needed_per_group(0.075, 0.5)
    assert actions.needed_per_group(0.075, 0.5, alpha=0.01) > actions.needed_per_group(0.075, 0.5)


def test_needed_per_group_changes_little_with_rounding_of_the_rate():
    # 표에 적은 7.5% 대신 반올림 전 비율(7.45%~7.55%)을 써도 결과가 크게 달라지지 않는다 (50% 감소 기준 3% 안쪽)
    low, high = actions.needed_per_group(0.0745, 0.5), actions.needed_per_group(0.0755, 0.5)
    assert abs(low - 589) / 589 < 0.03 and abs(high - 589) / 589 < 0.03


def test_sample_size_plan_small_segment_cannot_be_verified():
    plan = actions.sample_size_plan(0.075, 157)   # 03-31 상위 10%군 정도의 크기
    assert plan["per_group_if_split_in_half"] == 78 and plan["feasible"] is False
    assert [s["feasible"] for s in plan["scenarios"]] == [False, False]
    assert "검증할 수 없다" in plan["verdict"] and "1,847명" in plan["verdict"] and "589명" in plan["verdict"]


def test_sample_size_plan_partly_feasible():
    plan = actions.sample_size_plan(0.075, 1400)  # 그룹당 700: 50% 감소(589)는 되고 30% 감소(1,847)는 안 된다
    assert [s["assumed_reduction_pct"] for s in plan["scenarios"]] == [30, 50]
    assert [s["feasible"] for s in plan["scenarios"]] == [False, True]
    assert plan["feasible"] is True and "검증할 수 있는 가정이 있다" in plan["verdict"]


def test_sample_size_plan_large_segment_and_fields():
    plan = actions.sample_size_plan(0.075, 4000)
    assert plan["feasible"] and all(s["feasible"] for s in plan["scenarios"])
    assert plan["alpha_two_sided"] == 0.05 and plan["power"] == 0.8 and plan["base_rate_pct"] == 7.5
    assert [s["target_rate_pct"] for s in plan["scenarios"]] == [5.2, 3.8]   # 7.5% 의 70%, 50%
    assert "예상 효과가 아니다" in plan["note"]  # 30%/50% 는 계산을 위한 가정일 뿐이라고 항상 적는다


def test_sample_size_plan_boundary():
    needed = actions.needed_per_group(0.075, 0.5)
    assert actions.sample_size_plan(0.075, needed * 2)["scenarios"][1]["feasible"] is True       # 그룹당 정확히 필요한 만큼
    assert actions.sample_size_plan(0.075, needed * 2 - 2)["scenarios"][1]["feasible"] is False  # 1명 모자람


def test_channel_note_marks_the_list_as_an_assumption():
    assert "가정" in actions.CHANNEL_NOTE and all(c in actions.CHANNEL_NOTE for c in actions.CHANNELS)


def test_action_rules_prompt_has_the_decided_rules():
    rules = actions.ACTION_RULES
    assert "JSON" in rules                                   # OpenAI json_object 모드의 필수 조건
    assert all(w in rules for w in ("이탈", "위험", "휴면"))  # 팬 글 금지어 (결정 D1)
    assert "오랜만이에요" in rules and "요즘 안 오셨네요" in rules  # 코드로 못 막는 규칙은 프롬프트에만 있다
    assert "send_time" not in rules and "발송" not in rules   # 발송 시점은 만들지 않는다 (결정 D2)
