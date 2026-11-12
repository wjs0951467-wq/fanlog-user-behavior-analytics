# FANLOG AI 분석가

자연어로 질문하면 SQL을 만들어 안전하게 실행하고 결과를 돌려주는 분석 에이전트. (이탈 방지 액션 추천은 Day 3~4에 추가)

## 보안 구조 (방어 3겹)
1. **DB 계정**: `fanlog_ro` 는 SELECT 권한만, 읽기 전용 트랜잭션, 5초 타임아웃 (`sql/01_readonly_role.sql`)
2. **SQL 가드레일**: 실행 전 파싱해서 SELECT 1문장 / 허용 테이블 / 금지 함수 / LIMIT 강제 (`app/sql_guard.py`)
3. **연결 옵션**: 앱 연결 자체에도 read-only + statement_timeout (`app/db.py`)

## 시작하기
```bash
python -m venv .venv
.venv\Scripts\activate            # Windows PowerShell
pip install -r requirements.txt
copy .env.example .env             # 열어서 값 채우기

# 1) DBeaver(관리자 계정)에서 sql/01_readonly_role.sql 실행
# 2) DB 프로파일링 -> semantic/schema_profile.json 생성
python -m scripts.profile_db
# 3) semantic/semantic_layer.yaml 의 TODO / [검증 필요] 채우기  <- 가장 중요
# 4) 가드레일 테스트
pytest
# 5) 터미널에서 질문
python -m app.text2sql "아티스트별 현재 팔로워 수 상위 5명은?"
# 6) API 서버
uvicorn app.main:app --reload     # http://127.0.0.1:8000/docs
# 7) 화면 (Streamlit) - ai_analyst 폴더에서. 접속: http://localhost:8502
python -m streamlit run ui/app.py --server.port 8502 --server.headless true --server.address localhost
```
화면은 OpenAI 호출(공용 크레딧)을 쓰므로 외부에 열지 않는다 (`--server.address localhost` 를 빼지 않는다).
호출 한도: 세션 30회, 하루 100회(환경변수 `FANLOG_DAILY_CALL_LIMIT` 로 조정). 둘 다 남은 한도가 10회 미만이면 입력 차단.
