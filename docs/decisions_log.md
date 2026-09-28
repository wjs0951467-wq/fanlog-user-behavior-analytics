# FANLOG 프로젝트 의사결정 로그

> 이 파일은 `docs/PRD.md`와 `docs/event_tracking_plan.md`에는 담기지 않은 **"왜 이렇게 결정했는지"의 배경**을 정리한 문서다. 새 세션(특히 코딩 에이전트)이 이 프로젝트에 합류할 때는 이 파일을 먼저 읽고, 아래 원칙과 결정을 뒤집지 않은 상태로 작업을 이어간다.

---

## 0. 이 문서를 읽는 에이전트에게

- 이 프로젝트는 **엔터 업계 취업을 위한 1인 포트폴리오**다. 실제 서비스 개발이 목적이 아니라, 4주 안에 완주 가능한 분석 대시보드를 만드는 것이 목적이다.
- 작성자는 데이터 분석·개발 초보자다. 설명 없이 코드를 생성하거나 구조를 바꾸지 말고, 왜 그렇게 하는지 항상 짧게 설명한다.
- **불확실하거나 여러 선택지가 있는 사항은 추측해서 진행하지 말고 먼저 사용자에게 묻는다.** 이 원칙은 프로젝트 전체에서 반복적으로 요청된 핵심 작업 방식이다.
- 범위를 임의로 늘리거나(예: 텍스트 분석 부활, 팬 게시글 부활) 줄이지 않는다. 범위 변경은 항상 사용자 승인 후에만 PRD에 반영한다.
- 커밋은 작은 논리적 단위로 자주 한다. 큰 작업을 몰아서 한 번에 커밋하지 않는다.
- 브랜치는 **`main` 하나로만 작업한다.** 1인 프로젝트라 기능 브랜치 전략을 쓰지 않기로 확정했다 (아래 8절 참고).

---

## 1. 문서 버전 현황 (이 로그 작성 시점 기준)

| 문서 | 버전 |
| --- | --- |
| `docs/PRD.md` | v1.3 |
| `docs/event_tracking_plan.md` | v1.1 (내용상 v1.3 PRD와 정합성 맞춰 갱신됨, 문서 버전 숫자 자체는 아직 안 올림) |

두 문서 다 현재 `main` 브랜치에 커밋되어 있다.

---

## 2. 프로젝트 성격과 반복적으로 지킨 원칙

### 2.1 완주 가능성 최우선

- 최초 PRD(v1.0)는 팀 프로젝트 수준의 방대한 범위(6페이지 대시보드, 텍스트 감성분석, ML 세그먼트, 5팀 아티스트, 30만~50만 이벤트 등)로 작성되었다.
- 1인·4주 프로젝트로는 완주가 불가능하다고 판단해 v1.1에서 대대적으로 범위를 축소했다: 3페이지 대시보드, 3팀 아티스트, 8만~15만 이벤트, 텍스트 분석 전면 제외.
- **이후에도 범위를 늘리자는 제안이 나올 때마다(예: 팬 게시글, 콘텐츠 세분화) "완주 가능한가"를 기준으로 판단했다.** 이 기준은 앞으로도 유지한다.

### 2.2 가상 데이터의 정직성

- 모든 문서에서 반복적으로 강조된 것: 이 프로젝트는 가상 데이터로 "분석 구조와 탐지 가능성"을 검증하는 것이지, 실제 팬덤에 대한 사실을 주장하는 게 아니다.
- 데이터 생성 규칙에 잡음(확률)을 넣고, `communication_effect=0` 같은 비교 시나리오를 넣어서 "심어둔 패턴을 다시 발견하고 인사이트인 척하지 않도록" 방지 장치를 마련했다 (PRD 13.4).
- 실제 회사(FANS, bubble, JYP 등) 데이터는 절대 사용하지 않으며, 참고만 한다는 문구를 여러 곳에 명시했다.

### 2.3 PRD 우선 원칙

- `docs/event_tracking_plan.md`는 `docs/PRD.md`의 하위 구현 명세로 설계되었다. 두 문서가 충돌하면 PRD가 우선한다.
- 다만 이벤트 추적 계획서에서 먼저 구체화된 정의(예: 핵심 활동 12개 목록)는 확정 즉시 PRD에도 반영해서 두 문서가 항상 같은 근거를 갖도록 유지해왔다. 이 상호 반영 습관은 계속 지킨다.

---

## 3. 왜 이 프로젝트가 존재하는가 (핵심 컨셉)

- 작성자가 실제로 사용해본 FANS(팬 커뮤니티·공지·미디어·샵)와 bubble(아티스트 구독형 메시지)의 경험을 참고해서, 두 서비스를 통합한 가상의 팬덤 플랫폼 `FANLOG`를 설계했다.
- 핵심 분석 질문: **"아티스트 소통이 줄면 팬 활동도 줄어드는가?"**를 출발점으로, 소통→참여·재방문→구매로 이어지는 하나의 사용자 여정을 분석한다.
- 실제 회사를 재현하는 게 아니라 "이런 구조의 서비스가 있다면 어떤 데이터로 어떤 인사이트를 낼 수 있는가"를 보여주는 것이 목적이다.

---

## 4. 범위에서 뺀 것과 그 이유 (중요 — 임의로 되살리지 말 것)

| 뺀 항목 | 이유 | 재검토 조건 |
| --- | --- | --- |
| 팬 커뮤니티 자유 게시글 및 텍스트 감성·주제 분석 | 자유 텍스트 생성 로직 + 품질검사 + 분류까지 추가되면 4주 일정이 무너짐. "엔터 취업 포폴에 FANS+bubble 통합 느낌을 내고 싶다"는 욕심과 별개로, 완주가 우선이라고 판단해 제외를 유지하기로 사용자가 직접 결정함 (대화 중 재확인됨) | MVP 배포·보고서 완료 후 확장 범위 1순위로 진행 |
| 머신러닝 기반 팬 군집화·이탈 예측 | 설명 가능성이 낮고, 규칙 기반 세그먼트로도 분석 목적을 충분히 달성 가능 | 규칙 기반 세그먼트 완료 후 비교 실험으로만 추가 |
| 실시간 처리·자동 알림 | 배치 분석으로 충분하고, 실시간 인프라는 1인 프로젝트 범위 밖 | 대시보드 지표 안정화 후 |
| "이벤트"(할인 프로모션 등 커머스성 이벤트) 콘텐츠 유형 | 콘텐츠(`dim_content`)가 아니라 커머스(`dim_product`, `fact_order`) 영역이라 콘텐츠 유형에 넣지 않기로 결정. 팬미팅류 "이벤트 공지"는 기존 `notice` 유형으로 흡수 | 필요 시 재검토 |
| 앨범 수록곡·라이브 영상을 별도 콘텐츠 유형으로 분리 | 기존 `video`/`music_video`/`live_replay` 유형 안에서 충분히 커버 가능하다고 판단, 사용자도 "중요하지 않다"고 확인 | 해당 없음 |

---

## 5. 데이터 모델 관련 핵심 결정

### 5.1 아티스트 활동과 팬 행동의 분리

- `fact_artist_activity`(아티스트가 제공한 소통, 예: 메시지 발송 1건)와 `fact_user_event`(팬이 실제로 반응한 행동, 예: 그 메시지를 읽은 180명)를 **별도 테이블로 분리**한다.
- 이유: "아티스트가 얼마나 소통을 공급했는가"와 "팬이 실제로 얼마나 반응했는가"를 구분해야 핵심 가설(H-01, H-02: 소통 빈도와 팬 활동의 관계)을 검증할 수 있다.
- `event_source` 필드 같은 걸로 한 테이블에 통합하는 방식은 명시적으로 기각했다.

### 5.2 게시글 vs 콘텐츠(공지 등) 구분 기준

- **아티스트 게시글**: 아티스트/멤버 본인이 직접, 즉시성 있게 올리는 글·사진·짧은 영상 → `fact_artist_activity`, `activity_id`로 관리
- **운영 콘텐츠**: 운영팀이 사전 제작·편집해서 게시하는 공식 자료(공지, 사진, 영상, 뮤직비디오, 라이브 다시보기) → `dim_content`, `content_id`로 관리
- 이 구분은 실제 팬덤 플랫폼의 UX 차이(아티스트 계정 직접 포스팅 vs 운영팀이 관리하는 공식 콘텐츠 탭)를 참고해서 만든 기준이다.

### 5.3 `dim_content`의 콘텐츠 유형 (v1.2에서 확정)

5개 유형으로 확정: `notice`(공지), `photo`(공식 사진), `video`(자체 제작 영상/자컨), `music_video`(뮤직비디오), `live_replay`(라이브 다시보기).

모든 `dim_content` 행은 `artist_id`를 필수로 가진다 (FR-002 전역 아티스트 필터가 콘텐츠 페이지에서도 동작해야 하기 때문).

### 5.4 팔로우 이벤트 (v1.3에서 재확정)

- 처음에는 `artist_unfollow`를 MVP에서 뺐다가, `bridge_user_artist_follow`가 "팔로우·언팔로우 기간"을 관리한다는 PRD 설계와 충돌한다는 걸 발견하고 **다시 포함시키기로 결정**했다.
- 팔로우 시작 시 `bridge_user_artist_follow`에 새 행 생성(`followed_at`, `unfollowed_at=null`), 언팔로우 시 해당 활성 행에 `unfollowed_at` 채움.
- 동일 팬·아티스트 조합에서 종료되지 않은 활성 팔로우 행은 동시에 하나만 존재해야 한다는 무결성 규칙 추가.

### 5.5 메시지 구독 해지 (v1.3에서 확정)

- `message_subscription_cancel`은 **능동 해지와 자동 만료(미갱신) 둘 다** 포함한다.
- 구분은 `cancel_reason_category` 파라미터로: `user_cancel` / `expired_no_renewal`.

### 5.6 열린 퍼널과 닫힌 퍼널의 관계 (중요, 한 번 충돌했던 부분)

- 커머스 퍼널(`view_item`→`add_to_cart`→`begin_checkout`→`purchase`)에서 **앞 단계가 없는 것 자체는 데이터 오류가 아니다.**
- 예: 상품 목록에서 바로 장바구니에 담아서 `view_item` 없이 `add_to_cart`가 발생하는 건 정상적인 "열린 퍼널" 경로다.
- 시간 순서 규칙은 "같은 상품에 대해 두 이벤트가 모두 존재할 때, 그 순서가 뒤바뀌었는가"만 검증한다. 앞 단계 자체의 부재를 막지 않는다.
- 순서를 반드시 지키는 "닫힌 퍼널" 전환율은 별도로 계산한다.
- 이 구분은 이벤트 추적 계획서 초안에서 실수로 앞 단계 부재를 오류로 처리했다가, 사용자·클로드·지피티 3자 검토를 거쳐 수정된 이력이 있다. **다시 충돌시키지 말 것.**

### 5.7 핵심 활동(Core Activity) 목록

DAU/WAU/이탈위험/휴면/재활성 계산에 쓰이는 12개 이벤트가 확정되어 있다 (`event_tracking_plan.md` 8.1절 참고). `sign_up`, `session_start`, `artist_view`, `message_subscription_cancel`, `artist_unfollow`, `refund`는 핵심 활동에서 제외된다.

### 5.8 content_type도 조인으로만 파악 (v1.4)

- `content_view` 이벤트에 `content_type`을 직접 저장하지 않고 `dim_content` 조인으로 파악하기로 결정했다. `artist_id`와 동일한 원칙을 적용한 것이다(이벤트 자체의 속성이 아니라 콘텐츠 차원 테이블의 고정 속성이므로 중복 저장하지 않는다).
- `content_unlike`, 댓글 삭제 이벤트는 계속 MVP 제외를 유지한다(분석 목적상 필요성이 낮다).

### 5.9 data_generation.yaml 1차 검토 반영 (config_version 1.1)

- ChatGPT 검토를 거쳐 활동 강도(high/medium/low)에 실제 빈도 수치를 매핑하고, 활동 단계 배정 방식(겹침·공백 없이 90일을 정확히 채우는 규칙)을 명시했다.
- communication_effect 비교 시나리오는 애초 계획대로 `config/sensitivity_scenario.yaml`로 분리했다 (PRD 17절 리포지토리 구조와의 정합성 회복).
- 샘플 데이터 추출 방식을 "사용자 기준 선정 후 관련 행 추출"로 명확히 하여 외래키 무결성이 깨지지 않도록 했다.

### 5.10 기존 가입자의 sign_up 이벤트 미생성 결정 (fact_user_event 1/4 단계)

