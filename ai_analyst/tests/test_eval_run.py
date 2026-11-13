"""eval/run_eval.py 테스트. LLM(ask), DB(정답 SQL 실행), 로그는 모두 가짜다. 실제 OpenAI 호출 0회, DB 접속 0회."""
import io
import json
from datetime import datetime

import pytest
import yaml

from app import agent, text2sql
from eval import ablation, exposure, grading, run_eval
from eval.questions import parse_questions
from ui import view

NOW = datetime(2026, 11, 12, 9, 30, 0)
ALLOW = {run_eval.ALLOW_ENV: "1", "FANLOG_MODEL": "test-model"}


def item(qid, split="heldout", kind="scalar", verified=True, **over):
    base = {"id": qid, "question": f"{qid} 질문", "category": "거절" if kind == "refusal" else "단순 집계", "split": split,
            "expected_kind": kind, "verified": verified, "source": "test",
            "reference_sql": None if kind == "refusal" else "SELECT COUNT(*) FROM dim_user"}
    base.update(over)
    return base


def write_questions(tmp_path, items):
    path = tmp_path / "questions.yaml"
    path.write_text(yaml.safe_dump({"questions": items}, allow_unicode=True), encoding="utf-8")
    return path


def answered(value=10, calls=1):
    return {"question": "q", "sql": "SELECT 1 LIMIT 1000", "columns": ["n"], "rows": [[value]], "row_count": 1,
            "summary": None, "attempts": [{"sql": "SELECT 1", "error_type": "none", "error_message": None}],
            "error": None, "usage": {"llm_calls": calls, "tokens": 40}}


def refused():
    return {"question": "q", "sql": None, "columns": [], "rows": [], "row_count": 0, "summary": None,
            "attempts": [{"sql": None, "error_type": "refusal", "error_message": "없음"}],
            "error": "CANNOT_ANSWER: 없음", "usage": {"llm_calls": 1, "tokens": 20}}


class Fakes:
    """ask, 정답 SQL 실행, 로그를 가짜로 바꾸고 무엇이 불렸는지 기록한다."""

    def __init__(self, replies=None, reference=(["n"], [[10]])):
        self.replies, self.reference = replies or {}, reference
        self.asked, self.references, self.logged = [], [], []

    def ask(self, question):
        self.asked.append(question)
        reply = self.replies.get(question, answered())
        if isinstance(reply, Exception):
            raise reply
        return reply

    def ref(self, sql):
        self.references.append(sql)
        if isinstance(self.reference, Exception):
            raise self.reference
        return self.reference

    def log(self, out):
        self.logged.append(out)

    def deps(self):
        return {"ask_fn": self.ask, "reference_fn": self.ref, "log_fn": self.log, "now": NOW}


def call(argv, env=None, fakes=None):
    fakes = fakes or Fakes()
    out = io.StringIO()
    code = run_eval.main(argv, env=env or {}, out=out, **fakes.deps())
    return code, out.getvalue(), fakes


def args_for(tmp_path, items, *extra):
    return ["--questions", str(write_questions(tmp_path, items)), "--out", str(tmp_path / "results"), *extra]


def result_files(tmp_path):
    folder = tmp_path / "results"
    return sorted(folder.glob("run_*.json")) if folder.exists() else []


# ---------- 계획 ----------
def test_worst_case_calls_by_config():
    qs = parse_questions([item("A1"), item("A2"), item("A3")])
    assert run_eval.worst_case_calls(qs, ["D"]) == 9
    assert run_eval.worst_case_calls(qs, ["A", "B", "C"]) == 9
    assert run_eval.worst_case_calls(qs, ["A", "B", "C", "D"]) == 18
    assert run_eval.worst_case_calls([], ["D"]) == 0


@pytest.mark.parametrize("text", ["", " , ", "E", "A,A", "A,X"])
def test_bad_config_lists_are_rejected(text):
    with pytest.raises(ValueError):
        run_eval.parse_configs(text)


