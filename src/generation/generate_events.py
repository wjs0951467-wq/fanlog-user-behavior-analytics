import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config_loader import load_config
from generate_dimensions import KST, UTC, _random_utc_timestamp

FACT_USER_EVENT_COLUMNS = [
    "event_id",
    "event_name",
    "event_timestamp_utc",
    "event_date_kst",
    "user_id",
    "session_id",
    "artist_id",
    "content_id",
    "activity_id",
    "product_id",
    "transaction_id",
    "device_type",
    "traffic_source",
    "parameters",
]

# 가정: sign_up의 가입 방법 비율
SIGNUP_METHOD_DIST = {"email": 0.40, "google": 0.35, "apple": 0.25}
# 가정: 이벤트 단위 기기 유형 비율 (dim_user.primary_device_type과 별개로 이벤트마다 배정)
DEVICE_TYPE_DIST = {"mobile": 0.80, "desktop": 0.15, "tablet": 0.05}
# 세션이 "끝났다"고 보는 비활동 기준 (event_tracking_plan.md 3절 세션 정의와 동일)
SESSION_GAP = timedelta(minutes=30)


def _parse_utc(timestamp_str: str) -> datetime:
    return datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _has_value(v) -> bool:
    return pd.notna(v) and str(v).strip() != ""


def _random_uuid(rng: np.random.Generator) -> str:
    raw = bytes(rng.integers(0, 256, size=16, dtype=np.uint8))
    return str(uuid.UUID(bytes=raw))


def _random_device_type(rng: np.random.Generator) -> str:
    return rng.choice(list(DEVICE_TYPE_DIST.keys()), p=list(DEVICE_TYPE_DIST.values()))


def generate_fact_user_event_phase1(
    config: dict,
    dim_user: pd.DataFrame,
    bridge_user_artist_follow: pd.DataFrame,
    fact_message_subscription: pd.DataFrame,
):
    """1/4 단계: sign_up, session_start, artist_follow/unfollow,
    message_subscription_start/cancel 이벤트를 생성한다.

    반환값: (fact_user_event DataFrame, 즉석 생성된 세션 수)
    """
    seed = config["meta"]["random_seed"]
    rng = np.random.default_rng(seed)

    analysis_start_kst = datetime.strptime(
        config["meta"]["analysis_start_date"], "%Y-%m-%d"
    ).replace(tzinfo=KST)
    analysis_period_days = config["meta"]["analysis_period_days"]
    last_day_kst_date = (analysis_start_kst + timedelta(days=analysis_period_days - 1)).date()

    follow_by_user = {
        uid: g for uid, g in bridge_user_artist_follow.groupby("user_id")
    }
    sub_by_user = {
        uid: g for uid, g in fact_message_subscription.groupby("user_id")
    }

    all_rows = []
    adhoc_session_count = 0

    for _, urow in dim_user.iterrows():
        user_id = urow["user_id"]
        signup_utc = _parse_utc(urow["signup_timestamp_utc"])
        method = rng.choice(list(SIGNUP_METHOD_DIST.keys()), p=list(SIGNUP_METHOD_DIST.values()))

        # --- 신규 가입자(분석 시작일 이후 가입)만 sign_up을 생성한다.
        # 기존 가입자(분석 시작일 이전 가입)는 트래킹 시작 전에 이미 가입했다고 보고
        # sign_up 이벤트를 생성하지 않는다 (실제 분석 도구가 트래킹 이전 가입을
        # 소급 기록하지 않는 것과 동일한 원칙; ET-DQ-14 유지를 위한 결정).
        is_new_user = signup_utc >= analysis_start_kst

        # --- 후보 세션 시각: 신규 가입자는 세션 1이 반드시 signup_utc와 동일.
        # 기존 가입자는 강제 시작 세션이 없고, 분석 기간 중 처음 관측된 세션이
        # 자연스럽게 session_number=1이 된다. ---
        active_start = max(signup_utc, analysis_start_kst)
        visit_propensity = rng.beta(2, 5)  # 저장하지 않고 생성에만 사용
        daily_session_rate = 0.1 + 0.9 * visit_propensity

        candidate_session_times = [signup_utc] if is_new_user else []

        current_date = active_start.astimezone(KST).date()
        while current_date <= last_day_kst_date:
            day_start_kst = datetime(current_date.year, current_date.month, current_date.day, tzinfo=KST)
            day_end_kst_exclusive = day_start_kst + timedelta(days=1)
            window_start = max(day_start_kst, active_start)
            if window_start < day_end_kst_exclusive:
                n_sessions_today = int(rng.poisson(daily_session_rate))
                for _ in range(n_sessions_today):
                    candidate_session_times.append(
                        _random_utc_timestamp(rng, window_start, day_end_kst_exclusive)
                    )
            current_date += timedelta(days=1)

        sessions = [{"start": t, "last_activity": t} for t in sorted(candidate_session_times)]

        # --- 이 팬의 follow/unfollow, 구독 시작/해지 이벤트 ---
        other_events = []
        user_follows = follow_by_user.get(user_id)
        if user_follows is not None:
            for _, frow in user_follows.iterrows():
                other_events.append(
                    {
                        "timestamp": _parse_utc(frow["followed_at_utc"]),
                        "event_name": "artist_follow",
                        "artist_id": frow["artist_id"],
                        "parameters": None,
                    }
                )
                if _has_value(frow["unfollowed_at_utc"]):
                    other_events.append(
                        {
                            "timestamp": _parse_utc(str(frow["unfollowed_at_utc"])),
                            "event_name": "artist_unfollow",
                            "artist_id": frow["artist_id"],
                            "parameters": None,
                        }
                    )

        user_subs = sub_by_user.get(user_id)
        if user_subs is not None:
            for _, srow in user_subs.iterrows():
                other_events.append(
                    {
                        "timestamp": _parse_utc(srow["started_at_utc"]),
                        "event_name": "message_subscription_start",
                        "artist_id": srow["artist_id"],
                        "parameters": {"plan_type": "monthly"},
                    }
                )
                if _has_value(srow["ended_at_utc"]):
                    other_events.append(
                        {
                            "timestamp": _parse_utc(str(srow["ended_at_utc"])),
                            "event_name": "message_subscription_cancel",
                            "artist_id": srow["artist_id"],
                            "parameters": {
                                "cancel_reason_category": srow["cancel_reason_category"]
                            },
                        }
                    )

        other_events.sort(key=lambda e: e["timestamp"])

        # --- 세션 배정 시뮬레이션: 세션 시작과 다른 이벤트를 시간순으로 함께 훑는다 ---
        timeline = [{"type": "session", "time": s["start"], "ref": s} for s in sessions]
        timeline += [{"type": "other", "time": e["timestamp"], "ref": e} for e in other_events]
        timeline.sort(key=lambda x: x["time"])

        current_session = None
        for item in timeline:
            if item["type"] == "session":
                current_session = item["ref"]
            else:
                event = item["ref"]
                t = item["time"]
                if current_session is not None and (t - current_session["last_activity"]) < SESSION_GAP:
                    current_session["last_activity"] = t
                else:
                    # 활성 세션이 없음: 즉석에서 새 세션을 만들어 배정한다.
                    current_session = {"start": t, "last_activity": t}
                    sessions.append(current_session)
                    adhoc_session_count += 1
                event["_session_ref"] = current_session

        # --- 세션 번호/ID 확정 (시간순) ---
        sessions.sort(key=lambda s: s["start"])
        for i, s in enumerate(sessions, start=1):
            s["session_number"] = i
            s["session_id"] = _random_uuid(rng)

        for s in sessions:
            all_rows.append(
                {
                    "event_name": "session_start",
                    "timestamp": s["start"],
                    "user_id": user_id,
                    "session_id": s["session_id"],
                    "artist_id": "",
                    "device_type": _random_device_type(rng),
                    "parameters": {"session_number": s["session_number"]},
                }
            )

        if is_new_user:
            # session 1 == signup_utc (신규 가입자는 항상 가장 이른 시각의 세션이 존재)
            signup_session = sessions[0]
            all_rows.append(
                {
                    "event_name": "sign_up",
                    "timestamp": signup_utc,
                    "user_id": user_id,
                    "session_id": signup_session["session_id"],
                    "artist_id": "",
                    "device_type": _random_device_type(rng),
                    "parameters": {"method": method},
                }
            )

        for e in other_events:
            all_rows.append(
                {
                    "event_name": e["event_name"],
                    "timestamp": e["timestamp"],
                    "user_id": user_id,
                    "session_id": e["_session_ref"]["session_id"],
                    "artist_id": e["artist_id"],
                    "device_type": _random_device_type(rng),
                    "parameters": e["parameters"],
                }
            )

    # --- 전체 이벤트 시간순 정렬 후 event_id 전역 순번 부여 ---
    all_rows.sort(key=lambda r: r["timestamp"])
    final_rows = []
    for i, r in enumerate(all_rows, start=1):
        ts = r["timestamp"]
        params = r["parameters"]
        params_str = json.dumps(params, ensure_ascii=False) if params else ""
        final_rows.append(
            {
                "event_id": f"event_{i:08d}",
                "event_name": r["event_name"],
                "event_timestamp_utc": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "event_date_kst": ts.astimezone(KST).date().isoformat(),
                "user_id": r["user_id"],
                "session_id": r["session_id"],
                "artist_id": r["artist_id"],
                "content_id": "",
                "activity_id": "",
                "product_id": "",
                "transaction_id": "",
                "device_type": r["device_type"],
                "traffic_source": "",
                "parameters": params_str,
            }
        )

    return pd.DataFrame(final_rows, columns=FACT_USER_EVENT_COLUMNS), adhoc_session_count


