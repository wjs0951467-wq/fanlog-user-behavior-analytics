"""eval/questions.py 테스트: 스키마 검사, 로더, 검증되지 않은 문항 거부."""
import re
from pathlib import Path

import pytest

from eval import questions as Q

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "eval"


def item(**over):
    base = {"id": "X01", "question": "가입자 수는?", "category": "단순 집계", "split": "heldout",
            "expected_kind": "scalar", "reference_sql": "SELECT COUNT(*) FROM dim_user", "source": "test"}
    base.update(over)
    return {k: v for k, v in base.items() if v is not ...}


def good_verification(**over):
    base = {"verified_by": "담당자(사람)", "verified_on": "2026-11-13", "method": "DBeaver 직접 실행 + 이벤트 테이블 독립 확인",
            "result_value": "90", "independent_check": "일치"}
    base.update(over)
    return {k: v for k, v in base.items() if v is not ...}


# ---------- 정상 ----------
def test_minimal_item_gets_safe_defaults():
    q = Q.parse_questions([item()])[0]
    assert q.verified is False and q.tolerance == {} and q.ordered is False and q.notes == ""
    assert q.reference_sql == "SELECT COUNT(*) FROM dim_user"


def test_all_fields_are_read():
    q = Q.parse_questions([item(verified=True, verification=good_verification(),
                                tolerance={"abs": 0.01, "rel": 0, "accept_percent_or_ratio": True},
                                notes="메모", expected_kind="rows", ordered=True)])[0]
    assert q.verified is True and q.tolerance["abs"] == 0.01 and q.ordered is True and q.notes == "메모"


def test_refusal_item_has_no_reference_sql():
    q = Q.parse_questions([item(expected_kind="refusal", category="거절", reference_sql=None)])[0]
    assert q.reference_sql is None


# ---------- 거부 ----------
@pytest.mark.parametrize("over, word", [
    ({"verfied": True}, "모르는 키"),                       # 오타가 조용히 무시되면 안 된다
    ({"verified": "yes"}, "verified"),
    ({"verified": 1}, "verified"),
    ({"category": "기타"}, "category"),
    ({"split": "test"}, "split"),
    ({"expected_kind": "number"}, "expected_kind"),
    ({"reference_sql": None}, "reference_sql 이 필요"),
    ({"reference_sql": "   "}, "reference_sql 이 필요"),
    ({"expected_kind": "refusal"}, "reference_sql 을 쓰지 않는다"),
    ({"id": ""}, "필수 항목"),
    ({"question": None}, "필수 항목"),
    ({"source": ...}, "필수 항목"),
    ({"tolerance": {"abs": -1}}, "0 이상"),
    ({"tolerance": {"abs": True}}, "0 이상"),
    ({"tolerance": {"absolute": 1}}, "모르는 키"),
    ({"tolerance": {"accept_percent_or_ratio": "yes"}}, "true/false"),
    ({"tolerance": [1]}, "매핑"),
    ({"ordered": True}, "rows 문항에만"),
    ({"ordered": "yes", "expected_kind": "rows"}, "ordered"),
])
def test_bad_items_are_rejected_with_a_reason(over, word):
    with pytest.raises(Q.QuestionFileError, match=word):
        Q.parse_questions([item(**over)])


def test_duplicate_ids_and_duplicate_questions_are_rejected():
    with pytest.raises(Q.QuestionFileError, match="id 가 중복"):
        Q.parse_questions([item(), item(question="다른 질문")])
    with pytest.raises(Q.QuestionFileError, match="같은 질문"):
        Q.parse_questions([item(), item(id="X02")])


def test_all_problems_are_reported_together():
    with pytest.raises(Q.QuestionFileError) as info:
        Q.parse_questions([item(category="기타", split="test"), "문자열"])
    text = str(info.value)
    assert "category" in text and "split" in text and "매핑이 아니다" in text


def test_top_level_shape_is_checked(tmp_path):
    bad = tmp_path / "q.yaml"
    bad.write_text("- id: X01", encoding="utf-8")
    with pytest.raises(Q.QuestionFileError, match="questions 키"):
        Q.load_questions(bad)
    with pytest.raises(Q.QuestionFileError, match="목록"):
        Q.parse_questions({"id": "X01"})


# ---------- 검증되지 않은 문항은 실제 실행에서 거부 ----------
def test_unverified_questions_are_refused_for_real_runs():
    qs = Q.parse_questions([item(), item(id="X02", question="다른 질문", verified=True, verification=good_verification())])
    with pytest.raises(Q.UnverifiedQuestionError, match="X01") as info:
        Q.require_verified(qs)
    assert "X02" not in str(info.value)
    Q.require_verified([q for q in qs if q.verified])  # 전부 검증됐으면 통과


# ---------- 고르기 ----------
def test_select_by_split_and_ids():
    qs = Q.parse_questions([item(), item(id="D01", question="개발 질문", split="dev")])
    assert [q.id for q in Q.select(qs, "dev")] == ["D01"]
    assert [q.id for q in Q.select(qs, "all")] == ["X01", "D01"]
    assert [q.id for q in Q.select(qs, "all", ["X01"])] == ["X01"]
    with pytest.raises(ValueError, match="없는 id"):
        Q.select(qs, "dev", ["X01"])
    with pytest.raises(ValueError):
        Q.select(qs, "train")


# ---------- 실제 파일 ----------
def notes_questions():
    """eval_notes.md 첫 번째 표의 질문 6개 (개발용 질문의 기준)."""
    lines = (ROOT / "eval_notes.md").read_text(encoding="utf-8").splitlines()
    rows = [line.split("|")[1].strip() for line in lines if line.startswith("|") and "통과" in line]
    assert len(rows) == 6
    return rows


