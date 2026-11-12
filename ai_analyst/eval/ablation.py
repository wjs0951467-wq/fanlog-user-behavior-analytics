"""비교 실험(ablation) 구성 A~D. app/ 파일을 고치지 않고, 실행하는 동안만 text2sql 의 두 가지를 바꿨다가 되돌린다.

구성 (뒤로 갈수록 하나씩 더한다)
  A 스키마만            : 테이블, 컬럼, 타입만 보여준다. 값 목록과 시맨틱 레이어가 없다. SQL 호출 1회.
  B + 값 프로파일       : 컬럼의 실제 값 목록, 날짜 범위, 행 수를 더한다. SQL 호출 1회.
  C + 시맨틱 레이어     : 지표 정의(semantic_layer.yaml)를 더한다 = 지금 앱의 프롬프트. SQL 호출 1회.
  D + 재시도와 거짓 거절 교정 : 지금 앱 그대로 (SQL 호출 최대 3회). 아무것도 바꾸지 않는다.

바꾸는 것은 두 가지뿐이다
  - text2sql.build_system_prompt : ask() 가 매번 이 이름으로 불러 쓰므로, 모듈의 이름을 바꿔 끼우면 프롬프트가 바뀐다.
  - text2sql.MAX_SQL_CALLS       : 1 로 두면 재시도가 없다. 거짓 거절 교정도 "재시도"라서 같이 꺼진다
    (ask() 는 거짓 거절을 발견하면 다음 호출에서 교정하는데, 호출이 1회뿐이면 "[거짓 거절] 1회 시도 후 실패"로 끝난다).

한계 (PROGRESS.md 에도 적었다)
  - A, B 의 프롬프트에도 SYSTEM_RULES 는 그대로 들어간다. 그 안에 "SEMANTIC LAYER 를 따르라", "schema profile 의 값만 써라"
    같은 문장이 있다. 규칙 문장까지 구성별로 다르게 쓰면 무엇의 효과인지 흐려져서 그대로 두었다.
  - 재시도와 거짓 거절 교정을 따로 떼어 볼 수는 없다 (ask() 안에서 같은 반복문이라 app/ 를 고치지 않고는 분리할 수 없다).
"""
from contextlib import contextmanager

from app import text2sql
from app.sql_guard import ALLOWED_TABLES

CONFIGS = ("A", "B", "C", "D")
DESCRIPTIONS = {"A": "스키마만", "B": "+ 값 프로파일", "C": "+ 시맨틱 레이어", "D": "+ 재시도와 거짓 거절 교정"}
FULL_SQL_CALLS = text2sql.MAX_SQL_CALLS  # 앱의 원래 값(3). 이 모듈을 import 하는 시점에 한 번 읽어 둔다

_active = False  # 겹쳐 쓰기 방지: 구성 안에서 또 구성을 걸면 "원래 값"이 무엇인지 알 수 없게 된다


def calls_per_question(config: str) -> int:
    """구성별 질문 1개의 최대 LLM 호출 수 (평가에서는 요약을 끄므로 SQL 생성 호출만 있다)."""
    _check(config)
    return FULL_SQL_CALLS if config == "D" else 1


def _check(config: str) -> None:
    if config not in CONFIGS:
        raise ValueError(f"구성은 {CONFIGS} 중 하나여야 한다: {config!r}")


def render_schema_only(profile: dict) -> str:
    """테이블, 컬럼, 타입만. 값 목록, 날짜 범위, 행 수, JSON 키는 넣지 않는다 (그것들이 "값 프로파일"이다)."""
    lines = []
    for table, info in profile.items():
        if table not in ALLOWED_TABLES:
            continue
        lines.append(f"{info.get('kind', 'table').upper()} {table}")
        lines += [f"  - {col}: {ci['type']}" for col, ci in info["columns"].items()]
        lines.append("")
    return "\n".join(lines)


def build_prompt(config: str) -> str:
    """구성 A, B 의 시스템 프롬프트. C 와 D 는 앱의 프롬프트를 그대로 쓰므로 여기서 만들지 않는다."""
    profile = text2sql.load_profile()
    available = ", ".join(t for t in profile if t in ALLOWED_TABLES)
    head = f"{text2sql.SYSTEM_RULES}\nAVAILABLE TABLES: {available}\n\n"
    if config == "A":
        return head + f"=== SCHEMA ===\n{render_schema_only(profile)}\n"
    if config == "B":
        return head + f"=== SCHEMA PROFILE ===\n{text2sql.render_schema(profile)}\n"
    raise ValueError("build_prompt 는 구성 A, B 에만 쓴다")


@contextmanager
def applied(config: str):
    """with applied("A"): 안에서만 구성을 적용하고, 나갈 때(예외가 나도) 반드시 원래대로 되돌린다."""
    global _active
    _check(config)
    if _active:
        raise RuntimeError("비교 실험 구성은 겹쳐서 쓸 수 없다")
    original_prompt, original_calls = text2sql.build_system_prompt, text2sql.MAX_SQL_CALLS
    _active = True
    try:
        if config in ("A", "B"):
            text2sql.build_system_prompt = lambda: build_prompt(config)
        if config != "D":
            text2sql.MAX_SQL_CALLS = 1
        yield config
    finally:
        text2sql.build_system_prompt = original_prompt
        text2sql.MAX_SQL_CALLS = original_calls
        _active = False


def is_restored() -> bool:
    """지금 앱이 원래 상태인가 (실행기가 끝난 뒤 확인용)."""
    return not _active and text2sql.MAX_SQL_CALLS == FULL_SQL_CALLS
