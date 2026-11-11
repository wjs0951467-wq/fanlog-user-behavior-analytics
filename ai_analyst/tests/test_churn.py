"""app/churn.py 테스트. DB 와 LLM 없이 작은 가짜 표로 돌린다.

가짜 데이터: 2026-01-01 ~ 2026-02-28 (59일), 기준일 T = 2026-01-20.
  - 최근 14일 창 = 01-07 ~ 01-20,  라벨 창 = 01-21 ~ 02-03
"""
import pandas as pd
import pytest

from app import churn
from app.sql_guard import validate_sql

START, END, T = "2026-01-01", "2026-02-28", "2026-01-20"


def daily_rows(user, active_days=(), purchase_days=(), start=START, end=END):
    """mart_user_daily 와 같은 규칙으로 한 사용자의 일자별 행을 만든다 (0~13일 active, 14~29 at_risk, 30+ dormant)."""
    active_days = {pd.Timestamp(d) for d in active_days}
    purchase_days = {pd.Timestamp(d) for d in purchase_days}
    rows, last = [], pd.Timestamp(start)  # 활동이 한 번도 없으면 첫 추적일부터 센다 (마트와 같은 규칙)
    for d in pd.date_range(start, end):
        had = d in active_days
        if had:
            last = d
        gap = (d - last).days
        status = "active" if gap <= 13 else "at_risk" if gap <= 29 else "dormant"
        rows.append({"user_id": user, "activity_date_kst": d, "had_core_activity": had,
                     "had_purchase": d in purchase_days, "days_since_last_core_activity": gap,
                     "activity_status": status})
    return rows


def make_data(daily, users=None, follows=(), subs=(), artist_gaps=None):
    """테스트용 data dict. users 를 안 주면 daily 에 나온 사용자 모두 2025년 가입, 탈퇴 아님."""
    daily = pd.DataFrame(daily)
    if users is None:
        users = [{"user_id": u, "signup_date_kst": "2025-06-01", "is_deleted": False}
                 for u in daily["user_id"].unique()]
    span_cols = ["user_id", "artist_id", "start_date_kst", "end_date_kst"]
    artist_rows = [{"artist_id": a, "activity_date_kst": d, "days_since_last_communication": g}
                   for a, by_date in (artist_gaps or {}).items() for d, g in by_date.items()]
    return churn.prepare({
        "daily": daily,
        "users": pd.DataFrame(users),
        "follows": pd.DataFrame(list(follows), columns=span_cols),
        "subs": pd.DataFrame(list(subs), columns=span_cols),
        "artist_daily": pd.DataFrame(artist_rows,
                                     columns=["artist_id", "activity_date_kst", "days_since_last_communication"]),
    })


# ---------- 라벨 ----------
def test_label_boundaries():
    data = make_data(
        daily_rows("next_day", ["2026-01-21"])        # t+1 에 활동 -> 0
        + daily_rows("day_14", ["2026-02-03"])        # t+14 (창의 마지막 날) 에 활동 -> 0
        + daily_rows("day_15", ["2026-02-04"])        # t+15 (창 밖) 에만 활동 -> 1
        + daily_rows("only_today", ["2026-01-20"])    # 기준일 당일 활동은 "미래"가 아니다 -> 1
        + daily_rows("never", []))
    labels = churn.make_labels(data["daily"], T)
    assert labels.to_dict() == {"next_day": 0, "day_14": 0, "day_15": 1, "only_today": 1, "never": 1}


def test_label_unknown_near_data_end_raises():
    data = make_data(daily_rows("u", ["2026-02-10"]))
    churn.make_labels(data["daily"], "2026-02-14")  # 02-14 + 14일 = 02-28 (데이터 마지막 날) -> 가능
    with pytest.raises(ValueError):
        churn.make_labels(data["daily"], "2026-02-15")  # 하루만 넘어도 정답을 알 수 없다


# ---------- 특징 ----------
def test_activity_features():
    # 최근 7일(01-14~01-20) 중 2일, 그 앞 7일(01-07~01-13) 중 3일 활동. 01-06 은 창 밖.
    active = ["2026-01-06", "2026-01-07", "2026-01-08", "2026-01-13", "2026-01-15", "2026-01-18"]
    data = make_data(daily_rows("u", active, purchase_days=["2026-01-08"])
                     + daily_rows("old_buyer", ["2026-01-19"], purchase_days=["2026-01-03"]))
    f = churn.make_features(data, T)

    u = f.loc["u"]
    assert u["days_since_last_core_activity"] == 2
    assert u["active_days_7"] == 2 and u["active_days_14"] == 5
    assert u["activity_change"] == 2 - 3
    assert u["purchased_14d"] == 1 and u["purchased_in_period"] == 1
    # 01-03 구매는 최근 14일 창 밖이지만 "기간 내 구매 경험"에는 들어간다
    assert f.loc["old_buyer", "purchased_14d"] == 0 and f.loc["old_buyer", "purchased_in_period"] == 1


