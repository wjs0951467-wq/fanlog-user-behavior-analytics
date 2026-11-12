"""숫자 점검 (경고 전용).

에이전트의 최종 답에 나온 숫자가 도구 결과나 질문에 실제로 있는 숫자인지 대조한다.
없는 숫자는 unverified_numbers 로 돌려줘 화면에 경고로 보여준다. 답을 고치거나 재시도하지는 않는다.

왜 경고만 하는가: 이 점검은 "그 숫자가 어딘가에 있었는가"만 본다. 아래는 잡지 못한다.
  1) 결과에 있는 숫자를 엉뚱한 대상에 붙인 경우 (at_risk 75명을 "휴면 75명"이라고 쓰기)
  2) "절반", "두 배"처럼 글자로 쓴 숫자
  3) 정의에 쓰이는 숫자(14일, 30일, 10% 등)는 항상 통과시키므로, 그 숫자를 잘못 써도 모른다
반대로 정상인데 걸리는 경우도 있다 (거짓 경보).
  4) 모델이 직접 더하거나 뺀 합계/차이
  5) "약 1,600명" 같은 어림값
그래서 차단 수단이 아니라 "사람이 한 번 더 보라"는 표시로만 쓴다.
(주된 방어는 구조다: 표와 숫자는 코드가 도구 결과에서 직접 화면에 그린다.)
"""
import re

NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")

# 비즈니스 정의와 군 이름에 들어 있는 숫자. 도구 결과에 없어도 답에 자연스럽게 나온다.
# (이탈 위험 14~29일, 휴면 30일, 상위 10%군, 11~30%군)
DEFINITION_NUMBERS = {14.0, 29.0, 30.0, 10.0, 11.0}


def _to_float(token: str) -> float:
    return float(token.replace(",", "").rstrip("."))


def _decimals(token: str) -> int:
    return len(token.split(".")[1]) if "." in token else 0


def extract_numbers(text: str) -> list[str]:
    """글에서 숫자 토큰을 뽑는다. "1,643명" -> "1,643", "16.42%" -> "16.42" """
    return [t.rstrip(",") for t in NUMBER.findall(text or "")]


def known_numbers(source) -> set[float]:
    """도구 결과(dict/list/문자열/숫자가 섞인 구조)에 들어 있는 모든 숫자를 모은다."""
    found = set()
    if isinstance(source, bool) or source is None:
        return found
    if isinstance(source, (int, float)):
        found.add(float(source))
    elif isinstance(source, str):
        found.update(_to_float(t) for t in extract_numbers(source))
    elif isinstance(source, dict):
        for key, value in source.items():
            found |= known_numbers(key) | known_numbers(value)
    elif isinstance(source, (list, tuple)):
        for item in source:
            found |= known_numbers(item)
    return found


def unverified_numbers(answer: str, sources: list) -> list[str]:
    """answer 의 숫자 중 sources(질문, 도구 결과들) 어디에도 근거가 없는 것을 돌려준다.

    허용하는 변환: 쉼표 제거, 비율과 퍼센트 사이의 변환(0.1642 <-> 16.42),
                  답에 쓴 자릿수로 반올림한 값(7.46 -> "7.5").
    """
    known = set(DEFINITION_NUMBERS)
    for source in sources:
        known |= known_numbers(source)
    candidates = known | {k * 100 for k in known} | {k / 100 for k in known}

    missing = []
    for token in extract_numbers(answer):
        value, digits = _to_float(token), _decimals(token)
        if not any(abs(round(c, digits) - value) < 1e-9 for c in candidates) and token not in missing:
            missing.append(token)
    return missing
