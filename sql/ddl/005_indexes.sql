-- FANLOG 분석 쿼리용 인덱스
-- 대시보드·SQL 검산에서 자주 필터링하는 컬럼 위주로 생성한다.

CREATE INDEX idx_fact_user_event_event_date_kst ON fact_user_event (event_date_kst);
CREATE INDEX idx_fact_user_event_user_id ON fact_user_event (user_id);
CREATE INDEX idx_fact_user_event_artist_id ON fact_user_event (artist_id);

CREATE INDEX idx_fact_artist_activity_artist_id ON fact_artist_activity (artist_id);
CREATE INDEX idx_fact_artist_activity_activity_date_kst ON fact_artist_activity (activity_date_kst);
