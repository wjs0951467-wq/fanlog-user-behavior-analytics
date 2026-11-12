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


# ---------- 정상 ----------
def test_minimal_item_gets_safe_defaults():
    q = Q.parse_questions([item()])[0]
    assert q.verified is False and q.tolerance == {} and q.ordered is False and q.notes == ""
    assert q.reference_sql == "SELECT COUNT(*) FROM dim_user"


def test_all_fields_are_read():
    q = Q.parse_questions([item(verified=True, tolerance={"abs": 0.01, "rel": 0, "accept_percent_or_ratio": True},
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
    qs = Q.parse_questions([item(), item(id="X02", question="다른 질문", verified=True)])
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