def test_features_need_full_lookback_window():
    data = make_data(daily_rows("u", ["2026-01-05"]))
    churn.make_features(data, "2026-01-14")  # 01-01 ~ 01-14 = 14일 -> 가능
    with pytest.raises(ValueError):
        churn.make_features(data, "2026-01-13")


def test_no_leak_features_ignore_everything_after_t():
    """기준일 이후의 데이터를 전부 바꿔도 기준일의 특징은 한 글자도 달라지지 않아야 한다."""
    active = ["2026-01-10", "2026-01-18"]
    follows = [("u", "a1", "2026-01-02", None)]
    subs = [("u", "a1", "2026-01-05", None)]
    gaps = {"a1": {"2026-01-20": 3, "2026-01-25": 0}, "a2": {"2026-01-20": 9, "2026-01-25": 0}}
    before = make_data(daily_rows("u", active), follows=follows, subs=subs, artist_gaps=gaps)

    after = make_data(
        daily_rows("u", active + ["2026-01-21", "2026-01-30"], purchase_days=["2026-01-22"]),  # 미래 활동/구매
        follows=[("u", "a1", "2026-01-02", "2026-01-28"),   # 미래에 언팔로우
                 ("u", "a2", "2026-01-23", None)],          # 미래에 새 팔로우
        subs=[("u", "a1", "2026-01-05", "2026-01-27"),      # 미래에 구독 해지
              ("u", "a2", "2026-01-24", None)],
        artist_gaps={"a1": {"2026-01-20": 3, "2026-01-25": 7}, "a2": {"2026-01-20": 9, "2026-01-25": 12}})

    pd.testing.assert_frame_equal(churn.make_features(before, T), churn.make_features(after, T))


def test_follow_is_point_in_time():
    data = make_data(
        daily_rows("u", ["2026-01-19"]),
        follows=[("u", "a1", "2026-01-02", None),            # 유지 중 -> 포함
                 ("u", "a2", "2026-01-02", "2026-01-19"),    # 기준일 전에 언팔로우 -> 제외
                 ("u", "a3", "2026-01-02", "2026-01-20"),    # 기준일 당일 언팔로우 -> 포함 (마트와 같은 규칙)
                 ("u", "a4", "2026-01-02", "2026-02-10"),    # 지금은 끝났지만 기준일에는 유지 중 -> 포함
                 ("u", "a5", "2026-01-21", None)])           # 기준일 뒤에 팔로우 -> 제외
    assert churn.make_features(data, T).loc["u", "n_following"] == 3


def test_subscription_is_point_in_time():
    data = make_data(
        daily_rows("now", ["2026-01-19"]) + daily_rows("ended_before", ["2026-01-19"])
        + daily_rows("ended_later", ["2026-01-19"]) + daily_rows("starts_later", ["2026-01-19"])
        + daily_rows("none", ["2026-01-19"]),
        subs=[("now", "a1", "2026-01-05", None),
              ("ended_before", "a1", "2026-01-05", "2026-01-15"),
              ("ended_later", "a1", "2026-01-05", "2026-02-01"),   # ended_at 이 채워져 있어도 기준일에는 구독 중
              ("starts_later", "a1", "2026-01-25", None)])
    got = churn.make_features(data, T)["is_subscribed"].to_dict()
    assert got == {"now": 1, "ended_before": 0, "ended_later": 1, "starts_later": 0, "none": 0}


def test_comm_gap_is_min_over_followed_artists():
    data = make_data(
        daily_rows("two", ["2026-01-19"]) + daily_rows("one", ["2026-01-19"]) + daily_rows("nobody", ["2026-01-19"]),
        follows=[("two", "a1", "2026-01-02", None), ("two", "a2", "2026-01-02", None),
                 ("one", "a1", "2026-01-02", None)],
        artist_gaps={"a1": {T: 5}, "a2": {T: 2}, "a3": {T: 0}})  # a3 은 아무도 팔로우하지 않는다
    f = churn.make_features(data, T)
    assert f.loc["two", "min_comm_gap"] == 2 and f.loc["two", "no_follow"] == 0
    assert f.loc["one", "min_comm_gap"] == 5
    # 팔로우가 없으면 값이 없으므로 0 으로 채우고, 표시 변수로 구분한다
    assert f.loc["nobody", "min_comm_gap"] == 0 and f.loc["nobody", "no_follow"] == 1


