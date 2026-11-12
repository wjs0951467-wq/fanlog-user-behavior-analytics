"""에이전트가 부를 수 있는 도구 모음.

도구 하나는 dict 로 정의한다.
  spec             : 모델에게 보여주는 설명과 인자 형식 (OpenAI function calling 형식)
  run(args)        : 실제 실행 함수. 인자 값 검증도 여기서 한다 (모델이 준 값을 믿지 않는다)
  llm_cost         : 이 도구가 내부에서 쓸 수 있는 LLM 호출의 최대치 (예산 계산용)
  max_per_question : 질문 1개에서 이 도구를 부를 수 있는 횟수

run 의 반환값 (모든 도구 공통)
  status  : "ok" | "error" | "refusal" | "hold"(인원이 적어 해석 보류)
  for_llm : 모델에게 돌려줄 요약 (작게 자른다)
  for_ui  : 화면이 그릴 전체 결과 (표와 숫자는 모델을 거치지 않고 여기서 바로 그린다)
  usage   : {"llm_calls", "tokens"} 이 도구가 내부에서 쓴 LLM 사용량
"""
import json
from functools import lru_cache

from . import actions, churn, numcheck
from .llm import complete
from .safety import MODEL_TEXT_CHARS, clip_deep, clip_text
from .text2sql import MAX_SQL_CALLS, ask, llm_error_text

MAX_QUESTION_CHARS = 300
ROWS_FOR_LLM = 20         # 모델에게는 상위 20행만 준다. 전체 표는 화면이 for_ui 로 그린다
CELL_CHARS_FOR_LLM = MODEL_TEXT_CHARS  # 긴 문자열 칸은 자른다 (토큰 절약 + 데이터 안에 숨은 지시문이 통째로 들어가는 것 방지)

# 모든 도구가 공통으로 받는 인자. 설계서의 "어떤 도구를, 왜, 무슨 인자로"에서 "왜"를 기록하기 위한 것이다.
REASON_PARAM = {"type": "string", "description": "이 도구를 왜 부르는지 한국어 한 문장"}


def no_usage() -> dict:
    return {"llm_calls": 0, "tokens": 0}


def error_result(message: str, **extra) -> dict:
    """도구가 실행되지 못했을 때의 결과. 예외를 던지지 않고 모델에게 이유를 돌려줘 스스로 고치게 한다."""
    return {"status": "error", "for_llm": {"error": message, **extra}, "for_ui": {"error": message, **extra},
            "usage": no_usage()}


def _trim_rows(rows: list) -> list:
    """모델에게 보낼 행: 상위 20행, 문자열 칸은 200자까지."""
    def cell(v):
        if isinstance(v, (int, float, bool)) or v is None:
            return v
        return clip_text(v, CELL_CHARS_FOR_LLM)  # Decimal, date 등은 문자열로 바꾸고, 길면 자른다
    return [[cell(v) for v in row] for row in rows[:ROWS_FOR_LLM]]


# ---------- ask_data ----------
def run_ask_data(args: dict) -> dict:
    """자연어 질문을 검증된 ask() 파이프라인에 넘긴다.

    에이전트가 SQL 을 직접 쓰지 않고 ask() 를 도구로 재사용하는 이유:
    가드레일(SELECT 전용, 허용 테이블)과 읽기 전용 계정을 우회할 길을 만들지 않기 위해서다.
    """
    question = args.get("question")
    if not isinstance(question, str) or not question.strip():
        return error_result("question 은 비어 있지 않은 문자열이어야 합니다.")
    if len(question) > MAX_QUESTION_CHARS:
        return error_result(f"question 은 {MAX_QUESTION_CHARS}자 이하여야 합니다.")

    # 요약은 끈다: 최종 문장은 에이전트가 쓰므로 요약 호출 1회가 중복이다.
    out = ask(question.strip(), summarize_result=False)
    status = "ok" if not out["error"] else "refusal" if out["error"].startswith("CANNOT_ANSWER") else "error"
    # 모델에게 가는 모든 문자열 칸(sql, 컬럼 이름, 가정, 오류, 행 값)을 같은 길이로 자른다. 행 값만 자르면
    # 별칭이나 가정, 오류 문장에 실린 긴 지시문이 그대로 들어간다. (화면과 로그에는 for_ui 의 원본이 간다)
    for_llm = clip_deep({
        "sql": out["sql"], "columns": out["columns"], "row_count": out["row_count"],
        "rows": _trim_rows(out["rows"]),
        "rows_shown": min(out["row_count"], ROWS_FOR_LLM),
        "truncated": out.get("truncated", False),  # 상한에서 잘린 결과면 모델도 "일부만 봤다"는 것을 알아야 한다
        "row_cap_note": out.get("row_cap_note"),   # 결과가 정확히 상한 행이면 "더 있을 수 있음"
        "masked_ids": out.get("masked_ids", 0),    # 사용자 ID 모양이라 [ID] 로 가린 값의 수
        "assumptions": out["assumptions"], "error": out["error"],
        # attempts(실패한 SQL 과 에러 원문)는 모델에게 주지 않는다. 화면과 로그에서만 본다.
    })
    return {"status": status, "for_llm": for_llm, "for_ui": out, "usage": out["usage"]}


