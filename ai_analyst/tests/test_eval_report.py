"""eval/report.py 테스트: Wilson 구간, 개발용/보류 분리, 표, 오염 경고. 호출도 DB 도 없다."""
import io
import json

import pytest

from eval import exposure, grading, report

SHA_A, SHA_B = "a" * 64, "b" * 64


def res(qid, split="heldout", passed=True, failure=None, category="단순 집계", config="D", calls=1, ms=1000):
    return {"id": qid, "split": split, "category": category, "expected_kind": "scalar", "passed": passed,
            "failure": None if passed else (failure or grading.FAIL_VALUE), "detail": "", "generated": None,
            "reference": None, "llm_calls": calls, "tokens": 10, "attempt_types": [], "generated_sql": None,
            "config": config, "elapsed_ms": ms}


def run_of(results, **over):
    base = {"run_id": "run_20261112_093000", "model": "test-model", "configs": ["D"], "calls_used": 7, "hard_cap": 30,
            "stopped_by_call_limit": False, "semantic_sha256": SHA_A, "results": results}
    base.update(over)
    return base


def section(text, title):
    """제목(## ...)부터 다음 제목 전까지."""
    body = text.split(f"## {title}", 1)[1]
    return body.split("\n## ", 1)[0]


# ---------- Wilson 구간 ----------
@pytest.mark.parametrize("passed, total, low, high", [
    (5, 10, 0.2366, 0.7634), (8, 10, 0.4902, 0.9433), (0, 10, 0.0, 0.2775), (10, 10, 0.7225, 1.0),
    (24, 24, 0.8620, 1.0), (1, 1, 0.2065, 1.0), (50, 100, 0.4038, 0.5962),
])
def test_wilson_interval_matches_known_values(passed, total, low, high):
    got = report.wilson_interval(passed, total)
    assert got[0] == pytest.approx(low, abs=0.0005) and got[1] == pytest.approx(high, abs=0.0005)


def test_wilson_interval_stays_inside_0_and_1_and_contains_the_rate():
    for total in range(1, 40):
        for passed in range(total + 1):
            low, high = report.wilson_interval(passed, total)
            assert 0.0 <= low <= passed / total <= high <= 1.0


def test_a_perfect_score_on_a_small_sample_is_not_reported_as_certain():
    low, high = report.wilson_interval(6, 6)
    assert high == 1.0 and low < 0.65  # 6문항 전부 통과해도 하한은 61% 수준이다


def test_wilson_interval_narrows_as_the_sample_grows():
    small, big = report.wilson_interval(8, 10), report.wilson_interval(80, 100)
    assert (small[1] - small[0]) > (big[1] - big[0])


def test_wilson_interval_edge_cases():
    assert report.wilson_interval(0, 0) is None
    for bad in ((-1, 5), (6, 5)):
        with pytest.raises(ValueError):
            report.wilson_interval(*bad)


def test_accuracy_text():
    assert report.accuracy_text(8, 10) == "8/10 = 80.0% (95% 구간 49.0% ~ 94.3%)"
    assert report.accuracy_text(0, 0) == "문항 없음"


# ---------- 개발용과 보류 분리 ----------
RESULTS = ([res(f"D{n}", "dev", category="지표 정의") for n in range(1, 7)]
           + [res(f"H{n}", "heldout") for n in range(1, 9)]
           + [res("H9", "heldout", passed=False), res("H10", "heldout", passed=False, failure=grading.FAIL_GUARD, category="조인")])


def test_dev_and_heldout_accuracy_are_reported_separately():
    acc = section(report.build_report(run_of(RESULTS)), "정확도")
    assert "| 개발용 | 6/6 = 100.0% (95% 구간 61.0% ~ 100.0%) |" in acc
    assert "| 보류 | 8/10 = 80.0% (95% 구간 49.0% ~ 94.3%) |" in acc


def test_report_says_only_heldout_is_evidence_and_intervals_are_wide():
    acc = section(report.build_report(run_of(RESULTS)), "정확도")
    assert "일반화의 근거는 **보류 정확도뿐**이다" in acc
    assert "소표본" in acc and "구간이 넓다" in acc and "Wilson" in acc


def test_missing_split_is_shown_as_no_questions():
    acc = section(report.build_report(run_of([res("D1", "dev")])), "정확도")
    assert "| 보류 | 문항 없음 |" in acc


# ---------- 표 ----------
def test_category_table_splits_dev_and_heldout():
    table = section(report.build_report(run_of(RESULTS)), "카테고리별")
    assert "| 지표 정의 | 6/6 | - |" in table
    assert "| 단순 집계 | - | 8/9 |" in table
    assert "| 조인 | - | 0/1 |" in table
    assert "거절" not in table  # 문항이 없는 카테고리는 줄을 만들지 않는다


def test_failure_table_counts_by_class_and_split():
    extra = RESULTS + [res("D9", "dev", passed=False, failure=grading.FAIL_FALSE_REFUSAL)]
    table = section(report.build_report(run_of(extra)), "실패 분류")
    assert f"| {grading.FAIL_VALUE} | 0 | 1 |" in table
    assert f"| {grading.FAIL_GUARD} | 0 | 1 |" in table
    assert f"| {grading.FAIL_FALSE_REFUSAL} | 1 | 0 |" in table
    assert grading.FAIL_DB not in table  # 0건인 분류는 줄을 만들지 않는다


def test_failure_table_when_nothing_failed():
    assert "(실패 없음)" in section(report.build_report(run_of([res("H1")])), "실패 분류")


def test_average_calls_and_time_use_only_questions_that_ran():
    results = [res("H1", calls=1, ms=1000), res("H2", calls=3, ms=3000),
               res("H3", passed=False, failure=grading.FAIL_CALL_LIMIT, calls=0, ms=0)]
    table = section(report.build_report(run_of(results, stopped_by_call_limit=True)), "평균 호출 수와 응답 시간")
    assert "| D | + 재시도와 거짓 거절 교정 | 2 | 2.00 | 2.00 |" in table


