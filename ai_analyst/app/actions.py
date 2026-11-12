"""recommend_actions 도구가 쓰는 순수 함수들: 표본 수 계산, 출력 형식 검사, 안전 규칙 검사.

역할 나누기
- 숫자와 근거(군별 실제 비율, 표본 수, 주의 문구)는 코드가 만든다. LLM 은 숫자를 만들지 않는다.
- LLM 은 글만 쓴다: 세그먼트 설명, 가설, 메시지 초안, 채널 선택, 검증 방법, 주의사항.
- LLM 이 쓴 글은 코드가 형식과 금지 규칙을 검사한 뒤에만 내보낸다.
실제로 메시지를 보내는 기능은 없다.
"""
import math
import re
from statistics import NormalDist

# 채널 목록은 데이터 근거가 없는 가정이다 (FANLOG 데이터에는 CRM 발송 채널 정보가 없다).
CHANNELS = ["앱 푸시", "앱 내 알림", "이메일"]
CHANNEL_NOTE = "채널 목록(앱 푸시 / 앱 내 알림 / 이메일)은 가정이다. 데이터에 발송 채널 정보가 없다."

ALPHA = 0.05              # 유의수준 5% (양측)
POWER = 0.80              # 검정력 80%
REDUCTIONS = (0.30, 0.50)  # 효과 크기 가정: 기준 비율이 30% / 50% 줄어든다고 볼 때

MAX_TEXT = 400  # 한 항목의 글자 수 상한

# 효과를 약속하는 말. 전체 글에서 금지한다.
BANNED_WORDS = ["보장", "무조건", "반드시", "확실히", "틀림없이"]
# 팬에게 보내는 초안(message_draft)에만 금지하는 말: 내부 분류(이탈 위험군, 휴면)를 팬에게 드러내지 않기 위해서다.
# 가설과 주의사항은 운영자가 읽는 글이라 이 낱말을 써도 된다.
MESSAGE_BANNED_WORDS = ["이탈", "위험", "휴면"]
# 개인 식별 정보로 보이는 모양. 입력에 user_id 가 아예 없지만(구조적 방어), 출력도 한 번 더 본다.
#
# 경계를 \b 로 쓰지 않는 이유: 파이썬의 \b 는 한글도 "단어 문자"로 본다. 그래서 "user_123님",
# "010-1234-5678로" 처럼 조사가 바로 붙으면 경계가 없다고 판단해 놓친다. 영문·숫자·밑줄만 경계로 삼으면
# 한글이 붙어 있어도 잡히고, "abc123user_9" 같은 긴 영문 덩어리의 일부는 따로 건드리지 않는다.
_BEFORE = r"(?<![A-Za-z0-9_])"
_AFTER = r"(?![A-Za-z0-9_])"
PII_PATTERNS = {
    # 이메일은 ASCII 문자만으로 읽는다 (\w 는 한글을 포함해서 "abc@example.com으로" 의 "으로"까지 삼킨다)
    "이메일": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"),
    "전화번호": re.compile(_BEFORE + r"0\d{1,2}[-\s.]?\d{3,4}[-\s.]?\d{4}" + _AFTER),
    "사용자 ID": re.compile(_BEFORE + r"(?:user|fan)[_-]?\d{2,}" + _AFTER, re.IGNORECASE),
}

ACTION_RULES = """You draft a CRM action idea for a FANLOG operations manager. FANLOG is a K-entertainment fan platform.
The user message is a JSON object of facts computed by code (segment, sizes, observed rates). Use only those facts.

Respond with a single JSON object and nothing else, with exactly these keys (all text in Korean):
{
  "segment_description": "<who this segment is, 1-2 sentences, based only on the facts>",
  "hypothesis": "<one testable hypothesis, written as a hypothesis ('~일 수 있다'), not as a fact>",
  "message_draft": "<a short message to the fans, friendly, 1-3 sentences>",
  "channel": "<one of: 앱 푸시 | 앱 내 알림 | 이메일>",
  "validation": {"metric": "<what to measure>", "comparison_group": "<who to compare against>", "period": "<how long>"},
  "cautions": ["<1 to 3 short cautions for the operator>"]
}

Rules:
- Do not write any number that is not in the facts. Do not estimate effect sizes or sample sizes; code adds those.
- Never promise an effect. Do not use: 보장, 무조건, 반드시, 확실히, 틀림없이.
- Never state a cause ("~때문에 이탈한다"). The data is synthetic and shows correlation only.
- message_draft is read by fans. It must NOT contain the words 이탈, 위험, or 휴면, and must not tell fans they were
  selected by a score. No names, IDs, emails, or phone numbers. Do not use placeholders for personal data.
- message_draft must not mention the fan's own activity or absence (for example "요즘 안 오셨네요", "오랜만이에요").
  Write something that would read naturally to any fan of the platform. (Code cannot check this rule; only this prompt enforces it.)
- If the segment uses the communication-gap axis, remember it only reflects which artists the fan follows.
"""