def test_config_list_is_normalized():
    assert run_eval.parse_configs(" a, d ") == ["A", "D"]


# ---------- dry-run ----------
def test_default_is_a_dry_run_with_no_calls_and_no_files(tmp_path):
    code, text, fakes = call(args_for(tmp_path, [item("H1"), item("D1", split="dev", verified=False)]))
    assert code == run_eval.EXIT_OK
    assert "dry-run" in text and "OpenAI 호출 0회" in text and "H1" in text and "D1" in text
    assert "예상 최대 호출 수: 6회" in text and "--confirm-calls 6" in text and "미검증 1" in text
    assert fakes.asked == [] and fakes.references == [] and fakes.logged == [] and result_files(tmp_path) == []


def test_dry_run_with_all_configs_shows_each_config(tmp_path):
    code, text, fakes = call(args_for(tmp_path, [item("H1"), item("H2")], "--configs", "A,B,C,D"))
    assert code == 0 and "예상 최대 호출 수: 12회" in text and fakes.asked == []
    for config in "ABCD":
        assert f"구성 {config}" in text


def test_allow_env_alone_does_not_run(tmp_path):
    code, text, fakes = call(args_for(tmp_path, [item("H1")]), env=ALLOW)
    assert code == 0 and "dry-run" in text and "실행하지 않았다" in text and fakes.asked == []


def test_dry_run_works_on_the_real_question_file(tmp_path):
    code, text, fakes = call(["--out", str(tmp_path / "results")])
    assert code == 0 and "dry-run" in text and fakes.asked == [] and result_files(tmp_path) == []


# ---------- 실제 실행의 관문 ----------
@pytest.mark.parametrize("env, extra, items, word", [
    ({"FANLOG_MODEL": "m"}, ["--confirm-calls", "3"], [item("H1")], run_eval.ALLOW_ENV),              # 환경변수 없음
    ({run_eval.ALLOW_ENV: "0", "FANLOG_MODEL": "m"}, ["--confirm-calls", "3"], [item("H1")], run_eval.ALLOW_ENV),
    ({run_eval.ALLOW_ENV: "true", "FANLOG_MODEL": "m"}, ["--confirm-calls", "3"], [item("H1")], run_eval.ALLOW_ENV),
    (ALLOW, ["--confirm-calls", "2"], [item("H1")], "다르다"),                                         # 숫자가 틀림
    (ALLOW, ["--confirm-calls", "30"], [item("H1")], "다르다"),
    (ALLOW, ["--confirm-calls", "3"], [item("H1", verified=False)], "verified"),                       # 미검증 문항
    (ALLOW, ["--confirm-calls", "6"], [item("H1"), item("H2", verified=False)], "H2"),
    ({run_eval.ALLOW_ENV: "1"}, ["--confirm-calls", "3"], [item("H1")], "FANLOG_MODEL"),               # 모델 없음
    (ALLOW, ["--confirm-calls", "3", "--max-calls", "0"], [item("H1")], "--max-calls"),
    (ALLOW, ["--confirm-calls", "0", "--split", "dev"], [item("H1")], "고른 문항이 없다"),
])
def test_real_run_is_refused_unless_every_condition_holds(tmp_path, env, extra, items, word):
    code, text, fakes = call(args_for(tmp_path, items, *extra), env=env)
    assert code == run_eval.EXIT_REFUSED and "실행 거부" in text and word in text
    assert fakes.asked == [] and fakes.references == [] and fakes.logged == [] and result_files(tmp_path) == []


def test_all_refusal_reasons_are_listed_together(tmp_path):
    code, text, fakes = call(args_for(tmp_path, [item("H1", verified=False)], "--confirm-calls", "99"), env={})
    assert code == run_eval.EXIT_REFUSED and fakes.asked == []
    for word in (run_eval.ALLOW_ENV, "다르다", "verified", "FANLOG_MODEL"):
        assert word in text


