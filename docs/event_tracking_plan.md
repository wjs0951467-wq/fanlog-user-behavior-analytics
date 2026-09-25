# FANLOG 이벤트 추적 계획서

> FANLOG 사용자 행동 분석에 필요한 아티스트 활동과 팬 행동 이벤트의 발생 조건, 공통 필드 및 데이터 품질 기준을 정의한다.

---

## 0. 문서 정보

| 항목 | 내용 |
| --- | --- |
| 프로젝트명 | FANLOG 사용자 행동 분석 대시보드 |
| 문서명 | 이벤트 추적 계획서 |
| 문서 버전 | v1.2 |
| 문서 상태 | 작성 중 |
| 상위 기준 문서 | `docs/PRD.md` v1.1 |
| 데이터 유형 | 실제 사용자가 아닌 가상 사용자 행동 데이터 |
| 분석 기간 | 연속된 90일 |
| 기준 시간대 | 저장 UTC, 분석·표시 KST |
| 데이터 모델 | 아티스트 활동과 팬 행동을 별도 팩트 테이블로 관리 |

## 문서 변경 이력

| 버전 | 변경 내용 |
| --- | --- |
| v1.0 | 아티스트 활동·팬 행동 분리 모델과 PRD 우선 원칙을 반영한 최초 작성 |
| v1.1 | 게시글·콘텐츠 구분 기준, 커머스 이벤트 순서 규칙과 열린 퍼널의 관계, 핵심 활동 목록의 PRD 반영 필요성, 콘텐츠-아티스트 연결 기준을 보완 |

---

## 1. 문서 목적

본 문서는 가상의 팬덤 플랫폼 `FANLOG`에서 발생하는 아티스트 활동과 팬 행동을 일관된 형태로 기록하기 위한 추적 기준을 정의한다.

이벤트 및 활동 데이터를 활용하여 다음 내용을 분석한다.

1. 아티스트의 게시글·메시지·라이브 활동 빈도와 팬의 재방문 및 휴면 사이의 관계
2. 콘텐츠 조회 이후 좋아요·댓글 등 참여 행동으로 이어지는 비율
3. 팬의 활동 수준과 상품 조회·장바구니·구매 전환 사이의 관계
4. 아티스트별 팬 행동과 구매 특성의 차이
5. 활동 팬·조회 중심 팬·참여 팬·코어 팬의 행동 차이

본 문서는 가상 데이터 생성, PostgreSQL 테이블 설계, SQL 분석, 지표 계산 및 Streamlit 대시보드 구현의 기준으로 사용한다.

이 문서의 정의가 PRD와 충돌할 경우 `docs/PRD.md` v1.1을 우선 적용하고, 필요한 경우 두 문서를 함께 수정한다.

---

## 2. 데이터 모델 기준

### 2.1 아티스트 활동과 팬 행동 분리

FANLOG는 아티스트가 소통을 제공한 행동과 팬이 실제로 반응한 행동을 서로 다른 테이블에 저장한다.

| 구분 | 저장 테이블 | 한 행의 기준 | 기본키 | 예시 |
| --- | --- | --- | --- | --- |
| 아티스트 소통 공급 | `fact_artist_activity` | 아티스트의 공식 활동 1건 | `activity_id` | 게시글 작성, 메시지 발송, 라이브 진행 |
| 팬 행동 | `fact_user_event` | 팬이 수행한 행동 1건 | `event_id` | 게시글 조회, 메시지 열람, 좋아요, 구매 |
| 메시지 구독 상태 | `fact_message_subscription` | 팬과 아티스트의 구독 기간 1건 | `subscription_id` | 구독 시작일, 종료일, 상태 |
| 주문 | `fact_order` | 주문 1건 | `transaction_id` | 결제 상태, 주문 총액, 환불액 |
| 주문 상품 | `fact_order_item` | 주문에 포함된 상품 1건 | `order_item_id` | 상품, 수량, 단가 |

### 2.2 분리 이유

아티스트가 메시지를 한 번 발송하면 `fact_artist_activity`에는 활동 한 건이 저장된다.

해당 메시지를 구독 팬 300명 중 180명이 열람하면 `fact_user_event`에는 최대 180건의 `message_open`이 저장된다.

이 구조를 통해 다음 값을 구분할 수 있다.

