"""화면의 순수 함수(ui/view.py) 테스트. Streamlit 을 띄우지 않는다."""
from datetime import date
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
@pytest.mark.parametrize("total, blocked", [(0, False), (29, False), (30, True), (31, True), (39, True)])
def test_calls_blocked_at_the_limit(total, blocked):
    assert view.SESSION_CALL_LIMIT == 30
    assert view.calls_blocked(total) is blocked


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