def test_the_current_question_files_cannot_be_run_for_real(tmp_path):
    """지금 questions.yaml 은 전부 미검증이라, 허용 환경변수와 맞는 숫자를 줘도 실행되지 않는다."""
    # --out 을 임시 폴더로 준다: 관문이 망가져도 이 테스트가 진짜 eval/results/ 에 파일을 쓰지 않게 한다
    code, text, fakes = call(["--confirm-calls", "6", "--out", str(tmp_path / "results")], env=ALLOW)
    assert code == run_eval.EXIT_REFUSED and "verified" in text and fakes.asked == []
    assert result_files(tmp_path) == []


@pytest.mark.parametrize("extra", [["--ids", "없는id"], ["--configs", "Z"]])
def test_bad_arguments_stop_before_anything_runs(tmp_path, extra):
    code, text, fakes = call(args_for(tmp_path, [item("H1")], *extra), env=ALLOW)
    assert code == run_eval.EXIT_REFUSED and "중단" in text and fakes.asked == []


def test_a_broken_question_file_stops_before_anything_runs(tmp_path):
    code, text, fakes = call(args_for(tmp_path, [item("H1", category="기타")], "--confirm-calls", "3"), env=ALLOW)
    assert code == run_eval.EXIT_REFUSED and "category" in text and fakes.asked == []


# ---------- 실제 실행 (가짜 부품) ----------
def test_a_confirmed_run_asks_grades_logs_and_saves(tmp_path):
    items = [item("H1"), item("D1", split="dev"), item("R1", kind="refusal")]
    fakes = Fakes(replies={"H1 질문": answered(10), "D1 질문": answered(11, calls=2), "R1 질문": refused()})
    code, text, _ = call(args_for(tmp_path, items, "--confirm-calls", "9"), env=ALLOW, fakes=fakes)
    assert code == 0 and fakes.asked == ["H1 질문", "D1 질문", "R1 질문"]
    assert len(fakes.logged) == 3                      # 질문마다 일일 합계 로그에 남긴다
    assert len(fakes.references) == 2                  # 거절 문항에는 정답 SQL 이 없다
    assert "호출 4회 / 상한 9회" in text and "통과 2/3" in text

    record = json.loads(result_files(tmp_path)[0].read_text(encoding="utf-8"))
    assert record["run_id"] == "run_20261112_093000" and "model" in record
    assert record["configs"] == ["D"] and record["calls_used"] == 4 and record["hard_cap"] == 9
    assert record["stopped_by_call_limit"] is False and len(record["semantic_sha256"]) == 64
    by_id = {r["id"]: r for r in record["results"]}
    assert by_id["H1"]["passed"] is True and by_id["R1"]["passed"] is True
    assert by_id["D1"]["passed"] is False and by_id["D1"]["failure"] == grading.FAIL_VALUE
    assert all(r["config"] == "D" and "elapsed_ms" in r for r in record["results"])


def test_saved_results_contain_no_row_values(tmp_path):
    secret_rows = [["user_000123", "비밀이름", 98765.4321]]
    out = answered()
    out.update(columns=["id", "name", "v"], rows=secret_rows)
    fakes = Fakes(replies={"H1 질문": out}, reference=(["id", "name", "v"], secret_rows))
    call(args_for(tmp_path, [item("H1", kind="rows")], "--confirm-calls", "3"), env=ALLOW, fakes=fakes)
    text = result_files(tmp_path)[0].read_text(encoding="utf-8")
    for secret in ("user_000123", "비밀이름", "98765"):
        assert secret not in text
    assert json.loads(text)["results"][0]["passed"] is True


def test_heldout_exposure_is_recorded_only_for_heldout_questions_that_were_asked(tmp_path):
    call(args_for(tmp_path, [item("H1"), item("D1", split="dev")], "--confirm-calls", "6"), env=ALLOW)
    registry = exposure.load_registry(tmp_path / "results" / exposure.REGISTRY_NAME)
    assert set(registry) == {"H1"} and registry["H1"]["first_run"] == "run_20261112_093000"
    assert registry["H1"]["semantic_sha256"] == exposure.file_sha256(exposure.SEMANTIC_PATH)