- 아티스트가 제공한 소통량
- 소통을 받을 수 있었던 팬 수
- 실제로 소통을 확인한 팬 수
- 소통 이후 추가 행동을 수행한 팬 수

### 2.3 이벤트와 업무 사실 데이터의 관계

일부 행동은 이벤트 로그와 업무 사실 테이블에 함께 반영될 수 있다.

예를 들어 구매가 완료되면 다음 데이터가 생성된다.

- 사용자 행동 순서와 퍼널 분석을 위한 `purchase` 이벤트
- 주문 금액과 결제 상태를 관리하는 `fact_order`
- 구매 상품과 수량을 관리하는 `fact_order_item`

이벤트 로그는 행동의 발생 순서와 전환 분석에 사용하고, 업무 사실 테이블은 주문·구독의 상태와 금액을 검증하는 기준으로 사용한다.

### 2.4 콘텐츠와 아티스트 연결 기준

`content_view`를 포함한 일반 콘텐츠 이벤트에서 전역 아티스트 필터(PRD FR-002)를 적용하려면 해당 콘텐츠가 어느 아티스트 소속인지 항상 파악할 수 있어야 한다.

이를 위해 `dim_content`는 `artist_id` 외래키를 필수로 보유하며, `content_view` 이벤트의 `artist_id` 파라미터는 임의로 비워두지 않고 `dim_content.artist_id`에서 조인하여 채운다.

`dim_content.artist_id`와 `content_type`(5개 값)은 PRD v1.2의 6.1.1, 10.2, 10.4에 반영 완료되었다.

---

## 3. 핵심 용어

| 용어 | 정의 |
| --- | --- |
| 이벤트 | 특정 시점에 팬이 수행한 행동 |
| 이벤트 파라미터 | 이벤트가 발생한 상황을 설명하는 추가 정보 |
| 아티스트 활동 | 아티스트가 제공한 게시글·메시지·라이브 활동 |
| 팬 행동 이벤트 | 팬의 조회·참여·구독·구매 행동 |
| 세션 | 동일 팬의 이벤트가 30분 이상 끊기기 전까지의 연속 활동 |
| 콘텐츠 | 공지·사진·영상·라이브 다시보기 등 `dim_content`에서 관리하는 대상 |
| 아티스트 게시글 | 아티스트 활동으로 생성되어 `activity_id`로 관리되는 게시글 |
| 참여 행동 | 좋아요와 댓글 등 단순 조회 이후 발생한 적극적인 행동 |
| 소통 활동일 | 아티스트가 게시글·메시지·라이브 중 하나 이상을 수행한 KST 기준 날짜 |
| 소통 공백일 | 해당 아티스트의 공식 소통 활동이 연속으로 없었던 일수 |
| 핵심 활동 | 단순 접속을 제외하고 팬의 관심·소비·참여·구매를 나타내는 행동 |
| 이탈 위험 팬 | 이전 30일 내 핵심 활동이 있었지만 현재 14일 연속 핵심 활동이 없는 팬 |
| 휴면 팬 | 현재 30일 연속 핵심 활동이 없는 팬 |
| 재활성 팬 | 휴면 상태 이후 다시 핵심 활동을 수행한 팬 |
| 메시지 구독 해지 | 유료 메시지 구독을 취소하거나 만료 후 갱신하지 않은 상태 |

---

## 4. 추적 설계 원칙

### 4.1 PRD 우선 원칙

이벤트명, 필드명, 지표 및 데이터 모델은 `docs/PRD.md` v1.1을 기준으로 한다.

이벤트 추적 계획서에서 새로운 이벤트나 필드를 추가해야 할 경우 먼저 PRD에 미치는 영향을 확인한다.

다만 8.1의 핵심 활동 목록과 같이 이 문서에서 PRD보다 먼저 구체화된 정의는 확정 즉시 PRD에도 반영하여 두 문서가 같은 근거를 갖도록 한다.

### 4.2 분석 목적 우선

수집 가능한 모든 행동을 기록하지 않고, PRD에서 정의한 분석 질문과 핵심 지표 계산에 필요한 행동만 MVP 범위에 포함한다.

### 4.3 한 번의 행동은 하나의 이벤트로 기록

팬이 수행한 한 번의 행동은 원칙적으로 `fact_user_event`의 한 행으로 기록한다.

