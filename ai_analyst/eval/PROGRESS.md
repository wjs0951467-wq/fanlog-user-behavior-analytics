# Day 5 평가 체계 초안: 진행 기록

## 최종 요약 (2026-11-12, 세 번째 이어하기에서 끝냄)

실제 OpenAI 호출 0회, DB 접속 0회, 네트워크 0회, 패키지 설치 없음, `.env` 열람 없음, 커밋 없음. `app/`, `ui/`, `semantic/`, 기존 테스트, DESIGN.md, CLAUDE.md 는 수정하지 않았다
(확인함: `git status --short` 에 `eval/` 과 `tests/test_eval_*.py` 만 나온다).

### (1) 단계별 완료 / 미완료
| 단계 | 상태 |
|---|---|
| 1. `candidates.yaml` 40문항 + `verify/` + `tests/test_eval_candidates.py` | 완료 |
| 2. `tests/test_eval_exposure.py` + 변이 점검 | 완료 |
| 3. `run_eval.py` + mock 테스트 (실행은 하지 않음) | 완료 |
| 4. `report.py` + 테스트 | 완료 |
| 5. `README.md` | 완료 |
| (앞선 작업) `questions.py`, `grading.py`, `ablation.py`, `exposure.py` 와 각 테스트 | 완료 |
| 실제 평가 실행, 후보 SQL 의 DB 검증, `questions.yaml` 30문항 채우기 | 하지 않음 (사람이 할 일) |

### (2) 만든 파일
- 이번 이어하기: `eval/candidates.yaml`, `eval/verify/reference_queries.sql`, `eval/verify/VERIFY_CHECKLIST.md`, `eval/run_eval.py`, `eval/report.py`,
  `eval/README.md`, `tests/test_eval_candidates.py`, `tests/test_eval_exposure.py`, `tests/test_eval_run.py`, `tests/test_eval_report.py`.
- 앞선 작업(커밋 7fed3a4 에 이미 있음): `eval/__init__.py`, `eval/questions.py`, `eval/questions.yaml`, `eval/dev_drafts.yaml`, `eval/grading.py`,
  `eval/exposure.py`, `eval/ablation.py`, `eval/PROGRESS.md`, `tests/test_eval_questions.py`, `tests/test_eval_grading.py`, `tests/test_eval_ablation.py`.
- 의도하지 않게 생긴 파일(지워야 함): `eval/results/run_20261112_093000.json`. 아래 (4)의 1번 참고.

### (3) pytest 결과
`python -m pytest -q`: **1199 passed** (확인함). 파일별 개수는 `--collect-only` 출력에서 복사했다.

| 파일 | 개수 | 파일 | 개수 |
|---|---|---|---|
| tests/test_actions.py | 93 | tests/test_llm.py | 25 |
| tests/test_agent.py | 60 | tests/test_main.py | 15 |
| tests/test_churn.py | 38 | tests/test_numcheck.py | 32 |
| tests/test_db.py | 9 | tests/test_safety.py | 37 |
| tests/test_eval_ablation.py | 41 | tests/test_sql_guard.py | 136 |
| tests/test_eval_candidates.py | 242 | tests/test_text2sql.py | 107 |
| tests/test_eval_exposure.py | 14 | tests/test_tools.py | 52 |
| tests/test_eval_grading.py | 54 | tests/test_ui_app.py | 54 |
| tests/test_eval_questions.py | 31 | tests/test_ui_integration.py | 29 |
| tests/test_eval_report.py | 31 | tests/test_ui_view.py | 55 |
| tests/test_eval_run.py | 44 | **합계** | **1199** |

변이 점검(일부러 망가뜨려 테스트가 잡는지 확인하고 원복): exposure 4건, run_eval 3건, report 2건. 9건 모두 테스트가 잡았다(확인함).
원복 확인: `eval/*.py` 에서 MUTANT 표시 검색 0건, 원복 후 전체 통과. `grading.py`, `questions.py`, `ablation.py` 는 이번에 변이 점검을 하지 않았다.

