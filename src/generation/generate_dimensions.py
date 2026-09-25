import argparse
import os
import random
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config_loader import load_config

KST = ZoneInfo("Asia/Seoul")
UTC = ZoneInfo("UTC")

DIM_ARTIST_COLUMNS = ["artist_id", "artist_name", "artist_type", "debut_year"]
DIM_USER_COLUMNS = [
    "user_id",
    "signup_timestamp_utc",
    "signup_date_kst",
    "country_group",
    "acquisition_channel",
    "primary_device_type",
    "is_deleted",
    "deleted_at_utc",
]


def generate_dim_artist(config: dict) -> pd.DataFrame:
    # config의 artists 목록을 그대로 옮기는 작업이므로 무작위 요소가 없다 (시드와 무관).
    # activity_intensity는 dim_artist 컬럼이 아니라 생성 로직 파라미터이므로 제외한다.
    rows = [
        {
            "artist_id": a["artist_id"],
            "artist_name": a["artist_name"],
            "artist_type": a["artist_type"],
            "debut_year": a["debut_year"],
        }
        for a in config["artists"]
    ]
    return pd.DataFrame(rows, columns=DIM_ARTIST_COLUMNS)


def _random_utc_timestamp(rng: np.random.Generator, start_kst: datetime, end_kst: datetime) -> datetime:
    span_seconds = int((end_kst - start_kst).total_seconds())
    offset_seconds = int(rng.integers(0, span_seconds))
    dt_kst = start_kst + timedelta(seconds=offset_seconds)
    return dt_kst.astimezone(UTC)


def generate_dim_user(config: dict, user_count: int) -> pd.DataFrame:
    seed = config["meta"]["random_seed"]
    rng = np.random.default_rng(seed)
    random.seed(seed)

    analysis_start_kst = datetime.strptime(
        config["meta"]["analysis_start_date"], "%Y-%m-%d"
    ).replace(tzinfo=KST)
    analysis_period_days = config["meta"]["analysis_period_days"]

    # 가정: 기존 vs 신규 가입자 비율 70/30, 조정 가능
    # 기존 가입자: 분석 시작일 이전 최근 2년(730일) 사이에 가입
    # 신규 가입자: 분석 기간(90일) 동안 가입
    existing_window_start = analysis_start_kst - timedelta(days=730)
    existing_window_end = analysis_start_kst
    new_window_start = analysis_start_kst
    new_window_end = analysis_start_kst + timedelta(days=analysis_period_days)

    is_existing = rng.random(user_count) < 0.70

    # 가정: 국가 그룹 비율 domestic/overseas_asia/overseas_other = 60/25/15
    country_groups = rng.choice(
        ["domestic", "overseas_asia", "overseas_other"],
        size=user_count,
        p=[0.60, 0.25, 0.15],
    )

    # 가정: 유입 경로 비율 direct/push/social/search = 30/20/30/20
    acquisition_channels = rng.choice(
        ["direct", "push", "social", "search"],
        size=user_count,
        p=[0.30, 0.20, 0.30, 0.20],
    )

    # 가정: 주 사용 기기 비율 mobile/desktop/tablet = 80/15/5 (모바일 중심)
    primary_device_types = rng.choice(
        ["mobile", "desktop", "tablet"],
        size=user_count,
        p=[0.80, 0.15, 0.05],
    )

    # 약 2%만 삭제 상태로 설정
    is_deleted = rng.random(user_count) < 0.02

    rows = []
    for i in range(user_count):
        if is_existing[i]:
            signup_utc = _random_utc_timestamp(rng, existing_window_start, existing_window_end)
        else:
            signup_utc = _random_utc_timestamp(rng, new_window_start, new_window_end)

        signup_date_kst = signup_utc.astimezone(KST).date()

        if is_deleted[i]:
            # 가정: 삭제 시점은 가입 후 1~730일 사이 무작위 (상한 근거 없음, 조정 가능)
            delete_offset_days = int(rng.integers(1, 731))
            delete_offset_seconds = int(rng.integers(0, 86400))
            deleted_at_utc = signup_utc + timedelta(
                days=delete_offset_days, seconds=delete_offset_seconds
            )
            deleted_at_str = deleted_at_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            deleted_at_str = ""

        rows.append(
            {
                "user_id": f"user_{i + 1:06d}",
                "signup_timestamp_utc": signup_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "signup_date_kst": signup_date_kst.isoformat(),
                "country_group": country_groups[i],
                "acquisition_channel": acquisition_channels[i],
                "primary_device_type": primary_device_types[i],
                "is_deleted": bool(is_deleted[i]),
                "deleted_at_utc": deleted_at_str,
            }
        )

    return pd.DataFrame(rows, columns=DIM_USER_COLUMNS)


def main():
    parser = argparse.ArgumentParser(description="dim_artist, dim_user 생성")
    parser.add_argument(
        "--user-count",
        type=int,
        default=50,
        help="생성할 사용자 수 (기본값 50, 테스트용). 실제 실행 시 config의 scale.users "
        "범위(min~max)에서 정한 값을 전달하는 방식으로 재사용한다.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/data_generation.yaml",
        help="설정 파일 경로",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/raw",
        help="출력 CSV 디렉터리",
    )
    args = parser.parse_args()

    config = load_config(args.config)

    os.makedirs(args.output_dir, exist_ok=True)

    dim_artist = generate_dim_artist(config)
    dim_user = generate_dim_user(config, args.user_count)

    dim_artist_path = os.path.join(args.output_dir, "dim_artist.csv")
    dim_user_path = os.path.join(args.output_dir, "dim_user.csv")

    dim_artist.to_csv(dim_artist_path, index=False)
    dim_user.to_csv(dim_user_path, index=False)

    print(f"dim_artist: {len(dim_artist)}행 -> {dim_artist_path}")
    print(f"dim_user: {len(dim_user)}행 -> {dim_user_path}")


if __name__ == "__main__":
    main()
