"""이탈 위험 점수와 세그먼트 (Day 3). LLM 을 호출하지 않는다.

예측 문제: 기준일 t 에 active 인 팬이, t+1 ~ t+14일 동안 핵심 활동을 한 번도 하지 않는가 (churn_14d = 1).
          = "지금 활동 중인 팬이 14일 뒤 이탈 위험(at_risk) 상태로 넘어가는가"

이 파일의 원칙
- 특징(feature)은 기준일 t "이하"의 정보만 쓴다. 라벨(label)은 t "이후" 정보만 쓴다. (정보 누수 방지)
- 팔로우/구독처럼 "지금 상태"를 담은 컬럼은 기준일 시점으로 다시 계산한다.
- 계산은 DataFrame 을 받는 순수 함수로 만든다. DB 없이 작은 가짜 표로 테스트할 수 있게 하기 위해서다.
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .db import run_query
from .sql_guard import validate_sql

LABEL_DAYS = 14        # 라벨: 기준일 다음 날부터 14일
LOOKBACK_DAYS = 14     # 특징: 기준일 포함 최근 14일 고정 창 (기준일마다 같은 길이를 봐야 비교가 공정하다)
MIN_TENURE_DAYS = 14   # 가입 14일 미만은 제외 (최근 14일 특징이 불완전하고, 온보딩 이탈은 다른 문제다)
GAP_DAYS = 14          # 학습 마지막 기준일과 평가 첫 기준일 사이 간격 (= 라벨이 미래를 보는 길이)

FIRST_REF_DATE = "2026-01-15"  # 분석 시작(01-01) + 14일: 최근 14일 창이 처음으로 꽉 차는 다음 날
REF_STEP_DAYS = 7              # 매일을 기준일로 쓰면 같은 사용자의 거의 같은 행이 반복돼 표본 수가 부풀려진다
N_REF_DATES = 9                # 01-15 ~ 03-12. 마지막 기준일 + 14일 = 03-26 으로 분석 종료(03-31) 안에 든다
N_TRAIN_DATES = 5              # 학습 01-15 ~ 02-12 / 02-19 는 간격으로 버림 / 평가 02-26 ~ 03-12

# 가드레일의 기본 LIMIT 1000 으로는 mart_user_daily(약 13만 행)를 못 가져온다.
# 여기 SQL 은 모델이 만든 것이 아니라 코드에 고정된 것이므로, sql_guard.py 를 고치지 않고
# validate_sql 의 max_rows 인자만 크게 준다. SELECT 전용/허용 테이블 검사는 그대로 받는다.
LOAD_MAX_ROWS = 200_000

# 필요한 컬럼만 고른다 (5초 타임아웃 안에 끝나도록).
LOAD_SQL = {
    "daily": """
        SELECT user_id, activity_date_kst, had_core_activity, had_purchase,
               days_since_last_core_activity, activity_status
        FROM mart_user_daily""",
    "users": "SELECT user_id, signup_date_kst, is_deleted FROM dim_user",
    # 팔로우/구독 시각은 UTC 라서 KST 날짜로 바꿔 온다 (시맨틱 레이어 규칙: 날짜 분석은 KST)
    "follows": """
        SELECT user_id, artist_id,
               (followed_at_utc AT TIME ZONE 'Asia/Seoul')::date AS start_date_kst,
               (unfollowed_at_utc AT TIME ZONE 'Asia/Seoul')::date AS end_date_kst
        FROM bridge_user_artist_follow""",
    "subs": """
        SELECT user_id, artist_id,
               (started_at_utc AT TIME ZONE 'Asia/Seoul')::date AS start_date_kst,
               (ended_at_utc AT TIME ZONE 'Asia/Seoul')::date AS end_date_kst
        FROM fact_message_subscription""",
    "artist_daily": "SELECT artist_id, activity_date_kst, days_since_last_communication FROM mart_artist_daily",
}
DATE_COLUMNS = ("activity_date_kst", "signup_date_kst", "start_date_kst", "end_date_kst")

# 특징 묶음.
# 활동 기반: mart_user_daily 에서 나오며 분석 기간 내내 같은 방식으로 관측된다.
ACTIVITY_FEATURES = ["days_since_last_core_activity", "active_days_7", "active_days_14", "activity_change",
                     "purchased_14d"]
# 관계 기반: 팔로우 이력이 2026-01-01 부터만 있어서 이른 기준일일수록 "팔로우 없음"이 많다(학습 52% vs 평가 19%).
# 실제 관계보다 "기준일이 얼마나 이른가"를 나타내는 날짜 대리변수가 될 수 있어 주 모델에서 뺀다.
RELATION_FEATURES = ["n_following", "no_follow", "is_subscribed"]
# 소통 공백: 아티스트가 3팀뿐이라 이것도 날짜에 따라 움직인다. README 가설 H-02 와 연결되는 비교용.
GAP_FEATURES = ["min_comm_gap", "no_follow"]

# M0 은 모델이 아니라 규칙 기준선(마지막 핵심 활동 후 일수가 긴 순서)이다.
# 대표 성능은 M1. M2/M3 는 "특징을 추가했을 때 달라지는가"를 보는 비교다.
MODEL_FEATURES = {
    "M1": ACTIVITY_FEATURES,
    "M2": ACTIVITY_FEATURES + RELATION_FEATURES,
    "M3": ACTIVITY_FEATURES + GAP_FEATURES,
}
ALL_FEATURES = ACTIVITY_FEATURES + RELATION_FEATURES + ["min_comm_gap"]

LOGISTIC_C = 1.0   # 정규화 강도. scikit-learn 기본값으로 고정하고 평가 구간 결과를 보고 조정하지 않는다
TOP_N = 100        # precision@N 의 N (기준일별 상위 100명)
N_BOOTSTRAP = 1000
BOOTSTRAP_SEED = 0


# ---------- 데이터 로딩 ----------
def prepare(data: dict) -> dict:
    """날짜 컬럼을 pandas 날짜형으로 통일한다. (DB 는 date 객체, 테스트는 문자열로 주기 때문)"""
    out = {}
    for name, df in data.items():
        df = df.copy()
        for col in DATE_COLUMNS:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col])
        out[name] = df
    return out


def load_data() -> dict:
    """읽기 전용 계정으로 필요한 표 5개를 읽어 {이름: DataFrame} 으로 돌려준다."""
    data = {}
    for name, sql in LOAD_SQL.items():
        columns, rows = run_query(validate_sql(sql, max_rows=LOAD_MAX_ROWS))
        if len(rows) >= LOAD_MAX_ROWS:  # LIMIT 에 걸려 조용히 잘린 데이터로 모델을 만들지 않는다
            raise RuntimeError(f"{name}: 행 수가 상한({LOAD_MAX_ROWS:,})에 닿았습니다. 데이터가 잘렸을 수 있습니다.")
        data[name] = pd.DataFrame(rows, columns=columns)
    return prepare(data)


# ---------- 기준일과 분할 ----------
def reference_dates(first: str = FIRST_REF_DATE, n: int = N_REF_DATES, step_days: int = REF_STEP_DAYS) -> list:
    return list(pd.date_range(first, periods=n, freq=f"{step_days}D"))


def split_dates(ref_dates: list, n_train: int = N_TRAIN_DATES, gap_days: int = GAP_DAYS) -> tuple:
    """기준일을 (학습, 버림, 평가)로 나눈다. 시간순 분할이며 무작위로 섞지 않는다.

    학습 마지막 기준일의 라벨은 그 뒤 14일을 본다. 평가가 그 14일 안에서 시작하면
    학습 라벨이 평가 구간의 활동을 미리 본 셈이 되므로, 간격 안의 기준일은 버린다.
    """
    ref_dates = sorted(ref_dates)
    train = ref_dates[:n_train]
    first_test = train[-1] + pd.Timedelta(days=gap_days)
    dropped = [d for d in ref_dates[n_train:] if d < first_test]
    test = [d for d in ref_dates[n_train:] if d >= first_test]
    return train, dropped, test


# ---------- 라벨 ----------
def _wide(daily: pd.DataFrame, column: str) -> pd.DataFrame:
    """(사용자 x 날짜) 표로 펼친다. 값은 True/False. 가입 전이라 행이 없는 칸은 False."""
    wide = daily.pivot(index="user_id", columns="activity_date_kst", values=column)
    return wide.eq(True).sort_index(axis=1)


def make_labels(daily: pd.DataFrame, t) -> pd.Series:
    """churn_14d: t+1 ~ t+14일 동안 핵심 활동이 한 번도 없으면 1.

    데이터가 t+14일까지 없으면 정답을 알 수 없으므로 에러를 낸다 (조용히 0/1 을 만들지 않는다).
    """
    t = pd.Timestamp(t)
    last = t + pd.Timedelta(days=LABEL_DAYS)
    if last > daily["activity_date_kst"].max():
        raise ValueError(f"{t.date()} 는 이후 {LABEL_DAYS}일 데이터가 없어 라벨을 만들 수 없습니다.")
    future = _wide(daily, "had_core_activity").loc[:, t + pd.Timedelta(days=1): last]
    return (~future.any(axis=1)).astype(int).rename("label")


# ---------- 모집단 ----------
def select_population(data: dict, t) -> pd.Index:
    """기준일 t 의 예측 대상 user_id.

    1) t 에 active 인 사용자만: 이미 at_risk/dormant 인 사용자는 "계속 비활동인가"라는 다른 질문이 된다.
    2) 탈퇴자(is_deleted) 제외: 시맨틱 레이어/평가 기대값과 같은 기준.
       (탈퇴 시각이 t 이후인 사용자도 빠지므로 약한 미래 정보 사용이다. DESIGN.md 한계 참고)
    3) 가입 14일 미만 제외: 최근 14일 특징이 불완전하다.
    """
    t = pd.Timestamp(t)
    daily, users = data["daily"], data["users"]
    active = daily.loc[(daily["activity_date_kst"] == t) & (daily["activity_status"] == "active"), "user_id"]
    oldest_signup = t - pd.Timedelta(days=MIN_TENURE_DAYS - 1)  # 가입일 포함 14일째가 t
    ok = users.loc[~users["is_deleted"].astype(bool) & (users["signup_date_kst"] <= oldest_signup), "user_id"]
    return pd.Index(sorted(set(active) & set(ok)), name="user_id")


# ---------- 특징 ----------
def _active_on(spans: pd.DataFrame, t) -> pd.DataFrame:
    """기간 표(팔로우/구독)에서 기준일 t 에 유효한 행만 고른다.

    "end_date_kst IS NULL"(지금도 유지 중)로 고르면 오늘 기준 상태라서 미래 정보가 섞인다.
    t 시점 기준으로 "t 이전에 시작했고, 아직 안 끝났거나 t 이후에 끝난" 행을 고른다.
    끝난 당일은 유지 중으로 본다 (mart_artist_daily 의 active_follow_days 와 같은 규칙).
    """
    started = spans["start_date_kst"] <= t
    not_ended = spans["end_date_kst"].isna() | (spans["end_date_kst"] >= t)
    return spans[started & not_ended]


def make_features(data: dict, t) -> pd.DataFrame:
    """기준일 t 의 사용자별 특징 표 (index = user_id). t 이후 데이터는 한 줄도 쓰지 않는다."""
    t = pd.Timestamp(t)
    daily = data["daily"]
    window_start = t - pd.Timedelta(days=LOOKBACK_DAYS - 1)
    if window_start < daily["activity_date_kst"].min():
        raise ValueError(f"{t.date()} 는 최근 {LOOKBACK_DAYS}일 데이터가 다 없어 특징을 만들 수 없습니다.")
    week_start = t - pd.Timedelta(days=6)

    core = _wide(daily, "had_core_activity")
    purchase = _wide(daily, "had_purchase")
    today = daily[daily["activity_date_kst"] == t].set_index("user_id")

    f = pd.DataFrame(index=core.index)
    f["days_since_last_core_activity"] = today["days_since_last_core_activity"]
    f["active_days_7"] = core.loc[:, week_start:t].sum(axis=1)
    f["active_days_14"] = core.loc[:, window_start:t].sum(axis=1)
    # 직전 주 대비 변화 = 최근 7일 활동일수 - 그 앞 7일 활동일수 (음수면 활동이 줄어드는 중)
    f["activity_change"] = f["active_days_7"] - (f["active_days_14"] - f["active_days_7"])
    f["purchased_14d"] = purchase.loc[:, window_start:t].any(axis=1).astype(int)
    # 세그먼트용(모델에는 넣지 않음): 누적 값이라 기준일이 늦을수록 커져서 학습/평가 구간의 분포가 달라진다
    f["purchased_in_period"] = purchase.loc[:, :t].any(axis=1).astype(int)

    follows = _active_on(data["follows"], t)
    f["n_following"] = follows.groupby("user_id")["artist_id"].nunique()
    f["n_following"] = f["n_following"].fillna(0).astype(int)
    f["is_subscribed"] = f.index.isin(_active_on(data["subs"], t)["user_id"]).astype(int)

    # 체감 소통 공백: 팔로우 중인 아티스트들의 소통 공백 중 최솟값 (README 발견 1 과 같은 정의).
    # "한 팀이라도 최근에 소통했으면 팬은 공백을 덜 느낀다"는 가정이다.
    artist = data["artist_daily"]
    gaps = artist.loc[artist["activity_date_kst"] == t, ["artist_id", "days_since_last_communication"]]
    f["min_comm_gap"] = follows.merge(gaps, on="artist_id").groupby("user_id")["days_since_last_communication"].min()
    # 팔로우가 없으면 공백 값이 없다. 0 으로 채우되 "팔로우 없음" 표시를 따로 둬서 모델이 구분할 수 있게 한다.
    f["no_follow"] = f["min_comm_gap"].isna().astype(int)
    f["min_comm_gap"] = f["min_comm_gap"].fillna(0)
    return f


def build_snapshot(data: dict, t, with_label: bool = True) -> pd.DataFrame:
    """기준일 t 의 모집단 x (특징 + 라벨) 표. with_label=False 는 정답을 모르는 "현재" 점수용."""
    t = pd.Timestamp(t)
    snap = make_features(data, t).loc[select_population(data, t)].copy()
    snap.insert(0, "ref_date", t)
    if with_label:
        snap["label"] = make_labels(data["daily"], t).loc[snap.index]
    return snap.reset_index()


def build_dataset(data: dict, dates: list) -> pd.DataFrame:
    """여러 기준일의 스냅샷을 위아래로 붙인다. 같은 사용자가 기준일마다 한 행씩 나온다."""
    return pd.concat([build_snapshot(data, t) for t in dates], ignore_index=True)


# ---------- 점수: 기준선과 로지스틱 회귀 ----------
def baseline_score(df: pd.DataFrame) -> np.ndarray:
    """M0 규칙 기준선: 마지막 핵심 활동 후 일수가 길수록 위험하다고 본다. 학습이 필요 없다."""
    return df["days_since_last_core_activity"].to_numpy(dtype=float)


def fit_model(train: pd.DataFrame, features: list, C: float = LOGISTIC_C):
    """표준화 + 로지스틱 회귀.

    표준화를 파이프라인 안에 넣는 이유: fit 은 학습 데이터로만 하므로, 평균/표준편차도 학습 구간 값만 쓴다.
    평가 구간까지 합쳐 표준화하면 평가 구간의 정보가 모델에 새어 들어간다.
    class_weight 는 쓰지 않는다. 순위 지표에는 영향이 거의 없고 예측 확률만 왜곡되기 때문이다.
    """
    model = make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=1000))
    return model.fit(train[features], train["label"])


def model_score(model, df: pd.DataFrame, features: list) -> np.ndarray:
    """14일 안에 핵심 활동이 없을 확률 추정치 (0~1)."""
    return model.predict_proba(df[features])[:, 1]


def coefficients(model, features: list) -> pd.Series:
    """표준화한 특징의 계수. 단위가 "표준편차 1만큼"으로 같아져 크기를 서로 비교할 수 있다.

    해석 주의: 상관관계일 뿐 원인이 아니다. 또 비슷한 정보를 담은 특징끼리는 계수를 서로 나눠 가지므로
    (예: activity_change = 2 x active_days_7 - active_days_14) 개별 계수의 크기와 부호가 불안정하다.
    """
    return pd.Series(model[-1].coef_[0], index=features, name="coef_standardized")


# ---------- 지표 ----------
def precision_at_n(labels, scores, n: int = TOP_N) -> float:
    """점수 상위 n명 중 실제 양성(라벨=1)의 비율.

    동점 처리: 기준선은 "일수"라서 같은 점수가 많다. 경계에 걸린 동점자 중 누구를 뽑느냐에 따라
    값이 흔들리지 않도록, 동점자 중에서 무작위로 뽑았을 때의 기대값으로 계산한다.
    """
    labels, scores = np.asarray(labels, dtype=float), np.asarray(scores, dtype=float)
    n = min(n, len(scores))
    cutoff = np.sort(scores)[::-1][n - 1]  # n번째로 높은 점수
    above, tied = scores > cutoff, scores == cutoff
    slots_left = n - above.sum()            # 동점자에게 돌아가는 자리 수
    return float((labels[above].sum() + slots_left * labels[tied].mean()) / n)


def evaluate(df: pd.DataFrame, scores, n: int = TOP_N) -> dict:
    """기준일별 지표와 그 평균을 계산한다.

    왜 기준일별인가: 기준일마다 양성 비율이 다르다. 전체를 합쳐서 AUC 를 재면
    "누가 위험한가"가 아니라 "어느 날짜가 위험한가"만 맞혀도 점수가 올라간다.
    운영에서는 같은 날의 팬들 사이에서 순위를 매기므로, 기준일 안에서의 순위 성능이 주 지표다.
    """
    scored = df[["ref_date", "label"]].assign(score=np.asarray(scores, dtype=float))
    rows = []
    for t, g in scored.groupby("ref_date"):
        base_rate = g["label"].mean()
        precision = precision_at_n(g["label"], g["score"], n)
        rows.append({"ref_date": t, "n": len(g), "base_rate": base_rate,
                     "auc": roc_auc_score(g["label"], g["score"]),
                     "pr_auc": average_precision_score(g["label"], g["score"]),
                     "precision_at_n": precision,
                     "lift": precision / base_rate,           # 무작위로 뽑았을 때 대비 몇 배인가
                     "top_share": min(n, len(g)) / len(g)})   # 상위 n명이 그날 인원의 몇 %인가
    by_date = pd.DataFrame(rows)
    return {"by_date": by_date,
            "auc_mean": by_date["auc"].mean(),            # 주 지표
            "pr_auc_mean": by_date["pr_auc"].mean(),
            "lift_mean": by_date["lift"].mean(),
            "auc_pooled": roc_auc_score(scored["label"], scored["score"]),  # 참고용 (날짜 효과 포함)
            "pr_auc_pooled": average_precision_score(scored["label"], scored["score"])}


def bootstrap_ci(df: pd.DataFrame, scores: dict, pairs: list, n_boot: int = N_BOOTSTRAP,
                 seed: int = BOOTSTRAP_SEED, n: int = TOP_N) -> pd.DataFrame:
    """사용자 단위 부트스트랩으로 95% 신뢰구간을 구한다.

    왜 행이 아니라 사용자 단위인가: 같은 사용자가 여러 기준일에 나오고 그 행들은 서로 비슷하다.
    행을 독립인 것처럼 뽑으면 표본이 실제보다 많은 것처럼 보여 구간이 너무 좁게 나온다.
    그래서 "사용자"를 복원 추출하고, 뽑힌 사용자의 모든 행을 함께 가져온다.
    pairs 는 [("M1", "M0"), ...]: 같은 재표본에서 두 모델의 차이(앞 - 뒤)를 구해 "개선"의 구간을 낸다.
    """
    rng = np.random.default_rng(seed)
    rows_of_user = df.groupby("user_id").indices  # user_id -> 그 사용자의 행 위치들
    users = np.array(list(rows_of_user))
    samples = []
    for _ in range(n_boot):
        picked = rng.choice(users, size=len(users), replace=True)
        idx = np.concatenate([rows_of_user[u] for u in picked])
        part = df.iloc[idx]
        one = {}
        for name, s in scores.items():
            result = evaluate(part, np.asarray(s)[idx], n)
            one[f"{name} auc_mean"], one[f"{name} lift_mean"] = result["auc_mean"], result["lift_mean"]
        for a, b in pairs:
            one[f"{a}-{b} auc_mean"] = one[f"{a} auc_mean"] - one[f"{b} auc_mean"]
            one[f"{a}-{b} lift_mean"] = one[f"{a} lift_mean"] - one[f"{b} lift_mean"]
        samples.append(one)
    q = pd.DataFrame(samples).quantile([0.025, 0.975])
    return pd.DataFrame({"ci_low": q.loc[0.025], "ci_high": q.loc[0.975]})


def run_evaluation(data: dict, n_boot: int = N_BOOTSTRAP) -> dict:
    """학습 구간으로 M1~M3 를 학습하고 평가 구간에서 M0~M3 를 비교한다 (노트북과 보고용)."""
    train_dates, dropped_dates, test_dates = split_dates(reference_dates())
    train, test = build_dataset(data, train_dates), build_dataset(data, test_dates)

    models = {name: fit_model(train, feats) for name, feats in MODEL_FEATURES.items()}
    scores = {"M0": baseline_score(test)}
    scores.update({name: model_score(models[name], test, feats) for name, feats in MODEL_FEATURES.items()})

    return {
        "train": train, "test": test, "models": models, "scores": scores,
        "dates": {"train": train_dates, "dropped": dropped_dates, "test": test_dates},
        "metrics": {name: evaluate(test, s) for name, s in scores.items()},
        "ci": bootstrap_ci(test, scores, pairs=[("M1", "M0"), ("M2", "M1"), ("M3", "M1")], n_boot=n_boot),
        "coefficients": {name: coefficients(models[name], feats) for name, feats in MODEL_FEATURES.items()},
    }
