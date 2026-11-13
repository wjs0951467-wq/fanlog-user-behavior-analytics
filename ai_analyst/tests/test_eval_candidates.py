"""eval/candidates.yaml (후보 질문 초안)과 eval/verify/ 의 일관성 테스트. DB 와 LLM 을 쓰지 않는다 (SQL 은 파싱 검사만)."""
import re
from collections import Counter
from pathlib import Path

import pytest
import yaml

from app.sql_guard import SQLGuardError, validate_sql
from eval import questions as Q

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "eval"
SOURCE = "draft-by-claude-code-2026-11-12"
FIELDS = {"id", "question", "category", "expected_kind", "reference_sql", "reference_note", "trap", "likely_wrong",
          "needs_definition", "heldout_candidate", "guard_ok", "verified", "source"}
OPTIONAL_FIELDS = {"tolerance", "ordered"}

# 후보에서 빼야 하는 질문: 개발용 6문항, 이미 쓴 시나리오와 안전 확인 질문, 시맨틱 레이어의 예시 2개
EXCLUDED_QUESTIONS = (
    "구매 전환율은?", "유입 채널별 구매 전환율", "구매 건수는?", "현재 휴면 팬은 몇 명? (탈퇴자 제외)",
    "현재 이탈 위험 팬은 몇 명? (탈퇴자 제외)", "현재 활동 중인 팬은 몇 명? (탈퇴자 제외)",
    "현재 휴면 팬은 몇 명이야?", "소통 공백이 긴 아티스트는 누구야?",
    "이탈 위험이 높은 팬 중 구매 경험이 있는 팬은 몇 명이야?",
    "이 세그먼트에 보낼 메시지 초안과 효과를 검증하는 방법을 알려줘.",
    "아티스트별 현재 팔로워 수 상위 5명은?", "월별 신규 가입자 수를 유입 채널별로 보여줘",
)
# 같은 주제를 문장만 바꿔 쓴 것도 막는다: 이 낱말 조합이 질문에 함께 있으면 제외 대상과 거의 같은 질문이다
EXCLUDED_TOPICS = (("구매 전환율",), ("나이",), ("연령",), ("시스템 프롬프트",), ("사용자 ID",), ("user_id",),
                   ("팔로워", "상위"), ("신규 가입", "채널"), ("순위", "구매"), ("소통 공백",), ("메시지 초안",),
                   ("탈퇴", "포함", "상태별"))


def load():
    data = yaml.safe_load((EVAL / "candidates.yaml").read_text(encoding="utf-8"))
    return data["candidates"]


