"""질문 하나의 전체 마감 시간.

왜 필요한가
- OpenAI 호출에는 호출당 제한(60초)이, DB 에는 문 실행 제한(5초)이 있지만, 질문 전체에는 마감이 없었다.
  Docker(DB 컨테이너)가 꺼진 채로 질문을 제출했더니 연결 시도가 끝나지 않아 질문이 3분 넘게 끝나지 않았다.
- 마감이 지나면 "새 호출"을 시작하지 않고 오류로 끝낸다. 지금 진행 중인 호출을 강제로 끊을 수는 없다.
  그래서 최악의 종료 시각은 "마감 + 호출 하나가 끝나는 데 걸리는 시간"이다.
  호출당 제한(llm.CLIENT_TIMEOUT_SECONDS = 60초, DB 연결 5초 + 문 5초)이 마감(120초)보다 작아서, 마감 전에 시작한 호출은 마감 + 60초 안에 끝난다.

어떻게 쓰는가
- run_agent 가 질문을 시작할 때 start() 로 마감을 걸고, 끝나면(예외가 나도) clear() 로 되돌린다.
- ask(), recommend_actions 같은 곳은 새 LLM 호출 전에 expired() 를 확인한다. 마감이 걸리지 않은 호출(/ask, CLI, 평가)은 expired() 가 항상 False 라서 동작이 그대로다.
- 마감 상태는 contextvars 로 질문(실행 흐름)마다 따로 가진다. Streamlit 은 세션마다 다른 스레드에서 돌아서, 전역 변수 하나면 다른 세션의 마감과 섞인다.
- 평가 하네스(eval/)도 같은 상수(QUESTION_DEADLINE_SECONDS)를 쓸 수 있다.
"""
import contextvars
import time

QUESTION_DEADLINE_SECONDS = 120   # 질문 하나의 전체 마감 (한 곳에서만 정한다)
TIMEOUT_ERROR = f"[시간 초과] 질문 하나의 처리 시간 상한({QUESTION_DEADLINE_SECONDS}초)을 넘어 중단했습니다."

_now = time.monotonic             # 시계는 이 이름으로만 읽는다 (테스트가 가짜 시계로 바꿔 끼운다). monotonic 은 시스템 시계 변경에 흔들리지 않는다.
_deadline = contextvars.ContextVar("fanlog_question_deadline", default=None)


def start(seconds: float | None = None):
    """지금부터 seconds 초(기본: 상수) 뒤를 마감으로 건다. clear() 에 넘길 토큰을 돌려준다."""
    return _deadline.set(_now() + (QUESTION_DEADLINE_SECONDS if seconds is None else seconds))


def clear(token) -> None:
    """start() 이전 상태(마감 없음, 또는 바깥 마감)로 되돌린다."""
    _deadline.reset(token)


def expired() -> bool:
    """마감이 걸려 있고 그 시각이 지났는가. 마감이 걸려 있지 않으면 항상 False."""
    limit = _deadline.get()
    return limit is not None and _now() >= limit