# ---------- 이탈 위험 순위 세그먼트 ----------
ALL = "전체"
PURCHASE_ARG = {"있음": churn.PURCHASE_LABELS[1], "없음": churn.PURCHASE_LABELS[0]}
SEGMENT_ARGS = {  # 인자 이름 -> 허용 값. 모델이 준 값은 반드시 이 목록과 대조한다
    "tier": churn.TIERS + [ALL],
    "purchase": list(PURCHASE_ARG) + [ALL],
    "gap_group": churn.GAP_GROUPS + [ALL],
}
SEGMENT_COLUMNS = {"tier": "tier", "purchase": "purchase", "gap_group": "comm_gap"}  # 인자 이름 -> 표의 컬럼
M0_NOTE = "단순 기준선(마지막 핵심 활동 후 일수가 긴 순서)으로 나눈 군과 실제 비율이 구분되지 않는다."
GAP_AXIS_NOTE = "소통 공백 축은 '어떤 아티스트를 팔로우하는가'에 따른 아티스트 구성 분류이며 위험 요인으로 검증되지 않았다."
NO_SENDING_NOTE = "이 도구는 초안만 만든다. 실제 발송 기능은 없다."


@lru_cache(maxsize=1)
def get_report() -> dict:
    """이탈 위험 순위 결과를 프로세스에서 처음 필요할 때 한 번만 계산해 메모리에 둔다.

    왜 캐시하는가: 계산할 때마다 13만 행을 DB 에서 읽고 모델을 다시 학습한다. 데이터와 난수 시드가
    고정이라 결과가 매번 같으므로 질문마다 다시 계산할 이유가 없다. LLM 은 쓰지 않는다(DB 읽기만).
    파일로 저장하지 않는 이유: 오래된 결과 파일이 남아 지금 데이터와 어긋나는 일을 막기 위해서다.
    """
    data = churn.load_data()
    report = churn.churn_report(data)
    report["tier_comparison"] = churn.tier_comparison(data)  # M1 군과 기준선 M0 군의 비교 (탐색적 추가)
    return report


def _pct(x: float, digits: int = 1) -> float:
    return round(float(x) * 100, digits)


def _evidence(report: dict) -> dict:
    """군의 의미를 보여주는 근거. 세그먼트 결과에는 필터와 상관없이 항상 이것이 따라간다.

    비율은 코드가 퍼센트로 바꾸고 반올림해서 준다. 모델이 직접 계산하거나 반올림하지 않게 하기 위해서다.
    """
    tiers = [{"tier": r.tier, "rows_in_test_period": int(r.n), "positives": int(r.positives),
              "actual_rate_pct": _pct(r.label_rate), "rate_ci95_pct": [_pct(r.rate_ci_low), _pct(r.rate_ci_high)],
              "lift_vs_all": round(float(r.lift), 2),
              "lift_ci95": [round(float(r.lift_ci_low), 2), round(float(r.lift_ci_high), 2)],
              # "상위군"이라도 대부분은 14일 안에 다시 활동했다는 점을 숫자로 보여준다
              "active_again_within_14d_pct": _pct(1 - r.label_rate)}
             for r in report["tier_evidence"].itertuples()]
    comparison = report["tier_comparison"]
    m1, m0 = comparison.iloc[:len(churn.TIERS)], comparison.iloc[len(churn.TIERS):]
    versus = [{"tier": a.tier, "model_rate_pct": _pct(a.label_rate), "baseline_rate_pct": _pct(b.label_rate),
               "verdict": a.m1_vs_m0} for a, b in zip(m1.itertuples(), m0.itertuples())]
    all_same = all(v["verdict"] == churn.NOT_SEPARABLE for v in versus)
    return {"what": "평가 구간(02-26, 03-05, 03-12)에서 잰 군별 실제 비율. 실제 비율 = 이후 14일 동안 핵심 활동이 없었던 비율",
            "tiers": tiers,
            "model_vs_simple_baseline": {"by_tier": versus, "summary": M0_NOTE if all_same else
                                         "일부 군에서 모델과 단순 기준선의 실제 비율이 구분된다."},
            "notes": report["notes"]}


