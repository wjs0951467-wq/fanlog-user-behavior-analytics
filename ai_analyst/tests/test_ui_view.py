"""화면의 순수 함수(ui/view.py) 테스트. Streamlit 을 띄우지 않는다."""
import json
from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import pytest

from ui import view


# ---------- 마크다운 이스케이프 ----------
@pytest.mark.parametrize("text", [
    "![x](http://evil.example/a.png)", "[클릭](http://evil.example)", "11~30%군과 상위 10%군 ~ 끝",
    "**굵게** `코드` # 제목", "$수식$ :red[색] :material/home:", "<img src=x onerror=1>",
])
def test_escape_markdown_puts_a_backslash_before_every_ascii_punctuation(text):
    escaped = view.escape_markdown(text)
    punctuation = "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
    i = 0
    while i < len(escaped):
        if escaped[i] == "\\":  # 이스케이프용 역슬래시는 뒤따르는 글자와 한 쌍이다
            assert i + 1 < len(escaped) and escaped[i + 1] in punctuation
            i += 2
            continue
        assert escaped[i] not in punctuation, f"이스케이프되지 않은 특수문자 {escaped[i]!r} (위치 {i}): {escaped}"
        i += 1
    assert escaped.replace("\\", "") == text  # 역슬래시를 빼면 원문과 같다 (글자를 지우거나 바꾸지 않는다)


def test_escape_markdown_keeps_korean_and_handles_none():
    assert view.escape_markdown("이탈 위험 순위가 높은 팬") == "이탈 위험 순위가 높은 팬"
    assert view.escape_markdown(None) == "" and view.escape_markdown(123) == "123"


# ---------- 세션 한도 ----------
@pytest.mark.parametrize("total, blocked", [(0, False), (19, False), (20, False), (21, True), (29, True), (30, True), (39, True)])
def test_calls_blocked_when_remaining_is_less_than_one_question_can_use(total, blocked):
    assert view.SESSION_CALL_LIMIT == 30
    assert view.calls_blocked(total, 10) is blocked  # 남은 한도가 10회 미만이면 막는다 (20회 사용: 남은 10회는 연다)


