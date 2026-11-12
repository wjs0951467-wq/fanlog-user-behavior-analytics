"""화면이 쓰는 순수 함수 (Streamlit 을 부르지 않는다. 그래서 pytest 로 바로 시험한다).

화면의 원칙
- 표와 숫자는 모델이 쓴 글이 아니라 도구 결과(코드가 만든 값)에서 직접 그린다.
- 모델이 쓴 글, 질문, DB 문자열 같은 "동적 문자열"은 마크다운으로 해석하지 않는다.
  (링크, 이미지, 취소선 같은 서식이 켜지면 데이터 속 문장이 화면을 바꿀 수 있다.)
"""
import json
import re
from decimal import Decimal

import pandas as pd

SESSION_CALL_LIMIT = 30  # 세션 하나가 쓸 수 있는 LLM 호출 누적 한도 (공용 크레딧 보호)

# 개인을 가리키는 컬럼은 ask_data 표에서도 그리지 않는다
HIDDEN_COLUMN_WORDS = ("user_id",)

# ASCII 특수문자 앞에 역슬래시를 붙이면 마크다운에서 글자 그대로 나온다 (CommonMark)
_MARKDOWN_SPECIALS = re.compile(r"([!-/:-@\[-`{-~])")


def escape_markdown(text) -> str:
    """st.warning / st.error / st.caption 처럼 마크다운을 해석하는 자리에 동적 문자열을 넣을 때 쓴다."""
    return _MARKDOWN_SPECIALS.sub(r"\\\1", "" if text is None else str(text))


def calls_blocked(total: int, limit: int = SESSION_CALL_LIMIT) -> bool:
    """세션 누적 호출이 한도에 닿으면 입력을 막는다."""
    return total >= limit


def usage_text(usage: dict | None) -> str:
    """질문 하나의 호출 수: 총합과 출처별(에이전트 / 도구) 내역."""
    if not usage:
        return "LLM 호출 0회"
    parts = [f"{name} {v['llm_calls']}회" for name, v in (usage.get("by_source") or {}).items() if v["llm_calls"]]
    detail = f" ({', '.join(parts)})" if parts else ""
    return f"LLM 호출 {usage.get('llm_calls', 0)}회{detail}, 토큰 {usage.get('tokens', 0):,}"


# ---------- 표 ----------
def _cell(value):
    """표 칸 값을 화면이 그릴 수 있는 기본형으로 바꾼다 (Decimal 은 숫자로, 날짜 같은 것은 글자로)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def result_table(columns, rows) -> tuple[pd.DataFrame, list[str]]:
    """ask_data 결과 표. user_id 가 들어간 컬럼은 빼고, 뺀 컬럼 이름을 함께 돌려준다."""
    names = [str(c) for c in columns]
    keep = [i for i, name in enumerate(names) if not any(w in name.lower() for w in HIDDEN_COLUMN_WORDS)]
    hidden = [names[i] for i in range(len(names)) if i not in keep]
    seen, labels = {}, []
    for i in keep:  # 같은 이름이 두 번이면 표가 깨지므로 번호를 붙인다
        seen[names[i]] = seen.get(names[i], 0) + 1
        labels.append(names[i] if seen[names[i]] == 1 else f"{names[i]}_{seen[names[i]]}")
    data = [[_cell(row[i]) for i in keep] for row in rows if len(row) == len(names)]
    return pd.DataFrame(data, columns=labels), hidden


def cells_frame(cells: list) -> pd.DataFrame:
    """세그먼트 칸 표 (집계만. user_id 없음)."""
    names = {"tier": "군", "purchase": "구매 경험", "comm_gap": "소통 공백", "n": "인원", "note": "비고"}
    df = pd.DataFrame(cells)
    keep = [c for c in names if c in df.columns]
    return df[keep].rename(columns=names)


def tiers_frame(tiers: list) -> pd.DataFrame:
    """군별 실제 비율 근거 표 (평가 구간). 상위군이어도 대부분 다시 활동했다는 점이 같이 보인다."""
    return pd.DataFrame([{
        "군": t["tier"], "평가 구간 행 수": t["rows_in_test_period"], "양성 수": t["positives"],
        "실제 비율(%)": t["actual_rate_pct"], "95% 구간(%)": f"{t['rate_ci95_pct'][0]} ~ {t['rate_ci95_pct'][1]}",
        "전체 대비 배수": t["lift_vs_all"], "14일 안에 다시 활동한 비율(%)": t["active_again_within_14d_pct"],
    } for t in tiers])


def versus_frame(by_tier: list) -> pd.DataFrame:
    """모델로 나눈 군과 단순 기준선(M0)으로 나눈 군의 실제 비율 비교."""
    return pd.DataFrame([{
        "군": v["tier"], "모델(M1) 군 실제 비율(%)": v["model_rate_pct"],
        "기준선(M0) 군 실제 비율(%)": v["baseline_rate_pct"], "판정": v["verdict"],
    } for v in by_tier])


def scenarios_frame(scenarios: list) -> pd.DataFrame:
    return pd.DataFrame([{
        "가정한 감소율(%)": s["assumed_reduction_pct"], "목표 비율(%)": s["target_rate_pct"],
        "그룹당 필요 인원": s["needed_per_group"], "이 세그먼트로 검증 가능": "가능" if s["feasible"] else "불가능",
    } for s in scenarios])


def rounds_frame(rounds: list) -> pd.DataFrame:
    return pd.DataFrame([{
        "가정한 감소율(%)": r["assumed_reduction_pct"], "그룹당 필요 인원": r["needed_per_group"],
        "라운드당 그룹 인원": r["per_group_per_round"], "필요한 라운드 수": r["rounds_needed"], "걸리는 일수": r["days"],
    } for r in rounds])


def history_frame(steps: list) -> pd.DataFrame:
    """도구 호출 기록: 어떤 도구를, 왜(reason), 무슨 인자로 불렀는가."""
    return pd.DataFrame([{
        "단계": s.get("step"), "도구": s["tool"], "이유(reason)": s.get("reason") or "",
        "인자": json.dumps(s["args"], ensure_ascii=False) if not isinstance(s["args"], str) else s["args"],
        "상태": s["status"], "LLM 호출": s["llm_calls"], "걸린 시간(ms)": s["elapsed_ms"],
    } for s in steps])


def attempts_frame(attempts: list) -> pd.DataFrame:
    """SQL 생성 시도 이력 (실패한 시도 포함). 접속 오류 원문은 ask() 가 이미 고정 문구로 바꿨다."""
    return pd.DataFrame([{"시도": i, "종류": a["error_type"], "SQL": a["sql"] or "", "오류": a["error_message"] or ""}
                         for i, a in enumerate(attempts, 1)])