def _count(table, sel: dict) -> tuple:
    """조건(군, 구매 경험, 소통 공백)에 맞는 칸들과 그 인원 합. "전체"인 축은 거르지 않는다."""
    rows = table
    for name, value in sel.items():
        if value != ALL:
            wanted = PURCHASE_ARG[value] if name == "purchase" else value
            rows = rows[rows[SEGMENT_COLUMNS[name]] == wanted]
    return rows, int(rows["n"].sum())


def _select(args: dict, report: dict) -> dict:
    """인자(군, 구매 경험, 소통 공백)에 맞는 세그먼트 칸을 고른다. 잘못된 인자는 error_result 로 돌려준다."""
    unknown = sorted(set(args) - set(SEGMENT_ARGS))
    if unknown:
        return error_result(f"모르는 인자입니다: {unknown}", allowed=sorted(SEGMENT_ARGS))
    selection = {}
    for name, allowed in SEGMENT_ARGS.items():
        value = args.get(name, ALL)
        if value not in allowed:
            return error_result(f"{name} 값이 올바르지 않습니다: {value!r}", allowed=allowed)
        selection[name] = value
    table = report["segments"]
    if selection["gap_group"] != ALL and "comm_gap" not in table.columns:
        return error_result("소통 공백 축은 '해당 없음'입니다 (공백 4일 이상 인원이 너무 적다). gap_group 은 '전체'만 됩니다.")

    rows, n = _count(table, selection)
    out = {"selection": selection, "n": n, "share_pct": _pct(n / report["total"]),
           "population_total": report["total"], "ref_date": str(report["ref_date"])[:10],
           "cells": json.loads(rows.drop(columns="share").to_json(orient="records", force_ascii=False))}
    if n < churn.MIN_CELL:
        # 인원이 적은 칸은 우연으로도 크게 흔들린다. 축을 하나씩 합쳐 더 큰 집단을 대안으로 준다.
        out["status"] = "해석 보류"
        out["reason"] = f"인원이 {churn.MIN_CELL}명 미만이다."
        out["alternatives"] = [{"selection": {**selection, name: ALL}, "n": _count(table, {**selection, name: ALL})[1]}
                               for name, value in selection.items() if value != ALL]
    return out


def run_get_churn_segments(args: dict) -> dict:
    """이탈 위험 "순위" 기준 세그먼트의 인원을 돌려준다. user_id 는 어디에도 넣지 않는다(집계만)."""
    report = get_report()
    picked = _select(args, report)
    if "selection" not in picked:
        return picked  # 인자 오류
    picked["evidence"] = _evidence(report)
    full_table = json.loads(report["segments"].to_json(orient="records", force_ascii=False))
    return {"status": "hold" if picked.get("status") else "ok", "for_llm": picked,
            "for_ui": {**picked, "segments_table": full_table, "population_check": report["population"]},
            "usage": no_usage()}


# ---------- recommend_actions ----------
def _base_rate(report: dict, tier: str) -> float:
    """표본 수 계산에 쓸 기준 비율: 그 군의 실제 비율. 군을 고르지 않았으면 평가 구간 전체 비율."""
    evidence = report["tier_evidence"]
    if tier == ALL:
        return float(evidence["positives"].sum() / evidence["n"].sum())
    return float(evidence.loc[evidence["tier"] == tier, "label_rate"].iloc[0])


TOP_TIERS = churn.TIERS[:2]  # 상위 10%군 + 11~30%군 = 상위 30%군
MERGED_TIER_LABEL = "상위 30%군 (상위 10%군 + 11~30%군)"
AXIS_LABELS = {"purchase": "구매 경험", "gap_group": "소통 공백"}


