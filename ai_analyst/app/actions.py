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
# 팬에게 보내는 초안에만 금지하는 말: 받는 사람에게 "당신은 이탈 위험군"이라고 알리는 꼴이 된다.
MESSAGE_BANNED_WORDS = ["이탈", "위험"]
# 개인 식별 정보로 보이는 모양. 입력에 user_id 가 아예 없지만(구조적 방어), 출력도 한 번 더 본다.
PII_PATTERNS = {
    "이메일": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    "전화번호": re.compile(r"\b0\d{1,2}[-\s.]?\d{3,4}[-\s.]?\d{4}\b"),
    "사용자 ID": re.compile(r"\b(?:user|fan)[_-]?\d{2,}\b", re.IGNORECASE),
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
- message_draft is read by fans. It must NOT contain the words 이탈 or 위험, and must not tell fans they were
  selected by a score. No names, IDs, emails, or phone numbers. Do not use placeholders for personal data.
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
