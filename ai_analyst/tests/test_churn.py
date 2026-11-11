"""app/churn.py 테스트. DB 와 LLM 없이 작은 가짜 표로 돌린다.

가짜 데이터: 2026-01-01 ~ 2026-02-28 (59일), 기준일 T = 2026-01-20.
  - 최근 14일 창 = 01-07 ~ 01-20,  라벨 창 = 01-21 ~ 02-03
"""
import numpy as np
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
    assert set(churn.ALL_FEATURES) <= set(snap.columns)
    assert not snap[churn.ALL_FEATURES].isna().any().any()  # 모델에 넣을 값에 빈칸이 없다

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


# ---------- B단계: 기준선, 모델, 지표 ----------
def synthetic(n_users=400, dates=("2026-01-15", "2026-01-22"), seed=0):
    """신호를 심은 합성 데이터: 마지막 활동 후 일수가 길수록 라벨=1 이 될 확률이 높다."""
    rng = np.random.default_rng(seed)
    rows = []
    for t in dates:
        days = rng.integers(0, 14, n_users)
        a7 = rng.integers(0, 8, n_users)
        a14 = a7 + rng.integers(0, 8, n_users)
        rows.append(pd.DataFrame({
            "user_id": [f"u{i}" for i in range(n_users)], "ref_date": pd.Timestamp(t),
            "days_since_last_core_activity": days, "active_days_7": a7, "active_days_14": a14,
            "activity_change": 2 * a7 - a14, "purchased_14d": rng.integers(0, 2, n_users),
            "n_following": rng.integers(0, 4, n_users), "no_follow": rng.integers(0, 2, n_users),
            "is_subscribed": rng.integers(0, 2, n_users), "min_comm_gap": rng.integers(0, 9, n_users),
            "label": (rng.random(n_users) < 0.05 + 0.04 * days).astype(int)}))
    return pd.concat(rows, ignore_index=True)


def test_main_model_uses_activity_features_only():
    # 팔로우/구독 특징은 날짜 대리변수가 될 수 있어 주 모델(M1)에 넣지 않는다
    assert not set(churn.MODEL_FEATURES["M1"]) & set(churn.RELATION_FEATURES + churn.GAP_FEATURES)
    assert set(churn.RELATION_FEATURES) <= set(churn.MODEL_FEATURES["M2"])
    assert set(churn.GAP_FEATURES) <= set(churn.MODEL_FEATURES["M3"])


def test_baseline_is_days_since_last_activity():
    df = pd.DataFrame({"days_since_last_core_activity": [0, 13, 5]})
    assert list(churn.baseline_score(df)) == [0.0, 13.0, 5.0]


def test_precision_at_n():
    labels = [1, 0, 1, 0, 0]
    scores = [0.9, 0.8, 0.7, 0.2, 0.1]
    assert churn.precision_at_n(labels, scores, 2) == 0.5
    assert churn.precision_at_n(labels, scores, 3) == pytest.approx(2 / 3)
    assert churn.precision_at_n(labels, scores, 99) == pytest.approx(2 / 5)  # n 이 인원보다 크면 전체


def test_precision_at_n_ties_use_expected_value():
    # 상위 2명을 뽑는데 1등 뒤의 3명이 동점(그중 양성 1명) -> 남은 1자리의 기대값은 1/3
    assert churn.precision_at_n([1, 1, 0, 0], [9, 5, 5, 5], 2) == pytest.approx((1 + 1 / 3) / 2)
    # 행 순서를 바꿔도 값이 같다 (누가 먼저 적혀 있느냐에 좌우되지 않는다)
    assert churn.precision_at_n([0, 0, 1, 1], [5, 5, 5, 9], 2) == pytest.approx((1 + 1 / 3) / 2)


def test_per_date_auc_removes_date_effect():
    """날짜 안에서는 전혀 구분하지 못하는 점수(날짜별 상수)도, 합쳐서 재면 AUC 가 높게 나온다."""
    df = pd.DataFrame({
        "ref_date": [pd.Timestamp("2026-02-26")] * 4 + [pd.Timestamp("2026-03-05")] * 4,
        "label": [1, 0, 0, 0, 1, 1, 1, 0]})
    scores = [0.2] * 4 + [0.8] * 4  # "3월 5일이 더 위험하다"만 아는 점수
    result = churn.evaluate(df, scores, n=2)

    assert list(result["by_date"]["auc"]) == [0.5, 0.5] and result["auc_mean"] == 0.5
    assert result["auc_pooled"] > 0.7  # 날짜 효과만으로 부풀려진 값
    # lift = precision / 그 기준일의 양성 비율. 날짜 안에서 못 맞히면 1배
    assert list(result["by_date"]["lift"]) == pytest.approx([1.0, 1.0])
    assert list(result["by_date"]["top_share"]) == [0.5, 0.5]


