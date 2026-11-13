"""평가 실행기.

기본은 dry-run 이다: OpenAI 도 DB 도 부르지 않고, 질문 목록과 예상 최대 호출 수만 출력한다.
    python -m eval.run_eval                         (dry-run)
    python -m eval.run_eval --split dev --configs A,B,C,D   (dry-run)

실제 실행은 아래가 모두 맞을 때만 한다 (공용 크레딧 보호. 하나라도 빠지면 호출 0회로 끝난다).
  1) 환경변수 FANLOG_EVAL_ALLOW=1
  2) --confirm-calls N : N 이 dry-run 이 알려준 "예상 최대 호출 수"와 정확히 같아야 한다 (dry-run 을 먼저 봤다는 확인)
  3) 고른 문항이 전부 verified: true (사람이 정답 SQL 을 확인한 문항만)
  4) 환경변수 FANLOG_MODEL 이 설정돼 있음
실행 중에는 --max-calls(주지 않으면 N)를 하드 상한으로 쓴다. 다음 질문의 최대 사용량을 더하면 상한을 넘는 순간 즉시 멈추고,
실행하지 못한 문항은 "호출 상한 초과"로 기록한다. 그래서 실제 호출 수는 상한을 넘지 않는다.

평가 호출도 화면의 "오늘 전체 호출"에 들어간다: 질문마다 app.agent.write_ask_log(out, "eval") 로 기존 로그에 한 줄을 남긴다.
정답 SQL 은 가드레일을 거쳐 읽기 전용 계정으로 실행한다 (LLM 호출이 아니다).
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from . import ablation, exposure, grading
from .questions import UnverifiedQuestionError, load_questions, require_verified, select

EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_QUESTIONS = EVAL_DIR / "questions.yaml"
DEFAULT_OUT = EVAL_DIR / "results"
ALLOW_ENV = "FANLOG_EVAL_ALLOW"
LOG_SOURCE = "eval"

EXIT_OK, EXIT_REFUSED = 0, 2


class CallLimitReached(Exception):
    """하드 상한 때문에 더 실행하지 않는다."""


# ---------- 계획 (호출 없음) ----------
def worst_case_calls(questions, configs) -> int:
    """예상 최대 LLM 호출 수: 구성마다 (문항 수 x 그 구성의 질문당 최대 호출 수). 요약은 끄므로 SQL 생성 호출만 센다."""
    return sum(len(questions) * ablation.calls_per_question(c) for c in configs)


def parse_configs(text: str) -> list:
    configs = [c.strip().upper() for c in text.split(",") if c.strip()]
    if not configs:
        raise ValueError("구성을 하나 이상 지정해야 한다")
    for c in configs:
        ablation.calls_per_question(c)  # 모르는 구성이면 여기서 ValueError
    if len(set(configs)) != len(configs):
        raise ValueError("같은 구성을 두 번 지정했다")
    return configs


def plan_text(questions, configs) -> str:
    lines = ["[dry-run] OpenAI 호출 0회, DB 접속 0회. 아래는 계획이다.", "",
             f"문항 {len(questions)}개 (개발용 {sum(q.split == 'dev' for q in questions)}, "
             f"보류 {sum(q.split == 'heldout' for q in questions)}, 미검증 {sum(not q.verified for q in questions)})"]
    for q in questions:
        lines.append(f"  {q.id:<6} {q.split:<8} {q.category:<6} {q.expected_kind:<8} "
                     f"{'검증됨' if q.verified else '미검증'}  {q.question}")
    lines.append("")
    for c in configs:
        per = ablation.calls_per_question(c)
        lines.append(f"구성 {c} ({ablation.DESCRIPTIONS[c]}): 질문당 최대 {per}회 x {len(questions)}문항 = 최대 {per * len(questions)}회")
    total = worst_case_calls(questions, configs)
    lines += [f"예상 최대 호출 수: {total}회 (실제는 이보다 적을 수 있다. 첫 시도에 성공하면 질문당 1회다)", "",
              f"실제로 실행하려면: 환경변수 {ALLOW_ENV}=1 을 설정하고 --confirm-calls {total} 을 붙인다.",
              "평가 호출은 logs/ 의 오늘 합계에 들어가므로 화면의 일일 한도(FANLOG_DAILY_CALL_LIMIT)에 영향을 준다."]
    return "\n".join(lines)


# ---------- 실행 ----------
def default_ask(question: str) -> dict:
    from app.text2sql import ask
    return ask(question, summarize_result=False)  # 채점에는 숫자만 필요하다: 요약 호출을 아낀다


def default_reference(sql: str):
    """정답 SQL 을 가드레일을 거쳐 읽기 전용으로 실행한다. (컬럼, 행)"""
    from app.db import run_query
    from app.sql_guard import validate_sql
    return run_query(validate_sql(sql))


def default_log(out: dict) -> None:
    from app.agent import write_ask_log  # 기존 로그 기록 함수를 그대로 쓴다: 화면의 일일 합계가 이 호출도 센다
    write_ask_log(out, LOG_SOURCE)


def run(questions, configs, hard_cap: int, ask_fn=default_ask, reference_fn=default_reference, log_fn=default_log,
        clock=time.perf_counter) -> dict:
    """문항을 구성별로 실행하고 채점한다. 돌려주는 값에는 행 값이 없다 (행 수와 요약값만).

    하드 상한: 다음 질문을 실행하기 전에 "지금까지 쓴 호출 + 그 질문의 최대 호출"이 상한을 넘으면 멈춘다.
    그래서 어떤 경우에도 실제 호출 수가 상한을 넘지 않는다. 멈춘 뒤의 문항은 모두 "호출 상한 초과"로 기록한다.
    """
    used, stopped, results, asked_heldout, references = 0, False, [], [], {}
    for config in configs:
        per_question = ablation.calls_per_question(config)
        with ablation.applied(config):  # 나갈 때(예외가 나도) 앱을 원래대로 되돌린다
            for q in questions:
                if stopped or used + per_question > hard_cap:
                    stopped = True
                    results.append({**grading.not_run(q), "config": config, "elapsed_ms": 0})
                    continue
                started = clock()
                out = ask_fn(q.question)
                elapsed_ms = int((clock() - started) * 1000)
                used += int((out.get("usage") or {}).get("llm_calls", 0))
                try:
                    log_fn(out)
                except Exception:  # 로그 실패로 평가를 버리지 않는다 (그 호출은 일일 합계에서 빠진다)
                    pass
                if q.split == "heldout" and q.id not in asked_heldout:
                    asked_heldout.append(q.id)
                reference, reference_error = None, None
                if q.reference_sql:
                    if q.id not in references:  # 정답 SQL 은 문항당 한 번만 실행한다 (구성과 무관하다)
                        try:
                            references[q.id] = (reference_fn(q.reference_sql), None)
                        except Exception as e:  # 오류 원문에는 접속 정보가 섞일 수 있어 종류 이름만 남긴다
                            references[q.id] = (None, type(e).__name__)
                    reference, reference_error = references[q.id]
                results.append({**grading.grade(q, out, reference, reference_error), "config": config,
                                "elapsed_ms": elapsed_ms})
                if used > hard_cap:  # 질문 하나가 예상보다 많이 썼다면(있어서는 안 된다) 더 진행하지 않는다
                    stopped = True
    return {"results": results, "calls_used": used, "hard_cap": hard_cap, "stopped_by_call_limit": stopped,
            "asked_heldout": asked_heldout}


def save_run(outcome: dict, questions, configs, out_dir, now: datetime, semantic_sha, profile_sha, questions_sha) -> Path:
    """실행 결과를 results/run_YYYYMMDD_HHMMSS.json 에 쓰고, 보류 질문 노출 기록을 갱신한다."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"run_{now:%Y%m%d_%H%M%S}"
    record = {"run_id": run_id, "started_at": now.isoformat(timespec="seconds"),
              "model": os.getenv("FANLOG_MODEL"),  # 모델 이름은 비밀이 아니고 결과를 재현하려면 필요하다
              "configs": list(configs), "question_count": len(questions),
              "semantic_sha256": semantic_sha, "profile_sha256": profile_sha, "questions_sha256": questions_sha,
              "calls_used": outcome["calls_used"], "hard_cap": outcome["hard_cap"],
              "stopped_by_call_limit": outcome["stopped_by_call_limit"], "results": outcome["results"]}
    path = out_dir / f"{run_id}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if outcome["asked_heldout"]:
        exposure.record_exposure(out_dir / exposure.REGISTRY_NAME, outcome["asked_heldout"], semantic_sha, run_id)
    return path