- **충돌 발견**: `fact_user_event` 생성 중, `dim_user`의 기존 가입자(분석 시작일 이전 가입, 약 70%)는 `signup_timestamp_utc`가 분석 기간보다 최대 2년 앞설 수 있는데, `sign_up.event_timestamp_utc`는 이 값과 동일해야 한다는 규칙(11.1절)과 `event_tracking_plan.md`의 `ET-DQ-14`("분석 기간을 벗어난 이벤트·활동 0건") 규칙이 서로 충돌했다.
- **결정**: ET-DQ-14에 예외를 만들지 않고 그대로 지키는 쪽을 택했다. 실제 분석 도구(GA4 등)가 트래킹 시작 이전 가입자의 가입 이벤트를 소급 기록하지 않는 것과 동일한 원칙을 적용해, **기존 가입자는 `sign_up` 이벤트를 생성하지 않는다.** 신규 가입자(분석 기간 중 가입, 약 30%)만 기존 로직대로 `sign_up`을 생성한다. 가입 시각 정보 자체는 `dim_user.signup_timestamp_utc`에 그대로 남아있으므로 코호트 분석 등에는 지장이 없다.
- **연쇄 조정**: `session_start`도 신규 가입자는 세션 1이 `sign_up`과 동일 시각이어야 하지만, 기존 가입자는 강제 시작 세션이 없고 분석 기간 중 처음 관측된 세션이 자연스럽게 `session_number=1`이 된다. `bridge_user_artist_follow`/`fact_message_subscription`의 시작 시각 하한도 `signup_timestamp_utc`가 아니라 `max(signup_timestamp_utc, analysis_start_date)`로 변경해 같은 원칙을 적용했다.
- **부수적으로 발견한 버그**: 위 하한 변경 과정에서 `_random_instant_after` 헬퍼(2턴 전 `bridge_user_artist_follow` 작업 때 추가)가 결과를 UTC로 정규화하지 않는 버그가 드러났다. 시작 시각이 KST tzinfo를 가지는 경우(기존 가입자의 `analysis_start_kst`) KST 벽시계 시각이 "Z"(UTC) 접미사로 그대로 문자열화되어 9시간이 밀리는 문제였다. 이전에는 시작 시각이 항상 `signup_timestamp_utc`(이미 UTC)였기 때문에 잠복해 있다가 이번에 노출되었다. `astimezone(UTC)` 정규화를 추가해 수정했다.

### 5.11 소통 노출 모델 (exposure_model) — 프로젝트 핵심 메커니즘

- **왜 session_start를 소통 이벤트와 연결해야 했는가**: 이 프로젝트의 핵심 분석 질문은 "아티스트 소통이 줄면 팬 활동도 줄어드는가?"(3절)다. 이 관계가 데이터에 실제로 심어져 있으려면, 소통 노출(`artist_post_view`/`message_open`/`live_view_start`)이 팬의 세션(재방문)을 유도하는 구조가 있어야 한다. 그래서 1/4 단계에서 만든 "30분 이상 공백 뒤 이벤트가 오면 즉석에서 새 세션을 만든다"는 세션 배정 로직을 그대로 재사용해, 노출 이벤트가 비활동 팬을 다시 세션으로 끌어들이는("알림 보고 접속") 메커니즘을 구현했다. `fact_user_event`를 부분 추가가 아니라 매번 전체를 다시 생성하는 이유도 이 때문이다 — 노출 이벤트가 중간에 끼어들면 이후 `session_number` 전체가 바뀔 수 있다.
- **exposure_model 파라미터 요지** (`config/data_generation.yaml`): `base_exposure_rate=0.08`(활동 1건당 대상 팬의 기본 반응 확률), `propensity_multiplier_range=[0.7, 1.3]`(팬별 `engagement_propensity`(Beta(2,6))를 이 범위로 선형 변환해 개인차 반영), `phase_effect_scale=0.5`(활동 단계 강도가 노출 확률에 주는 영향의 세기, `communication_effect`와 곱해 사용), `live_watch_seconds`(최소 60초 + 평균 180초 지수분포, 최대 10800초 clip).
- **`communication_effect`는 여기서 적용된다**: `phase_effect = 1 + communication_effect * phase_effect_scale * (phase_multiplier[phase_type] - 1)`. `communication_effect=1.0`(baseline)이면 활동기(`comeback_active`/`tour`)는 노출 확률이 올라가고 비활동기(`inactive`)는 내려간다. `communication_effect=0`(null_effect)이면 이 항이 완전히 사라져 모든 phase_type에서 `phase_effect=1`이 된다 — PRD 13.4의 순환 논리 방지 장치가 실제로 여기서 작동한다.
- **baseline vs null_effect 검증 결과** (400명 규모, `n_exposures / n_eligible_target`로 계산한 노출률): baseline에서는 3개 아티스트 전부 활동기(`comeback_active`+`tour` 가중평균) 노출률이 비활동기보다 뚜렷이 높았다(차이 +0.047~+0.063). null_effect에서는 같은 차이가 -0.001~-0.011로 거의 사라졌다(작은 표본에서 오는 잡음 수준). 최초에는 "노출 이벤트 수 ÷ 활동 건수"로 비교했는데 `inactive` 구간의 활동 건수 자체가 너무 적어(`phase_multiplier=0.2`로 활동도 적게 생성됨) 비율이 크게 튀었다 — 대상 팬 수(분모)를 정확히 세는 방식으로 바꾸고 나서야 기대한 패턴이 뚜렷하게 확인됐다. 최종 산출물 `data/raw/fact_user_event.csv`는 baseline 결과이고, `fact_user_event_null_effect.csv`는 이 비교 검증용으로만 남겨둔 파일이다.

### 5.12 콘텐츠 소비 모델 (content_engagement)

- **설계 요지** (`config/data_generation.yaml`): 세션마다 조회 콘텐츠 수는 `Poisson(base_views_per_session_mean=1.5 × propensity_multiplier)`로 뽑는다(중복 조회 허용). 조회 대상 콘텐츠는 "그 세션 시각 이전에 발행된" 콘텐츠 전체 중에서 `weight = (팔로우 중이면 followed_artist_weight=5.0, 아니면 1.0) × 0.5^(콘텐츠 나이/14일)`로 가중 추출한다. 좋아요·댓글은 조회마다 독립적으로 `like_rate=0.35`/`comment_rate=0.08`에 같은 `propensity_multiplier`를 곱해 판정하고, 좋아요는 같은 (팬, 콘텐츠) 조합에 한 번만 허용한다. 콘텐츠는 전체 공개이므로 새 세션을 만들지 않고 기존 세션에만 붙인다.
- **검증 중 발견한 measurement 함정**: "팔로우 콘텐츠 조회 비중"을 처음에 `dim_content` 전체에서 "팬이 한 번이라도 팔로우한 아티스트의 콘텐츠 비중"으로 비교했더니(naive baseline 57.5%) 실제 관측치(53.7%)보다 오히려 낮게 나와 언뜻 가중치가 안 먹힌 것처럼 보였다. 원인은 이 baseline이 최신성 감쇠와 "그 세션 시각에 아직 발행/팔로우되지 않은 콘텐츠는 애초에 후보가 아니다"라는 제약을 반영하지 못했기 때문이다. `followed_artist_weight`만 1.0으로 끈 반사실(counterfactual, recency는 그대로 유지) 대비로 다시 비교하니 **34.5% → 53.7%**로 뚜렷한 상승이 확인됐다. 앞으로 이런 "가중치 하나의 효과"를 검증할 때는 전체 모수 대비 단순 비율이 아니라, 그 가중치만 끈 반사실과 비교해야 한다는 교훈을 남긴다.
- **좋아요/댓글 비율이 목표(35%/8%)보다 낮게 나온 이유**: `propensity_multiplier_range=[0.6,1.6]`에 `engagement_propensity~Beta(2,6)`(평균 0.25)를 대입하면 실제 평균 배수는 1.0이 아니라 `0.6+0.25×1.0=0.85`다. 댓글(중복 제약 없음)은 `8%×0.85=6.8%` 예측과 관측치 7.05%가 거의 일치해 모델이 정확히 작동함을 보여준다. 좋아요(26.78%)는 `35%×0.85=29.75%` 예측보다 더 낮은데, "같은 콘텐츠 두 번째 조회부터는 좋아요 재생성 안 함" 규칙이 추가로 비율을 깎기 때문이며 의도한 동작이다.
- **최종 검증 요약** (400명, baseline): 12종 이벤트 합계 38,945건(목표 상한 150,000건 대비 여유 있음). 팔로우 콘텐츠 조회 비중 34.5%→53.7%로 상승(반사실 대비), 조회 콘텐츠 평균 나이 15.4일 vs 전체 콘텐츠 평균 나이 50.9일(최신성 편향 확인), 좋아요 중복 0건, `content_id` 참조 무결성 위반 0건, `session_number` 순차성 위반 0건(콘텐츠 이벤트가 새 세션을 만들지 않으므로 1~2단계 결과 그대로 유지), 재현성 확인됨.

### 5.13 커머스 퍼널 모델 (commerce_funnel) — 묶음 주문 처리

- **묶음 주문(bundling) 결정**: 실제 쇼핑몰처럼 한 번의 결제에 여러 상품이 담길 수 있어야 분석 가치가 있다고 보고, `(user_id, session_id)` 단위로 그 세션에서 담긴 장바구니 전체를 하나의 `transaction_id`로 묶어 `begin_checkout`을 발생시키기로 했다. `fact_order_item`은 상품별로(add_to_cart 이벤트별이 아니라) 한 행만 생성하며, 같은 상품이 그 세션에서 여러 번 담겼더라도 `fact_order_item`에는 중복 없이 한 행 + 수량으로 반영된다.
- **설계 요지** (`config/data_generation.yaml`): `view_item` 조회 수는 `Poisson(base_view_rate=0.12 × purchase_multiplier × engagement_factor)`로 뽑는다. 상품 선택 가중치는 콘텐츠 모델과 동일한 패턴(`followed_artist_product_weight=3.0 × 0.5^(상품 나이/30일)`). `add_to_cart`는 조회 후 전환(경로 A, `view_to_cart_rate=0.25`)과 조회 없이 바로 담는 열린 퍼널 우회(경로 B, `direct_add_to_cart_rate_per_session=0.02`) 두 경로로 생성된다. `cart_to_checkout_rate=0.55`, `checkout_to_purchase_rate=0.85`를 통과 못 하면 각각 "미완료 장바구니"/"pending 주문"으로 남고 오류로 취급하지 않는다(9.2절 열린 퍼널 원칙과 동일). 환불은 완료 주문의 `refund_rate_target=0.05`만큼, 14일 이내 무작위 시점에 전액(70%) 또는 부분(20~80%) 환불로 처리한다.
- **검증 결과 (400명, baseline)**: `purchase.value`와 `fact_order_item` 합계 불일치 0건, `refund_amount > order_amount` 위반 0건, 모든 `product_id`/`transaction_id` 참조 무결성 위반 0건, 재현성 확인됨. **H-03 검증**(참여 팬이 구매전환도 높다): `content_like`+`comment_create` 총합 기준 상위 50% 그룹의 상품 조회→구매 전환율 **51.45%**, 하위 50% 그룹 **35.92%** — 뚜렷한 차이로 가설이 데이터에 반영됨을 확인했다.
- **⚠️ 400명(테스트 규모)에서 목표 범위 미달 — 조정 필요 여부 확인 필요**:
  - `fact_order` 총 247건 (`config.scale.orders` 목표 1,000~2,500 미달). 깔때기 역산(조회→장바구니→체크아웃→구매 각 단계 실측 전환율)으로 검증한 결과 설정값과 정확히 일치해 **로직 버그는 아니다.** 다만 400명은 최종 목표(1,500~2,000명)의 20~27%에 불과해 단순 비례 외삽 시 1,500명이면 약 926건(목표 미달), 2,000명이면 약 1,235건(목표 충족)으로 경계에 걸친다.
  - `fact_user_event` 총 38,908건(12→17종 확장 후에도 목표 80,000~150,000 미달). 같은 방식으로 외삽하면 1,500명 약 145,905건(목표 내), 2,000명 약 194,540건(**상한 초과**)로, 사용자 수 설정에 따라 상한을 넘을 수 있다.
  - 주문당 평균 상품 개수는 1.004(247건 중 2개 이상 묶인 주문 1건)로, "묶음 처리가 작동한다는 뚜렷한 증거"로 보기엔 약하다. 메커니즘 자체는 그 1건으로 정상 작동이 확인됐지만, `base_view_rate`가 낮아 한 세션에 서로 다른 상품 2개 이상이 담기는 경우가 드물다.
  - `add_to_cart` 중 `view_item` 없이 발생한 비율이 56.80%로 나왔는데, 이는 `direct_add_to_cart_rate_per_session`(0.02) 자체보다 훨씬 높다. 원인은 경로 A(조회→담기: 세션당 기대값 약 0.016)가 경로 B(직접 담기: 세션당 0.02)보다 오히려 작기 때문 — `base_view_rate`가 낮아서 생기는 연쇄 효과다.
  - 이상 네 가지 모두 최종 실행 규모(1,500~2,000명)로 재확인하거나, `base_view_rate`/`direct_add_to_cart_rate_per_session` 등을 조정할지 사용자 확인이 필요한 상태로 남겨뒀다 (직전 `activity_intensity_levels` 사례와 동일한 패턴).