def main():
    parser = argparse.ArgumentParser(
        description="fact_user_event 생성 (1/4 단계: 회원·세션 + 팔로우·구독 파생)"
    )
    parser.add_argument("--config", type=str, default="config/data_generation.yaml")
    parser.add_argument(
        "--input-dir",
        type=str,
        default="data/raw",
        help="dim_user.csv, bridge_user_artist_follow.csv, fact_message_subscription.csv가 있는 디렉터리",
    )
    parser.add_argument("--output-dir", type=str, default="data/raw")
    args = parser.parse_args()

    config = load_config(args.config)
    os.makedirs(args.output_dir, exist_ok=True)

    dim_user = pd.read_csv(
        os.path.join(args.input_dir, "dim_user.csv"), dtype={"deleted_at_utc": "string"}
    )
    bridge_user_artist_follow = pd.read_csv(
        os.path.join(args.input_dir, "bridge_user_artist_follow.csv"),
        dtype={"unfollowed_at_utc": "string"},
    )
    fact_message_subscription = pd.read_csv(
        os.path.join(args.input_dir, "fact_message_subscription.csv"),
        dtype={"ended_at_utc": "string", "cancel_reason_category": "string"},
    )

    fact_user_event, adhoc_session_count = generate_fact_user_event_phase1(
        config, dim_user, bridge_user_artist_follow, fact_message_subscription
    )

    output_path = os.path.join(args.output_dir, "fact_user_event.csv")
    fact_user_event.to_csv(output_path, index=False)

    print(f"fact_user_event: {len(fact_user_event)}행 -> {output_path}")
    print(f"즉석 생성된 세션(ad-hoc session) 수: {adhoc_session_count}")


if __name__ == "__main__":
    main()