def squash(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


CANDIDATES = load()
IDS = [c["id"] for c in CANDIDATES]


# ---------- 파일 전체 ----------
def test_there_are_exactly_40_candidates_with_ids_q01_to_q40():
    assert IDS == [f"Q{n:02d}" for n in range(1, 41)]


def test_header_says_the_draft_is_not_the_answer():
    head = (EVAL / "candidates.yaml").read_text(encoding="utf-8").split("candidates:")[0]
    assert "이 초안은 정답이 아니다" in head and "사람이 DBeaver 로 직접 확인해야 verified 가 된다" in head
    assert "모델이 낸 SQL 이나 숫자로 정답을 만들지 않는다" in head


def test_category_mix():
    counts = Counter(c["category"] for c in CANDIDATES)
    assert set(counts) == set(Q.CATEGORIES)
    assert counts["거절"] == 5 and sum(counts.values()) == 40
    assert all(counts[name] >= 5 for name in Q.CATEGORIES)


def test_questions_are_all_different():
    assert len({c["question"] for c in CANDIDATES}) == 40
    assert len({squash(c["reference_sql"]) for c in CANDIDATES if c["reference_sql"]}) == 35  # 같은 SQL 을 두 번 쓰지 않았다


# ---------- 문항별 ----------
@pytest.mark.parametrize("c", CANDIDATES, ids=IDS)
def test_fields_and_fixed_values(c):
    assert FIELDS <= set(c) and set(c) <= FIELDS | OPTIONAL_FIELDS
    assert c["verified"] is False            # 초안은 전부 미검증이다
    assert c["source"] == SOURCE
    assert c["category"] in Q.CATEGORIES and c["expected_kind"] in Q.KINDS
    for key in ("question", "reference_note", "trap", "likely_wrong"):
        assert isinstance(c[key], str) and c[key].strip(), key
    assert isinstance(c["needs_definition"], bool) and isinstance(c["heldout_candidate"], bool)
    assert len(c["reference_note"]) >= 20  # 사람이 추론으로 검증할 수 있을 만큼은 적는다


@pytest.mark.parametrize("c", CANDIDATES, ids=IDS)
def test_refusal_items_have_no_sql_and_others_do(c):
    if c["expected_kind"] == "refusal":
        assert c["category"] == "거절" and c["reference_sql"] is None and c["guard_ok"] is None
    else:
        assert c["category"] != "거절" and isinstance(c["reference_sql"], str) and c["reference_sql"].strip()


@pytest.mark.parametrize("c", [c for c in CANDIDATES if c["reference_sql"]], ids=[c["id"] for c in CANDIDATES if c["reference_sql"]])
def test_guard_ok_matches_the_real_guard(c):
    """reference_sql 을 가드레일로 파싱 검사만 한다 (DB 실행 없음). 파일에 적힌 guard_ok 가 실제 결과와 같아야 한다."""
    try:
        safe = validate_sql(c["reference_sql"])
        actual = True
    except SQLGuardError:
        safe, actual = "", False
    assert c["guard_ok"] is actual
    if actual:
        assert "LIMIT" in safe.upper()


def test_every_sql_passes_the_guard():
    """막힌 문항이 있으면 가드레일을 고치지 않고 SQL 을 바꿔 쓰거나 문항을 뺀다 (PROGRESS.md 에 기록)."""
    assert [c["id"] for c in CANDIDATES if c["reference_sql"] and c["guard_ok"] is not True] == []


@pytest.mark.parametrize("c", [c for c in CANDIDATES if c["reference_sql"]], ids=[c["id"] for c in CANDIDATES if c["reference_sql"]])
def test_sql_is_one_statement_and_never_lists_user_ids(c):
    sql = c["reference_sql"]
    assert ";" not in sql
    select_list = re.split(r"\bFROM\b", sql, maxsplit=1, flags=re.IGNORECASE)[0]
    assert not re.search(r"\buser_id\b(?![^(]*\))", select_list), "결과에 user_id 를 그대로 내면 안 된다 (집계 안에서만 쓴다)"
    assert "CURRENT_DATE" not in sql.upper() and "NOW()" not in sql.upper()  # 기준일은 데이터의 마지막 날짜다


@pytest.mark.parametrize("c", CANDIDATES, ids=IDS)
def test_needs_definition_items_are_not_heldout_candidates(c):
    if c["needs_definition"]:
        assert c["heldout_candidate"] is False


def test_the_w1_retention_item_is_marked_as_undefined():
    w1 = next(c for c in CANDIDATES if "W1" in c["question"])
    assert w1["needs_definition"] is True and "TODO" in w1["reference_note"]


@pytest.mark.parametrize("c", CANDIDATES, ids=IDS)
def test_excluded_questions_are_not_reused(c):
    text = c["question"]
    assert text not in EXCLUDED_QUESTIONS
    for words in EXCLUDED_TOPICS:
        assert not all(w in text for w in words), words


def test_trap_count_is_recorded_consistently():
    with_trap = [c["id"] for c in CANDIDATES if c["trap"].strip() != "없음"]
    assert len(with_trap) >= 25 and all(c["trap"].strip() for c in CANDIDATES)
    assert all(c["trap"].strip() != "없음" for c in CANDIDATES if c["category"] == "함정")


# ---------- 질문 스키마로 옮길 수 있는가 ----------
def as_question(c):
    """후보를 questions.yaml 에 옮길 때의 모양: 공통 필드만 남기고 split 과 notes 를 붙인다."""
    item = {"id": c["id"], "question": c["question"], "category": c["category"], "split": "heldout",
            "expected_kind": c["expected_kind"], "verified": c["verified"], "reference_sql": c["reference_sql"],
            "notes": c["reference_note"], "source": c["source"]}
    if "tolerance" in c:
        item["tolerance"] = c["tolerance"]
    if "ordered" in c:
        item["ordered"] = c["ordered"]
    return item


def test_candidates_load_through_the_question_schema():
    questions = Q.parse_questions([as_question(c) for c in CANDIDATES])
    assert len(questions) == 40 and all(q.verified is False for q in questions)
    with pytest.raises(Q.UnverifiedQuestionError):
        Q.require_verified(questions)  # 초안은 실제 실행에 쓸 수 없다


def test_candidate_ids_do_not_collide_with_existing_question_files():
    existing = {q.id for q in Q.load_questions(EVAL / "questions.yaml") + Q.load_questions(EVAL / "dev_drafts.yaml")}
    assert not existing & set(IDS)


# ---------- verify/ ----------
def test_reference_queries_file_has_every_sql_under_its_header():
    text = (EVAL / "verify" / "reference_queries.sql").read_text(encoding="utf-8")
    headers = re.findall(r"^-- \[(Q\d\d)\] (.*)$", text, flags=re.MULTILINE)
    assert [h[0] for h in headers] == IDS
    blocks = re.split(r"^-- \[Q\d\d\] .*$", text, flags=re.MULTILINE)[1:]
    for c, (qid, question), block in zip(CANDIDATES, headers, blocks):
        assert question.strip() == c["question"], qid
        body = squash(" ".join(line for line in block.splitlines() if not line.strip().startswith("--")))
        if c["reference_sql"]:
            assert body == squash(c["reference_sql"]) + ";", qid
        else:
            assert body == "", qid  # 거절 문항에는 실행할 SQL 이 없다


def test_reference_queries_file_is_read_only_sql():
    text = (EVAL / "verify" / "reference_queries.sql").read_text(encoding="utf-8").upper()
    code = " ".join(line for line in text.splitlines() if not line.strip().startswith("--"))
    for word in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "GRANT"):
        assert not re.search(rf"\b{word}\b", code), word