### 5.14 commerce_funnel 파라미터 1차 조정 및 1,750명 실규모 검증 (config_version 1.7)

- **조정 내용**: 5.13절에서 발견한 "경로 A(조회 후 전환)와 경로 B(직접 담기)가 거의 1:1로 나옴" 문제를 해결하기 위해 `base_view_rate`를 0.12→0.20으로 올리고 `direct_add_to_cart_rate_per_session`을 0.02→0.006으로 낮췄다.
- **1,750명(최종 목표 1,500~2,000명의 중간값) 실규모 검증 결과**:
  - `fact_order` **1,050건** — 목표(1,000~2,500) **충족**.
  - `add_to_cart` 중 `view_item` 없이 발생한 비율 **18.24%** — 목표(15~20%) **충족**. 경로 A/B 비율 문제가 해결됨.
  - 주문당 평균 상품 개수 **1.015**(1,050건 중 2개 이상 묶인 주문 16건) — 여전히 낮지만 400명 규모(1.004)보다는 개선. 묶음 처리 메커니즘 자체는 정상 작동.
  - H-03 재검증: 참여 상위 50% 그룹 전환율 **48.06%** vs 하위 50% **31.57%**(+16.5%p) — 400명 규모(51.45% vs 35.92%)와 유사한 폭으로 뚜렷하게 재현됨.
  - `fact_user_event` **179,191건** — 목표 상한(150,000) **초과**. `content_view`(74,477)+`session_start`(58,335)+`content_like`(20,258) 세 이벤트만으로 153,070건(전체의 85.4%)을 차지해, 이번에 조정한 `commerce_funnel`과는 무관하게 **콘텐츠 소비·세션 생성 쪽 파라미터가 원인**이다. 상한 안에 넉넉히 들어오려면 `content_engagement.base_views_per_session_mean`(현재 1.5)을 대략 **0.75 전후로 낮추는 것**을 제안한다(대략 계산: `content_view`+`content_like`+`comment_create` 합계 99,956건을 약 50%로 줄이면 총합이 약 130,000건대로 내려온다). 아직 값은 바꾸지 않았다.
- **이번에 새로 발견하고 수정한 버그**: 세션이 분석 기간 종료 직전(마지막 25분 이내)에 시작되면 `content_view`/`view_item` 등의 오프셋이 분석 기간을 넘어가는 경계 버그가 1,750명 규모에서 23건 발견됐다(400명 규모에선 세션 수가 적어 우연히 발생하지 않았음). `_clip_to_period()` 헬퍼로 경계를 넘는 시각을 분석 종료 1초 전으로 자르도록 수정하는 과정에서, `_random_instant_after`(5.10절) 때와 **완전히 동일한 패턴의 KST/UTC 타임존 버그**가 다시 발생했다 — 자른 결과값이 KST tzinfo를 가진 `analysis_end_exclusive`에서 파생되어 `.astimezone(UTC)` 없이 그대로 "Z" 접미사로 문자열화되는 문제. 같은 원인이 반복된 만큼, **앞으로 새 타임스탬프 계산 헬퍼를 추가할 때는 항상 반환 직전에 `.astimezone(UTC)`를 명시적으로 거치는 것을 기본 습관으로 삼는다.**
- **핵심 무결성 전수 재검증(1,750명)**: `purchase.value`/`refund_amount`/외래키(user_id·artist_id·content_id·activity_id·product_id·transaction_id)/`session_number` 순차성/분석 기간 준수 — 전부 위반 0건. 재현성 확인됨.

### 5.15 content_engagement 조정, 시간 유틸 통합, 1,750명 최종 검증 (config_version 1.8)

- **조정 내용**: 5.14절에서 제안한 대로 `content_engagement.base_views_per_session_mean`을 1.5→0.75로 낮췄다.
- **타임존 버그 재발 방지 — `time_utils.py` 통합**: `_random_instant_after`(5.10절)와 `_clip_to_period`(5.14절)에서 KST/UTC 타임존 버그가 두 번 반복된 것을 계기로, `generate_dimensions.py`(`random_utc_timestamp`), `generate_facts.py`(`random_instant_after`), `generate_events.py`(`clip_to_period`)에 흩어져 있던 시간 계산 헬퍼와 `parse_utc`, `KST`/`UTC` 상수를 `src/generation/time_utils.py` 하나로 모았다. 이 모듈의 모든 함수는 반환 직전에 `.astimezone(UTC)`를 거치도록 통일했고, 각 함수 docstring 맨 앞에 "이 함수는 항상 UTC-aware datetime을 반환해야 한다"를 명시했다. 세 생성 스크립트는 이제 이 모듈에서 함수를 import해서 쓴다(기존 `_` 접두사 이름은 공용 모듈로 옮기며 접두사를 뗐다 — `parse_utc`, `random_utc_timestamp`, `random_instant_after`, `clip_to_period`).
- **회귀 테스트 추가**: `tests/test_time_utils.py`에 `time_utils.py`의 모든 함수가 실제로 UTC-aware 값만 반환하는지 확인하는 pytest 10건을 추가했다(naive datetime이나 KST가 새어나오면 실패). 1,750명 규모에서 실제로 발견됐던 "분석 기간 종료 직전 경계" 케이스를 그대로 재현하는 회귀 테스트(`test_clip_to_period_exact_bug_regression`)도 포함했다. `requirements.txt`에 `pytest`가 이미 있다고 안내받았으나 실제로는 없어서 추가하고 설치했다. 전체 10건 통과.
- **1,750명 최종 검증 결과**: `fact_user_event` **129,595건**(목표 80,000~150,000 충족), `fact_order` **1,039건**(목표 1,000~2,500 충족) — 5.14절에서 초과했던 두 지표가 모두 해결됐다. H-03 재검증: 상위 50% 전환율 **49.59%** vs 하위 50% **33.85%**(+15.74%p) — 이전 규모들과 유사한 폭으로 계속 뚜렷하게 재현됨. `purchase.value`/`refund_amount`/외래키 6종/`session_number` 순차성/분석 기간 준수 전부 위반 0건. `dim_*`부터 `fact_order_item`까지 11개 산출 테이블 전체를 처음부터 다시 실행해 바이트 단위로 완전히 동일함을 확인(재현성).
- **데이터 생성 파이프라인 1차 완성**: 이로써 3개 아티스트, 1,750명 팬 규모로 `dim_artist`~`fact_order_item` 11개 테이블이 전부 목표 범위 안에서 생성되고 핵심 무결성 검증을 통과하는 상태에 도달했다. 다음 단계는 PostgreSQL DDL 작성과 데이터 적재다.

### 5.16 로컬 PostgreSQL과 포트 충돌 (5433 포트 사용)

- **원인**: 이 개발 환경에 수업용으로 이미 설치된 로컬 PostgreSQL이 기본 포트 5432를 점유하고 있어서, Docker Compose로 띄운 `fanlog_postgres` 컨테이너와 포트가 충돌했다. DBeaver에서 5432로 접속하면 Docker 컨테이너가 아니라 기존 로컬 PostgreSQL로 연결되어 비밀번호 인증 실패가 발생했다.
- **해결**: `docker-compose.yml`의 포트 매핑은 그대로 두고(컨테이너 내부는 항상 5432), `.env.example`의 `POSTGRES_PORT` 기본값을 5432에서 **5433**으로 바꿔 처음부터 충돌을 피하도록 했다. README "로컬 개발 환경 설정"에 트러블슈팅 항목도 추가했다.

---

## 6. 배포 전략 (한 번 정한 뒤 바뀌지 않은 부분)

- 로컬 PostgreSQL은 Streamlit Community Cloud에서 직접 접근할 수 없다.
- **결정: 정적 Parquet 스냅샷 방식.** 로컬에서 PostgreSQL로 데이터 적재·SQL 분석·검산을 하고, 최종 분석 마트 4개(`mart_artist_daily`, `mart_user_daily`, `mart_content_performance`, `mart_commerce_funnel`)만 Parquet으로 내보내 배포한다.
- 클라우드 PostgreSQL(Neon, Supabase 등) 연결은 실시간 갱신이 필요해질 때의 확장 범위로 미뤄뒀다.
- 이 결정은 Week 1에 확정해서 Week 4 배포 단계에서 막히지 않도록 하기 위함이었다 (실제로 지피티와의 논의에서도 이 리스크가 지적된 바 있음).

---

## 7. 기능 요구사항(FR) 관련 판단 근거

- **FR-003(활동 단계·팬 세그먼트 필터)은 Should에서 Must로 상향 조정**했다. Page 2의 "활동 단계별 비교"와 Page 1·3의 "세그먼트별 지표 비교"가 이 필터에 실제로 의존하기 때문에, 우선순위표와 실제 화면 구성이 어긋나지 않도록 맞췄다.

---

## 8. 작업 방식·툴체인 관련 결정

### 8.1 브랜치 전략: main 하나로 통일

- 처음에는 지피티의 제안대로 `feature/data-design` 기능 브랜치를 만들어 작업했다.
- 이후 "1인 프로젝트에서 브랜치를 여러 개 파는 게 오히려 관리 부담만 늘린다"는 판단 하에, **`feature/data-design`을 `main`에 merge하고 브랜치를 삭제**했다. 이후로는 `main` 브랜치 하나로만 작업한다.
- 커밋은 작은 논리 단위로 자주 나눠서 한다 (Git 히스토리 자체가 포트폴리오의 사고 흐름을 보여주는 요소이기 때문).

### 8.2 지피티와의 협업 이력

- 이 프로젝트는 처음에 ChatGPT와 함께 시작했고, 이후 Claude(이 대화)로 메인 작업 도구를 옮겼다. 이유: 지피티 쪽에서 수정사항이 너무 많이 생겨서 관리가 번거로웠음.
- 지피티가 제안한 내용(게시글/콘텐츠 구분, 열린 퍼널 처리, 핵심활동 목록, 콘텐츠-아티스트 연결)은 클로드가 검토했던 이슈들과 거의 동일했고, 실제로 반영에 참고했다.
- 앞으로 지피티나 다른 도구에서 조언을 가져올 경우, **그대로 반영하지 말고 이 로그의 원칙(완주 가능성, PRD 우선, 사전 확인)에 맞는지 먼저 검토한다.**

### 8.3 코딩 에이전트(Claude Code 등) 사용 전환

- 문서를 반복적으로 손으로 찾기/바꾸기 하는 게 비효율적이라고 판단해, 이 시점부터 Claude Code 같은 에이전트 도구로 작업 방식을 전환하기로 했다.
- 에이전트는 이 로그 파일을 먼저 읽고 작업을 시작해야 한다. 파일이 갱신되지 않은 채로 방치되면 맥락 손실이 누적되므로, **중요한 결정이 새로 생길 때마다 이 파일도 함께 갱신한다.**

---

## 10. 작업 방식 전환 (v1.4 이후)

- 포트폴리오 완성도는 문서의 정교함보다 "실제로 끝까지 작동하는 결과물 + 시각적 완성도 + 분석 스토리의 설득력 + README 품질"에서 나온다고 판단, 이 시점부터 문서 작업 깊이를 의도적으로 줄이고 실제 구현(데이터 생성, 대시보드, 분석 보고서)에 시간을 더 배분하기로 했다.
- 이후 세부 이벤트/규칙은 이미 정해진 원칙을 기계적으로 적용해 빠르게 채우고, 정말 중요한 설계 충돌이 있을 때만 사용자에게 확인한다.

### 10.1 커밋 습관 관련 사고 사례 (2026-09-25)

- 손으로 문서를 수정하던 세션에서 저장만 하고 커밋하지 않은 v1.3 변경사항이 워킹 디렉토리에 남아있는 채로 Claude Code 세션으로 전환되어, 그 위에 v1.4 작업이 얹혀 두 버전 변경사항이 섞이는 일이 있었다.
- 해결: 에이전트가 자신이 만든 v1.4 변경사항을 일시적으로 되돌려 v1.3 상태만 먼저 커밋(`79b20ba`)하고, 이후 v1.4 변경사항을 재적용해 별도 커밋(`e35bad6`)함.
- 교훈: 작업 단위가 끝나면 바로 커밋한다. 특히 세션(사람 손 작업 ↔ 에이전트 작업)을 전환하기 직전에는 항상 `git status`로 미커밋 변경사항이 없는지 확인한다.

---

## 9. 진행 상황 체크포인트 (이 로그 작성 시점)

