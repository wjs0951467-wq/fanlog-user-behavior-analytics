# FANLOG AI 분석가 프로젝트 규칙

## 목표
FANLOG DB(PostgreSQL)에 자연어로 질문하면 SQL을 생성·검증·실행해 답하고,
이탈 위험 사용자 세그먼트와 CRM 액션까지 제안하는 분석 에이전트. 취업 포트폴리오용.

## 현재 상태
- 완료: 읽기 전용 DB 계정(fanlog_ro), SQL 가드레일(app/sql_guard.py, pytest 23개),
  DB 프로파일링(scripts/profile_db.py, 뷰 포함), 시맨틱 레이어 v3, Text-to-SQL 1회 호출(app/text2sql.py).
- 완료: Day 3 이탈 위험 점수와 세그먼트(app/churn.py).
- 완료: Day 4 B단계 (A: 에이전트 루프, 호출 예산, 로그 / B: 도구 3개 ask_data, get_churn_segments, recommend_actions,
  app/actions.py, 숫자 점검 app/numcheck.py, ask() 오류 문장 정리). pytest 290개 통과 (DB 와 LLM 은 mock).
  아직 없는 것: Day 4 의 화면(Streamlit). 실제 OpenAI 로 에이전트를 돌려 본 적은 없다 (mock 테스트로만 검증).
- LLM은 OpenAI API를 쓴다 (환경변수 OPENAI_API_KEY, FANLOG_MODEL). 모델명을 코드에 박지 않는다.
- 사람이 직접 검증한 정답은 eval_notes.md 에 있다. 새 기능은 이 정답을 깨뜨리면 안 된다.

## 구조
- app/sql_guard.py : SQL 가드레일 (SELECT 1문장, 허용 테이블, 금지 함수, LIMIT 강제)
- app/db.py : 읽기 전용 계정으로만 DB 접속
- app/text2sql.py : 질문 -> SQL -> 검증 -> 실행
- semantic/semantic_layer.yaml : 지표 정의 (프롬프트에 통째로 들어감)
- semantic/schema_profile.json : 실제 컬럼 값/날짜 범위 (profile_db.py 가 생성, git 제외)

## 절대 규칙
- ai_analyst/ 밖의 기존 코드(src/, dashboard/, sql/ 등)는 수정하지 않는다.
- .env 는 열거나 출력하지 않는다. API 키/비밀번호를 코드나 대화에 쓰지 않는다.
- DB는 fanlog_ro 계정으로만 접근한다. INSERT/UPDATE/DELETE/DDL 을 실행하지 않는다.
- 실제 OpenAI API 를 호출하는 명령(python -m app.text2sql 등)은 실행 전에 나에게 허락을 받는다.
  (공용 크레딧이라 호출 횟수를 관리해야 한다.) 테스트에서는 LLM 호출을 mock 처리한다.
- 현재 브랜치가 main 이면 작업을 멈추고 알려준다. (작업 브랜치: feature/ai-analyst)
- sql_guard.py 의 허용 범위를 넓히는 변경은 하기 전에 나에게 묻는다.
- 비즈니스 정의(휴면 기준, 매출 기준 등)를 추측해서 확정하지 않는다. 근거를 보여주고 나에게 확인받는다.

## 작업 방식 (나는 이 코드를 이해하고 면접에서 설명할 수 있어야 한다)
- 구현 전에 변경 계획을 5줄 이내로 보여주고, 내가 "진행"이라고 답한 뒤에 파일을 수정한다.
- 새 기능에는 pytest 를 함께 만든다. pytest 는 ai_analyst 폴더에서 실행한다.
- 코드는 단순하게, 주석은 "왜 이렇게 했는지"를 한국어로 쓴다.
- 작업이 끝나면 (1) 바뀐 파일 목록 (2) 실행 방법 (3) 내가 이해했는지 확인할 질문 3개를 준다.

## 설계서
- 구현은 DESIGN.md 를 따른다. 내가 지정한 Day 섹션만 구현하고, 다른 Day 는 건드리지 않는다.
- DESIGN.md 와 현실(코드, 데이터)이 충돌하거나 설계가 모호하면 임의로 정하지 말고 먼저 나에게 묻는다.