def test_checklist_has_a_row_for_every_candidate():
    text = (EVAL / "verify" / "VERIFY_CHECKLIST.md").read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if re.match(r"^\| Q\d\d \|", line)]
    assert [line.split("|")[1].strip() for line in rows] == IDS
    for c, line in zip(CANDIDATES, rows):
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        assert len(cells) == 5 and cells[1] == c["question"], c["id"]
        assert cells[2] and cells[3] == "" and cells[4] == "[ ]"  # 결과 칸은 비어 있고 체크는 사람이 한다


# ---------- 2026-11-13 결정 반영: Q25, Q27, Q32 ----------
def by_id(qid):
    return next(c for c in CANDIDATES if c["id"] == qid)


def test_q25_says_the_last_day_is_included_in_the_seven_days():
    c = by_id("Q25")
    assert "마지막 날을 포함해서 7일" in c["question"]
    assert "마지막 날 - 6일 ~ 마지막 날" in c["reference_note"]
    sql = squash(c["reference_sql"])
    assert ">= (SELECT MAX(" in sql and sql.rstrip().endswith("- 6")          # MAX - 6 이상 (마지막 날 포함 7일)
    assert "- 7" not in sql


def test_q27_month_is_written_as_a_yyyy_mm_string():
    c = by_id("Q27")
    sql = squash(c["reference_sql"])
    assert "to_char(" in sql and "'YYYY-MM'" in sql and "Asia/Seoul" in sql
    assert "date_trunc" not in sql and "::date AS month" not in sql
    assert "2026-01" in c["reference_note"] and "YYYY-MM" in c["reference_note"]


def test_q27_keeps_pending_out_and_still_passes_the_guard():
    sql = squash(by_id("Q27")["reference_sql"])
    assert "status <> 'pending'" in sql and "GROUP BY 1" in sql and "ORDER BY 1" in sql
    assert by_id("Q27")["guard_ok"] is True


def test_q32_states_that_deleted_users_are_excluded_in_the_question_and_the_sql():
    c = by_id("Q32")
    assert "탈퇴한 사용자는 빼고" in c["question"]
    sql = squash(c["reference_sql"])
    assert "JOIN dim_user" in sql and "is_deleted IS NOT TRUE" in sql and "COUNT(DISTINCT o.user_id)" in sql
    assert "status <> 'pending'" in sql and "제외" in c["reference_note"]


# ---------- scalar 문항의 문장은 하나의 값만 묻는다 ----------
RATIO_WORDS = ("비율", "전환율", "재방문율", "율은")


def scalar_items():
    items = [(c["id"], c["question"], c["expected_kind"]) for c in CANDIDATES]
    for name in ("questions.yaml", "dev_drafts.yaml"):
        items += [(q.id, q.question, q.expected_kind) for q in Q.load_questions(EVAL / name)]
    return [i for i in items if i[2] == "scalar"]


def test_every_scalar_ratio_question_asks_for_a_single_value():
    """scalar 채점은 1행 1열만 통과시킨다. 분자, 분모, 비율을 같이 낼 수 있는 모호한 문장은 불공정하므로 '하나의 값'을 요구해야 한다."""
    vague = [qid for qid, text, _ in scalar_items() if any(w in text for w in RATIO_WORDS) and "하나의 값" not in text]
    assert vague == []


def test_ambiguous_ratio_questions_were_rewritten_to_ask_for_one_value():
    for qid in ("Q21", "Q23", "Q31"):
        c = by_id(qid)
        assert c["expected_kind"] == "scalar" and "하나의 값으로만" in c["question"], qid


def test_dev_ratio_question_whose_wording_is_fixed_is_a_rows_question():
    """DEV01 의 문장은 eval_notes.md 의 개발용 질문과 같아야 해서 고칠 수 없다. 대신 kind 를 rows 로 둔다."""
    dev01 = next(q for q in Q.load_questions(EVAL / "dev_drafts.yaml") if q.id == "DEV01")
    assert dev01.question == "구매 전환율은?" and dev01.expected_kind == "rows"
    assert dev01.tolerance.get("accept_percent_or_ratio") is True


def test_the_other_scalar_questions_are_single_count_or_amount_questions():
    singles = [(qid, text) for qid, text, _ in scalar_items() if not any(w in text for w in RATIO_WORDS)]
    assert len(singles) >= 20
    # "구매 건수는?"(DEV03)은 개발용 문장이 고정돼 있고, 건수 하나를 묻는 형태라서 "건수는?" 도 단일 값 질문으로 본다
    markers = ("몇 명", "몇 건", "몇 개", "얼마", "건수는?")
    assert [qid for qid, text in singles if not any(w in text for w in markers)] == []