예를 들어 팬이 게시글 하나를 조회하면 `artist_post_view` 이벤트 한 건을 생성한다.

### 4.4 아티스트 활동은 사용자 이벤트로 기록하지 않음

아티스트의 게시글 작성, 메시지 발송 및 라이브 진행은 `fact_user_event`에 저장하지 않는다.

해당 활동은 `fact_artist_activity`에 저장하며, 팬이 이를 조회하거나 참여했을 때만 사용자 이벤트를 생성한다.

따라서 `event_source` 필드는 사용하지 않는다.

### 4.5 이벤트 이름 작성 규칙

- 영문 소문자를 사용한다.
- 단어는 밑줄로 구분하는 `snake_case` 형식을 사용한다.
- PRD의 이벤트명을 그대로 사용한다.
- 동일 행동을 서로 다른 이름으로 중복 정의하지 않는다.
- 이벤트명을 변경할 경우 관련 SQL, 데이터 생성 코드 및 지표 문서를 함께 수정한다.

### 4.6 이벤트 발생 시점

이벤트는 행동이 완료되거나 유효 조건을 충족한 시점에 한 번 기록한다.

- 화면에 노출되기만 한 경우에는 조회로 기록하지 않는다.
- 상세 화면이 정상적으로 열린 경우 조회 이벤트를 기록한다.
- 라이브 시청 시간이 60초 이상이면 `live_view_start`를 기록한다.
- 결제가 성공한 경우에만 `purchase`를 기록한다.
- 환불 처리가 완료된 경우에만 `refund`를 기록한다.

### 4.7 시간대 기준

- 원천 발생 시각은 `event_timestamp_utc`에 UTC로 저장한다.
- `event_date_kst`는 `event_timestamp_utc`를 `Asia/Seoul`로 변환하여 생성한다.
- 일별·주별 집계와 대시보드 날짜 표시는 KST를 기준으로 한다.
- `event_date_kst`를 별도로 임의 생성하지 않는다.

### 4.8 식별자 및 개인정보 원칙

이벤트에는 실명, 이메일, 전화번호 및 자유 텍스트를 저장하지 않는다.

다음과 같은 가상 식별자를 사용한다.

- `user_id`
- `artist_id`
- `content_id`
- `activity_id`
- `product_id`
- `transaction_id`
- `session_id`

### 4.9 이벤트와 상태 데이터 구분

| 데이터 | 관리 위치 |
| --- | --- |
| 팬의 게시글 조회 | `fact_user_event` |
| 아티스트의 게시글 작성 | `fact_artist_activity` |
| 사용자의 가입일 | `dim_user` |
| 아티스트 팔로우 기간 | `bridge_user_artist_follow` |
| 메시지 구독 시작·종료 상태 | `fact_message_subscription` |
| 상품 기본 가격과 출시일 | `dim_product` |
| 상품 조회·장바구니·결제 행동 | `fact_user_event` |
| 주문 상태와 주문 총액 | `fact_order` |
| 주문별 상품과 수량 | `fact_order_item` |
| 위험·휴면·재활성 상태 | 사용자 이벤트에서 파생 |

---

## 5. 추적 대상 분류

### 5.1 아티스트 활동

아티스트 소통 공급은 이벤트명이 아닌 `fact_artist_activity.activity_type`으로 구분한다.

| 활동 유형 | 발생 조건 | 저장 테이블 |
| --- | --- | --- |
| `post` | 아티스트 게시글이 발행됨 | `fact_artist_activity` |
| `message` | 구독 팬에게 아티스트 메시지가 발송됨 | `fact_artist_activity` |
| `live` | 아티스트 라이브가 시작됨 | `fact_artist_activity` |

### 5.2 팬 행동 이벤트

MVP에서는 PRD v1.1에서 확정한 다음 17개 이벤트만 사용한다.

| 영역 | 이벤트 | 저장 테이블 |
| --- | --- | --- |
| 회원·세션 | `sign_up`, `session_start` | `fact_user_event` |
| 아티스트 탐색 | `artist_view`, `artist_follow` | `fact_user_event` |
| 메시지 구독 | `message_subscription_start`, `message_subscription_cancel` | `fact_user_event` |
| 소통 콘텐츠 이용 | `artist_post_view`, `message_open`, `live_view_start` | `fact_user_event` |
| 공식 콘텐츠 이용·참여 | `content_view`, `content_like`, `comment_create` | `fact_user_event` |
| 커머스 | `view_item`, `add_to_cart`, `begin_checkout`, `purchase`, `refund` | `fact_user_event` |

