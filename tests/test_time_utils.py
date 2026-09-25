import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "generation"))

from time_utils import (  # noqa: E402
    KST,
    UTC,
    clip_to_period,
    parse_utc,
    random_instant_after,
    random_utc_timestamp,
)


def _is_utc_aware(dt: datetime) -> bool:
    return dt.tzinfo is not None and dt.utcoffset() == timedelta(0)


def test_parse_utc_returns_utc_aware():
    result = parse_utc("2026-03-15T10:00:00Z")
    assert _is_utc_aware(result)
    assert result == datetime(2026, 3, 15, 10, 0, 0, tzinfo=UTC)


def test_random_utc_timestamp_with_kst_inputs_returns_utc():
    rng = np.random.default_rng(42)
    start = datetime(2026, 1, 1, tzinfo=KST)
    end = datetime(2026, 1, 2, tzinfo=KST)
    for _ in range(50):
        result = random_utc_timestamp(rng, start, end)
        assert _is_utc_aware(result)
        assert start <= result < end


def test_random_instant_after_with_kst_inputs_returns_utc_and_strictly_after():
    rng = np.random.default_rng(42)
    start = datetime(2026, 1, 1, tzinfo=KST)
    end = datetime(2026, 1, 2, tzinfo=KST)
    for _ in range(50):
        result = random_instant_after(rng, start, end)
        assert _is_utc_aware(result)
        assert result > start
        assert result < end


def test_random_instant_after_tiny_window_still_utc():
    """span_seconds < 2인 극히 드문 경계 케이스에서도 UTC-aware여야 한다."""
    rng = np.random.default_rng(42)
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=KST)
    end = start + timedelta(seconds=1)
    result = random_instant_after(rng, start, end)
    assert _is_utc_aware(result)


def test_clip_to_period_within_period_returns_utc_unchanged():
    period_end_exclusive = datetime(2026, 4, 1, tzinfo=KST)
    ts = datetime(2026, 3, 31, 12, 0, 0, tzinfo=UTC)
    result = clip_to_period(ts, period_end_exclusive)
    assert _is_utc_aware(result)
    assert result == ts


def test_clip_to_period_exact_bug_regression():
    """세션이 분석 기간 종료 직전에 시작되어 오프셋이 경계를 넘는 경우.

    이 케이스가 실제로 1,750명 규모 생성에서 KST 벽시계 시각이 "Z" 접미사로
    잘못 찍히는 버그를 드러냈다(23건). clip된 결과가 반드시 UTC-aware여야
    하고, 실제 절대 시각도 분석 기간 종료보다 앞서야 한다.
    """
    period_end_exclusive_kst = datetime(2026, 4, 1, 0, 0, 0, tzinfo=KST)  # == 2026-03-31T15:00:00Z
    ts_past_boundary = datetime(2026, 4, 1, 0, 20, 0, tzinfo=KST).astimezone(UTC)  # 경계를 20분 넘긴 시각
    result = clip_to_period(ts_past_boundary, period_end_exclusive_kst)

    assert _is_utc_aware(result)
    assert result < period_end_exclusive_kst
    assert result < datetime(2026, 3, 31, 15, 0, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "make_result",
    [
        lambda rng: random_utc_timestamp(
            rng, datetime(2026, 1, 1, tzinfo=KST), datetime(2026, 1, 2, tzinfo=KST)
        ),
        lambda rng: random_instant_after(
            rng, datetime(2026, 1, 1, tzinfo=KST), datetime(2026, 1, 2, tzinfo=KST)
        ),
        lambda rng: clip_to_period(
            datetime(2026, 1, 1, 12, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=KST)
        ),
        lambda rng: parse_utc("2026-01-01T00:00:00Z"),
    ],
    ids=["random_utc_timestamp", "random_instant_after", "clip_to_period", "parse_utc"],
)
def test_all_time_utils_functions_never_leak_naive_or_non_utc(make_result):
    """time_utils의 모든 공개 함수는 naive datetime이나 UTC 아닌 tzinfo를
    반환해서는 안 된다. 새 함수를 추가할 때는 이 리스트에도 추가한다.
    """
    rng = np.random.default_rng(1)
    result = make_result(rng)
    assert isinstance(result, datetime)
    assert result.tzinfo is not None, "naive datetime이 새어나왔다"
    assert result.utcoffset() == timedelta(0), "UTC가 아닌 tzinfo가 새어나왔다"