- [x] PRD v1.3 확정 및 커밋 완료 (main 브랜치)
- [x] 이벤트 추적 계획서 초안 + 정합성 보완 완료
- [x] 이벤트 상세 명세 작성 진행 중
  - [x] 11.1 회원·세션 (`sign_up`, `session_start`) 완료
  - [x] 11.2 아티스트 탐색·구독 (`artist_view`, `artist_follow`, `artist_unfollow`, `message_subscription_start`, `message_subscription_cancel`) 완료
  - [x] 11.3 소통·콘텐츠 이용 (`artist_post_view`, `message_open`, `live_view_start`, `content_view`, `content_like`, `comment_create`) 완료
  - [x] 11.4 커머스 (`view_item`, `add_to_cart`, `begin_checkout`, `purchase`, `refund`) 완료
- [x] ERD + `data_dictionary.md` 작성 완료
- [x] `config/data_generation.yaml` 초안 작성 완료
- [x] `config/sensitivity_scenario.yaml` 작성 완료
- [x] 소량 샘플 데이터 생성 스크립트 작성
  - [x] dim_artist, dim_user 생성 스크립트 작성 및 소량(50명) 실행 검증 완료
  - [x] 나머지 차원 테이블(dim_content, dim_product, dim_activity_phase) 생성 스크립트 작성 완료
  - [x] fact_artist_activity, bridge_user_artist_follow, fact_message_subscription 생성 스크립트 작성 완료
  - [x] fact_user_event 1/4(회원·세션+팔로우·구독 파생) 완료
  - [x] fact_user_event 2/4(소통 노출: artist_post_view/message_open/live_view_start) 완료
  - [x] fact_user_event 3/4(콘텐츠 소비: content_view/content_like/comment_create) 완료
  - [x] fact_user_event 4/4(커머스: view_item/add_to_cart/begin_checkout/purchase/refund) 및 fact_order/fact_order_item 생성 완료
- [x] 데이터 생성 파이프라인 1차 완성 (1,750명 규모, 전체 검증 통과)
- [x] PostgreSQL DDL 작성 및 데이터 적재 완료 (11개 테이블 + meta_generation_run, 행 수 검증 통과)
- [x] SQL 품질검사 1/5 (기본키·외래키·결측) 작성 및 실행 완료 (`sql/quality_checks/001_keys_and_referential_integrity.sql`, DQ-01~03·ET-DQ-01~06 총 9개 규칙, 1,750명 실규모 데이터 전수 검증 — 위반 0건)
- [x] SQL 품질검사 2/5 (시간순서) 작성 및 실행 완료 (`sql/quality_checks/002_temporal_order.sql`, DQ-04~06·ET-DQ-07,09,11,14,16~19,21 규칙, 1,750명 실규모 데이터 전수 검증 — 위반 0건)
- [x] SQL 품질검사 3/5 (허용값·카테고리) 작성 및 실행 완료 (`sql/quality_checks/003_allowed_values.sql`, ET-DQ-03,04,15,20 + 추가검사 A·B(product_type/order.status), 1,750명 실규모 데이터 전수 검증 — 위반 0건. 전부 CHECK 제약이 이미 막고 있어 예상대로 0건, 문서화·감사 가능성(NFR-10) 목적)
- [x] SQL 품질검사 4/5 (구매·환불 정합성) 작성 및 실행 완료 (`sql/quality_checks/004_commerce_integrity.sql`, DQ-07~09·ET-DQ-25~27 + 추가검사 C(refund_amount), 1,750명 실규모 데이터 전수 검증 — 위반 0건. ET-DQ-28(pending 주문 참고용 집계)은 160건이며 위반이 아니라 정상적인 열린 퍼널 결과)
- [x] SQL 품질검사 5/5 (타임존 일치) 작성 및 실행 완료 — 전체 5그룹 품질검사 완료 (run_all.sql로 통합 실행 가능) (`sql/quality_checks/005_timezone_consistency.sql`, DQ-10/ET-DQ-13, 5개 테이블 UTC→KST 파생 일자 전수 검증 — 위반 0건, 5.10절·5.14절 타임존 버그 재발 없음 확인. `sql/quality_checks/run_all.sql`로 001~005 전체 87개 세부 항목을 하나의 통합 표로 재확인 — 전부 0건)
- [x] SQL 분석 마트 1/4 (mart_artist_daily) 작성 완료 (`sql/marts/001_mart_artist_daily.sql`, VIEW로 구현. 아티스트 3팀 × 90일 = 270행 확인, comeback_active+tour 구간 소통일 비율 81.2% vs daily+inactive 58.6%로 방향성 확인, inactive 구간 평균 공백일 3.6일로 다른 구간(0.1~0.5일) 대비 뚜렷이 높음. active_followers는 사용자 확인 하에 "그 아티스트 관련 핵심 활동"으로 한정)
- [x] SQL 분석 마트 2/4 (mart_user_daily) 작성 완료 (`sql/marts/002_mart_user_daily.sql`, VIEW로 구현. 날짜 범위는 사용자 확인 하에 GREATEST(가입일, 분석 시작일)~분석 종료일로 제한(기존 가입자의 최대 2년 전 가입일을 그대로 쓰지 않음). 총 133,206행/1,750명 확인, activity_status 분포 active 95.6%·at_risk 4.2%·dormant 0.2%, 2026-02-15 DAU 마트 집계(289)와 fact_user_event 직접 집계(289) 완전 일치로 신뢰도 확인, was_reactivated_today 54건 확인)
- [x] SQL 분석 마트 3/4 (mart_content_performance) 작성 완료 (`sql/marts/003_mart_content_performance.sql`, VIEW로 구현. 콘텐츠 103개와 정확히 일치, engagement_rate는 PRD 14.6절 원칙대로 분모(unique_viewers)가 0이면 NULL 처리. 한 번도 조회되지 않은 콘텐츠 0건(최신 콘텐츠도 발행 1일 만에 조회 발생, 정상), null_engagement_rate_count도 0건으로 일관됨. "조회 높고 참여율 낮은" 콘텐츠 후보 5개 확인)
- [x] SQL 분석 마트 4/4 (mart_commerce_funnel) 작성 완료 — 4개 마트 전체 완성 (`sql/marts/004_mart_commerce_funnel.sql`, VIEW로 구현. (user_id,product_id) 4,817쌍과 마트 행수 정확히 일치. 깔때기 4817→1756(36.5%)→1000(56.9%)→791(79.1%), 열린 퍼널 우회 비율 15.38%(파이썬 검증치 18.24%와 유사 범위, 이벤트 단위 vs (팬,상품) 쌍 단위 집계 차이로 설명됨). is_closed_funnel_complete 537건은 완료 주문 821건 중 묶음 주문(11건)을 반영해도 다 설명되지 않는 부분(전략·기간 조건 미충족 주문 다수 포함)이 있어 관계를 정성적으로만 확인. **총 매출 검증에서 불일치 발견**(마트 56,478,000 vs fact_order 59,275,000, 차이 2,797,000): 이중 계산이 아니라 (a) 이 마트가 설계상 재구매를 추적하지 않아 재구매 매출 2,417,000이 애초에 빠짐(의도된 범위 제외), (b) 동일 (팬,상품) 쌍에서 첫 checkout 시도가 미완료로 끝나고 나중의 별도 시도가 완료된 4건(약 380,000)을 현재 매칭 로직이 놓침(사소한 설계 한계, 데이터 수정 아님)으로 전액 설명됨 — 검증 쿼리 5-1/5-2에 원인 분리 반영. **원칙: 이 마트는 (user_id, product_id) 쌍당 "첫 관심" 시점만 추적하며 재구매를 다루지 않는다. 총매출·환불 등 재무 지표의 정답 소스는 항상 fact_order/fact_order_item이며, 이 마트에서 매출을 집계해서 사용하지 않는다. 이 마트는 퍼널 단계별 전환율·이탈 분석 전용이다.**)

**다음 작업: Python 분석 노트북 작성 (01_data_validation, 02_communication_retention, 03_commerce_funnel)**
- [x] 분석 노트북 1/3 (`notebooks/01_data_validation.ipynb`) 작성 및 실행 완료. `sql/quality_checks/run_all.sql`의 87개 세부 품질검사를 SQLAlchemy로 Python에서 재실행(전부 위반 0건 재확인), 대표 규칙 3개(DQ-01 기본키 중복, DQ-03 외래키 고아 행, DQ-10 타임존 일치)는 SQL과 무관하게 pandas로 독립 재계산해 전부 일치 확인. `src/analysis/db.py`(공용 SQLAlchemy 연결 헬퍼) 추가, `requirements.txt`에 scipy/matplotlib/seaborn/jupyter/nbformat/nbclient/jinja2 추가.
- [x] 분석 노트북 2/3 (`notebooks/02_communication_retention.ipynb`) 작성 및 실행 완료. H-01(소통 활동일 vs WAU·참여율, 아티스트별+전체 pooled 동시·1주 시차 Spearman)은 전체 합산 시 유의한 양의 상관(중간~강함, `p<0.01`)이지만 아티스트별로는 방향이 엇갈리고 개별적으로 유의하지 않아 부분 지지로 정리. H-02(소통 공백 4구간 vs 14일 이탈위험·30일 휴면, 단일 팔로우 팬만)는 공백이 길수록 두 비율 모두 뚜렷하게 단조 증가(전 구간 n>1,500)해 가설 방향과 일치.
- [x] 분석 노트북 3/3 (`notebooks/03_commerce_funnel.ipynb`) 작성 및 실행 완료 — **노트북 3개 전체 완성**. 온보딩 퍼널(신규 가입 팬 n=550만 대상, 550→202→143→87), 콘텐츠 참여 퍼널((팬,콘텐츠) 31,026쌍 중 24시간 이내 참여 전환 36.0%), 커머스 퍼널(mart_commerce_funnel로 열린 퍼널 4817→1756→1000→791과 순서 기반 닫힌 퍼널 537/4817 구분, 매출·환불은 fact_order 기준 직접 계산 — 총매출 59,275,000원, 환불률 6.6%). PRD 11.1절 규칙 그대로 팬 세그먼트 계산(신규 80·조회중심 875·참여 391·코어 394·미분류 10). H-03을 생성시점 검증·SQL 재계산·세그먼트 분석 3방식으로 교차검증한 결과 고참여/저참여 큰 틀에서는 세 방식 모두 일관되게 지지(49.59%/33.85%, 48.89%/31.93%, 42.29%/33.30%)했으나, 세그먼트 4단계로 세분화하면 "참여"(27.4%)가 "조회중심"(35.8%)보다 낮게 나오는 역전 발견.
- [x] **REVIEW NEEDED 항목 11.1~11.12 전부 해소 완료** (2026-09-26, 11절·12절 참고). 주요 결과:
  - null_effect 비교 데이터를 1,750명·4/4단계 전체로 재생성해 baseline과 재검증 완료(활동기-비활동기 노출률 차이 baseline +0.0276 vs null_effect +0.0022로 거의 소멸 — `communication_effect` 스위치가 실제로 관계를 만든다는 근거 재확인). 파일명도 `fact_user_event_null_effect_full.csv`로 정정.
  - H-02를 다중 팔로우 팬 포함 전체 팬(100%)으로 재분석, artist_001의 H-01 음의 상관은 편상관계수로 "신규 가입자 유입 추세" 가설이 지지됨을 확인(`r=-0.449`→`r_partial=+0.580`).
  - 상관계수 결과 전체에 Fisher z 신뢰구간 추가, phase_type 활동기/비활동기 비교를 Mann-Whitney U로 보완(단, 시간 추세와 얽혀 있음을 발견 — 12.1절).
  - "참여 < 조회중심" 역전의 원인(코어 판정의 구매 이력 조건)을 반사실 재계산으로 실제 검증(참여 전환율 27.4%→40.6%로 역전 해소, 가설 지지).
  - 코어 팬 판정을 생애 전체 기준으로도 비교(394명→788명), "재방문율"을 PRD 공식 W1 지표와 나란히 제시(두 지표 순위가 다름 — 12.2절), H-03 서술을 "정의가 다른 지표 세 개가 같은 방향을 가리켰다"로 명확화.
  - 남은 보수적 판단(11.3, 11.5, 11.7, 11.9)은 이미 이전 세션에서 처리됐거나 그대로 유지하기로 확정, 11.13·11.14는 애초에 해결이 필요한 항목이 아니었음.
