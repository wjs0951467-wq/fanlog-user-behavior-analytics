import argparse
import os
import sys
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config_loader import load_config
from time_utils import KST, random_utc_timestamp, random_instant_after, parse_utc

BRIDGE_USER_ARTIST_FOLLOW_COLUMNS = [
    "follow_id",
    "user_id",
    "artist_id",
    "followed_at_utc",
    "unfollowed_at_utc",
]
FACT_MESSAGE_SUBSCRIPTION_COLUMNS = [
    "subscription_id",
    "user_id",
    "artist_id",
    "plan_type",
    "started_at_utc",
    "ended_at_utc",
    "cancel_reason_category",
]
FACT_ARTIST_ACTIVITY_COLUMNS = [
    "activity_id",
    "artist_id",
    "activity_type",
    "activity_timestamp_utc",
    "activity_date_kst",
    "content_id",
    "phase_id",
    "parameters",
]

# 가정: post 활동 중 30%만 dim_content의 콘텐츠와 연결한다 (콘텐츠 소개/공유 게시글 비중).
# 나머지 70%의 post와 모든 message/live는 content_id를 비워둔다.
POST_CONTENT_LINK_RATE = 0.30


def generate_bridge_user_artist_follow(
    config: dict, dim_user: pd.DataFrame, dim_artist: pd.DataFrame
) -> pd.DataFrame:
    seed = config["meta"]["random_seed"]
    rng = np.random.default_rng(seed)

    analysis_start_kst = datetime.strptime(
        config["meta"]["analysis_start_date"], "%Y-%m-%d"
    ).replace(tzinfo=KST)
    analysis_end_exclusive = analysis_start_kst + timedelta(days=config["meta"]["analysis_period_days"])

    rel_config = config["relationships"]
    follow_dist = rel_config["follow_count_distribution"]
    follow_counts = list(follow_dist.keys())
    follow_probs = list(follow_dist.values())

    artist_ids = list(dim_artist["artist_id"])
    artist_intensity = {a["artist_id"]: a["activity_intensity"] for a in config["artists"]}
    popularity_weight = rel_config["artist_popularity_weight"]
    artist_weights = np.array([popularity_weight[artist_intensity[aid]] for aid in artist_ids], dtype=float)
    artist_probs = artist_weights / artist_weights.sum()

    unfollow_rate = rel_config["unfollow_rate"]

    rows = []
    seq = 0
    for _, urow in dim_user.iterrows():
        user_id = urow["user_id"]
        signup_utc = parse_utc(urow["signup_timestamp_utc"])

        n_follow = int(rng.choice(follow_counts, p=follow_probs))
        n_follow = min(n_follow, len(artist_ids))
        chosen_artists = rng.choice(artist_ids, size=n_follow, replace=False, p=artist_probs)

        # 팔로우는 가입 이후 언제든 가능하지만, 분석 기간 이전에 가입한 기존 팬이라도
        # 우리가 실제로 관측하는 이벤트는 분석 기간 시작일부터다 (ET-DQ-14: 분석 기간을
        # 벗어난 이벤트 0건 원칙과 정합시키기 위한 하한 보정).
        follow_window_start = max(signup_utc, analysis_start_kst)

        for artist_id in chosen_artists:
            followed_utc = random_instant_after(rng, follow_window_start, analysis_end_exclusive)

            unfollowed_str = ""
            if rng.random() < unfollow_rate:
                unfollowed_utc = random_instant_after(rng, followed_utc, analysis_end_exclusive)
                unfollowed_str = unfollowed_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

            seq += 1
            rows.append(
                {
                    "follow_id": f"follow_{seq:06d}",
                    "user_id": user_id,
                    "artist_id": artist_id,
                    "followed_at_utc": followed_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "unfollowed_at_utc": unfollowed_str,
                }
            )

    return pd.DataFrame(rows, columns=BRIDGE_USER_ARTIST_FOLLOW_COLUMNS)