### (4) 내가(사람이) 결정해야 할 것
1. **`eval/results/run_20261112_093000.json` 을 지울 것.** run_eval 변이 점검 중(관문을 일부러 끈 상태) 테스트 하나가 진짜 결과 폴더에 쓴 가짜 산출물이다.
   실제 호출과 DB 접속은 없었다. 파일 삭제는 멈춤 조건이라 내가 지우지 않았다. 그 테스트는 임시 폴더를 쓰도록 고쳤다.
2. `eval/results/` 를 git 에 올릴지. 결과 파일에는 행 값이 없지만(행 수와 요약값만), 모델이 쓴 SQL 문장과 모델 이름이 들어간다.
   보류 질문 노출 기록(`heldout_exposure.json`)은 올려야 오염 경고가 다른 PC 에서도 동작한다. `.gitignore` 는 건드리지 않았다.
3. 후보 40문항 검증: `verify/reference_queries.sql` 을 DBeaver 로 실행하고 `VERIFY_CHECKLIST.md` 를 채운다. 그중 무엇을 보류 24문항으로 고를지.
4. 정의를 정해야 하는 것: Q21(W1 재방문율, 시맨틱 레이어 TODO), Q17(순매출, [검증 필요]). 정하기 전에는 보류 후보가 아니다.
5. 해석을 정해야 하는 것: Q25 "최근 7일"(마지막 날 포함 7일로 썼다), Q27 월 표기 형식(그 달 1일 날짜로 썼다. 모델이 글자 '2026-01' 로 내면 떨어진다),
   Q32 "구매한 적 있는 팬"의 탈퇴자 포함 여부(포함으로 썼다), Q16 처럼 질문에 "탈퇴한 사용자는 빼고"를 직접 쓴 문항을 그대로 둘지.
6. 채점 규칙의 느슨함 정도: scalar 는 "1행의 숫자 칸 중 하나가 맞으면 통과"로 했다(분자, 분모, 비율을 같이 내는 답을 받기 위해). 더 엄격하게(칸이 정확히 하나) 할지.
   rows 는 열 수가 다르면 실패다(모델이 열을 더 주면 떨어진다). 이대로 둘지.
7. 실패 분류에 3가지("LLM 오류", "정답 SQL 실행 실패", "기타 오류")를 더했다. 지시한 7가지로만 묶을지.
8. 실제 실행 조건을 지시보다 엄격하게 잡았다: `--confirm-calls N` 의 N 이 dry-run 의 예상 최대 호출 수와 같아야 하고, `FANLOG_MODEL` 이 있어야 한다. 이대로 둘지.
9. `dev_drafts.yaml` 의 dev 4문항을 `questions.yaml` 로 옮길지와 verified 값(eval_notes.md 의 정답과 SQL 결과가 같은지 확인한 뒤).
10. 평가 실행기를 일일 한도로도 막을지(지금은 로그만 남기고 `--max-calls` 로만 막는다).

### (5) 확인 못 한 것
- 후보 35개 SQL 과 dev 6개 SQL 의 실행 결과(값, 0행 여부, 실행 시간 5초 제한 안인지). DB 에 접속하지 않았다. 파싱 검사만 통과했다(확인함).
- 결과가 0 이 될 수 있는 문항: Q35(1월 1일 구매 완료 주문), Q25(최근 7일). 0 이 아닐 것으로 추정한다.
- Q30 이 함정으로 쓸모 있는지(기간 내 가입자 수가 sign_up 이벤트 550건과 다른지), Q14 에서 DISTINCT 유무로 값이 달라지는지, Q24/Q29/Q35 에서 KST 와 UTC 로 자른 값이 실제로 다른지.
- 실행기의 실제 실행 경로(진짜 `ask()`, 진짜 DB, 진짜 로그 파일)는 한 번도 돌리지 않았다. 가짜 부품 테스트뿐이다.
- 비교 실험 구성 A, B 의 프롬프트가 실제 모델에서 의도대로 동작하는지(프롬프트 문자열 모양만 테스트했다).
- 거절 5문항에서 모델이 실제로 거절하는지, 후보 질문 전체의 난이도가 적절한지(모델에 물어보지 않았다. 물어보면 보류 질문이 아니게 된다).
- 채점의 열 순서 맞추기와 허용 오차가 실제 모델 출력 형식에서 얼마나 거짓 실패를 내는지.