def test_dev_only_run_writes_no_exposure_registry(tmp_path):
    call(args_for(tmp_path, [item("D1", split="dev")], "--confirm-calls", "3"), env=ALLOW)
    assert not (tmp_path / "results" / exposure.REGISTRY_NAME).exists()


# ---------- 하드 상한 ----------
def test_max_calls_stops_the_run_before_the_cap_is_exceeded(tmp_path):
    items = [item(f"H{n}") for n in range(1, 5)]
    fakes = Fakes(replies={f"H{n} 질문": answered(10, calls=3) for n in range(1, 5)})
    code, text, _ = call(args_for(tmp_path, items, "--confirm-calls", "12", "--max-calls", "7"), env=ALLOW, fakes=fakes)
    record = json.loads(result_files(tmp_path)[0].read_text(encoding="utf-8"))
    assert code == 0 and fakes.asked == ["H1 질문", "H2 질문"]          # 6회 사용 후, 다음 질문(최대 3회)은 7을 넘는다
    assert record["calls_used"] == 6 <= record["hard_cap"] == 7 and record["stopped_by_call_limit"] is True
    assert [r["failure"] for r in record["results"]] == [None, None, grading.FAIL_CALL_LIMIT, grading.FAIL_CALL_LIMIT]
    assert "호출 상한에 닿아" in text


def test_the_cap_check_uses_the_worst_case_of_the_next_question():
    qs = parse_questions([item("H1"), item("H2"), item("H3")])
    fakes = Fakes(replies={"H1 질문": answered(10, calls=1), "H2 질문": answered(10, calls=3)})
    outcome = run_eval.run(qs, ["D"], 5, fakes.ask, fakes.ref, fakes.log)
    assert fakes.asked == ["H1 질문", "H2 질문"] and outcome["calls_used"] == 4 and outcome["stopped_by_call_limit"]
    assert outcome["results"][2]["failure"] == grading.FAIL_CALL_LIMIT and outcome["results"][2]["llm_calls"] == 0


def test_after_stopping_no_later_config_is_run_either():
    qs = parse_questions([item("H1"), item("H2")])
    fakes = Fakes()
    outcome = run_eval.run(qs, ["A", "D"], 2, fakes.ask, fakes.ref, fakes.log)
    assert fakes.asked == ["H1 질문", "H2 질문"] and outcome["calls_used"] == 2  # 구성 A 만 실행됐다
    assert [(r["config"], r["failure"]) for r in outcome["results"]][2:] == [("D", grading.FAIL_CALL_LIMIT)] * 2


def test_a_question_that_overspends_stops_the_run():
    qs = parse_questions([item("H1"), item("H2")])
    fakes = Fakes(replies={"H1 질문": answered(10, calls=9)})  # 질문 하나가 예상(3회)보다 많이 썼다
    outcome = run_eval.run(qs, ["D"], 6, fakes.ask, fakes.ref, fakes.log)
    assert fakes.asked == ["H1 질문"] and outcome["stopped_by_call_limit"] is True


def test_max_calls_above_the_confirmed_number_is_capped_at_the_confirmed_number(tmp_path):
    code, text, _ = call(args_for(tmp_path, [item("H1")], "--confirm-calls", "3", "--max-calls", "999"), env=ALLOW)
    assert code == 0 and "하드 상한 3회" in text


# ---------- 비교 실험 구성과 원복 ----------
def test_each_config_runs_every_question_and_reference_sql_runs_once_per_question():
    qs = parse_questions([item("H1"), item("H2")])
    fakes = Fakes()
    outcome = run_eval.run(qs, ["A", "B", "C", "D"], 100, fakes.ask, fakes.ref, fakes.log)
    assert len(fakes.asked) == 8 and len(fakes.references) == 2
    assert [r["config"] for r in outcome["results"]] == ["A", "A", "B", "B", "C", "C", "D", "D"]
    assert outcome["asked_heldout"] == ["H1", "H2"]