def generate_fact_message_subscription(
    config: dict, bridge_user_artist_follow: pd.DataFrame
) -> pd.DataFrame:
    seed = config["meta"]["random_seed"]
    rng = np.random.default_rng(seed)

    analysis_start_kst = datetime.strptime(
        config["meta"]["analysis_start_date"], "%Y-%m-%d"
    ).replace(tzinfo=KST)
    analysis_end_exclusive = analysis_start_kst + timedelta(days=config["meta"]["analysis_period_days"])

    sub_config = config["relationships"]["subscription"]
    conversion_rate = sub_config["conversion_rate_from_follow"]
    cancel_rate = sub_config["cancel_rate_within_period"]
    user_cancel_share = sub_config["user_cancel_share_of_cancellations"]

    rows = []
    seq = 0
    for _, frow in bridge_user_artist_follow.iterrows():
        # 대상: followed_at_utc ~ (unfollowed_at_utc 또는 분석 종료일) 사이에
        # 항상 유효한 구독 시작 윈도우가 존재하는 팔로우 관계 (모든 행이 해당).
        if rng.random() >= conversion_rate:
            continue

        followed_utc = parse_utc(frow["followed_at_utc"])
        if frow["unfollowed_at_utc"]:
            window_end = parse_utc(frow["unfollowed_at_utc"])
        else:
            window_end = analysis_end_exclusive

        started_utc = random_instant_after(rng, followed_utc, window_end)

        ended_str = ""
        cancel_reason = ""
        if rng.random() < cancel_rate:
            ended_utc = random_instant_after(rng, started_utc, analysis_end_exclusive)
            ended_str = ended_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            cancel_reason = (
                "user_cancel" if rng.random() < user_cancel_share else "expired_no_renewal"
            )

        seq += 1
        rows.append(
            {
                "subscription_id": f"subscription_{seq:06d}",
                "user_id": frow["user_id"],
                "artist_id": frow["artist_id"],
                "plan_type": "monthly",
                "started_at_utc": started_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "ended_at_utc": ended_str,
                "cancel_reason_category": cancel_reason,
            }
        )

    return pd.DataFrame(rows, columns=FACT_MESSAGE_SUBSCRIPTION_COLUMNS)


