# FANLOG 사용자 행동 분석 대시보드

가상의 통합 아이돌 팬덤 플랫폼 `FANLOG`의 아티스트 소통·팬 행동·커머스 데이터를 생성하고 분석하는 1인 포트폴리오 프로젝트입니다. 모든 데이터는 가상이며 실제 서비스나 회사의 데이터를 사용하지 않습니다.

자세한 배경과 설계 결정은 `docs/PRD.md`, `docs/event_tracking_plan.md`, `docs/data_dictionary.md`, `docs/decisions_log.md`를 참고하세요.

## 로컬 개발 환경 설정

로컬에서 PostgreSQL을 Docker Compose로 띄워 분석용 데이터베이스로 사용합니다.

1. `.env.example`을 복사해서 `.env`를 만들고, `POSTGRES_PASSWORD`를 직접 원하는 값으로 바꿉니다.
2. `docker compose up -d` 실행 (백그라운드로 PostgreSQL 실행)
3. DBeaver에서 새 연결 생성: Host=`localhost`, Port=`.env`의 `POSTGRES_PORT`, Database/User/Password는 `.env` 값과 동일하게 입력합니다.
4. 종료할 때는 `docker compose down` (데이터는 volume에 남아있어 다시 up하면 유지됩니다). 완전히 초기화하려면 `docker compose down -v`를 사용합니다.

### 문제 해결
- **DBeaver 접속 시 비밀번호 인증 실패**: 로컬에 이미 PostgreSQL이 설치되어 5432 포트를 쓰고 있다면(`netstat -ano | findstr :5432`로 확인 가능), Docker 컨테이너와 포트가 충돌해 엉뚱한 서버로 연결될 수 있다. `.env`의 `POSTGRES_PORT`를 5433 등 비어있는 포트로 바꾸고 `docker compose down -v && docker compose up -d`로 재시작한 뒤, DBeaver 연결 설정의 Port도 동일하게 맞춘다.
