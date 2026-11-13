"""평가 질문 파일(questions.yaml)의 스키마와 로더.

왜 엄격하게 읽는가
- 평가셋은 "정답"의 근거다. 오타 하나(verfied: true)로 검증하지 않은 문항이 검증된 것처럼 쓰이면 안 된다.
  그래서 모르는 키는 거부하고, verified 는 정확히 true/false 만 받고, 기본값은 false 다.
- verified 가 false 인 문항은 실제 실행 모드에서 거부한다 (require_verified). 정답 SQL 은 사람이 DBeaver 로 직접 확인해야 한다.
- verified: true 인데 사람의 확인 근거(verification)가 없으면 로딩 단계에서 막는다. 근거 없는 true 를 막기 위해서다.
  verification 은 사람이 남기는 기록이고 채점에는 쓰지 않는다 (채점은 SQL 실행 결과끼리 비교한다).
"""
import datetime
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

CATEGORIES = ("단순 집계", "조인", "지표 정의", "기간 해석", "함정", "거절")
SPLITS = ("dev", "heldout")
KINDS = ("scalar", "rows", "refusal")
TOLERANCE_KEYS = ("abs", "rel", "accept_percent_or_ratio")

REQUIRED = ("id", "question", "category", "split", "expected_kind", "source")
OPTIONAL = ("verified", "reference_sql", "tolerance", "notes", "ordered", "verification")
# verification: 필수 다섯 개는 항상 있어야 하고, trap_check 는 함정을 확인했을 때만 적는다 (어느 문항이든 쓸 수 있다)
VERIFICATION_REQUIRED = ("verified_by", "verified_on", "method", "result_value", "independent_check")
VERIFICATION_OPTIONAL = ("trap_check",)
DATE_FORMAT = re.compile(r"\d{4}-\d{2}-\d{2}")


class QuestionFileError(ValueError):
    """질문 파일이 스키마에 맞지 않는다. 메시지에 문제를 모두 모아서 알려준다."""


class UnverifiedQuestionError(ValueError):
    """사람이 검증하지 않은(verified: false) 문항으로 실제 실행을 하려고 했다."""


@dataclass(frozen=True)
class Question:
    id: str
    question: str
    category: str
    split: str
    expected_kind: str
    source: str
    verified: bool = False
    reference_sql: str | None = None
    tolerance: dict = field(default_factory=dict)
    notes: str = ""
    ordered: bool = False  # rows 문항에서 행 순서까지 맞아야 하는가 (질문이 순서를 요구할 때만 true)
    verification: dict = field(default_factory=dict)  # 사람의 확인 기록. 채점에는 쓰지 않는다


def _check_tolerance(value, problems: list, where: str) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        problems.append(f"{where}: tolerance 는 매핑이어야 한다")
        return {}
    for key, v in value.items():
        if key not in TOLERANCE_KEYS:
            problems.append(f"{where}: tolerance 에 모르는 키 {key!r}")
        elif key == "accept_percent_or_ratio":
            if not isinstance(v, bool):
                problems.append(f"{where}: accept_percent_or_ratio 는 true/false 여야 한다")
        elif isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
            problems.append(f"{where}: tolerance.{key} 는 0 이상의 숫자여야 한다")
    return dict(value)


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _valid_date(value) -> bool:
    """YYYY-MM-DD 글자(실제 있는 날짜)나 YAML 이 읽은 날짜. 시각이 붙은 값(datetime)은 받지 않는다."""
    if isinstance(value, datetime.datetime):
        return False
    if isinstance(value, datetime.date):
        return True
    if not isinstance(value, str) or not DATE_FORMAT.fullmatch(value):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _check_verification(value, verified: bool, problems: list, where: str) -> dict:
    """verification 을 검사한다. where 에 문항 id 가 들어 있어서 오류 문구가 어느 문항의 어느 키인지 알려준다."""
    if value is None or value == {}:
        if verified:
            problems.append(f"{where}: verified: true 인데 verification 이 없거나 비어 있다 "
                            f"(사람의 확인 근거가 필요하다: {', '.join(VERIFICATION_REQUIRED)})")
        return {}
    if not isinstance(value, dict):
        problems.append(f"{where}: verification 은 매핑이어야 한다")
        return {}
    for key in value:
        if key not in VERIFICATION_REQUIRED + VERIFICATION_OPTIONAL:
            problems.append(f"{where}: verification 에 모르는 키 {key!r}")
    for key in VERIFICATION_REQUIRED:
        if key not in value:
            problems.append(f"{where}: verification.{key} 가 없다")
        elif key == "verified_on":
            if not _valid_date(value[key]):
                problems.append(f"{where}: verification.verified_on 은 YYYY-MM-DD 형식의 실제 날짜여야 한다 (받은 값: {value[key]!r})")
        elif key == "result_value":
            v = value[key]
            if _is_blank(v):
                problems.append(f"{where}: verification.result_value 가 비어 있다")
            elif isinstance(v, bool) or not isinstance(v, (str, int, float)):
                problems.append(f"{where}: verification.result_value 는 글자나 숫자여야 한다")
        elif _is_blank(value[key]) or not isinstance(value[key], str):
            problems.append(f"{where}: verification.{key} 가 비어 있다 (비어 있지 않은 글자여야 한다)")
    if "trap_check" in value and (_is_blank(value["trap_check"]) or not isinstance(value["trap_check"], str)):
        problems.append(f"{where}: verification.trap_check 가 비어 있다 (적을 때는 내용이 있어야 한다)")
    return dict(value)