### (6) 후보 질문 40개의 구성
| 카테고리 | 개수 | 그중 trap 이 있는 문항 |
|---|---|---|
| 단순 집계 | 8 | 4 (Q01, Q05, Q06, Q07) |
| 조인 | 8 | 8 |
| 지표 정의 | 7 | 7 |
| 기간 해석 | 6 | 6 |
| 함정 | 6 | 6 |
| 거절 | 5 | 5 |
| **합계** | **40** | **36** (trap 이 "없음"인 문항: Q02, Q03, Q04, Q08) |

- expected_kind: scalar 23, rows 12, refusal 5. needs_definition: 2 (Q17, Q21). 보류 후보(heldout_candidate: true): 38.
- 전부 `verified: false`, `source: draft-by-claude-code-2026-11-12`, SQL 이 있는 35문항 전부 `guard_ok: true`.

---

## 결정 반영 (2026-11-13)

사람의 결정 6가지를 반영했다. 실제 호출 0회, DB 접속 0회. 작업 위치는 `eval/`, `tests/test_eval_*.py`, `.gitignore` 뿐이다.
1. `.gitignore`: `eval/results/*` 제외 + `!eval/results/heldout_exposure.json` 예외 (노출 기록 파일 이름은 `eval/exposure.py` 의 `REGISTRY_NAME`).
2. Q25: 질문과 reference_note 에 "마지막 날 포함 7일(마지막 날 - 6일 ~ 마지막 날)"을 명시했고 SQL 을 `>= MAX - 6` 으로 바꿨다.
3. Q27: 월을 `to_char(..., 'YYYY-MM')` 글자(예: 2026-01)로 통일했다 (가드레일 통과, ALLOWED_FUNCTIONS 에 to_char 가 있다).
4. Q32: 질문에 "탈퇴한 사용자는 빼고"를 적고 SQL 에 `dim_user` 조인과 `is_deleted IS NOT TRUE` 를 넣었다.
5. 채점: scalar 는 1행 1열이고 값이 맞을 때만 통과. rows 는 열 수가 다르면 실패 그대로. 지시 외 실패 분류 3가지는 유지했고 `report.py` 표에 나오는 것을 테스트로 확인했다.
6. `dev_drafts.yaml` 의 dev 4문항은 `questions.yaml` 로 옮기지 않았다 (README 에 이유 한 줄).

### scalar 문항 전수 점검 (질문 문장이 하나의 값만 묻는가)
scalar 28문항(후보 23 + 개발용 5: DEV01, DEV03, DEV04, DEV05, DEV06)을 모두 읽었다. 분자/분모/비율을 함께 낼 수 있는 모호한 문장은 4개였고 아래처럼 바꿨다.

| id | 이전 문장 | 새 문장 또는 kind 변경 이유 |
|---|---|---|
| Q21 | W1 참여 재방문율은 얼마야? | W1 참여 재방문율을 하나의 값으로만 알려줘. (정의 미확정 문항) |
| Q23 | 구매 건수 중에서 환불(부분 환불 포함)된 주문의 비율은 얼마야? | 구매 건수 중에서 환불(부분 환불 포함)된 주문의 비율을 하나의 값으로만 알려줘. |
| Q31 | 장바구니에 담은 건 중에서 구매까지 이어진 비율은 얼마야? | 장바구니에 담은 건 중에서 구매까지 이어진 비율을 하나의 값으로만 알려줘. |
| DEV01 | 구매 전환율은? (문장 고정) | 문장은 eval_notes.md 의 개발용 질문과 같아야 해서 고칠 수 없다. kind 를 scalar 에서 rows 로 바꿨다. 한 행 한 열만 맞고 열을 더 내면 실패하는 점은 같다(엄격화의 대가는 그대로). |
| Q25 | 최근 7일 동안 구매 건수는 몇 건이야? | 결정 2: "데이터의 마지막 날을 포함해서 7일로 세어줘." 추가 (모호함 제거) |
| Q32 | 한 번이라도 구매한 적 있는 팬은 몇 명이야? | 결정 4: "탈퇴한 사용자는 빼고." 추가 |