# ---------- 일일 상한 ----------
def write_log(tmp_path, lines, day="20260315"):
    folder = tmp_path / "logs"
    folder.mkdir(exist_ok=True)
    (folder / f"agent_{day}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return folder


def record(calls):
    return json.dumps({"question": "q", "usage": {"llm_calls": calls, "tokens": 1}})


NOW = datetime(2026, 3, 15, 12, 0)


def test_daily_calls_sums_todays_log_only(tmp_path):
    folder = write_log(tmp_path, [record(3), record(4), ""])  # 빈 줄은 깨진 줄이 아니다
    write_log(tmp_path, [record(50)], day="20260314")  # 어제 로그는 세지 않는다
    assert view.daily_calls(folder, NOW) == (7, 0)


def test_daily_calls_is_zero_when_there_is_no_log_yet(tmp_path):
    assert view.daily_calls(tmp_path / "없는폴더", NOW) == (0, 0)


@pytest.mark.parametrize("bad_line", ["{깨진 json", json.dumps({"question": "q"}), json.dumps({"usage": {"llm_calls": "많이"}}), "[1, 2]"])
def test_broken_lines_are_skipped_and_counted_so_the_total_is_a_lower_bound(tmp_path, bad_line):
    folder = write_log(tmp_path, [record(3), bad_line, record(4), bad_line])
    assert view.daily_calls(folder, NOW) == (7, 2)  # 읽을 수 있는 줄의 합계(하한값)와 건너뛴 줄 수


def test_a_line_with_broken_bytes_is_skipped_not_fatal(tmp_path):
    folder = tmp_path / "logs"
    folder.mkdir()
    bad = bytes([0xff, 0xfe, 0x00]) + " 깨진 바이트".encode()
    (folder / "agent_20260315.jsonl").write_bytes(record(3).encode() + b"\n" + bad + b"\n" + record(2).encode() + b"\n")
    assert view.daily_calls(folder, NOW) == (5, 1)


def test_daily_calls_is_none_when_the_file_cannot_be_read_at_all(tmp_path):
    (tmp_path / "logs" / "agent_20260315.jsonl").mkdir(parents=True)  # 파일 자리에 폴더가 있다
    assert view.daily_calls(tmp_path / "logs", NOW) == (None, 0)


@pytest.mark.parametrize("used, blocked", [(0, False), (90, False), (91, True), (99, True), (100, True), (150, True), (None, False)])
def test_daily_blocked_uses_the_same_rule_as_the_session_limit(used, blocked):
    assert view.daily_blocked(used, 10, 100) is blocked  # 90 열림 / 91 막힘 / 100 막힘, None(확인 못함)은 막지 않는다
    if used is not None:
        assert view.daily_blocked(used, 10, 100) == view.calls_blocked(used, 10, 100)  # 세션 규칙과 한 함수를 쓴다


def test_too_many_broken_lines_block_even_when_the_lower_bound_is_low():
    assert view.MAX_BROKEN_LINES == 5
    assert [view.daily_blocked(10, 10, 100, skipped) for skipped in (0, 1, 4, 5, 6, 50)] == [False, False, False, True, True, True]
    assert view.log_too_broken(4) is False and view.log_too_broken(5) is True
    assert "로그가 많이 깨져 사용량을 확인할 수 없습니다" in view.BROKEN_LOG_MESSAGE and "logs/" in view.BROKEN_LOG_MESSAGE


def test_the_quota_rule_still_applies_with_few_broken_lines():
    assert view.daily_blocked(91, 10, 100, 4) is True and view.daily_blocked(90, 10, 100, 4) is False


@pytest.mark.parametrize("env, expected", [({}, 100), ({"FANLOG_DAILY_CALL_LIMIT": "250"}, 250), ({"FANLOG_DAILY_CALL_LIMIT": " 5 "}, 5),
                                           ({"FANLOG_DAILY_CALL_LIMIT": "abc"}, 100), ({"FANLOG_DAILY_CALL_LIMIT": "0"}, 100),
                                           ({"FANLOG_DAILY_CALL_LIMIT": "-3"}, 100), ({"FANLOG_DAILY_CALL_LIMIT": ""}, 100)])
def test_daily_limit_comes_from_the_environment_with_a_safe_default(env, expected):
    assert view.DAILY_CALL_LIMIT == 100 and view.daily_limit(env) == expected


def test_usage_text_shows_total_and_sources():
    usage = {"llm_calls": 4, "tokens": 12345, "by_source": {"agent": {"llm_calls": 2, "tokens": 1},
                                                            "ask_data": {"llm_calls": 2, "tokens": 1},
                                                            "get_churn_segments": {"llm_calls": 0, "tokens": 0}}}
    text = view.usage_text(usage)
    assert "LLM 호출 4회" in text and "agent 2회" in text and "ask_data 2회" in text and "12,345" in text
    assert "get_churn_segments" not in text  # 0회인 출처는 생략
    assert view.usage_text(None) == "LLM 호출 0회"


# ---------- 표 ----------
def test_result_table_hides_user_id_columns_and_reports_them():
    df, hidden = view.result_table(["user_id", "n", "Fan_User_ID"], [["u1", 3, "x"], ["u2", 4, "y"]])
    assert list(df.columns) == ["n"] and df["n"].tolist() == [3, 4]
    assert hidden == ["user_id", "Fan_User_ID"]
    assert "u1" not in df.to_csv()  # 값도 표에 남지 않는다


def test_result_table_converts_odd_types_and_dedupes_names():
    df, hidden = view.result_table(["a", "a", "d"], [[Decimal("1.5"), 2, date(2026, 3, 31)]])
    assert list(df.columns) == ["a", "a_2", "d"] and hidden == []
    assert df.iloc[0].tolist() == [1.5, 2, "2026-03-31"]


def test_result_table_skips_rows_with_the_wrong_width_and_handles_empty():
    df, _ = view.result_table(["a", "b"], [[1, 2], [3]])
    assert len(df) == 1
    empty, _ = view.result_table([], [])
    assert empty.empty


def test_cells_frame_renames_and_never_has_user_ids():
    cells = [{"tier": "상위 10%군", "purchase": "있음", "comm_gap": "공백 4일 이상", "n": 100, "share": 0.1, "note": ""}]
    df = view.cells_frame(cells)
    assert list(df.columns) == ["군", "구매 경험", "소통 공백", "인원", "비고"]  # share 같은 나머지는 그리지 않는다
    no_gap = view.cells_frame([{"tier": "나머지", "purchase": "없음", "n": 5, "note": "해석 보류"}])
    assert list(no_gap.columns) == ["군", "구매 경험", "인원", "비고"]


def test_evidence_frames():
    tiers = [{"tier": "상위 10%군", "rows_in_test_period": 1400, "positives": 105, "actual_rate_pct": 7.5,
              "rate_ci95_pct": [6.0, 9.0], "lift_vs_all": 1.9, "active_again_within_14d_pct": 92.5}]
    df = view.tiers_frame(tiers)
    assert df.iloc[0]["실제 비율(%)"] == 7.5 and df.iloc[0]["95% 구간(%)"] == "6.0 ~ 9.0"
    assert df.iloc[0]["14일 안에 다시 활동한 비율(%)"] == 92.5
    versus = view.versus_frame([{"tier": "상위 10%군", "model_rate_pct": 7.5, "baseline_rate_pct": 7.0, "verdict": "구분 안 됨"}])
    assert versus.iloc[0].tolist() == ["상위 10%군", 7.5, 7.0, "구분 안 됨"]


def test_scenario_and_round_frames():
    s = view.scenarios_frame([{"assumed_reduction_pct": 50, "target_rate_pct": 3.8, "needed_per_group": 589, "feasible": False}])
    assert s.iloc[0].tolist() == [50, 3.8, 589, "불가능"]
    r = view.rounds_frame([{"assumed_reduction_pct": 50, "needed_per_group": 589, "per_group_per_round": 78,
                            "rounds_needed": 8, "days": 112}])
    assert r.iloc[0].tolist() == [50, 589, 78, 8, 112]


def test_history_frame_has_reason_and_args():
    steps = [{"step": 1, "tool": "ask_data", "reason": "휴면 수를 알아보려고", "args": {"question": "휴면 팬은?"},
              "status": "ok", "llm_calls": 1, "elapsed_ms": 12},
             {"step": 2, "tool": "x", "reason": None, "args": "{깨진 json", "status": "error", "llm_calls": 0, "elapsed_ms": 1}]
    df = view.history_frame(steps)
    assert df.iloc[0]["이유(reason)"] == "휴면 수를 알아보려고" and "휴면 팬은?" in df.iloc[0]["인자"]
    assert df.iloc[1]["이유(reason)"] == "" and df.iloc[1]["인자"] == "{깨진 json"  # 깨진 인자는 원문 그대로


def test_attempts_frame():
    df = view.attempts_frame([{"sql": None, "error_type": "parse", "error_message": "x"},
                              {"sql": "SELECT 1", "error_type": "none", "error_message": None}])
    assert df["시도"].tolist() == [1, 2] and df.iloc[0]["SQL"] == "" and df.iloc[1]["오류"] == ""
    assert isinstance(df, pd.DataFrame)


# =====================================================================
# 보안 점검: 화면의 ID 가리기, 1000행 안내
# =====================================================================
def test_aliased_user_ids_are_masked_by_value_in_the_table():
    """컬럼 이름이 user_id 가 아니어도(별칭) 값이 사용자 ID 모양이면 표에서 가려진다 (이름 기준 숨김의 빈틈 보완)."""
    df, hidden = view.result_table(["id", "n"], [["user_000123", 3], ["txn_000001", 4]])
    assert df["id"].tolist() == ["[ID]", "txn_000001"] and hidden == []  # 주문번호는 그대로


def test_result_table_masks_ids_inside_longer_text_cells():
    df, _ = view.result_table(["memo"], [["user_000123 님이 구매"]])
    assert df["memo"].tolist() == ["[ID] 님이 구매"]