def _pooled_rate(report: dict, tiers: list) -> float:
    """여러 군을 합친 기준 비율 = 평가 구간의 (양성 수 합 / 행 수 합). 군 하나나 전체는 _base_rate 와 같은 값이다."""
    if tiers == [ALL]:
        return _base_rate(report, ALL)
    evidence = report["tier_evidence"]
    picked = evidence[evidence["tier"].isin(tiers)]
    return float(picked["positives"].sum() / picked["n"].sum())


def _alternatives(selection: dict, report: dict, plan: dict) -> list:
    """표본 수 판정이 "검증할 수 없다"일 때 막다른 길로 끝나지 않게, 코드가 계산해 붙이는 대안 목록이다.

    LLM 은 이 목록을 만들지 않는다. 대안마다 인원과 필요 인원을 같은 계산식(sample_size_plan)으로 다시 구한다.
    """
    table, tier = report["segments"], selection["tier"]
    own_tiers = [tier]

    def plan_for(sel: dict, tiers: list) -> dict:
        n = sum(_count(table, {**sel, "tier": t})[1] for t in tiers)
        return actions.sample_size_plan(_pooled_rate(report, tiers), n)

    items = []
    for axis, label in AXIS_LABELS.items():  # 1) 조건 하나를 빼고 합치기
        if selection[axis] != ALL:
            sel = {**selection, axis: ALL}
            items.append(actions.labeled_plan("조건 빼기", f"{label} 조건을 빼고 합치기", sel, plan_for(sel, own_tiers)))
    if tier in TOP_TIERS:  # 2) 이웃한 군과 합치기 (상위 30%군)
        items.append(actions.labeled_plan("군 합치기", MERGED_TIER_LABEL, {**selection, "tier": MERGED_TIER_LABEL},
                                          plan_for(selection, TOP_TIERS)))
    if any(v != ALL for v in selection.values()):  # 3) 활동 중인 팬 전체
        everyone = {name: ALL for name in selection}
        items.append(actions.labeled_plan("전체 합치기", "활동 중인 팬 전체", everyone, plan_for(everyone, [ALL])))
    items.append(actions.repeat_rounds(plan))  # 4) 라운드를 여러 번 모으기 (이 세그먼트 그대로)
    items.append(actions.OBSERVATION_ALTERNATIVE)  # 5) 발송 없이 관찰 분석
    return items


def run_recommend_actions(args: dict) -> dict:
    """세그먼트 하나에 대한 운영 액션 초안을 만든다.

    LLM 에게 주는 입력은 코드가 계산한 통계와 정해진 목록의 값뿐이다. 질문 원문이나 DB 의 문자열을
    넣지 않으므로, 데이터에 숨은 지시문이 이 호출에 끼어들 길이 구조적으로 없다.
    """
    report = get_report()
    picked = _select(args, report)
    if "selection" not in picked:
        return picked
    if picked.get("status"):  # 20명 미만: LLM 을 부르지 않는다
        return {"status": "hold", "for_llm": picked, "for_ui": picked, "usage": no_usage()}

    selection = picked["selection"]
    evidence = _evidence(report)
    base_rate = _base_rate(report, selection["tier"])
    plan = actions.sample_size_plan(base_rate, picked["n"])
    notes = [churn.CAVEAT, evidence["model_vs_simple_baseline"]["summary"], actions.CHANNEL_NOTE, NO_SENDING_NOTE]
    if selection["gap_group"] != ALL:
        notes.insert(2, GAP_AXIS_NOTE)

    facts = {"segment": selection, "segment_size": picked["n"], "share_of_population_pct": picked["share_pct"],
             "population_total": picked["population_total"], "ref_date": picked["ref_date"],
             "tier_evidence": evidence["tiers"], "allowed_channels": actions.CHANNELS, "notes": notes}
    messages = [{"role": "user", "content": json.dumps(facts, ensure_ascii=False)}]
    usage = no_usage()
    errors = []
    for _ in range(2):  # 형식 위반이면 1회만 다시 시킨다 (이 2회는 질문당 예산 안에서 센다)
        usage["llm_calls"] += 1
        try:
            reply = complete(actions.ACTION_RULES, messages, json_mode=True)
        except Exception as e:
            return {**error_result(llm_error_text(e)), "usage": usage}
        usage["tokens"] += reply["tokens"]
        try:
            draft = json.loads(reply["text"])
        except ValueError:
            draft = None
        errors = actions.schema_errors(draft)
        if not errors:
            break
        messages += [{"role": "assistant", "content": reply["text"]},
                     {"role": "user", "content": "Your JSON did not match the required format: "
                                                 + "; ".join(errors) + ". Respond again with the corrected JSON object."}]
    if errors:
        return {**error_result("액션 초안이 정해진 JSON 형식을 지키지 못했습니다.", details=errors), "usage": usage}

    violations = actions.safety_violations(draft)
    if violations:  # 안전 규칙 위반은 그 출력을 버린다. 다시 시키지 않는다
        return {**error_result("액션 초안이 안전 규칙을 어겨 버렸습니다.", violations=violations), "usage": usage}

    result = {
        "selection": selection, "segment_size": picked["n"],
        "draft": draft,  # 여기까지가 LLM 이 쓴 글
        # 아래는 모두 코드가 붙인다. LLM 이 쓰거나 고칠 수 없다.
        "evidence": evidence["tiers"], "sample_size": plan, "notes": notes,
        # 검증할 수 없다는 판정이면 코드가 계산한 대안을 붙인다. 검증할 수 있으면 비어 있다.
        "alternatives": [] if plan["feasible"] else _alternatives(selection, report, plan),
        # 초안에 사실 자료에 없는 숫자가 있으면 표시한다 (경고 전용)
        "unverified_numbers_in_draft": numcheck.unverified_numbers(json.dumps(draft, ensure_ascii=False), [facts]),
    }
    return {"status": "ok", "for_llm": result, "for_ui": result, "usage": usage}


