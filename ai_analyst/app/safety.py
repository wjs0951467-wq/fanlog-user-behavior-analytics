"""출력 경계에서 쓰는 안전 함수: 사용자 ID 가리기, 모델 입력 길이 자르기.

왜 "값 기준"인가
- 화면은 컬럼 이름에 user_id 가 있을 때만 숨기지만, SELECT user_id AS id 처럼 별칭을 쓰면 이름 기준 숨김은 뚫린다.
  그래서 값이 사용자 ID 모양이면 어떤 이름의 컬럼이든, 문장 속이든 "[ID]" 로 바꾼다.
- SQL 자체를 막지 않는 이유: churn.py 의 고정 SQL 이 user_id 를 읽어야 한다. 가리는 것은 ask() 가 내보내는 결과에만 적용한다.

가리는 대상은 dim_user.user_id 모양("user_" + 숫자 6자리)뿐이다. 주문번호(txn_), 상품(product_), 콘텐츠(content_),
이벤트(event_), 팔로우(follow_), 구독(subscription_) 같은 다른 ID 는 가리지 않는다.
"""
import re

ID_MASK = "[ID]"

# 앞뒤가 ASCII 글자/숫자/밑줄이면 다른 이름의 일부(xuser_000123, user_000123abc)라서 가리지 않는다.
# 한글이 바로 붙은 "user_000123의"는 가린다. 숫자는 6자리 이상으로 잡아 사용자가 늘어도(7자리) 새지 않게 한다.
USER_ID_PATTERN = re.compile(r"(?<![A-Za-z0-9_])user_\d{6,}(?![A-Za-z0-9_])", re.IGNORECASE)

MODEL_TEXT_CHARS = 200          # 모델에게 보내는 모든 문자열 칸의 길이 상한 (토큰 절약 + 데이터 속 지시문이 통째로 들어가는 것 방지)
CLIP_MARK = "...(잘림)"


def mask_ids_counted(text) -> tuple:
    """(가린 문자열, 가린 개수). 문자열이 아니면 str() 로 바꿔서 처리한다."""
    return USER_ID_PATTERN.subn(ID_MASK, "" if text is None else str(text))


def mask_ids(text) -> str:
    return mask_ids_counted(text)[0]


def _walk(obj, fn):
    """dict, list, tuple 안의 문자열에 fn 을 적용한 "새" 객체를 돌려준다 (입력은 바꾸지 않는다). 키와 숫자는 그대로다."""
    if isinstance(obj, str):
        return fn(obj)
    if isinstance(obj, dict):
        return {k: _walk(v, fn) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk(v, fn) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_walk(v, fn) for v in obj)
    return obj


def mask_deep(obj):
    return _walk(obj, mask_ids)


def mask_rows(rows) -> tuple:
    """결과 행의 모든 칸에서 사용자 ID 를 가린 새 행 목록과, 가린 개수를 돌려준다."""
    count = 0

    def one(text):
        nonlocal count
        masked, n = mask_ids_counted(text)
        count += n
        return masked

    return [_walk(list(row), one) for row in rows], count


def clip_text(text, limit: int = MODEL_TEXT_CHARS) -> str:
    text = "" if text is None else str(text)
    return text if len(text) <= limit else text[:limit] + CLIP_MARK


def clip_deep(obj, limit: int = MODEL_TEXT_CHARS):
    return _walk(obj, lambda s: clip_text(s, limit))