def test_questions_not_run_count_as_failures_and_are_flagged():
    results = [res("H1"), res("H2", passed=False, failure=grading.FAIL_CALL_LIMIT, calls=0, ms=0)]
    text = report.build_report(run_of(results, stopped_by_call_limit=True))
    assert "| 보류 | 1/2 = 50.0%" in text
    assert "호출 상한에 닿아 1건을 실행하지 못했다" in section(text, "경고")


def test_reference_failures_are_flagged_as_an_eval_set_problem():
    text = report.build_report(run_of([res("H1", passed=False, failure=grading.FAIL_REFERENCE)]))
    assert "정답 SQL 을 실행하지 못한 채점이 1건" in section(text, "경고") and "평가셋의 문제" in text


# ---------- 비교 실험 ----------
def test_ablation_table_appears_only_with_several_configs():
    assert "## 비교 실험" not in report.build_report(run_of(RESULTS))
    results = [res("H1", config=c, passed=(c in "CD"), calls=(3 if c == "D" else 1)) for c in "ABCD"]
    results += [res("D1", "dev", config=c) for c in "ABCD"]
    text = report.build_report(run_of(results, configs=["A", "B", "C", "D"]))
    table = section(text, "비교 실험 (구성별)")
    assert "| A | 스키마만 | 1/1 = 100.0%" in table and "0/1 = 0.0%" in table
    assert "| D | + 재시도와 거짓 거절 교정 | 1/1 = 100.0%" in table
    assert "보류 정확도를 우선한다" in table
    calls = section(text, "평균 호출 수와 응답 시간")
    assert "| A | 스키마만 | 2 | 1.00 |" in calls and "| D | + 재시도와 거짓 거절 교정 | 2 | 2.00 |" in calls


def test_headline_accuracy_uses_config_d_when_present():
    results = [res("H1", config="A", passed=False), res("H1", config="D", passed=True)]
    text = report.build_report(run_of(results, configs=["A", "D"]))
    assert "## 정확도 (구성 D" in text and "| 보류 | 1/1 = 100.0%" in section(text, "정확도")


# ---------- 오염 경고 ----------
def registry(*ids, sha=SHA_A):
    return {qid: {"first_run": "run_1", "semantic_sha256": sha, "runs": 1} for qid in ids}


def test_no_warning_when_the_semantic_layer_is_unchanged():
    text = report.build_report(run_of(RESULTS), registry("H1", "H2"), SHA_A)
    assert exposure.WARNING not in text and "## 경고" not in text


def test_warning_when_the_semantic_layer_changed_after_heldout_exposure():
    text = report.build_report(run_of(RESULTS), registry("H2", "H1"), SHA_B)
    warn = section(text, "경고")
    assert "보류 질문 노출 후 시맨틱 레이어가 바뀜: 해당 문항은 개발용으로 이동해야 함" in warn
    assert "문항: H1, H2" in warn and "일반화의 근거로 쓸 수 없다" in warn
    assert "실행 뒤에 semantic_layer.yaml 이 바뀌었다" in warn


def test_warning_when_this_run_used_a_different_layer_than_the_first_exposure():
    """레이어를 고친 뒤 보류 질문을 다시 평가한 실행: 지금 파일과 실행은 같지만 처음 보인 때와 다르다."""
    text = report.build_report(run_of(RESULTS, semantic_sha256=SHA_B), registry("H1", sha=SHA_A), SHA_B)
    warn = section(text, "경고")
    assert exposure.WARNING in warn and "문항: H1" in warn


def test_dev_questions_never_trigger_the_warning():
    text = report.build_report(run_of([res("D1", "dev")], semantic_sha256=SHA_B), {}, SHA_B)
    assert exposure.WARNING not in text


def test_no_registry_and_no_current_hash_means_no_contamination_claim():
    text = report.build_report(run_of(RESULTS))
    assert exposure.WARNING not in text


# ---------- 전체 모양, 명령줄 ----------
def test_report_has_all_sections_and_no_row_values():
    text = report.build_report(run_of(RESULTS))
    for title in ("# FANLOG 평가 리포트", "## 정확도", "## 카테고리별", "## 실패 분류", "## 평균 호출 수와 응답 시간",
                  "## 이 리포트에 없는 것"):
        assert title in text
    assert "run_20261112_093000" in text and "test-model" in text and "7회 (하드 상한 30회)" in text
    assert "행 값은 저장하지 않았다" in text


def test_empty_run_does_not_crash():
    text = report.build_report({"results": []})
    assert "문항 없음" in text and "(실패 없음)" in text


def test_cli_reads_the_result_file_and_the_registry_next_to_it(tmp_path):
    (tmp_path / "run_x.json").write_text(json.dumps(run_of(RESULTS, semantic_sha256="0" * 64)), encoding="utf-8")
    (tmp_path / exposure.REGISTRY_NAME).write_text(json.dumps(registry("H1", sha="0" * 64)), encoding="utf-8")
    out = io.StringIO()
    assert report.main([str(tmp_path / "run_x.json")], out=out) == 0
    text = out.getvalue()
    assert "# FANLOG 평가 리포트" in text and exposure.WARNING in text  # 진짜 semantic_layer.yaml 의 해시는 0000... 이 아니다

    target = tmp_path / "report.md"
    out = io.StringIO()
    assert report.main([str(tmp_path / "run_x.json"), "--out", str(target)], out=out) == 0
    assert target.read_text(encoding="utf-8").startswith("# FANLOG 평가 리포트") and "저장했다" in out.getvalue()