# ---------- 모집단 ----------
def test_population_rules():
    daily = (daily_rows("ok", ["2026-01-15"])
             + daily_rows("at_risk", ["2026-01-06"])                       # 기준일에 14일째 비활동
             + daily_rows("deleted", ["2026-01-15"])
             + daily_rows("tenure_14", ["2026-01-15"], start="2026-01-07")  # 가입일 포함 14일째 -> 포함
             + daily_rows("tenure_13", ["2026-01-15"], start="2026-01-08"))  # 13일째 -> 제외
    users = [{"user_id": "ok", "signup_date_kst": "2025-06-01", "is_deleted": False},
             {"user_id": "at_risk", "signup_date_kst": "2025-06-01", "is_deleted": False},
             {"user_id": "deleted", "signup_date_kst": "2025-06-01", "is_deleted": True},
             {"user_id": "tenure_14", "signup_date_kst": "2026-01-07", "is_deleted": False},
             {"user_id": "tenure_13", "signup_date_kst": "2026-01-08", "is_deleted": False}]
    data = make_data(daily, users=users)
    assert list(churn.select_population(data, T)) == ["ok", "tenure_14"]


def test_snapshot_and_dataset_shape():
    data = make_data(daily_rows("a", ["2026-01-15", "2026-01-25"]) + daily_rows("b", ["2026-01-15"]))
    snap = churn.build_snapshot(data, T)
    assert list(snap["user_id"]) == ["a", "b"] and list(snap["label"]) == [0, 1]
    assert set(churn.BASE_FEATURES + churn.GAP_FEATURES) <= set(snap.columns)
    assert not snap[churn.BASE_FEATURES + churn.GAP_FEATURES].isna().any().any()  # 모델에 넣을 값에 빈칸이 없다

    assert "label" not in churn.build_snapshot(data, T, with_label=False).columns  # "현재" 점수용

    both = churn.build_dataset(data, [T, "2026-01-27"])
    assert len(both) == 4 and both["ref_date"].nunique() == 2  # 같은 사용자가 기준일마다 한 행


# ---------- 기준일과 분할 ----------
def test_reference_dates_are_all_labelable():
    dates = churn.reference_dates()
    assert len(dates) == 9
    assert dates[0] == pd.Timestamp("2026-01-15") and dates[-1] == pd.Timestamp("2026-03-12")
    # 마지막 기준일 + 14일이 분석 종료일(03-31)을 넘지 않는다
    assert dates[-1] + pd.Timedelta(days=churn.LABEL_DAYS) <= pd.Timestamp("2026-03-31")


def test_split_has_gap_and_no_overlap():
    train, dropped, test = churn.split_dates(churn.reference_dates())
    assert [d.strftime("%m-%d") for d in train] == ["01-15", "01-22", "01-29", "02-05", "02-12"]
    assert [d.strftime("%m-%d") for d in dropped] == ["02-19"]
    assert [d.strftime("%m-%d") for d in test] == ["02-26", "03-05", "03-12"]
    assert not set(train) & set(test)
    # 학습 마지막 기준일의 라벨 창(14일)이 끝난 뒤에 평가가 시작된다
    assert (min(test) - max(train)).days >= churn.LABEL_DAYS


# ---------- 데이터 로딩 ----------
def test_load_sql_passes_guard():
    """고정 SQL 도 가드레일(SELECT 전용, 허용 테이블)을 그대로 통과해야 한다."""
    for sql in churn.LOAD_SQL.values():
        assert f"LIMIT {churn.LOAD_MAX_ROWS}" in validate_sql(sql, max_rows=churn.LOAD_MAX_ROWS)


def test_load_data_raises_when_truncated(monkeypatch):
    monkeypatch.setattr(churn, "LOAD_MAX_ROWS", 3)
    monkeypatch.setattr(churn, "run_query", lambda sql: (["user_id"], [["a"], ["b"], ["c"]]))
    with pytest.raises(RuntimeError):
        churn.load_data()