def generate_fact_artist_activity(
    config: dict,
    dim_artist: pd.DataFrame,
    dim_activity_phase: pd.DataFrame,
    dim_content: pd.DataFrame,
) -> pd.DataFrame:
    seed = config["meta"]["random_seed"]
    rng = np.random.default_rng(seed)

    intensity_levels = config["activity_intensity_levels"]
    phase_multiplier = config["activity_phases"]["phase_multiplier"]
    artist_intensity = {a["artist_id"]: a["activity_intensity"] for a in config["artists"]}

    all_rows = []
    for artist_id in dim_artist["artist_id"]:
        intensity = artist_intensity[artist_id]
        levels = intensity_levels[intensity]
        # 각 강도 구간의 중간값을 "일상 활동기(daily)" 기준 빈도로 사용
        post_base = sum(levels["posts_per_week"]) / 2
        message_base = sum(levels["messages_per_week"]) / 2
        live_base = sum(levels["live_per_month"]) / 2

        artist_content_ids = dim_content.loc[
            dim_content["artist_id"] == artist_id, "content_id"
        ].to_numpy()

        artist_phases = dim_activity_phase[dim_activity_phase["artist_id"] == artist_id]

        artist_rows = []
        for _, prow in artist_phases.iterrows():
            phase_id = prow["phase_id"]
            phase_type = prow["phase_type"]
            start_date = date.fromisoformat(prow["start_date_kst"])
            end_date = date.fromisoformat(prow["end_date_kst"])
            phase_days = (end_date - start_date).days + 1
            multiplier = phase_multiplier[phase_type]

            start_kst = datetime(start_date.year, start_date.month, start_date.day, tzinfo=KST)
            # 종료일을 포함(inclusive)하기 위해 다음날 00:00을 배타적 상한으로 사용
            end_kst_exclusive = datetime(
                end_date.year, end_date.month, end_date.day, tzinfo=KST
            ) + timedelta(days=1)

            for activity_type, base_freq, unit_days in (
                ("post", post_base, 7),
                ("message", message_base, 7),
                ("live", live_base, 30),
            ):
                adjusted_freq = base_freq * multiplier
                expected_count = adjusted_freq * (phase_days / unit_days)
                actual_count = int(rng.poisson(expected_count))

                for _ in range(actual_count):
                    activity_utc = random_utc_timestamp(rng, start_kst, end_kst_exclusive)

                    content_id = ""
                    if (
                        activity_type == "post"
                        and len(artist_content_ids) > 0
                        and rng.random() < POST_CONTENT_LINK_RATE
                    ):
                        content_id = str(rng.choice(artist_content_ids))

                    artist_rows.append(
                        {
                            "artist_id": artist_id,
                            "activity_type": activity_type,
                            "activity_timestamp_utc": activity_utc,
                            "content_id": content_id,
                            "phase_id": phase_id,
                        }
                    )

        # 시간순 정렬 후 아티스트별로 activity_id 순번(00001~)을 부여한다.
        artist_rows.sort(key=lambda r: r["activity_timestamp_utc"])
        for seq, row in enumerate(artist_rows, start=1):
            activity_utc = row["activity_timestamp_utc"]
            all_rows.append(
                {
                    "activity_id": f"activity_{artist_id}_{seq:05d}",
                    "artist_id": row["artist_id"],
                    "activity_type": row["activity_type"],
                    "activity_timestamp_utc": activity_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "activity_date_kst": activity_utc.astimezone(KST).date().isoformat(),
                    "content_id": row["content_id"],
                    "phase_id": row["phase_id"],
                    "parameters": "",
                }
            )

    return pd.DataFrame(all_rows, columns=FACT_ARTIST_ACTIVITY_COLUMNS)


def main():
    parser = argparse.ArgumentParser(
        description="fact_artist_activity, bridge_user_artist_follow, fact_message_subscription 생성"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/data_generation.yaml",
        help="설정 파일 경로",
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default="data/raw",
        help="dim_artist.csv, dim_user.csv, dim_activity_phase.csv, dim_content.csv가 있는 디렉터리",
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

    dim_artist = pd.read_csv(os.path.join(args.input_dir, "dim_artist.csv"))
    dim_user = pd.read_csv(os.path.join(args.input_dir, "dim_user.csv"), dtype={"deleted_at_utc": "string"})
    dim_activity_phase = pd.read_csv(os.path.join(args.input_dir, "dim_activity_phase.csv"))
    dim_content = pd.read_csv(os.path.join(args.input_dir, "dim_content.csv"))

    bridge_user_artist_follow = generate_bridge_user_artist_follow(config, dim_user, dim_artist)
    fact_message_subscription = generate_fact_message_subscription(config, bridge_user_artist_follow)
    fact_artist_activity = generate_fact_artist_activity(
        config, dim_artist, dim_activity_phase, dim_content
    )

    bridge_path = os.path.join(args.output_dir, "bridge_user_artist_follow.csv")
    subscription_path = os.path.join(args.output_dir, "fact_message_subscription.csv")
    activity_path = os.path.join(args.output_dir, "fact_artist_activity.csv")

    bridge_user_artist_follow.to_csv(bridge_path, index=False)
    fact_message_subscription.to_csv(subscription_path, index=False)
    fact_artist_activity.to_csv(activity_path, index=False)

    print(f"bridge_user_artist_follow: {len(bridge_user_artist_follow)}행 -> {bridge_path}")
    print(f"fact_message_subscription: {len(fact_message_subscription)}행 -> {subscription_path}")
    print(f"fact_artist_activity: {len(fact_artist_activity)}행 -> {activity_path}")


if __name__ == "__main__":
    main()