def parse_questions(items) -> list[Question]:
    """YAML 에서 읽은 목록을 Question 목록으로 바꾼다. 문제가 하나라도 있으면 전부 모아서 QuestionFileError."""
    if not isinstance(items, list):
        raise QuestionFileError("질문 파일의 questions 는 목록이어야 한다")
    problems, questions, seen_ids, seen_texts = [], [], set(), set()
    for index, item in enumerate(items, 1):
        where = f"{index}번째 항목"
        if not isinstance(item, dict):
            problems.append(f"{where}: 매핑이 아니다")
            continue
        where = f"{where}({item.get('id', '?')})"
        unknown = [k for k in item if k not in REQUIRED + OPTIONAL]
        if unknown:  # 오타(verfied 등)를 조용히 무시하면 기본값 false 가 아니라 "의도와 다른 값"이 된다
            problems.append(f"{where}: 모르는 키 {unknown}")
        missing = [k for k in REQUIRED if not isinstance(item.get(k), str) or not item[k].strip()]
        if missing:
            problems.append(f"{where}: 필수 항목이 없거나 문자열이 아니다 {missing}")
            continue
        if item["category"] not in CATEGORIES:
            problems.append(f"{where}: category 는 {CATEGORIES} 중 하나여야 한다")
        if item["split"] not in SPLITS:
            problems.append(f"{where}: split 은 {SPLITS} 중 하나여야 한다")
        kind = item["expected_kind"]
        if kind not in KINDS:
            problems.append(f"{where}: expected_kind 는 {KINDS} 중 하나여야 한다")
        verified = item.get("verified", False)
        if not isinstance(verified, bool):  # "yes", 1 같은 값은 받지 않는다
            problems.append(f"{where}: verified 는 true/false 여야 한다")
            verified = False
        sql = item.get("reference_sql")
        if sql is not None and not isinstance(sql, str):
            problems.append(f"{where}: reference_sql 은 문자열이어야 한다")
            sql = None
        sql = sql.strip() if sql and sql.strip() else None
        if kind == "refusal" and sql:
            problems.append(f"{where}: 거절이 정답인 문항에는 reference_sql 을 쓰지 않는다")
        if kind in ("scalar", "rows") and not sql:
            problems.append(f"{where}: {kind} 문항에는 reference_sql 이 필요하다")
        ordered = item.get("ordered", False)
        if not isinstance(ordered, bool):
            problems.append(f"{where}: ordered 는 true/false 여야 한다")
            ordered = False
        if ordered and kind != "rows":
            problems.append(f"{where}: ordered 는 rows 문항에만 쓴다")
        notes = item.get("notes") or ""
        if not isinstance(notes, str):
            problems.append(f"{where}: notes 는 문자열이어야 한다")
            notes = ""
        verification = _check_verification(item.get("verification"), verified, problems, where)
        if item["id"] in seen_ids:
            problems.append(f"{where}: id 가 중복된다")
        if item["question"].strip() in seen_texts:
            problems.append(f"{where}: 같은 질문이 두 번 있다")
        seen_ids.add(item["id"])
        seen_texts.add(item["question"].strip())
        questions.append(Question(
            id=item["id"].strip(), question=item["question"].strip(), category=item["category"], split=item["split"],
            expected_kind=kind, source=item["source"].strip(), verified=verified, reference_sql=sql,
            tolerance=_check_tolerance(item.get("tolerance"), problems, where), notes=notes.strip(), ordered=ordered,
            verification=verification))
    if problems:
        raise QuestionFileError("질문 파일 오류:\n- " + "\n- ".join(problems))
    return questions


def load_questions(path) -> list[Question]:
    """questions.yaml 을 읽는다. 파일 모양: {questions: [ ... ]}."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "questions" not in data:
        raise QuestionFileError("질문 파일의 맨 위는 questions 키를 가진 매핑이어야 한다")
    return parse_questions(data["questions"])


def require_verified(questions: list[Question]) -> None:
    """실제 실행 모드의 관문: 검증되지 않은 문항이 하나라도 있으면 실행하지 않는다."""
    unverified = [q.id for q in questions if not q.verified]
    if unverified:
        raise UnverifiedQuestionError(
            "verified: false 인 문항은 실제 실행에서 쓸 수 없다 (사람이 DBeaver 로 정답 SQL 을 확인한 뒤 true 로 바꾼다): "
            + ", ".join(unverified))


def select(questions: list[Question], split: str = "all", ids: list[str] | None = None) -> list[Question]:
    """split(dev / heldout / all)과 id 목록으로 고른다. 없는 id 를 주면 조용히 넘어가지 않고 알려준다."""
    if split not in SPLITS + ("all",):
        raise ValueError(f"split 은 {SPLITS + ('all',)} 중 하나여야 한다")
    picked = [q for q in questions if split == "all" or q.split == split]
    if ids:
        known = {q.id for q in picked}
        missing = [i for i in ids if i not in known]
        if missing:
            raise ValueError(f"해당 split 에 없는 id: {missing}")
        picked = [q for q in picked if q.id in ids]
    return picked
