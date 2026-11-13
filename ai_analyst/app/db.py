"""DB 연결. 앱은 반드시 읽기 전용 계정(DATABASE_URL_RO)만 사용한다."""
import os
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from .sql_guard import MAX_ROWS

load_dotenv()

# DB 연결을 맺는 데 기다리는 최대 시간(초). 이 제한이 없으면 DB 컨테이너(Docker)가 꺼진 채로 질문을 제출했을 때
# 연결 시도가 끝나지 않아 질문 전체가 멈추고, 블로킹 중인 서버는 Ctrl+C 에도 바로 반응하지 못했다(사건 기록: DESIGN.md 10장).
# statement_timeout(문 실행 5초)과 다른 제한이다: 이쪽은 "연결 맺기", 저쪽은 "맺은 뒤 문 실행".
# libpq 의 connect_timeout 은 초 단위 정수이고, 2초 미만으로 주면 2초로 올려 쓴다.
CONNECT_TIMEOUT_SECONDS = 5


class Rows(list):
    """행 목록. 보통의 list 와 똑같이 쓰고, 상한에서 잘렸는지를 truncated 로 알려준다.

    왜 list 를 상속했나: run_query 의 반환 형태 (컬럼, 행 목록) 을 바꾸지 않기 위해서다.
    기존 호출부와 테스트의 가짜 run_query(그냥 list 를 돌려준다)는 그대로 동작하고,
    잘림 여부가 필요한 쪽만 getattr(rows, "truncated", False) 로 읽는다.
    """
    truncated = False


@lru_cache(maxsize=1)
def get_engine():
    return create_engine(
        os.environ["DATABASE_URL_RO"],
        # 3차 방어선: 계정 설정과 별개로 연결 단위에서도 읽기 전용 + 5초 제한
        connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS,
                      "options": "-c default_transaction_read_only=on -c statement_timeout=5000"},
        pool_pre_ping=True,
    )


def run_query(sql: str, max_rows: int = MAX_ROWS):
    """(컬럼명 리스트, 행 리스트) 반환. 호출 전에 반드시 sql_guard.validate_sql 을 거칠 것.

    가드레일이 LIMIT 을 강제하지만, 여기서도 한 번 더 막는다 (가드레일에 빈틈이 있어도 결과가 폭주하지 않게).
    fetchall() 은 결과 전체를 메모리에 올리므로 쓰지 않는다. max_rows + 1 행까지만 읽어서
    상한을 넘었는지 확인하고, 넘었으면 max_rows 행으로 자르고 rows.truncated = True 로 표시한다.
    """
    with get_engine().connect() as conn:
        result = conn.execute(text(sql))
        columns = list(result.keys())
        fetched = result.fetchmany(max_rows + 1)
    rows = Rows(list(r) for r in fetched[:max_rows])
    rows.truncated = len(fetched) > max_rows
    return columns, rows
