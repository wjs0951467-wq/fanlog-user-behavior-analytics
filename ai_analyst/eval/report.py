"""평가 리포트(마크다운). run_eval 이 저장한 결과 파일(JSON)을 읽어 글로 만든다. 호출도 DB 접속도 없다.

    python -m eval.report eval/results/run_YYYYMMDD_HHMMSS.json            (화면에 출력)
    python -m eval.report eval/results/run_....json --out eval/report.md   (파일로 저장)

읽는 법 (리포트에도 같은 문장이 들어간다)
- 개발용(dev) 정확도와 보류(heldout) 정확도를 따로 적는다. 일반화의 근거는 보류 정확도뿐이다.
  개발용 문항은 시맨틱 레이어의 정의를 그 질문에 맞춰 고쳤으므로 높게 나오는 것이 당연하다.
- 문항 수가 적어서 정확도의 신뢰구간이 넓다. 그래서 점 하나(예: 80%)가 아니라 Wilson 95% 구간을 같이 적는다.
- 호출 상한 때문에 실행하지 못한 문항과 정답 SQL 을 실행하지 못한 문항도 분모에 넣고 실패로 센다 (빼면 정확도가 부풀려진다).
"""
import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

from . import ablation, exposure, grading
from .questions import CATEGORIES

SPLIT_NAMES = (("dev", "개발용"), ("heldout", "보류"))
Z_95 = 1.959963984540054  # 표준정규분포의 97.5% 분위수


def wilson_interval(passed: int, total: int, z: float = Z_95) -> tuple | None:
    """Wilson 점수 구간 (하한, 상한). 표본이 작거나 비율이 0, 1 에 가까워도 0~1 을 벗어나지 않는다.

    정규 근사 구간(p ± z*sqrt(p(1-p)/n))은 5문항 중 5개 통과면 구간 폭이 0 이 되어 "확실히 100%"처럼 보인다.
    Wilson 구간은 그 경우에도 하한이 1 보다 작게 나온다.
    """
    if total <= 0:
        return None
    if not 0 <= passed <= total:
        raise ValueError("통과 수는 0 이상 전체 이하여야 한다")
    p = passed / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    # 통과 0개(또는 전부)일 때 이론값은 정확히 0(또는 1)인데 부동소수점 오차로 1e-17 만큼 어긋난다. 구간이 비율을 벗어나지 않게 맞춘다.
    return min(p, max(0.0, center - half)), max(p, min(1.0, center + half))


def accuracy_text(passed: int, total: int) -> str:
    if total == 0:
        return "문항 없음"
    low, high = wilson_interval(passed, total)
    return f"{passed}/{total} = {passed / total:.1%} (95% 구간 {low:.1%} ~ {high:.1%})"


def _mean(values) -> str:
    values = list(values)
    return f"{sum(values) / len(values):.2f}" if values else "-"


def _table(header: list, rows: list) -> list:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return lines + ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]


def _of(results, config=None, split=None, category=None) -> list:
    return [r for r in results
            if (config is None or r.get("config") == config) and (split is None or r["split"] == split)
            and (category is None or r["category"] == category)]


def _passed(rows) -> int:
    return sum(bool(r["passed"]) for r in rows)