바꾸지 않은 scalar 문항(질문이 "몇 명/몇 건/몇 개/얼마" 또는 "건수는?"으로 숫자 하나를 묻는다): Q01 Q02 Q03 Q05 Q08 Q14 Q17 Q18 Q19 Q20 Q22 Q24 Q26 Q28 Q29 Q30 Q33 Q35, DEV03 DEV04 DEV05 DEV06.
다만 "몇 명이야?"에도 모델이 부가 열(예: 날짜, 라벨)을 붙여 낼 수 있어서 엄격 채점에서 떨어질 위험이 남는다(추정). 실제 모델로 보기 전에는 크기를 모른다.

### 고친 기존 테스트 (의도된 규칙 변경이라서)
- `tests/test_eval_grading.py::test_scalar_in_a_row_with_numerator_and_denominator_passes_and_says_how` -> `test_scalar_with_several_cells_in_the_row_fails_even_if_one_cell_is_right` 로 이름과 기대를 바꿨다.
  이유: 이 테스트는 "한 행의 여러 칸 중 하나가 맞으면 통과(one_of_cells)"를 지켰는데, 2026-11-13 결정으로 그 규칙이 정반대가 됐다(1행 1열만 통과).
- `tests/test_eval_grading.py::test_scalar_wrong_shapes_fail` 의 입력 4개를 더했다(여러 칸 행 3종과 빈 행). 기존 입력과 기대는 그대로이고 이유: 새 규칙의 실패 모양을 같은 표에 모았다.
- 코드를 약화하려고 고친 테스트는 없다(스스로 확인함): 위 두 변경은 모두 규칙을 엄격하게 하는 방향이고, 통과 조건을 넓힌 단언은 없다.
  `tests/test_eval_candidates.py` 의 새 테스트 하나(`test_the_other_scalar_questions_are_single_count_or_amount_questions`)는 첫 작성 때 "구매 건수는?"(DEV03)을 단일 값 문장으로 인식하지 못해
  표지 낱말에 "건수는?"을 더했다. 질문 쪽이 아니라 검사 쪽의 휴리스틱을 넓힌 것이고(DEV03 의 문장은 고정이며 건수 하나를 묻는다), 모호한 비율 문장을 통과시키는 방향은 아니다.
- 변이 점검: `compare_scalar` 에서 "열 수가 1이 아님" 검사를 끄면 10개 테스트가 실패했고 원복했다(확인함).

---

(아래는 진행 중 기록이다.)

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

## 이어하기 기록

### 재개 점검 (세 번째 이어하기)
- 확인함: 브랜치 `feature/ai-analyst-eval`, 마지막 커밋 `7fed3a4`, `git status --short` 출력 없음(미커밋 변경 없음).
- 확인함: `python -m pytest -q` 결과 868 passed (실패 없음).
- 확인함(파일 목록): `eval/` 에 `__init__.py`, `questions.py`, `questions.yaml`, `dev_drafts.yaml`, `grading.py`, `exposure.py`, `ablation.py`, `PROGRESS.md`.
  `tests/` 에 `test_eval_questions.py`, `test_eval_grading.py`, `test_eval_ablation.py`. 없는 것: `run_eval.py`, `report.py`, `candidates.yaml`, `verify/`, `README.md`, `test_eval_exposure.py`.
- 완성도: 만들어진 `.py` 다섯 개는 pytest 가 import 해서 통과하므로 문법 오류가 없다(확인함). 빈 함수와 TODO 는 없다(작성 내용 기준, 추정이 아니라 작성자가 쓴 그대로다).
  `exposure.py` 는 구현만 있고 테스트가 없다(확인함).
- `dev_drafts.yaml`: 개발용 6문항 중 `questions.yaml` 예시 2개에 넣지 않은 나머지 4문항(구매 전환율, 유입 채널별 구매 전환율, 이탈 위험 팬 수, 활동 중 팬 수)의
  정답 SQL 초안을 같은 스키마로 둔 파일이다. 지시에 없던 파일이다. 사용자 ID 는 없다(확인함). 집계 값은 있다: `notes` 에 eval_notes.md 의 정답 값
  (791 / 4,817 = 16.42%, 채널별 17.2 / 16.6 / 16.4 / 15.5, 75, 77, 2, 1,643, 1,670, 27)을 옮겨 적었다. `questions.yaml` 의 `notes` 에도 879 와 3 이 있다.
  모두 eval_notes.md 에 이미 커밋된 집계 값이며 개인 단위 값이 아니다.