# ---------- 도구 목록 ----------
def _spec(name: str, description: str, properties: dict, required: list) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "additionalProperties": False,
                       "properties": {**properties, "reason": REASON_PARAM}, "required": required + ["reason"]}}}


SEGMENT_PROPERTIES = {
    "tier": {"type": "string", "enum": SEGMENT_ARGS["tier"], "description": "이탈 위험 순위 군"},
    "purchase": {"type": "string", "enum": SEGMENT_ARGS["purchase"],
                 "description": "기간 내 구매 경험 (2026-01-01 이후)"},
    "gap_group": {"type": "string", "enum": SEGMENT_ARGS["gap_group"],
                  "description": "체감 소통 공백 분류 (아티스트 구성 분류일 뿐 위험 요인이 아님)"},
}

TOOLS = {
    "ask_data": {
        "spec": _spec("ask_data",
                      "FANLOG DB 에 대한 지표/집계 질문을 SQL 로 계산해 답한다. "
                      "예: 가입자 수, 구매 건수, 전환율, 현재 휴면/이탈 위험(at_risk 상태)/활동 중인 팬 수. "
                      "질문은 한국어 한 문장으로, 한 번에 하나의 지표만 묻는다.",
                      {"question": {"type": "string", "description": "DB 에 물을 한국어 질문"}}, ["question"]),
        "run": run_ask_data,
        "llm_cost": MAX_SQL_CALLS,  # 요약을 껐으므로 SQL 생성 3회가 최대
        "max_per_question": 2,
    },
    "get_churn_segments": {
        "spec": _spec("get_churn_segments",
                      "현재 활동 중(active)인 팬을 이탈 위험 '순위'로 나눈 군(상위 10%군 / 11~30%군 / 나머지)의 인원을 "
                      "구매 경험, 소통 공백 분류와 함께 돌려준다. at_risk 상태인 팬 수를 묻는 질문에는 쓰지 않는다. "
                      "인자를 생략하면 '전체'다.", SEGMENT_PROPERTIES, []),
        "run": run_get_churn_segments,
        "llm_cost": 0,  # LLM 을 쓰지 않는다 (캐시된 계산 결과를 읽는다)
        "max_per_question": 3,
    },
    "recommend_actions": {
        "spec": _spec("recommend_actions",
                      "세그먼트 하나에 대한 운영 액션 초안(가설, 메시지 초안, 채널, 검증 방법)을 만든다. "
                      "군별 실제 비율, 필요 표본 수, 주의 문구는 코드가 붙인다. 20명 미만 세그먼트는 해석 보류로 돌려준다. "
                      "실제 발송은 하지 않는다.", SEGMENT_PROPERTIES, []),
        "run": run_recommend_actions,
        "llm_cost": 2,  # 초안 1회 + 형식 위반 시 재시도 1회
        "max_per_question": 1,
    },
}