# ---------- 표본 수 ----------
def needed_per_group(base_rate: float, reduction: float, alpha: float = ALPHA, power: float = POWER) -> int:
    """두 그룹의 비율 차이를 검출하는 데 필요한 그룹당 인원 (두 비율 비교의 표준 근사식).

    n = (z_alpha/2 + z_beta)^2 x (p1(1-p1) + p2(1-p2)) / (p1 - p2)^2
    p1 = 기준 비율, p2 = 효과가 있다고 가정했을 때의 비율(= p1 x (1 - 감소율))
    """
    z = NormalDist().inv_cdf(1 - alpha / 2) + NormalDist().inv_cdf(power)
    p1, p2 = base_rate, base_rate * (1 - reduction)
    return math.ceil(z * z * (p1 * (1 - p1) + p2 * (1 - p2)) / (p1 - p2) ** 2)


def sample_size_plan(base_rate: float, segment_n: int) -> dict:
    """이 세그먼트를 반으로 나눠 A/B 테스트를 한 번 했을 때 효과를 검증할 수 있는지 숫자로 판정한다."""
    per_group = segment_n // 2
    scenarios = []
    for reduction in REDUCTIONS:
        needed = needed_per_group(base_rate, reduction)
        scenarios.append({"assumed_reduction_pct": round(reduction * 100),
                          "target_rate_pct": round(base_rate * (1 - reduction) * 100, 1),
                          "needed_per_group": needed, "feasible": per_group >= needed})
    feasible = any(s["feasible"] for s in scenarios)
    needs = ", ".join(f"{s['assumed_reduction_pct']}% 감소 검출에 그룹당 {s['needed_per_group']:,}명" for s in scenarios)
    verdict = (f"이 세그먼트({segment_n:,}명)를 두 그룹으로 나누면 그룹당 약 {per_group:,}명이다. "
               f"필요 인원은 {needs}이다. "
               + ("14일 한 번의 A/B 테스트로 검증할 수 있는 가정이 있다." if feasible
                  else "14일 한 번의 A/B 테스트로는 검증할 수 없다."))
    return {"alpha_two_sided": ALPHA, "power": POWER, "base_rate_pct": round(base_rate * 100, 1),
            "segment_n": segment_n, "per_group_if_split_in_half": per_group,
            "scenarios": scenarios, "feasible": feasible, "verdict": verdict,
            "note": "효과 크기(30%, 50% 감소)는 계산을 위한 가정이며 예상 효과가 아니다."}


# ---------- "검증할 수 없다"일 때의 대안 (모두 코드가 만든다. LLM 은 만들지 않는다) ----------
ROUND_DAYS = 14  # 한 번의 A/B 테스트 길이: 효과를 보는 창(이후 14일)과 같다
RATE_BASIS = "기준 비율은 평가 구간(02-26, 03-05, 03-12)의 실제 비율(양성 수 / 행 수)로 구했다."
OBSERVATION_ALTERNATIVE = {
    "kind": "관찰 분석", "label": "발송 없이 기술 통계로 보기",
    "description": "메시지를 보내지 않고, 군별 / 구매 경험별 / 소통 공백별 실제 비율(이후 14일 비활동 비율)을 관찰해 가설을 다듬는다. "
                   "필요 인원이 없고 효과를 검증하는 것은 아니다. 군별 실제 비율 표는 get_churn_segments 결과에 항상 있다.",
}


def labeled_plan(kind: str, label: str, selection: dict, plan: dict) -> dict:
    """대안 하나: 종류, 이름, 대상 조건에 표본 수 계산 결과(sample_size_plan)를 그대로 붙인다."""
    return {"kind": kind, "label": label, "selection": selection, "rate_basis": RATE_BASIS, **plan}