- `exposure.py`: 보류(heldout) 질문을 모델에 처음 보인 때의 semantic_layer.yaml sha256 을 문항별로 기록하고, 지금 해시와 다르면 오염으로 판정하는 모듈이다
  (지시의 "오염 방지" 항목을 실행기와 리포트가 같이 쓰도록 파일로 뗐다). 지시에 없던 파일 이름이다. 실제 값은 없다(코드뿐, 확인함).
- 스키마 파악: `semantic/schema_profile.json` 과 `semantic_layer.yaml` 을 읽었다(확인함). 허용 테이블 15개, 날짜 범위 2026-01-01 ~ 2026-03-31(KST),
  값 목록(status, event_name, activity_status 등)을 후보 질문과 정답 SQL 초안의 근거로 썼다. DB 에는 접속하지 않았다.
- 지시 범위를 넘은 명령: 첫 번째 작업 때 파일 목록과 requirements.txt 를 보려고 `ls`, `cat`, `wc` 를 한 번 썼다(읽기 전용). 그 뒤로는 pytest, git 읽기, 파일 읽기/쓰기만 쓴다.

### 단계 1 완료: 후보 질문 40문항과 verify/
- 만든 파일: `eval/candidates.yaml`, `eval/verify/reference_queries.sql`, `eval/verify/VERIFY_CHECKLIST.md`, `tests/test_eval_candidates.py`.
- pytest 전체: 1110 passed (확인함). `tests/test_eval_candidates.py` 는 242개.
- 가드레일 파싱 검사: SQL 이 있는 35문항 모두 `validate_sql` 통과(확인함, 테스트가 매번 다시 확인한다). 막혀서 바꿔 쓰거나 뺀 문항은 없다.
- DB 에서 실행하지 않았다. 그래서 정답 값은 모른다(확인 못 함). 결과가 0 이 될 가능성이 있어 사람이 봐야 하는 문항: Q35(1월 1일 구매 완료 주문),
  Q25(최근 7일 구매 건수). 둘 다 0 이 아닐 것으로 추정하지만 확인하지 못했다. 거절 5문항은 결과가 없다.
- 정의 미확정(needs_definition: true, 보류 후보에서 제외): Q17(순매출, 시맨틱 레이어에 [검증 필요]), Q21(W1 재방문율, TODO).
  Q21 의 SQL 은 임의 가정으로 쓴 자리 채움이다.
- 사람이 정해야 하는 해석: Q25 "최근 7일"이 마지막 날 포함 7일인지, Q27 월 표기 형식(날짜 / 글자), Q32 "구매한 적 있는 팬"의 탈퇴자 포함 여부,
  Q30 이 함정으로 쓸모 있는지(기간 내 가입자 수가 sign_up 이벤트 550건과 다른지).

### 단계 2 완료: exposure.py 테스트와 변이 점검
- 만든 파일: `tests/test_eval_exposure.py` (14개). pytest 전체 1124 passed (확인함).
- 변이 점검 4건, 모두 테스트가 잡았고 원복했다 (확인함: 원복 후 `git diff --stat -- eval/exposure.py` 에 변경 없음).
  1) 다시 실행할 때 처음 해시를 덮어쓰기 -> `test_later_runs_keep_the_first_hash_and_only_count` 실패
  2) 실행 횟수를 늘리지 않기 -> 같은 테스트 실패
  3) 지금 해시를 모를 때(None) 오염이 아니라고 보기 -> `test_unknown_current_hash_counts_as_changed` 실패
  4) 깨진 기록 파일을 빈 기록으로 읽기 -> `test_broken_registry_is_an_error_not_an_empty_registry` 2건 실패

### 단계 3 완료: run_eval.py 와 mock 테스트
- 만든 파일: `eval/run_eval.py`, `tests/test_eval_run.py` (44개). pytest 전체 1168 passed (확인함). 실행기는 실행하지 않았다(테스트에서 가짜 부품으로만 돌렸다).
- 일일 합계 로그: 기존 함수 `app.agent.write_ask_log(out, "eval")` 를 그대로 재사용했다(확인함: 테스트에서 `view.daily_calls` 가 평가 호출을 센다).
  평가도 /ask, CLI 와 같이 "남기기만" 하고 일일 한도로 막지는 않는다.
