"""FANLOG 데이터 생성 파이프라인 공용 시간 유틸리티.

이 모듈의 모든 함수는 반드시 UTC-aware datetime을 반환해야 한다. KST(Asia/Seoul)
tzinfo를 가진 값을 입력받아 계산하더라도, 반환 직전에 반드시 astimezone(UTC)를
거쳐야 한다. 이 규칙을 어기면 KST 벽시계 시각이 "Z"(UTC) 접미사로 그대로
문자열화되어 9시간이 밀리는 버그가 생긴다 — 이 프로젝트에서 이미 두 번
(bridge_user_artist_follow의 _random_instant_after, fact_user_event의
_clip_to_period) 반복된 실수이므로, 새 시간 헬퍼를 추가할 때는 항상 이 규칙을
지킨다.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np

KST = ZoneInfo("Asia/Seoul")
UTC = ZoneInfo("UTC")


def parse_utc(timestamp_str: str) -> datetime:
    """이 함수는 항상 UTC-aware datetime을 반환해야 한다.

    "YYYY-MM-DDTHH:MM:SSZ" 형식의 UTC 타임스탬프 문자열을 파싱한다.
    """
    return datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def random_utc_timestamp(rng: np.random.Generator, start: datetime, end_exclusive: datetime) -> datetime:
    """이 함수는 항상 UTC-aware datetime을 반환해야 한다.

    [start, end_exclusive) 구간에서 균등 무작위 시각을 뽑는다(start 자체도 나올 수
    있다). start/end_exclusive는 KST 등 다른 tzinfo를 가져도 되지만, 반환값은
    항상 UTC로 정규화한다.
    """
    span_seconds = int((end_exclusive - start).total_seconds())
    offset_seconds = int(rng.integers(0, span_seconds))
    result = start + timedelta(seconds=offset_seconds)
    return result.astimezone(UTC)


def random_instant_after(rng: np.random.Generator, start: datetime, end_exclusive: datetime) -> datetime:
    """이 함수는 항상 UTC-aware datetime을 반환해야 한다.

    start보다 항상 엄격히 늦고 end_exclusive 미만인 무작위 시각을 뽑는다.
    start/end_exclusive는 KST 등 다른 tzinfo를 가져도 되지만, 반환값은 항상
    UTC로 정규화한다.
    """
    span_seconds = int((end_exclusive - start).total_seconds())
    if span_seconds < 2:
        # 극히 드문 경계 케이스(윈도우가 1초 이하): 최소 1초 뒤로 보정한다.
        result = start + timedelta(seconds=1)
    else:
        offset_seconds = int(rng.integers(1, span_seconds))
        result = start + timedelta(seconds=offset_seconds)
    return result.astimezone(UTC)


def clip_to_period(ts: datetime, period_end_exclusive: datetime) -> datetime:
    """이 함수는 항상 UTC-aware datetime을 반환해야 한다.

    ts가 period_end_exclusive를 넘으면(예: 세션이 분석 기간 종료 직전에 시작되어
    그 뒤의 오프셋이 경계를 넘는 경우) period_end_exclusive 1초 전 시각으로
    잘라낸다. period_end_exclusive는 KST 등 다른 tzinfo를 가져도 되지만,
    반환값은 항상 UTC로 정규화한다.
    """
    if ts < period_end_exclusive:
        return ts.astimezone(UTC)
    return (period_end_exclusive - timedelta(seconds=1)).astimezone(UTC)