- [x] **최종 분석 보고서(`docs/analysis_report.md`) 초안 작성 완료** — 핵심 발견 3개(H-02 소통 공백-재방문, H-01+11.7 편상관 반전, H-03+11.12 반사실 재검증)를 분자/분모·r·p·신뢰구간 전부 포함해 정리, 11·12절 유지 항목을 한계로, PRD SC-10 고지문 포함. 이후 검증 과정에서 발견된 오차 2건(H-02 표 합계 4건 차이는 분석 시작일 공백일 계산 불가 사례, 코어 팬 "정확히 2배"는 부분집합 관계는 구조적이나 배수 자체는 우연)을 반영해 수정. 아직 초안 상태(git 미반영).
- [x] **Streamlit 대시보드 디자인 시스템 + Page 1(종합현황) 구현 완료** (`dashboard/theme.py`, `dashboard/data.py`, `dashboard/app.py`, `dashboard/pages/01_overview.py`). 디자인 토큰(deep_violet/surface/brand_violet/brand_pink/signal_cyan 등)과 Pretendard 폰트로 Streamlit 기본 스타일을 덮어쓰는 `inject_theme()`, 그라데이션 KPI 렌더러 `render_kpi()`, 가상 데이터 배지, Plotly 다크 테마 `get_plotly_theme()`을 구현. `dashboard/data.py`는 `src/analysis/db.py`의 SQLAlchemy 엔진을 재사용해 DAU/WAU(일평균·주평균)·W1 재방문율(03_commerce_funnel.ipynb 11.10절 방식 재사용)·14일 이탈위험률·콘텐츠 참여율·구매 전환율(순서 기반 닫힌 퍼널)과 아티스트 비교·저참여 콘텐츠·세그먼트 분포(PRD 11.1절 규칙, 전체 팬 대상 재계산 시 875/394/391/80/10으로 노트북과 완전히 일치 확인)를 계산한다. 아티스트 필터는 "그 아티스트 팔로우 팬 집단으로 모집단 제한" 방식으로 설계(문서화된 판단, PRD에 명시 안 됨). `streamlit run dashboard/app.py`로 기동 확인 및 `AppTest`로 기본 상태·아티스트 부분선택·기간 축소·빈 선택·단일일 선택 등 여러 필터 조합에서 예외 없음을 확인.
- [x] **버그 수정: `inject_theme()` 등이 주입한 CSS가 실제 브라우저에서 스타일로 적용되지 않고 화면 상단에 그대로 텍스트로 노출됨** (사용자가 실제 브라우저에서 직접 발견). 원인 2가지, 둘 다 `st.markdown()`의 CommonMark 파서 규칙 때문:
  1. CSS/HTML을 담은 f-string이 함수 코드의 들여쓰기를 그대로 물려받아(8칸 이상) 한 줄이라도 4칸 이상 들여써진 채로 블록이 시작되면 "들여쓰기된 코드 블록"으로 해석되어 `<style>`·`<div>` 태그가 파싱되지 않고 그대로(HTML 이스케이프된 채로) 화면에 노출된다.
  2. `inject_theme()`의 CSS 규칙 사이에 가독성을 위해 넣어둔 빈 줄이, CommonMark의 "원시 HTML 블록"을 빈 줄에서 끊어버려 `<style>` 태그 뒤에 오는 CSS 규칙 중 일부가 다시 일반 문단 텍스트로 해석되어 노출된다.
  - **수정**: `theme.py`의 `inject_theme()`/`render_kpi()`/`render_virtual_data_badge()` 세 곳 모두 `textwrap.dedent()`로 공통 들여쓰기를 제거하고, `inject_theme()`의 CSS 규칙 사이 빈 줄을 전부 제거했다. `markdown-it-py`(CommonMark 파서)로 수정 전/후 렌더링 결과를 직접 비교해 수정 전에는 `<pre><code>`·`&lt;style&gt;`·문단(`<p>`) 형태로 이스케이프되거나 끊겨 나오던 것이, 수정 후에는 전부 의도한 그대로(`<style>`, `<div style="...">`) 파싱됨을 확인했다.
  - **함께 발견한 부수 버그**: `dashboard/pages/01_overview.py`의 아티스트별 비교 막대 차트(`px.bar`, `color=` 인자 없이 생성)가 Plotly 기본 하늘색으로 나오는 문제도 있었다. `px.bar`는 `color=` 없이 단일 트레이스를 만들면 생성 시점에 Plotly 기본 팔레트 색을 그 트레이스에 고정해버려서, 이후 `fig.update_layout(colorway=...)`을 적용해도 이미 고정된 트레이스 색은 바뀌지 않는다. `color="artist_name", color_discrete_sequence=get_plotly_theme()["colorway"]`를 명시해 해결(범례는 x축과 중복되어 숨김). 도넛 차트도 기존에는 팔레트 외 색(`text_muted` 회색)을 하나 섞어 썼는데, 4색 팔레트만 순환(5번째 세그먼트는 첫 색으로 순환)하도록 통일했다.
- [x] **버그 수정 2건 (사용자가 실제 브라우저에서 직접 발견)**:
  1. **사이드바 접기 버튼 아이콘이 "keyboard_double_arrow_left" 글자 그대로 노출됨**: `inject_theme()`의 전역 폰트 규칙(`html, body, [class*="css"], [class*="st-"] { font-family: ... !important }`)이 너무 넓어서, Streamlit이 emotion으로 생성하는 클래스명(대부분 "css-"를 포함)에 걸려 아이콘 요소(`data-testid="stIconMaterial"`)까지 Pretendard로 강제 적용됐다. 이 아이콘은 리게이처 텍스트(예: `keyboard_double_arrow_left`)를 자체 번들 아이콘 폰트(`Material Symbols Rounded`, `.venv/Lib/site-packages/streamlit/static/static/css/*.css`의 `@font-face`로 직접 확인)로 그림처럼 렌더링하는 방식이라, 폰트가 바뀌면 그 글자가 그대로 보인다. `[data-testid="stIconMaterial"] { font-family: "Material Symbols Rounded" !important }` 규칙을 전역 폰트 규칙 바로 뒤에 추가해 아이콘 요소만 원래 폰트로 되돌렸다(같은 CSS 안에서 뒤에 오는 규칙이 이긴다).
  2. **세그먼트 도넛 차트가 5개 세그먼트(신규/조회중심/참여/코어/미분류)에 4색만 순환해 마지막 색이 겹침**: `theme.py`의 카테고리 팔레트에 5번째 색으로 `positive`(`#34D399`, 이미 정의돼 있던 톤)를 추가해 `_CATEGORY_PALETTE`/`get_plotly_theme()["colorway"]`를 5색으로 확장했다. 아티스트 3팀만 쓰는 막대 차트는 앞 3색만 그대로 쓰여 영향 없음을 확인.
  - **재검증**: `streamlit run dashboard/app.py` 재기동 + `AppTest`로 기본/아티스트 부분선택/기간 축소 조합 재확인(예외 없음), `markdown-it-py`로 CSS 텍스트 노출 재확인(리크 0건), 5개 세그먼트 색상이 전부 서로 다름을 직접 계산해 확인.
- [x] **Streamlit 대시보드 Page 2(아티스트 소통·리텐션) 구현 완료** (`dashboard/pages/02_communication_retention.py`, `dashboard/data.py`에 7개 함수 추가). `theme.py`의 디자인 토큰·`inject_theme()`·`render_kpi()`·`render_virtual_data_badge()`·`get_plotly_theme()`을 새로 만들지 않고 그대로 재사용했다. 사이드바는 Page 1과 동일한 기간 필터 + 단일 아티스트 라디오 선택. 4개 섹션: (1) 일별 게시글/메시지/라이브 건수(배경 막대) + 주별 WAU(선) 이중축 시계열, 소통 활동일수·최대 연속 공백일 KPI, (2) 소통 공백 4구간별 14일 이탈위험률·30일 휴면율(단일 팔로우 팬 기준, `docs/analysis_report.md` 발견 1의 다중 팔로우 최솟값 로직은 이 페이지 범위 밖이라 주석으로 명시하고 생략) + 현재 스냅샷 KPI 3종, (3) 소통 빈도-WAU 동시·1주 시차 Spearman 상관(Fisher z 95% CI 포함, 완전한 주만 사용, n<8이면 계산 생략)과 누적 가입자 수 통제 편상관계수를 그라데이션 강조 카드로 비교 — 원본·편상관 부호가 다르면 "부호가 반전되었습니다" 문구를, 같으면 "방향이 유지되었습니다" 문구를 조건문으로 자동 생성, (4) 인과관계 해석 주의문(PRD 13.4·14.6절 톤).
  - **검증**: `data.py`의 신규 상관계수 함수들을 3개 아티스트 전체에 대해 직접 실행해 `notebooks/02_communication_retention.ipynb`의 기존 수치(예: artist_001 동시상관 `r=-0.449`→편상관 `r_partial=+0.580`, artist_002 `r=0.429`→`0.670`)와 정확히 일치함을 확인. `AppTest`로 3개 아티스트 × 2개 기간(전체 90일, 짧은 기간) = 6개 조합 전부 헤드리스 검증(예외 없음), artist_001에서 "부호가 반전되었습니다" 문구가, artist_002에서 "방향이 유지되었습니다" 문구가 실제로 렌더링됨을 확인. 개발 중 `get_plotly_theme()`가 이미 `title` 키를 갖고 있어 `fig.update_layout(**get_plotly_theme(), title=...)`처럼 별도로 `title=`을 더 넘기면 `TypeError`(중복 키워드 인자)가 나는 버그와, `title=`에 문자열만 넘기면 테마가 설정한 `title.font`가 통째로 사라지는(문자열 shorthand가 전체 Title 객체를 새로 만듦) 문제를 함께 발견해 `theme_dict["title"]["text"] = ...` 방식으로 병합하도록 고쳤다.
  - **새로 판단한 부분(문서화)**: 재활성률을 "was_reactivated_today=true인 (팬,날짜) 행의 비율"이라는 날짜 단위 간이 지표로 계산했다(PRD 8.2절 공식 정의는 "분석 시작 시점 휴면 팬 중 재활성한 팬 비율"이라는 팬 단위 코호트 지표라 분모가 다르다 — 캡션에 명시).
- [x] **Page 2 섹션 1 차트를 누적 막대에서 게시글/메시지/라이브 개별 선(line) 3개로 교체**. 이전에 누적 막대(barmode="stack") opacity·테두리를 조정해 가독성을 개선했었지만(직전 항목), 그래도 "겹친 날 값이 합쳐져서 보인다"는 근본적인 한계는 남아 있었다(예: post=4·message=4인 날은 막대 총높이가 8로 보여 각 채널의 정확한 건수를 바로 읽을 수 없었음). 막대 대신 채널별 독립된 선 3개(y축 값 자체가 서로 겹치지 않고 각자의 정확한 일별 건수)로 바꿔 이 한계를 근본적으로 해결했다. WAU는 그대로 보조축의 signal_cyan 굵은 선으로 유지, `connectgaps=True`로 0건인 날도 선이 끊기지 않게 했다(실제 데이터에는 NaN이 없어 원래도 끊기지 않았지만 방어적으로 명시). 차트 아래에 `st.expander("일별 소통 상세 보기")`로 날짜별 게시글·메시지·라이브·합계·그 주 WAU 표를 추가해, 선 그래프에서 읽기 어려운 정확한 수치는 표로 확인할 수 있게 했다.
  - **검증**: kaleido로 실제 렌더링해 artist_001의 1/18(게시글1·메시지1·라이브1)·1/19(게시글4·메시지4)가 각 채널 값 그대로 표시됨을 확인(막대였을 때와 달리 값이 합산되지 않음). `AppTest`로 3개 아티스트 + 짧은 기간 조합 재검증(예외 없음), expander·상세 표 렌더링 확인.
- [x] **Page 2 섹션 1 차트를 겹친 선 3개에서 4행 1열 서브플롯으로 다시 교체**. 막대 → 개별 선(직전 항목)으로 값 합산 문제는 해결됐지만, 게시글·메시지·라이브 3개 선을 한 차트에 겹쳐 그리다 보니 이번엔 선끼리 교차·중첩되어 눈으로 추적하기 어려운 새 가독성 문제가 생겼다. `make_subplots(rows=4, cols=1, shared_xaxes=True)`로 게시글/메시지/라이브/WAU를 세로로 완전히 분리했다. x축(날짜)은 공유하고 맨 아래 행에만 표시. 게시글·메시지·라이브 3개 행은 y축 범위를 세 채널 전체 최댓값 기준으로 통일해(`channel_max * 1.15`) 채널 간 규모를 왜곡 없이 비교할 수 있게 했고, WAU 행은 스케일이 달라 별도로 뒀다. 각 행의 y축 제목을 채널명으로 달아 범례를 대신하게 하고(`showlegend=False`), `vertical_spacing=0.035`·`height=560`으로 4개를 합쳐도 과하게 길어지지 않게 압축했다. `get_plotly_theme()`는 배경·격자·폰트·여백만 골라 적용했다 — subplot 구조에서는 `xaxis`/`yaxis` 딕셔너리를 통째로 `update_layout(**theme)`에 넘기면 첫 번째 축(xaxis/yaxis)에만 적용되고 xaxis2~4/yaxis2~4에는 반영되지 않아서, 격자색 등은 `fig.update_xaxes(...)`/`update_yaxes(...)`를 행 지정 없이 호출해 전체 축에 일괄 적용하는 방식으로 바꿨다.
  - **검증**: 페이지 코드 블록을 그대로 추출해 kaleido로 렌더링(코드 복사로 인한 오차 방지). artist_001 전체 90일과 1/15~1/22 확대 뷰 모두에서 4개 행이 서로 겹치거나 잘리지 않고 뚜렷이 분리됐고, 1/18·1/19가 각자의 행에서 정확한 값으로 바로 읽힘을 확인. 처음 확대 뷰 테스트에서 WAU만 축소하지 않은 전체 기간 데이터를 그대로 써서 x축이 전체 90일로 되돌아가는 실수를 발견 — 실제 페이지는 두 데이터 함수(`get_communication_timeline`/`get_retention_timeline`)에 항상 같은 기간을 넘기므로 실제 버그는 아니었고, 테스트 스크립트만 수정해 재확인했다. `AppTest`로 3개 아티스트 + 짧은 기간 조합 재검증(예외 없음), expander·상세 표 그대로 유지 확인.