def build_report(run: dict, registry: dict | None = None, current_semantic_sha: str | None = None) -> str:
    """결과 dict 를 마크다운 문자열로 만든다.

    registry: 보류 질문 노출 기록(heldout_exposure.json). current_semantic_sha: 지금 semantic_layer.yaml 의 sha256.
    둘 다 주면 "보류 질문 노출 후 시맨틱 레이어가 바뀜" 경고를 판단한다.
    """
    results = run.get("results") or []
    configs = run.get("configs") or sorted({r.get("config", "D") for r in results})
    main_config = "D" if "D" in configs else (configs[-1] if configs else "D")
    lines = ["# FANLOG 평가 리포트", "",
             f"- 실행: {run.get('run_id', '?')} / 모델: {run.get('model') or '(기록 없음)'} / 구성: {', '.join(configs)}",
             f"- LLM 호출: {run.get('calls_used', '?')}회 (하드 상한 {run.get('hard_cap', '?')}회)",
             f"- 시맨틱 레이어 sha256: {(run.get('semantic_sha256') or '(기록 없음)')[:16]}", ""]

    # ---------- 경고 ----------
    warnings = []
    registry = registry or {}
    changed = set(exposure.contaminated_ids(registry, current_semantic_sha)) if registry and current_semantic_sha else set()
    run_sha = run.get("semantic_sha256")
    if registry and run_sha:  # 이 실행 자체가 "처음 보인 때와 다른 레이어"로 돌았는가
        changed |= {r["id"] for r in results if r["split"] == "heldout" and r["id"] in registry
                    and registry[r["id"]].get("semantic_sha256") != run_sha and r["failure"] != grading.FAIL_CALL_LIMIT}
    if changed:
        warnings.append(f"**{exposure.WARNING}** (문항: {', '.join(sorted(changed))}). "
                        "이 문항들의 결과는 일반화의 근거로 쓸 수 없다.")
    if current_semantic_sha and run_sha and current_semantic_sha != run_sha:
        warnings.append("이 실행 뒤에 semantic_layer.yaml 이 바뀌었다. 아래 수치는 지금의 시맨틱 레이어가 아니라 실행 당시의 것이다.")
    if run.get("stopped_by_call_limit"):
        n = sum(r["failure"] == grading.FAIL_CALL_LIMIT for r in results)
        warnings.append(f"호출 상한에 닿아 {n}건을 실행하지 못했다. 실행하지 못한 문항은 실패로 셌다.")
    n_ref = sum(r["failure"] == grading.FAIL_REFERENCE for r in results)
    if n_ref:
        warnings.append(f"정답 SQL 을 실행하지 못한 채점이 {n_ref}건 있다. 모델이 아니라 평가셋의 문제이며, 실패로 셌다.")
    if warnings:
        lines += ["## 경고", ""] + [f"- {w}" for w in warnings] + [""]

    # ---------- 정확도 ----------
    lines += [f"## 정확도 (구성 {main_config}: {ablation.DESCRIPTIONS.get(main_config, '')})", ""]
    rows = []
    for split, name in SPLIT_NAMES:
        picked = _of(results, main_config, split)
        rows.append([name, accuracy_text(_passed(picked), len(picked))])
    lines += _table(["구분", "정확도"], rows) + [
        "",
        "- 일반화의 근거는 **보류 정확도뿐**이다. 개발용 문항은 시맨틱 레이어의 정의를 그 질문에 맞춰 고쳤으므로 높게 나오는 것이 당연하다.",
        "- 문항 수가 적은 소표본이라 **구간이 넓다**. 정확도는 한 숫자가 아니라 95% 구간(Wilson)으로 읽는다. "
        "구간이 겹치는 두 값은 차이가 있다고 말할 수 없다.", ""]

    # ---------- 카테고리별 ----------
    lines += ["## 카테고리별", ""]
    rows = []
    for category in CATEGORIES:
        dev, held = _of(results, main_config, "dev", category), _of(results, main_config, "heldout", category)
        if dev or held:
            rows.append([category, f"{_passed(dev)}/{len(dev)}" if dev else "-", f"{_passed(held)}/{len(held)}" if held else "-"])
    lines += _table(["카테고리", "개발용 (통과/문항)", "보류 (통과/문항)"], rows or [["(결과 없음)", "-", "-"]])
    lines += ["", "- 카테고리 하나의 문항 수는 더 적다. 이 표는 어디서 틀리는지 보는 용도이고, 카테고리 간 우열의 근거가 아니다.", ""]

    # ---------- 실패 분류 ----------
    lines += ["## 실패 분류", ""]
    picked = _of(results, main_config)
    counts = Counter(r["failure"] for r in picked if not r["passed"])
    rows = [[name, sum(1 for r in picked if r["failure"] == name and r["split"] == "dev"),
             sum(1 for r in picked if r["failure"] == name and r["split"] == "heldout")]
            for name in grading.FAILURE_CLASSES if counts.get(name)]
    lines += _table(["분류", "개발용", "보류"], rows or [["(실패 없음)", 0, 0]]) + [""]

    # ---------- 호출 수와 응답 시간 ----------
    lines += ["## 평균 호출 수와 응답 시간", ""]
    rows = []
    for config in configs:
        ran = [r for r in _of(results, config) if r["failure"] != grading.FAIL_CALL_LIMIT]
        rows.append([config, ablation.DESCRIPTIONS.get(config, ""), len(ran), _mean(r["llm_calls"] for r in ran),
                     _mean(r.get("elapsed_ms", 0) / 1000 for r in ran)])
    lines += _table(["구성", "설명", "실행한 문항", "평균 LLM 호출", "평균 응답 시간(초)"], rows)
    lines += ["", "- 평균은 실제로 실행한 문항만으로 낸다 (호출 상한으로 실행하지 못한 문항 제외). 응답 시간에는 DB 실행 시간이 포함된다.", ""]

    # ---------- 비교 실험 ----------
    if len(configs) > 1:
        lines += ["## 비교 실험 (구성별)", ""]
        rows = []
        for config in configs:
            dev, held = _of(results, config, "dev"), _of(results, config, "heldout")
            rows.append([config, ablation.DESCRIPTIONS.get(config, ""), accuracy_text(_passed(dev), len(dev)),
                         accuracy_text(_passed(held), len(held))])
        lines += _table(["구성", "설명", "개발용 정확도", "보류 정확도"], rows)
        lines += ["", "- 구성 간 개선의 근거는 보류 정확도를 우선한다. 구간이 겹치면 '나아졌다'고 쓰지 않는다.",
                  "- 재시도와 거짓 거절 교정은 같은 반복문이라 따로 떼어 보지 못했다 (구성 D 가 둘을 함께 켠다).", ""]

    lines += ["## 이 리포트에 없는 것", "",
              "- 행 값은 저장하지 않았다. 문항별 결과에는 행 수와 요약값(해시)만 있다.",
              "- 요약(summary)과 가정(assumptions)의 품질은 채점하지 않았다. SQL 실행 결과만 정답과 비교했다.", ""]
    return "\n".join(lines)


def main(argv=None, out=None) -> int:
    out = sys.stdout if out is None else out
    p = argparse.ArgumentParser(prog="python -m eval.report", description="평가 결과 파일로 마크다운 리포트를 만든다 (호출 없음)")
    p.add_argument("result_file", help="run_eval 이 저장한 결과 JSON")
    p.add_argument("--out", default=None, help="저장할 마크다운 파일 (없으면 화면에 출력)")
    args = p.parse_args(argv)
    path = Path(args.result_file)
    run = json.loads(path.read_text(encoding="utf-8"))
    registry = exposure.load_registry(path.parent / exposure.REGISTRY_NAME)
    text = build_report(run, registry, exposure.file_sha256(exposure.SEMANTIC_PATH))
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"리포트를 저장했다: {args.out}", file=out)
    else:
        print(text, file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