def repeat_rounds(plan: dict) -> dict:
    """한 번에 모자라면 같은 조건의 A/B 테스트를 여러 번(라운드) 모아 합치는 경우의 횟수를 센다.

    가정: 라운드마다 서로 다른 사람이 같은 비율로 대상이 된다. 같은 사람이 계속 대상이면 성립하지 않는다.
    """
    per_round = max(plan["per_group_if_split_in_half"], 1)
    rounds = [{"assumed_reduction_pct": s["assumed_reduction_pct"], "needed_per_group": s["needed_per_group"],
               "per_group_per_round": per_round, "rounds_needed": math.ceil(s["needed_per_group"] / per_round),
               "days": math.ceil(s["needed_per_group"] / per_round) * ROUND_DAYS}
              for s in plan["scenarios"]]
    return {"kind": "반복 모집", "label": f"{ROUND_DAYS}일 단위 라운드를 여러 번 모아 합치기", "rounds": rounds,
            "assumption": "라운드마다 서로 다른 사람이 같은 기준 비율로 대상이 된다고 가정한 계산이다. "
                          "같은 사람이 반복해서 대상이 되거나 기간이 길어지면 기준 비율이 달라질 수 있다."}


# ---------- LLM 출력 검사 ----------
def _texts(rec: dict) -> dict:
    """검사할 글을 {항목 이름: 글}로 편다."""
    validation = rec.get("validation") if isinstance(rec.get("validation"), dict) else {}
    cautions = rec.get("cautions") if isinstance(rec.get("cautions"), list) else []
    out = {key: rec.get(key) for key in ("segment_description", "hypothesis", "message_draft", "channel")}
    out.update({f"validation.{k}": validation.get(k) for k in ("metric", "comparison_group", "period")})
    out.update({f"cautions[{i}]": c for i, c in enumerate(cautions)})
    return out


def schema_errors(rec) -> list[str]:
    """형식 위반 목록. 비어 있으면 통과. (형식 위반은 모델에게 돌려줘 1회 재시도한다)"""
    if not isinstance(rec, dict):
        return ["JSON 객체가 아니다"]
    errors = []
    expected = {"segment_description", "hypothesis", "message_draft", "channel", "validation", "cautions"}
    if set(rec) != expected:
        errors.append(f"키가 정확히 {sorted(expected)} 여야 한다")
    if not isinstance(rec.get("validation"), dict) or set(rec["validation"]) != {"metric", "comparison_group", "period"}:
        errors.append("validation 은 metric, comparison_group, period 를 가진 객체여야 한다")
    cautions = rec.get("cautions")
    if not isinstance(cautions, list) or not 1 <= len(cautions) <= 3:
        errors.append("cautions 는 1~3개의 문자열 목록이어야 한다")
    for name, text in _texts(rec).items():
        if not isinstance(text, str) or not text.strip():
            errors.append(f"{name} 은 비어 있지 않은 문자열이어야 한다")
        elif len(text) > MAX_TEXT:
            errors.append(f"{name} 은 {MAX_TEXT}자 이하여야 한다")
    if isinstance(rec.get("channel"), str) and rec["channel"] not in CHANNELS:
        errors.append(f"channel 은 {CHANNELS} 중 하나여야 한다")
    return errors


def safety_violations(rec: dict) -> list[str]:
    """안전 규칙 위반 목록. 하나라도 있으면 그 출력은 버린다 (재시도하지 않는다).

    위반한 글 자체는 사유에 싣지 않는다. 개인 정보로 보이는 문자열을 다시 퍼뜨리지 않기 위해서다.
    한계: 낱말과 모양만 본다. 같은 뜻을 다른 말로 쓰면 통과하고, 사람 이름은 잡지 못한다.
    """
    violations = []
    for name, text in _texts(rec).items():
        if not isinstance(text, str):
            continue
        for label, pattern in PII_PATTERNS.items():
            if pattern.search(text):
                violations.append(f"{name}: 개인 식별 정보로 보이는 문자열({label})")
        for word in BANNED_WORDS:
            if word in text:
                violations.append(f"{name}: 효과를 약속하는 표현 '{word}'")
    for word in MESSAGE_BANNED_WORDS:
        if word in str(rec.get("message_draft", "")):
            violations.append(f"message_draft: 팬에게 보내는 글에 쓸 수 없는 낱말 '{word}'")
    return violations