다음 이벤트는 MVP에 포함하지 않는다.

- `login`
- `artist_unfollow`
- `content_unlike`
- `message_reply_send`
- `live_view_complete`
- `product_view`
- `subscription_start`
- `subscription_cancel`

상품 상세 조회는 `product_view`가 아니라 `view_item`을 사용한다.

메시지 구독 시작과 취소는 각각 `message_subscription_start`, `message_subscription_cancel`을 사용한다.

### 5.3 아티스트 게시글과 일반 콘텐츠 구분

| 대상 | 조회 이벤트 | 참조 식별자 |
| --- | --- | --- |
| 아티스트가 작성한 게시글 | `artist_post_view` | `activity_id`, `artist_id` |
| 공지·사진·영상·라이브 다시보기 | `content_view` | `content_id` |

`artist_post_view`와 `content_view`를 하나의 이벤트로 합치지 않는다.

아티스트 게시글은 소통 공급량과 팬 반응량을 연결해야 하므로 `activity_id`를 사용하고, 일반 콘텐츠는 `dim_content`와 연결하기 위해 `content_id`를 사용한다.

**구분 기준**: 두 유형은 발행 주체와 실시간성을 기준으로 나눈다.

- 아티스트 또는 멤버 계정이 직접, 즉시성 있게 올리는 소식·사진·짧은 영상 → **게시글**(`fact_artist_activity`, `activity_id`)
- 운영팀이 사전 제작·편집하여 게시하는 공식 자료(포토카드, 뮤직비디오, 라이브 다시보기, 공지사항 등) → **콘텐츠**(`dim_content`, `content_id`)

데이터 생성 시나리오를 작성할 때도 위 기준을 그대로 적용하여, 아티스트 활동 시나리오(PRD 13.2)에서 늘어나는 항목은 게시글·메시지·라이브로, 콘텐츠 생성량(PRD 13.1의 공식 콘텐츠)은 별도 규칙으로 관리한다.

---

## 6. 팬 행동 이벤트 공통 필드

다음 필드는 `fact_user_event`에 적용한다.

| 필드명 | 논리 형식 | PostgreSQL 예시 | 필수 여부 | 설명 |
| --- | --- | --- | --- | --- |
| `event_id` | 문자열 | UUID | 필수 | 이벤트 고유 식별자 |
| `event_name` | 문자열 | VARCHAR | 필수 | PRD에 정의된 이벤트명 |
| `event_timestamp_utc` | 타임스탬프 | TIMESTAMPTZ | 필수 | 이벤트가 발생한 UTC 시각 |
| `event_date_kst` | 날짜 | DATE | 필수 | UTC 발생 시각에서 파생한 KST 날짜 |
| `user_id` | 문자열 | VARCHAR | 필수 | 가상 팬 식별자 |
| `session_id` | 문자열 | UUID 또는 VARCHAR | 조건부 | 이벤트가 속한 세션 |
| `artist_id` | 문자열 | VARCHAR | 조건부 | 이벤트와 관련된 아티스트. `content_view`는 `dim_content.artist_id`를 조인하여 채운다 |
| `content_id` | 문자열 | VARCHAR | 조건부 | 이벤트와 관련된 일반 콘텐츠 |
| `activity_id` | 문자열 | VARCHAR | 조건부 | 이벤트와 관련된 아티스트 활동 |
| `product_id` | 문자열 | VARCHAR | 조건부 | 이벤트와 관련된 상품 |
| `transaction_id` | 문자열 | VARCHAR | 조건부 | 결제·구매·환불 관련 주문 |
| `device_type` | 범주형 | VARCHAR | 필수 | `mobile`, `desktop`, `tablet` |
| `traffic_source` | 범주형 | VARCHAR | 조건부 | `direct`, `push`, `social`, `search` |
| `parameters` | JSON | JSONB | 조건부 | 이벤트별 추가 속성 |

### 6.1 필수 여부 기준

- `필수`: 모든 팬 행동 이벤트에 반드시 값이 있어야 한다.
- `조건부`: 해당 객체 또는 상황과 관련된 이벤트일 때 값이 있어야 한다.