def test_questions_yaml_has_two_example_items_and_none_is_verified():
    qs = Q.load_questions(EVAL / "questions.yaml")
    assert len(qs) == 2
    assert all(q.verified is False for q in qs)  # verified 는 사람이 정한다: 초안은 전부 false


def test_dev_questions_are_exactly_the_six_from_eval_notes():
    dev = [q for q in Q.load_questions(EVAL / "questions.yaml") + Q.load_questions(EVAL / "dev_drafts.yaml")
           if q.split == "dev"]
    assert sorted(q.question for q in dev) == sorted(notes_questions())
    assert all(q.verified is False and q.source == "eval_notes.md" for q in dev)
    assert len({q.id for q in dev}) == 6


def test_real_run_gate_refuses_the_current_files():
    with pytest.raises(Q.UnverifiedQuestionError):
        Q.require_verified(Q.load_questions(EVAL / "questions.yaml"))


def test_reference_sql_of_dev_items_passes_the_guard():
    from app.sql_guard import validate_sql
    for q in Q.load_questions(EVAL / "questions.yaml") + Q.load_questions(EVAL / "dev_drafts.yaml"):
        assert re.search("LIMIT", validate_sql(q.reference_sql), re.IGNORECASE), q.id


# ---------- verified: true 에는 사람의 확인 근거(verification)가 있어야 한다 ----------
REQUIRED_KEYS = ("verified_by", "verified_on", "method", "result_value", "independent_check")


def problems_of(*items):
    with pytest.raises(Q.QuestionFileError) as info:
        Q.parse_questions(list(items))
    return str(info.value)


def test_verification_required_keys_are_exactly_these_five():
    assert Q.VERIFICATION_REQUIRED == REQUIRED_KEYS and Q.VERIFICATION_OPTIONAL == ("trap_check",)


def test_verified_true_with_a_complete_verification_loads_and_keeps_the_record():
    q = Q.parse_questions([item(verified=True, verification=good_verification(result_value=90))])[0]
    assert q.verified is True and q.verification["independent_check"] == "일치" and q.verification["result_value"] == 90


def test_verified_true_without_verification_is_rejected_and_names_the_question():
    for over in ({}, {"verification": None}, {"verification": {}}):
        text = problems_of(item(id="Q99", verified=True, **over))
        assert "Q99" in text and "verified: true" in text and "verification" in text, over


@pytest.mark.parametrize("key", REQUIRED_KEYS)
def test_missing_required_key_is_named(key):
    text = problems_of(item(id="Q98", verified=True, verification=good_verification(**{key: ...})))
    assert "Q98" in text and f"verification.{key}" in text and "없다" in text


@pytest.mark.parametrize("key", ("verified_by", "method", "result_value", "independent_check"))
@pytest.mark.parametrize("bad", ("", "   ", None))
def test_blank_values_are_rejected_with_question_and_key(key, bad):
    text = problems_of(item(id="Q97", verified=True, verification=good_verification(**{key: bad})))
    assert "Q97" in text and f"verification.{key}" in text and "비어" in text


@pytest.mark.parametrize("bad", ("2026-13-01", "2026-02-30", "2026/11/13", "26-11-13", "어제", "", "   "))
def test_verified_on_must_be_a_real_yyyy_mm_dd_date(bad):
    text = problems_of(item(id="Q96", verified=True, verification=good_verification(verified_on=bad)))
    assert "Q96" in text and "verification.verified_on" in text and "YYYY-MM-DD" in text


def test_verified_on_accepts_a_yaml_date_and_a_string_but_not_a_datetime():
    import datetime
    for ok in ("2026-11-13", datetime.date(2026, 11, 13)):
        assert Q.parse_questions([item(verified=True, verification=good_verification(verified_on=ok))])[0].verified
    text = problems_of(item(id="Q95", verified=True, verification=good_verification(verified_on=datetime.datetime(2026, 11, 13, 9))))
    assert "verification.verified_on" in text


def test_result_value_may_be_a_number_but_not_a_bool_or_a_list():
    assert Q.parse_questions([item(verified=True, verification=good_verification(result_value=7))])[0].verified
    for bad in (True, [7], {"a": 1}):
        assert "verification.result_value" in problems_of(item(id="Q94", verified=True, verification=good_verification(result_value=bad)))


def test_trap_check_is_optional_for_any_question_but_not_blank_when_given():
    q = Q.parse_questions([item(id="Q50", verified=True, verification=good_verification(trap_check="UTC 로 자르면 12 건, KST 는 7 건"))])[0]
    assert q.verification["trap_check"].startswith("UTC")
    text = problems_of(item(id="Q51", verified=True, verification=good_verification(trap_check="  ")))
    assert "Q51" in text and "verification.trap_check" in text and "비어" in text


def test_unknown_verification_keys_and_non_mapping_are_rejected():
    assert "verification" in problems_of(item(id="Q93", verified=True, verification=good_verification(verifed_by="오타")))
    assert "verifed_by" in problems_of(item(id="Q93", verified=True, verification=good_verification(verifed_by="오타")))
    assert "매핑" in problems_of(item(id="Q92", verified=True, verification="확인함"))


def test_a_verification_on_an_unverified_question_is_still_checked():
    """verified: false 여도 적어 둔 기록이 깨져 있으면 조용히 넘기지 않는다."""
    assert "verification.method" in problems_of(item(id="Q91", verified=False, verification=good_verification(method="")))


def test_every_problem_is_reported_together():
    text = problems_of(item(id="Q90", verified=True, verification=good_verification(verified_by="", verified_on="어제")))
    assert "verification.verified_by" in text and "verification.verified_on" in text


def test_a_verification_without_the_flag_does_not_make_a_question_verified():
    q = Q.parse_questions([item(verification=good_verification())])[0]
    assert q.verified is False