def test_evaluate_perfect_scores():
    df = pd.DataFrame({"ref_date": [pd.Timestamp("2026-02-26")] * 4, "label": [1, 0, 0, 0]})
    row = churn.evaluate(df, [0.9, 0.3, 0.2, 0.1], n=1)["by_date"].iloc[0]
    assert row["auc"] == 1.0 and row["precision_at_n"] == 1.0
    assert row["base_rate"] == 0.25 and row["lift"] == 4.0


def test_model_smoke_finds_planted_signal():
    train, test = synthetic(seed=0), synthetic(seed=1)
    features = churn.MODEL_FEATURES["M1"]
    model = churn.fit_model(train, features)
    scores = churn.model_score(model, test, features)

    assert ((scores >= 0) & (scores <= 1)).all()
    assert churn.evaluate(test, scores)["auc_mean"] > 0.65  # 심어 둔 신호를 찾는다
    assert churn.coefficients(model, features)["days_since_last_core_activity"] > 0


def test_standardization_uses_train_statistics_only():
    train, test = synthetic(seed=0), synthetic(seed=1)
    test = test.assign(days_since_last_core_activity=test["days_since_last_core_activity"] + 100)  # 평가 구간만 크게 다름
    features = churn.MODEL_FEATURES["M1"]
    model = churn.fit_model(train, features)
    scaler = model[0]

    np.testing.assert_allclose(scaler.mean_, train[features].mean().to_numpy())
    churn.model_score(model, test, features)
    np.testing.assert_allclose(scaler.mean_, train[features].mean().to_numpy())  # 점수를 매겨도 다시 맞추지 않는다


def test_bootstrap_ci_is_reproducible_and_brackets_point_estimate():
    test = synthetic(n_users=150, seed=1)
    scores = {"M0": churn.baseline_score(test), "RANDOM": np.random.default_rng(5).random(len(test))}
    # 반복 횟수는 테스트에서만 줄인다 (운영/노트북 기본값은 1,000회)
    ci = churn.bootstrap_ci(test, scores, pairs=[("M0", "RANDOM")], n_boot=20, seed=3)
    again = churn.bootstrap_ci(test, scores, pairs=[("M0", "RANDOM")], n_boot=20, seed=3)

    pd.testing.assert_frame_equal(ci, again)  # 시드가 같으면 결과가 같다
    point = churn.evaluate(test, scores["M0"])["auc_mean"]
    assert ci.loc["M0 auc_mean", "ci_low"] < point < ci.loc["M0 auc_mean", "ci_high"]
    assert ci.loc["M0-RANDOM auc_mean", "ci_low"] > 0  # 신호가 있는 점수는 무작위보다 확실히 낫다


def test_bootstrap_resamples_users_not_rows(monkeypatch):
    test = synthetic(n_users=50, seed=1)
    sizes = []
    real = churn.evaluate
    monkeypatch.setattr(churn, "evaluate", lambda df, s, n=100: sizes.append(len(df)) or real(df, s, n))
    churn.bootstrap_ci(test, {"M0": churn.baseline_score(test)}, pairs=[], n_boot=5)
    # 사용자 50명을 복원 추출하면 사용자당 2행(기준일 2개)이 통째로 따라온다 -> 항상 100행
    assert sizes == [100] * 5


# ---------- C단계: 위험 군, 현재 점수, 세그먼트 ----------
def scored_users(n=200, n_gap_long=60, n_no_follow=10, seed=0):
    """score_current 결과 모양의 가짜 표."""
    rng = np.random.default_rng(seed)
    scores = rng.random(n)
    long_gap, short_gap, no_follow = churn.GAP_GROUPS
    return pd.DataFrame({
        "user_id": [f"u{i}" for i in range(n)], "score": scores, "tier": churn.assign_tiers(scores),
        "purchased_in_period": rng.integers(0, 2, n),
        "gap_group": [long_gap] * n_gap_long + [no_follow] * n_no_follow
                     + [short_gap] * (n - n_gap_long - n_no_follow)})


