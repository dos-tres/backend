# DB 테이블 안내

PostgreSQL 17 테이블 전체를 한곳에 정리한다. 테이블을 추가·변경하면 모델·migration과 함께 이 문서를 고친다. 2026-11-19 기준.

| 상태 | 테이블 |
| --- | --- |
| 구현 완료 (migration 적용) | `catalog_items`, `catalog_item_changes`, `users`, `user_profiles`, `user_consents`, `checkin_responses` |
| 계획 (코드 주석으로만) | `user_identities`, `auth_sessions` — 로그인 방식 미정 |
| 계획 (문서로만) | `saved_items`, `activity_records`, `schedule_events`, `conversations`, `conversation_messages` |

회원 테이블은 **테이블만** 있다. 가입·로그인·프로필 저장 API와 인증은 아직 없어서, 지금은 이 테이블에 쓰는 코드가 없다.

## 1. 관계

```text
catalog_items ─< catalog_item_changes                      (정책·프로그램, 매일 파이프라인이 채움)

users ─┬─ user_profiles        (1:1)
       ├─< user_consents
       ├─< checkin_responses
       ├─< user_identities     (계획: 로그인 방식 확정 후)
       ├─< auth_sessions       (계획)
       ├─< saved_items >─ catalog_items          (계획: 마이페이지)
       ├─< activity_records >─ catalog_items     (계획)
       ├─< schedule_events                       (계획)
       └─< conversations ─< conversation_messages (계획: 대화 저장)
```

`─<` 는 1:N. 회원 데이터는 모두 `users.id`를 `ON DELETE CASCADE`로 참조한다 → **회원 행을 지우면 개인 데이터가 함께 지워진다.**

## 2. 공통 규칙

- 이름: 테이블은 복수형 snake_case. 제약 이름은 `app/database.py`의 naming convention(`pk_`·`fk_`·`ck_`·`ix_`).
- 시각은 모두 `timestamptz`, 기본값 `now()`.
- 회원 id는 UUID(`gen_random_uuid()`). URL·토큰에 순번이 드러나지 않게 한다. 이력 테이블 id는 BIGINT identity.
- 이력성 데이터(동의, 상태 체크, 카탈로그 변경)는 덮어쓰지 않고 행을 쌓는다.
- **민감한 값은 동의가 있을 때만 저장한다.** 상황(장애·수급·한부모 등) → `sensitive_info`, 상태 체크 응답 → `checkin_storage`, 대화 → `chat_history`. DB 제약으로는 강제할 수 없으므로 저장하는 서비스 코드가 `user_consents`를 확인한다.
- 스키마 변경은 Alembic으로만 한다(README "로컬 PostgreSQL과 마이그레이션").

## 3. 정책·프로그램 (구현 완료)

자세한 컬럼·적재 규칙은 [추천 문서](RECOMMENDATION.md) 2장.

| 테이블 | 내용 | migration |
| --- | --- | --- |
| `catalog_items` | 정책·청년센터 프로그램 한 줄씩. 필터 컬럼(나이·지역·영역·상황·마감·상태) + 원본 `payload`(JSONB) | 0002 |
| `catalog_item_changes` | 적재할 때의 변경 이력: created / updated / reopened / closed, 이전 payload | 0003 |

## 4. 회원 (구현 완료: 테이블만, migration 0004)

모델: `app/users/models.py`

### `users` — 회원

로그인 수단과 분리했다. 로그인 방식이 바뀌거나 여러 개가 되어도 이 테이블과 아래 개인 데이터는 그대로 둔다.

| 컬럼 | 형식 | 설명 |
| --- | --- | --- |
| `id` | UUID PK | `gen_random_uuid()` |
| `status` | varchar(10) | `active` / `withdrawn` (CHECK) |
| `created_at`, `updated_at` | timestamptz | |
| `withdrawn_at` | timestamptz, null | 탈퇴 요청 시각. 바로 지울지 유예 뒤 지울지는 미정 |

### `user_profiles` — 추천에 쓰는 기본 정보 (회원당 1행)

값 목록은 추천 API `profile`(`app/recommend/router.py`)과 같다. 로그인한 사용자는 이 행으로 바로 추천을 받는다.

| 컬럼 | 형식 | 설명 |
| --- | --- | --- |
| `user_id` | UUID PK, FK → users (CASCADE) | |
| `birth_year` | smallint, null | 나이 대신 출생연도 (해마다 고칠 필요 없음). 1900~2100 CHECK |
| `sex` | varchar(2), null | `남` / `여` (CHECK) |
| `sigungu_cd` | varchar(5), null | 원본(온통청년) 시군구 코드. 5자리 숫자 CHECK. 실제 코드인지는 서비스가 `known_sigungu_codes`로 확인 (예: 곡성은 통합 뒤 `12720`) |
| `job` | varchar(20), null | `rules.JOB` 키: 구직 중, 회사원, 아르바이트·단기, 프리랜서, 창업·자영업, 농어업, 학생, 쉬는 중 |
| `school` | varchar(20), null | `rules.SCHOOL` 키: 고등학생, 대학생, 대학원생 |
| `situations` | varchar(20)[] | 임신·출산, 육아, 장애인, 기초생활수급자, 한부모가정 … — **`sensitive_info` 동의가 있을 때만** |
| `interests` | varchar(20)[] | 상태 체크 관심 분야 (일자리·취업 …) |
| `updated_at` | timestamptz | |

FE 마이페이지의 "활동 지역"은 지금 자유 입력이다. 저장하려면 시군구 선택으로 바꿔야 한다.

### `user_consents` — 동의 이력

