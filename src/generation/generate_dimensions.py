import argparse
import os
import random
import sys
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config_loader import load_config
from time_utils import KST, random_utc_timestamp

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
DIM_ACTIVITY_PHASE_COLUMNS = [
    "phase_id",
    "artist_id",
    "phase_type",
    "start_date_kst",
    "end_date_kst",
]
DIM_CONTENT_COLUMNS = [
    "content_id",
    "artist_id",
    "content_type",
    "title",
    "published_timestamp_utc",
    "published_date_kst",
]
DIM_PRODUCT_COLUMNS = [
    "product_id",
    "artist_id",
    "product_name",
    "product_type",
    "price",
    "release_timestamp_utc",
    "release_date_kst",
]

# 가정: 활동 강도에 비례한 콘텐츠 배분 가중치
ACTIVITY_INTENSITY_CONTENT_WEIGHT = {"high": 1.5, "medium": 1.0, "low": 0.7}


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
            signup_utc = random_utc_timestamp(rng, existing_window_start, existing_window_end)
        else:
            signup_utc = random_utc_timestamp(rng, new_window_start, new_window_end)

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


def _compute_phase_lengths(config: dict) -> dict:
    """activity_phases.duration_weight를 일수로 환산한다 (모든 아티스트 공통).

    phase_types 순서(canonical order)대로 앞 4개 유형은 반올림하고,
    마지막 유형(inactive)에 나머지를 배정해 합이 정확히
    analysis_period_days가 되도록 오차를 보정한다.
    """
    phase_types = config["activity_phases"]["phase_types"]
    duration_weight = config["activity_phases"]["duration_weight"]
    analysis_period_days = config["meta"]["analysis_period_days"]

    lengths = {}
    running_total = 0
    for phase_type in phase_types[:-1]:
        length = round(analysis_period_days * duration_weight[phase_type])
        lengths[phase_type] = length
        running_total += length
    lengths[phase_types[-1]] = analysis_period_days - running_total
    return lengths


def generate_dim_activity_phase(config: dict, dim_artist: pd.DataFrame) -> pd.DataFrame:
    seed = config["meta"]["random_seed"]
    rng = np.random.default_rng(seed)

    phase_types = config["activity_phases"]["phase_types"]
    lengths = _compute_phase_lengths(config)
    analysis_start = datetime.strptime(
        config["meta"]["analysis_start_date"], "%Y-%m-%d"
    ).date()

    rows = []
    for artist_id in dim_artist["artist_id"]:
        # 구간 길이는 모든 아티스트가 동일하게 쓰고, 5개 구간의 "순서"만 아티스트별로 섞는다.
        order = list(rng.permutation(phase_types))

        # 제약: comeback_prep은 반드시 comeback_active보다 먼저 나와야 한다.
        # 순서가 뒤바뀐 경우에만 두 위치를 맞바꿔 최소한으로 보정한다.
        prep_idx = order.index("comeback_prep")
        active_idx = order.index("comeback_active")
        if prep_idx > active_idx:
            order[prep_idx], order[active_idx] = order[active_idx], order[prep_idx]

        current_start = analysis_start
        for seq, phase_type in enumerate(order, start=1):
            length = lengths[phase_type]
            phase_end = current_start + timedelta(days=length - 1)
            rows.append(
                {
                    "phase_id": f"phase_{artist_id}_{seq:02d}",
                    "artist_id": artist_id,
                    "phase_type": phase_type,
                    "start_date_kst": current_start.isoformat(),
                    "end_date_kst": phase_end.isoformat(),
                }
            )
            current_start = phase_end + timedelta(days=1)

    return pd.DataFrame(rows, columns=DIM_ACTIVITY_PHASE_COLUMNS)


def _split_by_weights(total: int, weights) -> list:
    """total을 weights 비율로 나누고, 반올림 오차는 마지막 항목에서 보정한다."""
    weights = np.asarray(weights, dtype=float)
    raw = total * weights / weights.sum()
    counts = [round(v) for v in raw[:-1]]
    counts.append(total - sum(counts))
    return counts


def generate_dim_content(
    config: dict, dim_artist: pd.DataFrame, dim_activity_phase: pd.DataFrame
) -> pd.DataFrame:
    seed = config["meta"]["random_seed"]
    rng = np.random.default_rng(seed)

    content_scale = config["scale"]["content"]
    total_content = int(rng.integers(content_scale["min"], content_scale["max"] + 1))

    artist_ids = list(dim_artist["artist_id"])
    artist_intensity = {
        a["artist_id"]: a["activity_intensity"] for a in config["artists"]
    }
    artist_name_lookup = dict(zip(dim_artist["artist_id"], dim_artist["artist_name"]))

    # 아티스트별 콘텐츠 개수를 activity_intensity 가중치로 배분
    artist_weights = [
        ACTIVITY_INTENSITY_CONTENT_WEIGHT[artist_intensity[aid]] for aid in artist_ids
    ]
    artist_content_counts = dict(zip(artist_ids, _split_by_weights(total_content, artist_weights)))

    content_type_dist = config["content_types"]["distribution"]
    type_names = list(content_type_dist.keys())
    type_probs = list(content_type_dist.values())
    phase_multiplier = config["activity_phases"]["phase_multiplier"]

    rows = []
    for aid in artist_ids:
        artist_phases = dim_activity_phase[dim_activity_phase["artist_id"] == aid].reset_index(drop=True)

        # 구간 배분 가중치 = 구간 일수 x phase_multiplier(해당 phase_type)
        phase_weights = []
        for _, prow in artist_phases.iterrows():
            start = date.fromisoformat(prow["start_date_kst"])
            end = date.fromisoformat(prow["end_date_kst"])
            days = (end - start).days + 1
            phase_weights.append(days * phase_multiplier[prow["phase_type"]])

        phase_counts = _split_by_weights(artist_content_counts[aid], phase_weights)

        seq = 0
        for (_, prow), phase_count in zip(artist_phases.iterrows(), phase_counts):
            if phase_count <= 0:
                continue

            start_date = date.fromisoformat(prow["start_date_kst"])
            end_date = date.fromisoformat(prow["end_date_kst"])
            start_kst = datetime(start_date.year, start_date.month, start_date.day, tzinfo=KST)
            # 종료일을 포함(inclusive)하기 위해 다음날 00:00을 배타적 상한으로 사용
            end_kst_exclusive = datetime(end_date.year, end_date.month, end_date.day, tzinfo=KST) + timedelta(days=1)

            phase_content_types = rng.choice(type_names, size=phase_count, p=type_probs)

            for i in range(phase_count):
                seq += 1
                published_utc = random_utc_timestamp(rng, start_kst, end_kst_exclusive)
                content_type = phase_content_types[i]
                rows.append(
                    {
                        "content_id": f"content_{aid}_{seq:04d}",
                        "artist_id": aid,
                        "content_type": content_type,
                        "title": f"[{artist_name_lookup[aid]}] {content_type} #{seq:04d}",
                        "published_timestamp_utc": published_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "published_date_kst": published_utc.astimezone(KST).date().isoformat(),
                    }
                )

    return pd.DataFrame(rows, columns=DIM_CONTENT_COLUMNS)