def test_tiers_are_by_rank():
    scores = np.arange(100) / 100          # 0.00 ~ 0.99, 뒤로 갈수록 위험 순위가 높다
    tiers = churn.assign_tiers(scores)
    assert list(tiers[90:]) == [churn.TIERS[0]] * 10       # 상위 10%
    assert list(tiers[70:90]) == [churn.TIERS[1]] * 20     # 다음 20%
    assert list(tiers[:70]) == [churn.TIERS[2]] * 70       # 나머지


def test_tiers_with_ties_keep_fixed_sizes():
    tiers = churn.assign_tiers([0.5] * 50)  # 전원 동점이어도 인원 비율은 지킨다
    assert [list(tiers).count(t) for t in churn.TIERS] == [5, 10, 35]
    assert list(tiers) == list(churn.assign_tiers([0.5] * 50))  # 항상 같은 결과


def test_tier_names_do_not_say_high_risk():
    assert not any("위험" in name for name in churn.TIERS)


def test_tier_table_rates_and_lift():
    # 상위 10%군 10행 중 양성 4, 11~30%군 20행 중 2, 나머지 70행 중 4 -> 전체 10%
    labels = [1] * 4 + [0] * 6 + [1] * 2 + [0] * 18 + [1] * 4 + [0] * 66
    tiers = [churn.TIERS[0]] * 10 + [churn.TIERS[1]] * 20 + [churn.TIERS[2]] * 70
    df = pd.DataFrame({"user_id": [f"u{i}" for i in range(100)], "label": labels})
    table = churn.tier_table(df, tiers, n_boot=20, seed=1).set_index("tier")

    assert list(table["n"]) == [10, 20, 70] and list(table["positives"]) == [4, 2, 4]
    assert table.loc[churn.TIERS[0], "label_rate"] == pytest.approx(0.4)
    assert table.loc[churn.TIERS[0], "lift"] == pytest.approx(4.0)   # 0.4 / 전체 0.1
    assert table.loc[churn.TIERS[1], "lift"] == pytest.approx(1.0)
    assert (table["rate_ci_low"] <= table["label_rate"]).all() and (table["label_rate"] <= table["rate_ci_high"]).all()
    pd.testing.assert_frame_equal(table, churn.tier_table(df, tiers, n_boot=20, seed=1).set_index("tier"))


def test_segments_sum_to_total_and_hide_user_id():
    scored = scored_users()
    result = churn.segment_table(scored)
    table = result["table"]

    assert result["gap_axis"] == "사용" and result["n_gap_long"] == 60
    assert table["n"].sum() == result["total"] == len(scored)
    assert "user_id" not in table.columns
    assert len(table) == 3 * 2 * 3  # 군 3 x 구매 2 x 공백 3 = 18칸, 0명인 칸도 빠지지 않는다
    assert table["share"].sum() == pytest.approx(1.0)
    # 팔로우 없는 팬은 "공백 4일 미만"에 섞이지 않고 따로 센다
    by_gap = table.groupby("comm_gap", observed=False)["n"].sum()
    assert by_gap.to_dict() == {"공백 4일 이상": 60, "공백 4일 미만": 130, "팔로우 없음": 10}


def test_segments_drop_gap_axis_when_too_few():
    for n_gap_long in (0, 19):
        result = churn.segment_table(scored_users(n_gap_long=n_gap_long))
        assert result["gap_axis"] == "해당 없음" and result["n_gap_long"] == n_gap_long
        assert "comm_gap" not in result["table"].columns
        assert len(result["table"]) == 3 * 2
        assert result["table"]["n"].sum() == result["total"] == 200  # 축을 빼도 합계는 그대로


def test_segments_mark_small_cells():
    table = churn.segment_table(scored_users())["table"]
    small = table["n"] < churn.MIN_CELL
    assert small.any()  # 상위 10%군(20명)을 6칸으로 나누면 20명 미만인 칸이 생긴다
    assert (table.loc[small, "note"] == churn.HOLD_NOTE).all()
    assert (table.loc[~small, "note"] == "").all()