# ---------- 명령줄 ----------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m eval.run_eval", description="FANLOG 평가 실행기 (기본은 dry-run)")
    p.add_argument("--questions", default=str(DEFAULT_QUESTIONS), help="질문 파일 (기본: eval/questions.yaml)")
    p.add_argument("--split", default="all", choices=("dev", "heldout", "all"))
    p.add_argument("--ids", default="", help="쉼표로 구분한 문항 id (비우면 전부)")
    p.add_argument("--configs", default="D", help="비교 실험 구성. 쉼표로 구분 (A,B,C,D). 기본은 D(지금 앱 그대로)")
    p.add_argument("--confirm-calls", type=int, default=None, help="dry-run 이 알려준 예상 최대 호출 수. 실제 실행에 필요")
    p.add_argument("--max-calls", type=int, default=None, help="하드 상한. 기본은 --confirm-calls 값")
    p.add_argument("--out", default=str(DEFAULT_OUT), help="결과 폴더 (기본: eval/results)")
    return p


def main(argv=None, env=None, out=None, **deps) -> int:
    """돌려주는 값은 종료 코드다. deps 는 테스트가 ask_fn, reference_fn, log_fn, now 를 바꿔 끼우는 자리다."""
    env = os.environ if env is None else env
    out = sys.stdout if out is None else out

    def say(text):
        print(text, file=out)

    args = build_parser().parse_args(argv)
    try:
        configs = parse_configs(args.configs)
        ids = [i.strip() for i in args.ids.split(",") if i.strip()]
        questions = select(load_questions(args.questions), args.split, ids or None)
    except ValueError as e:  # 질문 파일 오류, 없는 id, 모르는 구성
        say(f"[중단] {e}")
        return EXIT_REFUSED
    total = worst_case_calls(questions, configs)

    if args.confirm_calls is None:  # dry-run: 여기서 끝난다. 어떤 호출도 하지 않는다
        say(plan_text(questions, configs))
        if env.get(ALLOW_ENV) == "1":
            say(f"({ALLOW_ENV}=1 이 설정돼 있지만 --confirm-calls 가 없어서 실행하지 않았다.)")
        return EXIT_OK

    # 여기부터 실제 실행 요청이다. 조건을 하나씩 확인하고, 하나라도 안 맞으면 호출 0회로 끝낸다.
    problems = []
    if env.get(ALLOW_ENV) != "1":
        problems.append(f"환경변수 {ALLOW_ENV}=1 이 없다")
    if args.confirm_calls != total:
        problems.append(f"--confirm-calls {args.confirm_calls} 이 예상 최대 호출 수 {total} 과 다르다 (dry-run 을 다시 확인할 것)")
    if args.max_calls is not None and args.max_calls < 1:
        problems.append("--max-calls 는 1 이상이어야 한다")
    if not questions:
        problems.append("고른 문항이 없다")
    try:
        require_verified(questions)
    except UnverifiedQuestionError as e:
        problems.append(str(e))
    if not env.get("FANLOG_MODEL"):
        problems.append("환경변수 FANLOG_MODEL 이 없다 (모델 없이 실행하면 질문마다 오류만 쌓인다)")
    if problems:
        say("[실행 거부] OpenAI 호출 0회.\n- " + "\n- ".join(problems))
        return EXIT_REFUSED

    hard_cap = min(args.confirm_calls, args.max_calls) if args.max_calls is not None else args.confirm_calls
    now = deps.pop("now", None) or datetime.now()
    say(f"[실행] 문항 {len(questions)}개, 구성 {','.join(configs)}, 하드 상한 {hard_cap}회")
    outcome = run(questions, configs, hard_cap, **deps)
    path = save_run(outcome, questions, configs, args.out, now,
                    exposure.file_sha256(exposure.SEMANTIC_PATH), exposure.file_sha256(exposure.PROFILE_PATH),
                    exposure.file_sha256(args.questions))
    passed = sum(r["passed"] for r in outcome["results"])
    say(f"[완료] 호출 {outcome['calls_used']}회 / 상한 {hard_cap}회, 통과 {passed}/{len(outcome['results'])}, 결과 파일: {path}")
    if outcome["stopped_by_call_limit"]:
        say("[주의] 호출 상한에 닿아 일부 문항을 실행하지 못했다 (실패 분류: 호출 상한 초과).")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