- 실제 실행 조건(모두 맞아야 함): `FANLOG_EVAL_ALLOW=1`, `--confirm-calls N`(N 이 dry-run 의 예상 최대 호출 수와 같아야 함), 고른 문항 전부 `verified: true`,
  `FANLOG_MODEL` 설정. 지시보다 엄격하게 잡은 것: N 이 예상값과 같아야 한다는 것과 FANLOG_MODEL 확인(보수적 결정).
- 하드 상한: 다음 질문의 최대 호출 수(구성 D 는 3, A~C 는 1)를 더했을 때 상한을 넘으면 그 질문을 시작하지 않고 멈춘다. 그래서 실제 호출이 상한을 넘지 않는다.
- 변이 점검 3건, 모두 테스트가 잡았고 원복했다(확인함: 원복 후 MUTANT 표시 검색 0건, 전체 통과).
  A) 상한 검사에서 "다음 질문의 최대 호출"을 빼기 -> 상한 테스트 3건 실패 / B) 허용 환경변수 검사 끄기 -> 관문 테스트 실패 /
  C) 미검증 문항 검사 끄기 -> 관문 테스트 실패.
- **사람이 처리해야 하는 것(파일 삭제는 하지 않았다)**: 위 변이 점검 중(관문 B, C 를 일부러 끈 상태) 테스트 하나가 진짜 `eval/results/` 에
  `run_20261112_093000.json` 을 썼다. 가짜 ask 와 가짜 정답으로 만든 테스트 산출물이며 실제 OpenAI 호출, DB 접속, logs/ 기록은 없었다(확인함: 그 테스트는 가짜 부품만 쓴다).
  실제 평가 결과가 아니므로 지워야 한다. 파일 삭제는 멈춤 조건이라 내가 지우지 않았다. 재발 방지로 그 테스트가 `--out` 을 임시 폴더로 쓰게 고쳤다.

### 단계 4 완료: report.py 와 테스트
- 만든 파일: `eval/report.py`, `tests/test_eval_report.py` (31개). pytest 전체 1199 passed (확인함).
- 테스트가 찾은 코드 결함 1건을 코드에서 고쳤다: 통과 0개일 때 Wilson 하한이 부동소수점 오차로 5.5e-17 이 되어 비율(0)보다 컸다. 구간이 비율을 벗어나지 않게 맞췄다
  (테스트를 느슨하게 하지 않았다).
- 변이 점검 2건, 둘 다 테스트가 잡았고 원복했다: Wilson 식에서 z^2/(4n^2) 항 빼기(13건 실패 중 10건), 오염 경고 끄기(3건).
- 호출 상한으로 실행하지 못한 문항과 정답 SQL 을 실행하지 못한 문항은 분모에 넣고 실패로 센다(빼면 정확도가 부풀려진다. 보수적 결정).

### 단계 5 완료: README.md
- 만든 파일: `eval/README.md`. DESIGN.md 와 CLAUDE.md 는 수정하지 않았다. pytest 전체 1199 passed (확인함).

### 결정 기록 (보수적으로 정한 것)
- `questions.yaml` 에는 예시 2문항만 두고(지시), 나머지 dev 4문항은 `dev_drafts.yaml` 에 초안으로 두었다. 모두 `verified: false`.
- `questions.py` 로더는 모르는 키를 거부한다. `candidates.yaml` 은 초안용 필드(reference_note, trap, likely_wrong, guard_ok, needs_definition, heldout_candidate)가
  더 있어서 로더로 직접 읽히지 않는다. 이미 만든 `questions.py` 는 고치지 않고, 테스트에서 "후보를 질문 스키마로 옮겼을 때 로더가 받는지"를 확인한다
  (공통 필드만 골라 `split: heldout` 을 붙여 `parse_questions` 에 넣는다).
- 채점 실패 분류는 지시한 7가지에 3가지를 더했다: "LLM 오류", "정답 SQL 실행 실패", "기타 오류". 7가지에 억지로 넣으면 원인을 잘못 읽게 되어서다.