def generate_dim_product(config: dict, dim_artist: pd.DataFrame) -> pd.DataFrame:
    seed = config["meta"]["random_seed"]
    rng = np.random.default_rng(seed)

    product_scale = config["scale"]["products"]
    total_products = int(rng.integers(product_scale["min"], product_scale["max"] + 1))

    artist_ids = list(dim_artist["artist_id"])
    artist_name_lookup = dict(zip(dim_artist["artist_id"], dim_artist["artist_name"]))

    # 아티스트별로 균등 배분, 반올림(나머지) 오차는 마지막 아티스트에서 보정
    base_count = total_products // len(artist_ids)
    artist_product_counts = {aid: base_count for aid in artist_ids}
    artist_product_counts[artist_ids[-1]] = total_products - base_count * (len(artist_ids) - 1)

    product_type_dist = config["commerce"]["product_types"]["distribution"]
    type_names = list(product_type_dist.keys())
    type_probs = list(product_type_dist.values())
    price_range = config["commerce"]["price_range_krw"]

    analysis_start_kst = datetime.strptime(
        config["meta"]["analysis_start_date"], "%Y-%m-%d"
    ).replace(tzinfo=KST)
    analysis_period_days = config["meta"]["analysis_period_days"]

    # 가정: 기존 상품은 분석 시작일 이전 최근 1년 이내에 이미 출시되어 있었다고 가정.
    # 전체 상품의 약 20%는 분석 기간(90일) 중에 신규 출시되는 것으로 한다.
    existing_window_start = analysis_start_kst - timedelta(days=365)
    existing_window_end = analysis_start_kst
    new_window_start = analysis_start_kst
    new_window_end = analysis_start_kst + timedelta(days=analysis_period_days)

    rows = []
    for aid in artist_ids:
        count = artist_product_counts[aid]
        product_types = rng.choice(type_names, size=count, p=type_probs)
        is_new = rng.random(count) < 0.20

        for i in range(count):
            seq = i + 1
            product_type = product_types[i]

            low, high = price_range[product_type]
            raw_price = rng.uniform(low, high)
            price = int(round(raw_price / 1000)) * 1000

            if is_new[i]:
                release_utc = random_utc_timestamp(rng, new_window_start, new_window_end)
            else:
                release_utc = random_utc_timestamp(rng, existing_window_start, existing_window_end)

            rows.append(
                {
                    "product_id": f"product_{aid}_{seq:03d}",
                    "artist_id": aid,
                    "product_name": f"[{artist_name_lookup[aid]}] {product_type} #{seq:03d}",
                    "product_type": product_type,
                    "price": price,
                    "release_timestamp_utc": release_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "release_date_kst": release_utc.astimezone(KST).date().isoformat(),
                }
            )

    return pd.DataFrame(rows, columns=DIM_PRODUCT_COLUMNS)


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
    dim_activity_phase = generate_dim_activity_phase(config, dim_artist)
    dim_content = generate_dim_content(config, dim_artist, dim_activity_phase)
    dim_product = generate_dim_product(config, dim_artist)

    dim_artist_path = os.path.join(args.output_dir, "dim_artist.csv")
    dim_user_path = os.path.join(args.output_dir, "dim_user.csv")
    dim_activity_phase_path = os.path.join(args.output_dir, "dim_activity_phase.csv")
    dim_content_path = os.path.join(args.output_dir, "dim_content.csv")
    dim_product_path = os.path.join(args.output_dir, "dim_product.csv")

    dim_artist.to_csv(dim_artist_path, index=False)
    dim_user.to_csv(dim_user_path, index=False)
    dim_activity_phase.to_csv(dim_activity_phase_path, index=False)
    dim_content.to_csv(dim_content_path, index=False)
    dim_product.to_csv(dim_product_path, index=False)

    print(f"dim_artist: {len(dim_artist)}행 -> {dim_artist_path}")
    print(f"dim_user: {len(dim_user)}행 -> {dim_user_path}")
    print(f"dim_activity_phase: {len(dim_activity_phase)}행 -> {dim_activity_phase_path}")
    print(f"dim_content: {len(dim_content)}행 -> {dim_content_path}")
    print(f"dim_product: {len(dim_product)}행 -> {dim_product_path}")


if __name__ == "__main__":
    main()