@pytest.fixture(scope="module")
def full_data():
    """분석 기간 전체(01-01 ~ 03-31)를 덮는 가짜 데이터. 사용자마다 활동 확률이 다르다."""
    rng = np.random.default_rng(7)
    days = pd.date_range("2026-01-01", "2026-03-31")
    daily, users, follows = [], [], []
    for i in range(80):
        u = f"u{i:02d}"
        active = days[rng.random(len(days)) < rng.uniform(0.05, 0.5)]
        daily += daily_rows(u, active, purchase_days=active[:1] if i % 3 == 0 else (), end="2026-03-31")
        users.append({"user_id": u, "signup_date_kst": "2025-06-01", "is_deleted": i < 3})
        if i % 2 == 0:
            follows.append((u, "a1", "2026-01-02", None))
    # 03-25 가입자: 03-31 에 active 이지만 가입 14일 미만이라 모집단에서 빠진다
    daily += daily_rows("newbie", ["2026-03-30"], start="2026-03-25", end="2026-03-31")
    users.append({"user_id": "newbie", "signup_date_kst": "2026-03-25", "is_deleted": False})
    gaps = {"a1": {d: (5 if d == days[-1] else 0) for d in days}}
    return make_data(daily, users=users, follows=follows, artist_gaps=gaps)


def test_population_check_adds_up(full_data):
    check = churn.population_check(full_data)
    assert check["ref_date"] == pd.Timestamp("2026-03-31")
    assert check["excluded_short_tenure"] == 1  # newbie
    assert check["active_not_deleted"] == check["population"] + check["excluded_short_tenure"]


def test_score_current_uses_last_date_and_has_no_label(full_data):
    scored = churn.score_current(full_data)
    assert (scored["ref_date"] == pd.Timestamp("2026-03-31")).all()
    assert "label" not in scored.columns  # 03-31 의 정답은 데이터에 없다
    assert len(scored) == churn.population_check(full_data)["population"]
    assert scored["user_id"].is_unique and "newbie" not in set(scored["user_id"])
    assert scored["score"].between(0, 1).all()
    # 상위 10%군의 최저 점수가 나머지 군의 최고 점수보다 낮지 않다 (순위로 나눴다)
    top, rest = scored[scored["tier"] == churn.TIERS[0]], scored[scored["tier"] == churn.TIERS[2]]
    assert top["score"].min() >= rest["score"].max()
    # 소통 공백 3분류: 팔로우 없음은 따로, 나머지는 공백 값(이 가짜 데이터는 03-31 에 5일)으로 나뉜다
    assert set(scored["gap_group"]) <= set(churn.GAP_GROUPS)
    assert (scored.loc[scored["no_follow"] == 1, "gap_group"] == "팔로우 없음").all()
    assert (scored.loc[scored["no_follow"] == 0, "gap_group"] == "공백 4일 이상").all()


def test_gap_by_artist_combo_counts_without_user_id(full_data):
    scored = churn.score_current(full_data)
    combo = churn.gap_by_artist_combo(full_data, scored)
    assert "user_id" not in combo.columns
    assert combo["n"].sum() == len(scored)
    # 이 가짜 데이터는 아티스트가 a1 하나뿐이다: 팔로우하면 공백 5일, 아니면 팔로우 없음
    got = {(r.gap_group, r.artists) for r in combo.itertuples()}
    assert got == {("공백 4일 이상", "a1"), ("팔로우 없음", "(팔로우 없음)")}


def test_tier_comparison_is_side_by_side_and_marked_exploratory(full_data):
    table = churn.tier_comparison(full_data, n_boot=20)
    assert list(table["tier"]) == churn.TIERS * 2
    m1, m0 = table.iloc[:3], table.iloc[3:]
    assert (m1["ranking"] == "M1 주 모델").all() and m0["ranking"].str.contains("탐색적 추가").all()
    assert m1["n"].sum() == m0["n"].sum()  # 같은 평가 구간을 두 가지 순위로 나눈 것
    assert set(m1["m1_vs_m0"]) <= {churn.NOT_SEPARABLE, churn.SEPARABLE}
    # 판정 규칙: 두 구간이 겹치면 "구분 안 됨"
    overlap = (m1["rate_ci_low"].to_numpy() <= m0["rate_ci_high"].to_numpy()) & \
              (m0["rate_ci_low"].to_numpy() <= m1["rate_ci_high"].to_numpy())
    assert list(m1["m1_vs_m0"] == churn.NOT_SEPARABLE) == list(overlap)


def test_churn_report_always_pairs_segments_with_evidence(full_data):
    report = churn.churn_report(full_data, n_boot=20)
    assert report["segments"]["n"].sum() == report["total"] == report["population"]["population"]
    assert "user_id" not in report["segments"].columns
    assert list(report["tier_evidence"]["tier"]) == churn.TIERS  # 군의 의미를 보여주는 근거 표가 함께 온다
    assert churn.CAVEAT in report["notes"]
    assert "인과가 아니다" in churn.CAVEAT and "이탈 위험 순위가 높은 팬" in churn.CAVEAT