### 6.2 공통 필드에서 제외하는 값

다음 값은 `fact_user_event`의 공통 필드로 사용하지 않는다.

| 제외 필드 | 제외 이유 |
| --- | --- |
| `event_source` | 팬 행동과 아티스트 활동을 별도 테이블로 분리하므로 필요하지 않음 |
| `event_timestamp` | `event_timestamp_utc`를 사용하여 시간대 의미를 명확히 함 |
| `properties` | PRD에서 확정한 `parameters`로 통일 |
| `order_id` | PRD에서 확정한 `transaction_id`로 통일 |
| `platform` | PRD에서 확정한 `device_type`을 사용 |

---

## 7. 아티스트 활동 공통 필드

다음 필드는 `fact_artist_activity`에 적용한다.

| 필드명 | 논리 형식 | PostgreSQL 예시 | 필수 여부 | 설명 |
| --- | --- | --- | --- | --- |
| `activity_id` | 문자열 | UUID 또는 VARCHAR | 필수 | 아티스트 활동 고유 식별자 |
| `artist_id` | 문자열 | VARCHAR | 필수 | 활동을 수행한 가상 아티스트 |
| `activity_type` | 범주형 | VARCHAR | 필수 | `post`, `message`, `live` |
| `activity_timestamp_utc` | 타임스탬프 | TIMESTAMPTZ | 필수 | 활동이 발생한 UTC 시각 |
| `activity_date_kst` | 날짜 | DATE | 필수 | UTC 발생 시각에서 파생한 KST 날짜 |
| `content_id` | 문자열 | VARCHAR | 조건부 | 별도 콘텐츠와 연결되는 경우 사용 |
| `phase_id` | 문자열 | VARCHAR | 조건부 | 일상·컴백·공연·비활동기 등 활동 단계 |
| `parameters` | JSON | JSONB | 조건부 | 활동 유형별 추가 속성 |

`fact_artist_activity`에는 `user_id`와 `session_id`를 저장하지 않는다.

---

## 8. 핵심 활동과 사용자 상태

### 8.1 핵심 활동 이벤트

DAU·WAU·이탈 위험·휴면·재활성 계산에는 다음 이벤트를 핵심 활동으로 사용한다.

- `artist_follow`
- `message_subscription_start`
- `artist_post_view`
- `message_open`
- `live_view_start`
- `content_view`
- `content_like`
- `comment_create`
- `view_item`
- `add_to_cart`
- `begin_checkout`
- `purchase`

다음 이벤트는 기록은 유지하지만 핵심 활동 계산에서는 제외한다.

| 이벤트 | 제외 이유 |
| --- | --- |
| `sign_up` | 가입 완료를 나타내며 지속적인 서비스 활동은 아님 |
| `session_start` | 단순 접속이므로 핵심 행동으로 보지 않음 |
| `artist_view` | 탐색 행동이지만 핵심 참여·소비 행동에서는 제외 |
| `message_subscription_cancel` | 구독 해지 행동으로 활성 상태를 연장하지 않음 |
| `refund` | 구매 이후의 취소·사후 처리 행동으로 활성 상태를 연장하지 않음 |

이 12개 항목은 PRD 8.1의 "핵심 활동" 정의("단순 세션 시작을 제외한 팔로우·콘텐츠·메시지·라이브·상품 관련 행동")를 이벤트 단위로 구체화한 확정 목록이다. PRD를 다음에 개정할 때 이 목록을 그대로 반영하여 두 문서의 핵심 활동 범위를 일치시킨다.

### 8.2 활동 상태 정의

분석 기준일을 `D`라고 할 때 다음 기준을 적용한다.

| 상태 | 계산 기준 |
| --- | --- |
| 정상 활동 | `D`를 포함한 최근 14일 안에 핵심 활동이 1건 이상 있음 |
| 이탈 위험 | 최근 30일 안에는 핵심 활동이 있지만 최근 14일에는 핵심 활동이 없음 |
| 휴면 | 최근 30일 동안 핵심 활동이 없음 |
| 재활성 | 30일 이상 핵심 활동이 없었던 팬이 다시 핵심 활동을 수행함 |

이탈 위험과 휴면은 동시에 부여하지 않는다.

