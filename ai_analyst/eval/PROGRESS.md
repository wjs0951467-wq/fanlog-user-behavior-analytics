# Day 5 평가 체계 초안: 진행 기록

(작업이 끝나면 이 파일 맨 위에 최종 요약을 붙인다. 아래는 진행 중 기록이다.)

## 시작 점검 (2026-11-12)
- 브랜치: `feature/ai-analyst-eval` (확인함: `git branch --show-current`).
- 미커밋 변경: 없음 (확인함: `git status --short` 출력이 비어 있었다).
- `.env`: 열지 않았고 고치지 않았다.

## 계획
1. 1단계 평가 하네스: `eval/questions.py`(스키마와 로더), `eval/grading.py`(채점), `eval/run_eval.py`(실행기, 기본 dry-run),
   `eval/exposure.py`(오염 방지), `eval/report.py`(리포트). 각 모듈에 `tests/test_eval_*.py`.
2. 2단계 비교 실험: `eval/ablation.py` 가 `app.text2sql` 의 `build_system_prompt` 와 `MAX_SQL_CALLS` 를 일시적으로 바꾸고 반드시 원복한다.
3. 3단계 후보 질문 초안 40문항: `eval/candidates.yaml`, `eval/verify/reference_queries.sql`, `eval/verify/VERIFY_CHECKLIST.md`.
4. 4단계 문서: `eval/README.md`.
