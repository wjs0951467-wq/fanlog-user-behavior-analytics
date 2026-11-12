"""run_query 의 행 수 상한 테스트. 실제 DB 에 접속하지 않는다 (가짜 엔진을 끼운다)."""
import pytest

from app import db
from app.sql_guard import MAX_ROWS


class FakeResult:
    def __init__(self, total_rows):
        self.total_rows = total_rows
        self.fetchmany_sizes = []

    def keys(self):
        return ["n"]

    def fetchmany(self, size):
        self.fetchmany_sizes.append(size)
        return [(i,) for i in range(min(size, self.total_rows))]

    def fetchall(self):  # 쓰면 안 된다: 결과 전체를 메모리에 올린다
        raise AssertionError("fetchall() 을 부르면 안 된다")


class FakeEngine:
    def __init__(self, total_rows):
        self.result = FakeResult(total_rows)
        self.executed = []

    def connect(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement):
        self.executed.append(str(statement))
        return self.result


@pytest.fixture
def engine(monkeypatch):
    def install(total_rows):
        fake = FakeEngine(total_rows)
        monkeypatch.setattr(db, "get_engine", lambda: fake)
        return fake
    return install


def test_returns_columns_and_a_plain_list_of_rows(engine):
    engine(3)
    columns, rows = db.run_query("SELECT n FROM dim_user LIMIT 1000")  # 기존 호출 형태 그대로 (값 2개로 풀린다)
    assert columns == ["n"] and rows == [[0], [1], [2]]
    assert isinstance(rows, list) and rows.truncated is False


def test_reads_at_most_max_rows_plus_one_and_never_uses_fetchall(engine):
    fake = engine(5_000_000)  # 가드레일이 뚫려 LIMIT 없는 질의가 왔다고 가정
    _, rows = db.run_query("SELECT n FROM dim_user")
    assert fake.result.fetchmany_sizes == [MAX_ROWS + 1]  # 딱 한 번, 상한 + 1 행만 읽는다
    assert len(rows) == MAX_ROWS and rows.truncated is True


@pytest.mark.parametrize("total, expected_len, truncated", [
    (0, 0, False), (999, 999, False), (1000, 1000, False), (1001, 1000, True)])
def test_truncated_flag_boundary(engine, total, expected_len, truncated):
    engine(total)
    _, rows = db.run_query("SELECT n FROM dim_user LIMIT 1000")
    assert len(rows) == expected_len and rows.truncated is truncated


def test_max_rows_can_be_raised_by_the_caller(engine):
    fake = engine(130_000)  # churn.py 의 고정 SQL 경로 (약 13만 행)
    _, rows = db.run_query("SELECT n FROM mart_user_daily LIMIT 200000", max_rows=200_000)
    assert fake.result.fetchmany_sizes == [200_001]
    assert len(rows) == 130_000 and rows.truncated is False


def test_small_max_rows(engine):
    engine(10)
    _, rows = db.run_query("SELECT n FROM dim_user", max_rows=3)
    assert rows == [[0], [1], [2]] and rows.truncated is True


def test_default_cap_is_the_guard_cap():
    assert db.run_query.__defaults__ == (MAX_ROWS,)