사용자 상태는 원천 이벤트로 생성하지 않고 `mart_user_daily`에서 기준일별 파생 값으로 계산한다.

---

## 9. 공통 데이터 품질 규칙

| 규칙 ID | 검증 내용 | 기대 결과 |
| --- | --- | --- |
| ET-DQ-01 | `event_id` 중복 | 0건 |
| ET-DQ-02 | `activity_id` 중복 | 0건 |
| ET-DQ-03 | 허용 목록에 없는 `event_name` | 0건 |
| ET-DQ-04 | 허용 목록에 없는 `activity_type` | 0건 |
| ET-DQ-05 | 팬 이벤트의 `user_id` 결측 | 0건 |
| ET-DQ-06 | 참조 대상이 없는 외래키 | 0건 |
| ET-DQ-07 | 사용자 가입 시각보다 빠른 팬 이벤트 | 0건 |
| ET-DQ-08 | 유효한 구독 없이 발생한 `message_open` | 0건 |
| ET-DQ-09 | 중복된 `purchase.transaction_id` | 0건 |
| ET-DQ-10 | 성공 주문과 연결되지 않은 `purchase` | 0건 |
| ET-DQ-11 | 상품 출시 시각보다 빠른 상품 이벤트 | 0건 |
| ET-DQ-12 | 음수 금액·수량·시청 시간 | 0건 |
| ET-DQ-13 | UTC 시각과 KST 파생 일자 불일치 | 표본 검산 100% 일치 |
| ET-DQ-14 | 분석 기간을 벗어난 이벤트·활동 | 0건 |
| ET-DQ-15 | 허용 목록에 없는 `dim_content.content_type` | 0건 |

### 9.1 식별자 참조 규칙

- 모든 `user_id`는 `dim_user`에 존재해야 한다.
- 모든 `artist_id`는 `dim_artist`에 존재해야 한다.
- 모든 `content_id`는 `dim_content`에 존재해야 한다.
- 모든 `activity_id`는 `fact_artist_activity`에 존재해야 한다.
- 모든 `product_id`는 `dim_product`에 존재해야 한다.
- 구매·환불의 `transaction_id`는 `fact_order`에 존재해야 한다.

### 9.2 시간 순서 규칙

- 팬 이벤트는 해당 팬의 가입 시각보다 빠를 수 없다.
- `artist_post_view`, `message_open`, `live_view_start`는 관련 아티스트 활동보다 빠를 수 없다.
- 상품 이벤트는 해당 상품의 출시 시각보다 빠를 수 없다.
- `add_to_cart`는 동일 사용자·동일 상품의 관련 `view_item`이 존재하는 경우 그 시각보다 빠를 수 없다.
- `begin_checkout`은 관련 장바구니 추가보다 빠를 수 없다.
- `purchase`는 관련 결제 시작보다 빠를 수 없다.
- `refund`는 관련 구매 완료보다 빠를 수 없다.

위 순서 규칙은 이벤트 간 선후관계만 검증하며, `view_item` 없이 `add_to_cart`가 먼저 발생하는 것 자체를 막지 않는다. 이를 통해 PRD 8.3의 열린 퍼널(상품 상세조회 없이 장바구니에 담는 경로 등 단계 건너뛰기)을 그대로 허용하면서, 동일 상품에 대해 두 이벤트가 모두 존재할 때의 시간 역전만 오류로 검출한다. 순서를 반드시 지키는 닫힌 퍼널 전환율은 PRD 8.3의 계산 조건에 따라 별도로 집계한다.

### 9.3 구매 무결성 규칙

- 하나의 `transaction_id`에는 성공한 `purchase` 이벤트가 최대 한 건만 존재한다.
- `purchase`의 `transaction_id`는 `fact_order`의 성공 주문과 1:1로 대응한다.
- `purchase.parameters.value`는 주문 총액과 일치해야 한다.
- `refund` 금액은 해당 주문의 구매 금액을 초과할 수 없다.

---

## 10. 이후 작성할 내용

다음 단계에서 아래 항목을 순서대로 작성한다.

1. `fact_artist_activity` 활동 유형별 상세 명세
2. 17개 사용자 이벤트별 발생 조건
3. 이벤트별 필수 식별자와 `parameters`
4. 중복 이벤트 방지 기준
5. 이벤트와 핵심 지표의 연결 관계
6. 이벤트 생성 예시