- [x] **Page 2 섹션 1 차트의 게시글/메시지/라이브(row 1~3) 집계 단위를 일별에서 주별로 변경, WAU(row 4)와 시간 단위 통일**. 일별 값은 요일 편차로 들쭉날쭉해 추세보다 노이즈가 두드러졌고, 무엇보다 3개 채널만 일별·WAU만 주별이라 한 차트 안에서 시간 단위가 뒤섞여 있었다. `dashboard/data.py`에 `_week_start()` 헬퍼(KST 월~일, 월요일 시작 — PRD 8.2절 WAU 정의와 동일 공식: `date - timedelta(weekday())`)를 새로 추출하고, 기존 `_weekly_communication_wau_panel`(섹션 3 상관계수 계산의 기반)의 중복 계산식을 이 헬퍼 호출로 교체했다. 같은 헬퍼로 새 함수 `get_communication_timeline_weekly()`를 추가해(`get_communication_timeline()`의 일별 결과를 재사용해 그룹핑만 다시 하는 방식, 별도 SQL 중복 없음) 게시글/메시지/라이브 주별 합계와 `is_partial_week`(그 주 관측일수<7) 플래그를 계산한다. 이 헬퍼 하나로 시계열 차트와 섹션 3 상관계수가 같은 주 경계를 공유하도록 만들어, 두 지표가 서로 다른 주 정의를 쓰는 모순을 구조적으로 차단했다. 차트는 y축 범위 통일(`channel_max*1.15`) 기준도 주별 합계 최댓값으로 재계산했고, 경계에 걸려 7일을 못 채운 부분 주(이 데이터에서는 선택 기간 첫 주·마지막 주 모두 해당)는 마커만 속이 빈 다이아몬드(`diamond-open`)로 바꿔 구분했다(값 자체는 왜곡하지 않음, 부분 주가 있으면 캡션으로 별도 안내). "일별 소통 상세 보기" expander·표는 이번 변경과 무관하게 그대로 일별을 유지했고, 차트 위에 "차트=주별(부드럽게)·표=일별(정확하게)" 역할 분담을 캡션으로 짧게 명시했다.
  - **검증**: 스크립트로 `get_communication_timeline_weekly()`와 `_weekly_communication_wau_panel()`의 `week_start` 집합을 3개 아티스트 모두에서 직접 비교 — artist_001 기준 양쪽 다 14주, `symmetric_difference` 빈 집합으로 완전히 동일함을 확인(교차 확인 요구사항 충족). `get_communication_wau_correlation`의 동시 상관 n=12(부분 주 2개를 제외한 완전한 주 개수)로 14주 중 부분 주 2개라는 계산과도 정합. 페이지 코드 블록을 그대로 추출해 kaleido로 3개 아티스트 전부 렌더링 — 90일이 14개의 부드러운 주간 점으로 표시되고, 첫 주·마지막 주만 빈 다이아몬드 마커로 표시됨을 확인. `AppTest`로 3개 아티스트 × (전체 기간/짧은 기간) 6개 조합 재검증(예외 없음, expander·상세 표 존재 확인).