def test_the_config_is_active_while_asking_and_the_app_is_restored_afterwards():
    seen = []

    def ask(question):
        seen.append(text2sql.MAX_SQL_CALLS)
        return answered()

    before = (text2sql.build_system_prompt, text2sql.MAX_SQL_CALLS)
    run_eval.run(parse_questions([item("H1")]), ["A", "D"], 100, ask, Fakes().ref, lambda out: None)
    assert seen == [1, 3]
    assert (text2sql.build_system_prompt, text2sql.MAX_SQL_CALLS) == before and ablation.is_restored()


def test_the_app_is_restored_when_ask_raises():
    before = (text2sql.build_system_prompt, text2sql.MAX_SQL_CALLS)
    fakes = Fakes(replies={"H1 질문": RuntimeError("예상 못한 오류")})
    with pytest.raises(RuntimeError):
        run_eval.run(parse_questions([item("H1")]), ["A"], 100, fakes.ask, fakes.ref, fakes.log)
    assert (text2sql.build_system_prompt, text2sql.MAX_SQL_CALLS) == before and ablation.is_restored()


# ---------- 정답 SQL, 로그, 시간 ----------
def test_reference_failure_is_recorded_by_type_name_only():
    fakes = Fakes(reference=RuntimeError("host=db.internal password=secret"))
    outcome = run_eval.run(parse_questions([item("H1")]), ["D"], 100, fakes.ask, fakes.ref, fakes.log)
    r = outcome["results"][0]
    assert r["failure"] == grading.FAIL_REFERENCE and r["detail"] == "RuntimeError"
    assert "secret" not in json.dumps(outcome, ensure_ascii=False)


def test_a_log_failure_does_not_stop_the_evaluation():
    def broken_log(out):
        raise OSError("디스크 가득")

    fakes = Fakes()
    outcome = run_eval.run(parse_questions([item("H1"), item("H2")]), ["D"], 100, fakes.ask, fakes.ref, broken_log)
    assert len(fakes.asked) == 2 and all(r["passed"] for r in outcome["results"])


def test_elapsed_time_is_measured_around_the_ask_call():
    ticks = iter([1.0, 1.25, 5.0, 5.5])
    outcome = run_eval.run(parse_questions([item("H1"), item("H2")]), ["D"], 100, Fakes().ask, Fakes().ref,
                           lambda out: None, clock=lambda: next(ticks))
    assert [r["elapsed_ms"] for r in outcome["results"]] == [250, 500]


def test_default_log_writes_to_the_same_daily_total_as_the_screen(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "LOG_DIR", tmp_path / "logs")  # 진짜 logs/ 에 쓰지 않는다
    run_eval.default_log(answered(calls=2))
    run_eval.default_log(refused())
    assert view.daily_calls(tmp_path / "logs") == (3, 0)  # 화면의 "오늘 전체 호출"이 평가 호출도 센다
    lines = next((tmp_path / "logs").glob("agent_*.jsonl")).read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["source"] for line in lines] == ["eval", "eval"] and '"rows"' not in lines[0]


def test_default_ask_turns_the_summary_off(monkeypatch):
    seen = {}

    def fake_ask(question, summarize_result=True):
        seen.update(question=question, summarize_result=summarize_result)
        return answered()

    monkeypatch.setattr(text2sql, "ask", fake_ask)
    run_eval.default_ask("질문")
    assert seen == {"question": "질문", "summarize_result": False}


def test_default_reference_goes_through_the_guard(monkeypatch):
    from app import db
    seen = []
    monkeypatch.setattr(db, "run_query", lambda sql: (seen.append(sql), (["n"], [[1]]))[1])
    assert run_eval.default_reference("SELECT COUNT(*) FROM dim_user") == (["n"], [[1]])
    assert "LIMIT" in seen[0].upper()                      # 가드레일이 LIMIT 을 붙인 SQL 만 실행된다
    with pytest.raises(Exception):
        run_eval.default_reference("DELETE FROM dim_user")
    assert len(seen) == 1                                  # 막힌 SQL 은 DB 까지 가지 않는다