| 컬럼 | 형식 | 설명 |
| --- | --- | --- |
| `id` | bigint identity PK | |
| `user_id` | UUID FK → users (CASCADE) | |
| `consent_type` | varchar(30) | `terms` 이용약관 / `privacy` 개인정보(기본 프로필) / `sensitive_info` 상황 정보 / `checkin_storage` 상태 체크 응답 / `chat_history` 대화 (CHECK) |
| `version` | varchar(20) | 동의한 약관·안내문 버전 |
| `agreed_at` | timestamptz | |
| `withdrawn_at` | timestamptz, null | 철회 시각 |

현재 동의 여부 = 같은 종류에서 가장 최근 행이 철회되지 않았는가. 인덱스 `(user_id, consent_type)`.

### `checkin_responses` — 상태 체크 응답 이력

요구사항(docs/requirements.md 6장): 문항·선택지 버전, 응답, 응답 시점, 완료/부분 응답, 사용자 수정. 다시 하거나 고치면 새 행을 쌓는다.

| 컬럼 | 형식 | 설명 |
| --- | --- | --- |
| `id` | bigint identity PK | |
| `user_id` | UUID FK → users (CASCADE) | |
| `question_version` | varchar(30) | `app.checkin.questions.QUESTION_VERSION` (지금 `draft-2026-11-19`) |
| `answers` | JSONB | 문항 id → 선택지 code (`/api/checkin/summary`와 같은 형식) |
| `summary` | JSONB | `summarize()` 결과 (영역 수준·우선순위). 점수·위험 등급 없음 |
| `completed` | boolean | 다섯 영역 문항을 모두 지나갔는지 |
| `source` | varchar(10) | `survey` 설문 화면 / `chat` 대화에서 알아들은 답 (CHECK) |
| `created_at` | timestamptz | 인덱스 `(user_id, created_at)` |

## 5. 계획: 로그인 수단·세션 (로그인 방식 미정)

`app/users/models.py` 아래쪽에 모델을 **주석으로** 적어 두었다. 방식이 정해지면 주석을 풀고 migration을 추가한다.

이렇게 하려고 했다:

- 회원과 로그인 수단을 나눈다. 한 회원이 카카오·구글·이메일 등 여러 수단을 연결할 수 있다.
- `provider_subject`는 제공자가 주는 고유 id(소셜 로그인의 sub 등). 이메일·전화번호를 식별자로 쓰지 않는다.
- 세션은 서버에 저장하는 불투명 토큰. 원문은 저장하지 않고 SHA-256 해시만 둔다. 로그아웃·강제 만료는 `revoked_at`. JWT만 쓰면 로그아웃·탈퇴 즉시 무효화가 어려워 서버 세션을 기본으로 생각했다.
- 정부 서비스 연동(본인확인 등)을 쓰면 provider에 추가하고, 받은 개인정보는 저장하지 않는 쪽으로 검토한다.
- 로그인 없이 먼저 써 보는 흐름을 넣으면, 익명 사용자도 `users` 행을 만들고 `provider='anonymous'` 세션만 둔 뒤 가입할 때 identity를 연결한다(기록이 이어진다).

| 테이블 | 주요 컬럼 |
| --- | --- |
| `user_identities` | `id`, `user_id`(FK CASCADE), `provider`(kakao/naver/google/email/gov/anonymous 후보), `provider_subject`, `created_at`, `last_login_at`. UNIQUE(`provider`, `provider_subject`) |
| `auth_sessions` | `id`, `user_id`(FK CASCADE), `token_hash`(UNIQUE, SHA-256), `created_at`, `expires_at`, `revoked_at`. 인덱스 `user_id`, `expires_at` |

## 6. 계획: 마이페이지 기록·대화 저장 (화면·기능 연결할 때)

FE 마이페이지(내 정보, 대화 이력, 관심 목록, 참여 이력, 일정, 섬 진행도) 기준이다. 아직 모델도 없다.

| 테이블 | 주요 컬럼 | 화면·용도 |
| --- | --- | --- |
| `saved_items` | `user_id`, `catalog_item_id`(FK), `created_at`. UNIQUE(user, item) | 관심 목록. `catalog_item_changes`와 이어 "마감일이 바뀌었어요" 알림 |
| `activity_records` | `user_id`, `catalog_item_id`(null 가능), `title`, `status`(planned/applied/attended/cancelled), `planned_on`, `memo` | 참여 이력·섬 진행도. 계획과 실제 참여를 구분 |
| `schedule_events` | `user_id`, `title`, `date`, `catalog_item_id`(null 가능), `done` | 일정 |
| `conversations` | `user_id`, `title`, `created_at`, `updated_at` | 대화 이력 (`chat_history` 동의) |
| `conversation_messages` | `conversation_id`(FK CASCADE), `role`, `content`, `mode`, `created_at` | 대화 내용. 위기 대화 저장 여부·보관 기간은 정책 결정 필요 |

전화 문의 대행 등 실행 업무(요구사항 6장의 실행 업무·문의 작업·실행 결과)는 그 기능을 만들 때 설계한다.

## 7. 정해야 할 것

1. 로그인 방식 (소셜·이메일·정부 서비스 연동), 로그인 없이 먼저 써 보기 허용 여부
2. 상황 정보(민감 정보)를 저장할지, 추천할 때마다 물을지
3. 탈퇴 후 즉시 삭제 / 유예 기간, 대화·상태 체크 보관 기간
4. 동의 문구와 버전 관리 방식

## 8. migration 목록

| revision | 내용 |
| --- | --- |
| 0001 | baseline (Alembic 버전 테이블만) |
| 0002 | `catalog_items` |
| 0003 | `catalog_item_changes` |
| 0004 | `users`, `user_profiles`, `user_consents`, `checkin_responses` |