- [x] **Page 2 섹션 1 차트 1~3행(게시글/메시지/라이브)을 선 그래프에서 막대 그래프로 교체, 차트 전체 크기 확대**. 주별 집계(직전 항목)로 바꾼 뒤에도 "그 주의 합계"라는 의미는 막대(면적)가 선보다 더 직관적으로 전달된다고 판단해 `go.Scatter` 대신 `go.Bar`로 바꿨다(채널 고유색 brand_violet/brand_pink/#F59E0B는 그대로). 부분 주(첫 주·마지막 주) 표시 방식도 막대에 맞게 바꿔, 마커 대신 그 막대만 `opacity`를 0.85→0.45로 낮춰 "7일을 다 채우지 못한 주"임을 구분했다(값 자체는 왜곡하지 않음, 캡션도 "속이 빈 마커" 대신 "옅은 막대" 표현으로 수정). WAU(4행)는 막대로 바꾸면 절대적 스케일이 채널과 달라 오히려 비교가 어려워지므로 기존 굵은 선(signal_cyan)을 그대로 유지했다. 전체적으로 4개 패널이 답답해 보인다는 피드백에 따라 `height`를 560→820, `vertical_spacing`을 0.035→0.055로 늘려 패널 사이 여백을 넓혔고, 커진 차트 크기에 맞춰 y축 제목(행 라벨) 폰트를 11→14, y축·x축 눈금 폰트를 명시적으로 13으로 키워 전체 균형을 맞췄다.
  - **검증**: 페이지 코드 블록을 그대로 추출해 kaleido로 3개 아티스트 전부 렌더링 — 1~3행이 막대로, 4행은 선으로 표시됨을 확인(`fig.data`의 trace type이 `['bar','bar','bar','scatter']`임을 직접 확인). artist_001·artist_002 모두 첫 주(그리고 값이 있는 경우 마지막 주) 막대가 다른 주보다 눈에 띄게 옅게(투명하게) 표시되어 부분 주 구분이 잘 보임을 확인. `height=820`으로 렌더링된 이미지에서 4개 패널이 이전보다 여유 있게 분리됨을 확인. `AppTest`로 3개 아티스트 × (전체 기간/짧은 기간) 6개 조합 재검증(예외 없음, expander·상세 표 존재 확인). `streamlit run dashboard/app.py` 재기동 후 `_stcore/health` OK 확인.
- [x] **Page 2 섹션 1 차트를 4행 세로 서브플롯(게시글/메시지/라이브/WAU 완전 분리)에서 2행으로 축소, 채널 3개는 `barmode="group"` 그룹 막대로 재통합**. 4행 분리(직전 항목)는 채널끼리 겹치지 않는 대신, 같은 주에 어느 채널이 더 활발했는지 눈으로 바로 비교하기 어렵다는 한계가 있었다. 1행에 게시글·메시지·라이브 3개를 `barmode="group"`으로 합쳐 같은 주 안에서 세 막대를 나란히 비교할 수 있게 하고, 채널 구분은 (행 제목 대신) 범례로 옮겼다. 막대를 슬림하고 촘촘하게 보이도록 `bargap=0.3`(주 그룹 사이 간격)·`bargroupgap=0.08`(그룹 내 막대 간격)로 조정했다. 부분 주 표시는 이전과 동일하게 그 주에 속한 막대들의 `opacity`를 0.45로 낮추는 방식을 그대로 유지했다(막대 형태만 겹친 그룹 막대에 맞게 자연스럽게 이어짐). 2행은 WAU 선(signal_cyan, 굵게) 그대로. 패널이 2개로 줄어든 만큼 `height`를 820→620으로 줄이되, 그룹 막대가 있는 1행이 상대적으로 더 크게 보이도록 `row_heights=[0.6, 0.4]`로 배분했고, `vertical_spacing`은 0.055→0.1로 늘려 두 패널 사이 여백을 확보했다. 범례를 켜면서 기본 위치가 왼쪽 상단 제목과 겹치는 문제가 있어 우측 상단(`xanchor="right", x=1`)으로 옮기고 상단 여백(`margin.t` 40→70)도 늘려 제목·범례가 겹치지 않게 했다.
  - **검증**: 페이지 코드 블록을 그대로 추출해 kaleido로 3개 아티스트 전부 렌더링 — `fig.layout.barmode == "group"`, `bargap`/`bargroupgap` 값, trace 구성(`['bar','bar','bar','scatter']`)을 직접 확인. 렌더링된 이미지에서 매주 3개 막대가 서로 겹치지 않고 나란히 슬림하게 서 있음을 확인, 제목과 범례가 겹치지 않음을 확인(첫 시도에서는 겹쳐서 범례를 우측 상단으로 재조정 후 재확인). artist_001·artist_002 모두 첫 주·마지막 주 그룹의 막대들이 옅게 표시되어 부분 주 구분이 유지됨을 확인. `AppTest`로 3개 아티스트 × (전체 기간/짧은 기간) 6개 조합 재검증(예외 없음, expander·상세 표 존재 확인). `streamlit run dashboard/app.py` 재기동 후 `_stcore/health` OK 확인.
- [x] **Page 2 섹션 1의 막대·WAU 두 패널에 `hovermode="x unified"` + 스파이크 라인 적용**. 마우스를 올린 주의 게시글/메시지/라이브/WAU 값을 한 툴팁에 모아 보여주고 두 패널에 동시에 세로 기준선이 뜨게 하기 위해 `showspikes=True, spikemode="across", spikesnap="cursor"`를 추가했다. `make_subplots(shared_xaxes=True)`만으로는 아래 패널의 x축 눈금 표시만 감출 뿐 두 x축이 실제로 연결(matches)되지는 않아 — 직접 `fig.layout.xaxis2.matches`를 확인해 `None`임을 발견 — unified 툴팁과 스파이크 라인이 패널을 넘나들지 않는 문제가 있었다. `fig1.update_xaxes(matches="x", row=2, col=1)`로 2행 x축을 1행과 명시적으로 동일시해 해결했다(재확인 결과 `matches == "x"`).
- [x] **Page 3 데이터 함수 4개 추가 완료, 화면 구현은 다음 세션 예정**. `dashboard/data.py`에 `get_commerce_funnel_summary`(mart_commerce_funnel 기준 열린 퍼널 단계별 인원·전환율, artist_id로 필터), `get_segment_conversion`(PRD 11.1절 세그먼트별 구매 전환율, `core_definition="with_purchase"`(공식)/`"subscription_only"`(03_commerce_funnel.ipynb 11.12절 반사실 재정의) 두 가지 지원, 새 헬퍼 `_classify_segment_variant`로 기존 `_classify_segment`와 로직 공유), `get_revenue_summary`(fact_order/fact_order_item 기준, 마트 미사용 — 5.13절 원칙 — artist_ids 필터 시 상품 단위로 매출을 귀속하고 환불액은 아티스트별 상품 매출 비중으로 비례 배분해 묶음 주문 11건의 교차귀속을 방지), `get_purchase_timing`(mart_commerce_funnel의 `days_to_purchase` 원시 분포, 구간화는 화면 구현 때 결정)을 추가했다.
  - **검증**: 4개 함수를 실제 DB에 직접 실행해 결과 확인. `get_commerce_funnel_summary`(전체)는 4817→1756(36.5%)→1000(56.9%)→791(79.1%)로 노트북·마트 값과 정확히 일치. `get_segment_conversion`은 두 `core_definition` 모두에서 노트북 표와 일치 — 참여 27.4%(n=391, with_purchase) → 40.6%(n=478, subscription_only), 코어 57.1%(n=394) → 45.0%(n=307), 조회중심 35.8%(n=875)는 두 정의에서 동일. `get_revenue_summary`(전체)는 총매출 59,275,000원·환불률 6.6%로 노트북과 정확히 일치. 아티스트별로 나눠 합산한 결과 매출 합계 59,275,000원, 환불액 합계 3,583,604원으로 전체 합계와 정확히 재구성됨을 확인(상품 단위 귀속·비례 배분 로직이 이중계산·누락 없이 정확함을 검증). `get_purchase_timing`은 791행으로 `get_commerce_funnel_summary`의 구매 완료 수(791)와 일치.

**다음 작업: Page 3(팬 행동·커머스 퍼널) 화면 구현(데이터 함수는 이미 완료), `docs/analysis_report.md` 초안 사용자 검토 및 확정**

---

## 11. 검토 필요 항목 (REVIEW NEEDED)

> 이 섹션은 2026-09-26 밤샘 자동 진행 세션(노트북 1~3 작성)에서 발생한, "여러 해석이 가능하거나 애매한 판단 지점"을 빠짐없이 기록한 것이다. 각 항목은 통계적으로든 정의상으로든 확정된 정답이 아니라 이번 세션에서 **가장 보수적이고 절제된 해석을 기본값으로 선택**한 것이며, 다음에 사용자가 검토 후 다른 선택으로 바꿀 수 있다.

### 11.1 상관계수 강도 해석 기준 (`02_communication_retention.ipynb`)

- **판단**: `|r|<0.3` 약함, `0.3~0.5` 중간, `>0.5` 강함이라는, 사회과학 연구에서 흔히 쓰이는 경험적 기준(Cohen 1988 계열)을 채택해 사용했다.
- **왜 애매한가**: 이 기준은 여러 통용되는 기준 중 하나일 뿐이고, 분야·표본 크기·측정 방식에 따라 다른 임계값을 쓰는 경우도 많다. 특히 이번처럼 표본이 매우 작을 때(n=11~13)는 "강함"으로 분류된 상관도 신뢰구간이 넓어 실제로는 불확실성이 크다.
- **대안**: 임계값을 명시하지 않고 r값과 p값만 제시하거나, 신뢰구간을 함께 계산해서 보여주는 방법도 있다.
- **[해결됨: 임계값 기준은 그대로 두되(여전히 논쟁적일 수 있음은 유지), 모든 상관계수 결과표(동시·1주 시차·편상관)에 Fisher z 변환 기반 95% 신뢰구간(`ci_low`/`ci_high`)을 추가했다. `n<15`면 "표본이 작아 신뢰구간이 넓음" 주석을 자동으로 붙인다. 실제로 아티스트별 상관(n=11~12)은 신뢰구간이 0을 가로지르는 경우가 대부분(예: artist_001 WAU `r=-0.449`, CI `[-0.813, 0.168]`)이라 애초 텍스트로 설명했던 "통계적으로 유의하지 않음"이 신뢰구간으로도 시각적으로 뒷받침됨을 확인했다]**

### 11.2 아티스트별 주간 "참여율(engagement_rate)" 정의 (`02_communication_retention.ipynb`)

- **판단**: 그 아티스트에 귀속되는 핵심 활동 12종 중 "참여 행동" 4종(좋아요·댓글·메시지열람·라이브참여)을 수행한 고유 팬 수 ÷ 그 아티스트의 주간 WAU로 정의했다.
- **왜 애매한가**: PRD·이벤트 추적 계획서 어디에도 "아티스트별 주간 참여율"의 공식 정의가 없다. PRD 8.2절의 "콘텐츠 참여율"(콘텐츠 단위)을 아티스트·주 단위로 유추 확장한 것이라 공식 지표와 이름은 같지만 계산 대상이 다르다.
- **대안**: 참여 유형을 3종(좋아요·댓글·라이브, 메시지 열람 제외)으로 좁히거나, 분모를 WAU가 아니라 "노출된 팬 수(exposed_fans)"로 바꾸는 방법도 가능하다.
- **[해결됨: 계산 방식·변수명(`engagement_rate`)은 그대로 두고, 이 지표를 설명하는 모든 마크다운 텍스트(가설 서술, 데이터 준비, 결과 요약, 종합 결론)에 "주간 아티스트 참여율(확장 지표, PRD 8.2절 콘텐츠 참여율과는 다른 지표)"라는 명칭을 명확히 병기해 혼동 가능성을 줄였다. print문·차트 제목에는 이 지표를 직접 노출하는 곳이 없어 추가 수정 대상이 없었다]**

### 11.3 H-01 pooled(전체) 상관계수의 해석 우선순위 (`02_communication_retention.ipynb`)

- **판단**: 3개 아티스트를 합친 "전체(pooled)" 상관계수보다 아티스트별 개별 상관계수를 우선 근거로 삼았다(pooled는 참고용으로만 제시).
- **왜 애매한가**: pooled 상관은 표본이 커서(n=33~36) 통계적으로 유의하게 나오지만, 서로 다른 방향을 보이는 아티스트들을 합친 것이라 "아티스트 간 차이"와 "한 아티스트 내부의 주차별 변동"이 섞여 있다. 어느 쪽을 주된 근거로 볼지는 분석 목적에 따라 달라질 수 있는 방법론적 선택이다.
- **[유지: 이번 세션에서 사용자가 수정을 요청하지 않았고, 개별 아티스트 결과를 우선 근거로 삼는 방침 자체가 11.3의 "왜 애매한가"에서 지적한 문제(pooled가 between-artist·within-artist 변동을 섞음)를 피하는 더 보수적인 선택이라 그대로 유지한다]**

### 11.4 H-01 phase_type(활동 단계)별 상관계수 분석 생략 (`02_communication_retention.ipynb`)

- **판단**: PRD 14.4절이 요구하는 "일상·컴백·공연·비활동기별 결과 비교"를 상관계수 형태로는 계산하지 않고, 이미 마트 검증 때 확인한 "구간별 소통일 비율 비교"(`docs/decisions_log.md` 9절, comeback_active+tour 81.2% vs daily+inactive 58.6%)로 대체했다.
- **왜 애매한가**: 각 활동 단계가 아티스트당 최대 6주 정도(예: comeback_active)뿐이라 단계별로 쪼개면 상관계수 표본이 n<10, 심하면 n<5까지 줄어 통계적으로 사실상 무의미하다고 판단했다. 이는 "생략"이라는 판단 자체가 맞는지 다시 검토할 여지가 있다.
- **[해결됨: 상관계수 대신 일 단위 `active_followers`로 활동기(comeback_active+tour) vs 비활동기(daily+inactive) Mann-Whitney U 검정을 추가했다(표본은 아티스트당 최대 81일까지 확보). 결과는 3개 아티스트 모두 `p>0.05`로 유의한 차이를 확인하지 못했고, 2개 아티스트는 오히려 반대 방향(비활동기가 더 높음)이었다. 원인을 조사한 결과 `phase_type`이 90일 안에서 겹치지 않는 시간순 구간으로 배정돼 있어 이 비교가 시간 추세(팬 유입에 따른 우상향)와 얽혀 있음을 확인했다 — 상세 내용과 새로 발견된 한계는 "12. 추가 검토 필요 항목" 12.1 참고. 결과가 가설과 다르게 나왔지만 있는 그대로 기록했고, 대신 9절의 "구간별 소통일 비율" 비교가 이 교란에서 더 자유로운 근거로 남는다]**

### 11.5 H-02 분석 대상을 "단일 아티스트 팔로우 팬"으로 제한 (`02_communication_retention.ipynb`)

- **판단**: 여러 아티스트를 동시에 팔로우 중인 (팬,날짜) 조합(전체의 약 33%)을 제외하고, 정확히 한 아티스트만 팔로우 중인 조합(약 67%)만으로 소통 공백-이탈 관계를 분석했다.
- **왜 애매한가**: 복수 팔로우 팬의 "그날의 소통 공백"을 어느 아티스트 기준으로 볼지(최솟값/최댓값/평균) 규칙이 PRD·이벤트 추적 계획서 어디에도 없다. 이 제한 때문에 전체 팬의 1/3에 대한 결과가 이 분석에 반영되지 않았다.
- **대안**: 팔로우 중인 아티스트들의 공백일 중 최솟값(가장 최근 소통) 또는 평균을 사용해 전체 팬을 포함하는 방법도 있다.
- **[해결됨: 이미 이전 세션(커밋 `8c3c9dc`)에서 팔로우 중인 아티스트들의 공백일 중 최솟값을 쓰는 방식으로 전체 팬(100%)을 포함해 재분석을 완료했다. 결과는 단일 팔로우 버전과 사실상 동일한 패턴(공백이 길수록 이탈위험률·휴면율 단조 증가)이었고, 오히려 다중 팔로우 팬을 포함하면 비율이 낮아지는(다중 팔로우의 "보호 효과") 추가 근거까지 확인해 이 "전체 팬(100%)" 버전을 H-02의 주 결과로 삼았다. 이번 세션에서는 재작업하지 않음(사용자 지시)]**

### 11.6 null_effect 비교 데이터 재생성 필요 (`02_communication_retention.ipynb`)

- **상태**: `data/raw/fact_user_event_null_effect.csv` 파일은 존재하지만, 400명 규모(현재 baseline은 1,750명)·`fact_user_event` 생성 2/4 단계까지만(콘텐츠·커머스 이벤트 없음) 담고 있어 현재 baseline과 나란히 비교할 수 없다. 사용자 지시에 따라 임의로 재생성하지 않고 비교를 생략했다.
- **다음 필요 작업**: `config/sensitivity_scenario.yaml`의 `null_effect` 시나리오로 1,750명 규모·`fact_user_event` 4/4 단계 전체를 다시 생성해서 별도 CSV로 저장해야, PRD 13.4절이 요구하는 "심어둔 패턴을 다시 발견하고 인사이트인 척하지 않는지" 검증을 baseline과 동일 조건에서 할 수 있다.
- **[해결됨: 1,750명·4/4단계 전체로 재생성 완료(128,667행/1,750명), baseline 대비 재검증까지 마침(활동기-비활동기 노출률 차이 baseline +0.0276 vs null_effect +0.0022로 거의 소멸 확인). 이후 파일명을 `fact_user_event_null_effect_full.csv`로 정정(같은 파일명을 덮어써 규모·단계가 바뀐 사실이 파일명에 드러나지 않는 문제를 해결)하고 `02_communication_retention.ipynb`의 참조 경로도 갱신, 재실행해서 동일 결과 재확인함]**

### 11.7 artist_001의 H-01 음의 상관에 대한 사후적 설명 (`02_communication_retention.ipynb`)

- **판단**: artist_001만 소통 활동일수와 WAU가 음의 상관(`r=-0.449`)을 보인 이유로 "분석 기간 동안 신규 가입자가 계속 유입되어 WAU 자체에 우상향하는 시간 추세가 섞여 있을 수 있다"는 설명을 제시했다.
- **왜 애매한가**: 이 설명은 차트를 보고 사후적으로 추정한 것이며, 실제로 신규 가입자 유입 효과를 통제한 재계산은 하지 않았다. 확정된 원인이 아니라 가능한 가설 중 하나로만 다뤄야 한다.
- **[해결됨: 이미 이전 세션(커밋 `c7ccf10`)에서 그 주 시점 누적 가입자 수를 통제 변수로 넣은 편상관계수로 실제 검증을 마쳤다. `artist_001`의 WAU 상관이 `r=-0.449`(원래)→`r_partial=+0.580`(통제 후)으로 부호가 뒤집혀 가설이 지지됨을 확인했다(`artist_002`도 `r=0.429`→`r_partial=0.670`, `p=0.024`로 유의하게 강화). 이번 세션에서는 재작업하지 않음(사용자 지시)]**

### 11.8 "코어 팬" 판정의 구독/구매 이력 범위를 30일로 제한 (`03_commerce_funnel.ipynb`)

- **판단**: PRD 11.1절 "코어 팬 = 참여 팬 기준 + 메시지 구독 또는 상품 구매 **이력**"의 "이력"을, 다른 세그먼트 조건과 일관되게 최근 30일 윈도우(2026-03-02~03-31)로 제한해서 계산했다.
- **왜 애매한가**: "이력"이라는 단어는 생애 전체(over 전체 기간 한 번이라도 구독·구매)를 뜻할 수도 있다. PRD 11.1절 서두의 "최근 30일 행동을 기준으로"라는 문구를 근거로 30일로 좁혔지만, 이 해석이 PRD 작성자의 의도와 정확히 같다고 확신할 수 없다.
- **대안**: 생애 전체 구독/구매 이력 기준으로 다시 계산하면 "코어" 팬 수가 늘어날 것으로 예상된다.
- **[해결됨: 공식 기준(최근 30일)은 그대로 유지하고, 생애 전체 이력 기준으로 다시 계산한 코어 팬 수를 참고용 비교표로 추가했다. 최근 30일 394명(22.5%) → 생애 전체 788명(45.0%)로 정확히 2배 늘어 예상 방향을 확인했다. 증가폭이 예상보다 커서, 생애 전체 기준으로 바꾸면 "지금 활발한 핵심 팬"이 아니라 "한 번이라도 지갑을 연 적 있는 팬"으로 코어의 성격 자체가 넓어진다는 점도 함께 기록했다. 어느 정의를 실제로 채택할지는 사용자 확인 필요]**

### 11.9 PRD에 없는 "미분류(최근 30일 무활동)" 세그먼트 추가 (`03_commerce_funnel.ipynb`)

- **판단**: 신규가 아니면서 최근 30일 동안 조회·참여 활동이 전혀 없는 팬(10명)을 PRD 11.1절의 4개 세그먼트 중 어디에도 넣지 않고 별도 "미분류" 범주로 뒀다.
- **왜 애매한가**: PRD는 이 잔여 집단을 명시적으로 다루지 않는다. "조회중심"에 강제로 편입시키거나 "휴면에 가까운 팬"이라는 별도 이름을 붙이는 등 다른 처리도 가능하다.
- **[유지: 이번 세션에서 사용자가 수정을 요청하지 않았다. "미분류"라는 이름 자체가 이미 이 집단이 PRD 4개 세그먼트 밖의 잔여 범주임을 드러내고, 표에서도 별도 행으로 분리해 다른 세그먼트와 섞이지 않게 하고 있어 현재 처리를 그대로 유지한다]**

### 11.10 "재방문율"의 독자적 운영 정의 (`03_commerce_funnel.ipynb`)

- **판단**: 세그먼트별 비교표의 "재방문율"을 "분석 마지막 7일(2026-03-25~03-31) 중 핵심 활동이 있었던 날이 2일 이상인 팬의 비율"로 정의했다.
- **왜 애매한가**: PRD 8.2절의 공식 "W1 참여 재방문율"은 "기준 참여 후 1~7일 이내 다시 핵심 활동을 수행한 팬 비율"이라는 코호트·트리거 기반 정의로, 이번에 쓴 "특정 7일 구간의 스냅샷 비교"와 다르다. 세그먼트 비교를 위해 편의상 간이 정의를 새로 만든 것이며, PRD의 공식 W1 지표와 이름만 유사하고 계산 방식은 다르다는 점에 유의해야 한다.
- **[해결됨: 이 지표의 이름을 "재방문율" 대신 "최근 7일 활성일수 비율(비공식 스냅샷 지표)"로 바꾸고, PRD 8.2절 공식 W1 정의(분석 기간 전체에서 핵심 활동일마다 그 후 1~7일 이내 재활동 여부를 날짜 단위로 집계)로 계산한 값을 별도 컬럼(`w1_official_return_rate_pct`)으로 나란히 추가했다. 두 지표는 세그먼트 순위가 다르게 나왔다 — 자세한 결과와 해석은 "12. 추가 검토 필요 항목" 12.2절 참고]**

### 11.11 H-03 세 방식의 "참여" 정의가 서로 다름 (`03_commerce_funnel.ipynb`)

- **판단**: 생성 시점 검증·SQL 재계산은 `content_like+comment_create` 총합의 중앙값 2분할을, 세그먼트 분석은 PRD 11.1절 규칙 기반 4단계 분류를 "참여"의 기준으로 썼다. 세 방식 모두 "고참여 집단이 저참여 집단보다 구매 전환율이 높다"는 같은 방향을 보였다는 것만 교차검증 결론으로 삼았고, 절대 수치가 다른 것은 정의 차이 때문이라고 설명했다.
- **왜 애매한가**: "세 방식이 같은 결론을 낸다"고 할 때, 엄밀히는 "같은 지표를 세 번 다르게 잰 것"이 아니라 "서로 다른 정의의 지표 세 개가 우연히 같은 방향을 가리킨 것"이다. 이것이 가설을 얼마나 강하게 뒷받침하는 증거인지에 대한 판단은 방법론적 관점에 따라 달라질 수 있다.
- **[해결됨: 노트북의 관련 서술(도입부, H-03 섹션 제목·도입, 결론 비교, 종합 결론)을 전부 "세 방식이 동일 지표를 검증했다"가 아니라 "정의가 서로 다른 지표 세 개가 같은 방향을 가리켰다"는 표현으로 명확히 고쳤다. 계산 결과나 수치는 바꾸지 않았다]**

### 11.12 "참여 < 조회중심" 역전을 정의상 순환성으로 설명한 것 (`03_commerce_funnel.ipynb`)

- **판단**: 4단계 세그먼트에서 "참여"(27.4%)가 "조회중심"(35.8%)보다 구매 전환율이 낮게 나온 것을, "코어" 판정 기준(최근 30일 구매 이력)이 참여 집단에서 구매 성향이 높은 사람을 먼저 빼가는 정의상 순환성 때문이라고 설명하고 실제 행동 차이로 해석하지 않았다.
- **왜 애매한가**: 이 설명은 논리적으로 그럴듯하지만, 실제로 "코어로 분류되지 않았다면 참여 집단의 전환율이 조회중심보다 높았을 것"이라는 반사실 계산까지 하지는 않았다. 즉 이 설명 자체도 확정된 검증을 거치지 않은 가설이다.
- **다음에 필요한 작업**: 코어 판정에서 "구매 이력" 조건을 빼고 "참여+구독만"으로 다시 정의해 참여 집단의 전환율이 실제로 올라가는지 확인하면 이 가설을 검증할 수 있다.
- **[해결됨: 반사실 재계산으로 가설 지지 확인. 코어 판정에서 구매 이력 조건을 빼고 "참여+구독만"으로 재정의하자 코어(394명)→참여 87명이 이동(전원 90일 기준 구매 이력 보유)했고, 재정의된 "참여" 세그먼트 구매 전환율이 27.4%→40.6%로 올라 조회중심(35.8%)을 웃돌아 역전이 사라졌다. "참여 팬이 실제로 구매를 덜 한다"가 아니라 세그먼트 정의의 순환성이 원인이었음이 데이터로 확인됨. `03_commerce_funnel.ipynb` "반사실(counterfactual) 재검증" 절 참고]**

### 11.13 온보딩 퍼널의 표본 범위 한계 (`03_commerce_funnel.ipynb`)

- **상태(애매함이라기보다 명확한 한계)**: 온보딩 퍼널은 `sign_up` 이벤트가 있는 신규 가입 팬(n=550, 전체의 약 31%)만 대상으로 하며, 기존 가입자(약 70%)는 분석에서 원천적으로 제외된다(`docs/decisions_log.md` 5.10절 결정에 따른 구조적 결과). 이 퍼널의 전환율을 "전체 팬 기준 온보딩 성과"로 일반화해서 읽지 않아야 한다.
- **[해결 불필요: 애매한 판단이 아니라 5.10절 결정에 따른 구조적·확정적 한계이며, 노트북에도 이미 이 한계가 명시돼 있다]**

### 11.14 개발 환경 관찰: scipy import가 간헐적으로 실패함 (참고용, 해석 판단 아님)

- Python 3.14 + scipy 1.18.1 조합에서, ipykernel 서브프로세스 최초 실행 시 `scipy.optimize`의 컴파일된 확장 모듈(`givens_elimination`) DLL 로드가 간헐적으로 실패하는 현상이 1회 관측됐다(같은 코드를 재실행하면 성공). PRD 21.1절이 이미 "Python 3.14에서 일부 패키지 설치 문제가 발생할 수 있음"을 위험으로 지목했는데, 그 사례로 기록해둔다. 노트북 실행이 원인 불명으로 실패하면 재실행부터 시도해볼 것.
- **[해결 불필요: 해석 판단이 아니라 개발 환경 참고용 관찰이며, 이번 세션에서도 동일 증상 없이 모든 노트북 재실행이 정상적으로 완료됐다]**

---

## 12. 추가 검토 필요 항목

> 이 섹션은 2026-09-26 REVIEW NEEDED 항목 해소 작업 세션에서 새로 발견된, 사전에 예상하지 못했던 애매한 판단 지점을 기록한다. 11절과 마찬가지로 확정된 정답이 아니라 이번 세션에서 선택한 해석이며, 다음에 사용자가 검토 후 다른 선택으로 바꿀 수 있다.

### 12.1 `phase_type`별 raw 활동 수준 비교는 시간 추세와 얽혀 있음 (`02_communication_retention.ipynb`)

- **발견 경위**: 11.4절 보완으로 활동기(comeback_active+tour) vs 비활동기(daily+inactive)의 일 단위 `active_followers`를 Mann-Whitney U 검정으로 비교했는데, 예상(활동기가 더 높음)과 달리 3개 아티스트 모두 `p>0.05`였고 2개 아티스트(`artist_001`, `artist_002`)는 오히려 비활동기가 더 높게 나왔다.
- **원인**: 각 아티스트의 `phase_type`은 90일 분석 기간 안에서 겹치지 않는 연속 구간으로만 한 번씩 배정된다(예: `artist_001`은 활동기가 1/10~2/1, 비활동기가 2/2~3/31로 시기 자체가 다르다). 분석 기간 내내 신규 가입자가 유입되어 팬 규모가 우상향하는 시간 추세(H-01 편상관에서 이미 확인한 교란과 동일)가 있으므로, "활동기 vs 비활동기"를 raw 수준(개수)으로 비교하면 실제로는 "이 시기가 분석 초반이냐 후반이냐"를 비교하는 셈이 되어 방향이 뒤집힐 수 있다.
- **왜 애매한가**: 이 문제는 이 데이터셋의 `phase_type` 배정 방식(아티스트당 각 단계가 정확히 한 번, 겹치지 않게 시간순으로만 나타남) 자체에서 비롯된 구조적 한계로 보인다. 시간 추세를 통제한 재비교(예: 각 구간 내에서 날짜를 표준화하거나, H-01처럼 편상관/회귀로 시간 변수를 통제)를 하면 결과가 달라질 수 있으나, 이번 세션에서는 추가 통제 계산까지는 하지 않았다.
- **현재 처리**: raw 수준 비교(Mann-Whitney U) 결과는 있는 그대로 노트북에 기록하되, "활동기와 비활동기의 팬 활동에 차이가 없다"는 결론으로 사용하지 않고, 대신 시간 추세 교란에서 상대적으로 자유로운 9절의 "구간별 소통일 비율"(81.2% vs 58.6%)을 phase_type 비교의 근거로 계속 사용한다.
- **다음에 필요한 작업**: 각 구간 내 날짜를 "그 구간 시작 후 경과일" 등으로 표준화하거나, 회귀/편상관으로 절대 시점(누적 가입자 수 등)을 통제한 뒤 다시 비교하면 이 교란을 제거한 phase_type 효과를 볼 수 있다.

### 12.2 "최근 7일 활성일수 비율"과 "PRD 공식 W1 재방문율"의 세그먼트 순위가 서로 다름 (`03_commerce_funnel.ipynb`)

- **발견 경위**: 11.10절 보완으로 PRD 8.2절 공식 W1 재방문율(기준 참여 후 1~7일 이내 재활동 비율, 분석 기간 전체의 핵심 활동일마다 날짜 단위로 집계)을 실제로 계산해서 기존 "최근 7일 활성일수 비율"과 나란히 비교했는데, 두 지표의 세그먼트 순위가 다르게 나왔다.
  - **최근 7일 활성일수 비율**: 조회중심(42.2%) < 참여(51.2%) < 코어(60.9%) — "더 참여도가 높은 세그먼트일수록 최근에도 활발하다"는 직관과 일치하는 순서.
  - **PRD 공식 W1 재방문율**: 신규(90.8%)가 가장 높고, 조회중심(81.1%)·참여(86.1%)·코어(89.2%)는 서로 큰 차이가 없다(전부 80%대 후반~90%대).
- **왜 애매한가**: 두 지표가 "다른 것을 재는 서로 다른 지표"이므로 순위가 다른 것 자체는 이상하지 않지만(코호트·트리거 기반 vs 특정 스냅샷 구간 비교), **신규 세그먼트의 W1 재방문율이 유독 높게 나온 이유**는 사후적으로 추정한 가설일 뿐 검증하지 않았다 — 신규 팬은 정의상 가입 후 14일 이내라 관측 가능한 기준 참여일 자체가 얼마 없고(이 세그먼트 전체 `w1_eligible_days`=65), 가입 직후의 "허니문 기간" 활동 패턴이 압축적으로 몰려 있어 재방문 성공률이 높게 잡혔을 가능성이 있다. 또한 공식 W1 지표는 세그먼트 간 차이를 잘 드러내지 못하는 것처럼 보이는데, 이것이 "세그먼트 간 실제 재방문 행태 차이가 크지 않다"는 뜻인지 "지표 설계(개별 날짜 단위 집계라 세그먼트 특성이 희석됨)의 한계"인지 구분하지 않았다.
- **현재 처리**: 두 지표를 있는 그대로 나란히 제시하고, 어느 쪽이 "더 맞는 지표"라고 판단하지 않았다. 세그먼트 비교 목적에는 기존 "최근 7일 활성일수 비율"을 계속 주 지표로 쓴다.
- **다음에 필요한 작업**: 신규 세그먼트만 따로 떼어 `w1_eligible_days`가 특정 구간(가입 직후)에 쏠려 있는지 확인하거나, 세그먼트별로 `w1_eligible_days` 대비 `n`(팬당 평균 기준 참여일 수)을 비교해 표본 편향 여부를 확인하면 이 차이의 원인을 더 명확히 할 수 있다.