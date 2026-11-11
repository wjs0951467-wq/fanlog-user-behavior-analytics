"""이탈 위험 점수와 세그먼트 (Day 3). LLM 을 호출하지 않는다.

예측 문제: 기준일 t 에 active 인 팬이, t+1 ~ t+14일 동안 핵심 활동을 한 번도 하지 않는가 (churn_14d = 1).
          = "지금 활동 중인 팬이 14일 뒤 이탈 위험(at_risk) 상태로 넘어가는가"

이 파일의 원칙
- 특징(feature)은 기준일 t "이하"의 정보만 쓴다. 라벨(label)은 t "이후" 정보만 쓴다. (정보 누수 방지)
- 팔로우/구독처럼 "지금 상태"를 담은 컬럼은 기준일 시점으로 다시 계산한다.
- 계산은 DataFrame 을 받는 순수 함수로 만든다. DB 없이 작은 가짜 표로 테스트할 수 있게 하기 위해서다.
"""
import pandas as pd

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

# 모델에 넣는 특징. 소통 공백 2개는 "뺀 모델"과 비교하기 위해 따로 묶어 둔다 (Day 3 Q17).
BASE_FEATURES = ["days_since_last_core_activity", "active_days_7", "active_days_14", "activity_change",
                 "purchased_14d", "n_following", "is_subscribed"]
GAP_FEATURES = ["min_comm_gap", "no_follow"]


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
