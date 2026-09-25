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

**다음 작업: SQL 분석 마트 4개 작성 (mart_artist_daily, mart_user_daily, mart_content_performance, mart_commerce_funnel)**