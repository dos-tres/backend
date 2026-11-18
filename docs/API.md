# 둘셋 API — 첫 구현

작성일: 2026-11-18. 실제 구현은 아래 6개 경로입니다. 실행 중인 `/docs`와
`/openapi.json`을 요청·응답 스키마의 기준으로 사용합니다.

| 메서드 | 경로 | 인증 | 역할 |
| --- | --- | --- | --- |
| GET | `/healthz` | 없음 | 프로세스 상태 |
| GET | `/readyz` | 없음 | DB 연결·초기 테이블 준비 확인 |
| POST | `/api/v1/sessions` | 없음 | 익명 세션과 빈 기본 프로필 생성 |
| DELETE | `/api/v1/sessions/current` | Bearer | 현재 세션과 프로필 삭제 |
| GET | `/api/v1/profile` | Bearer | 현재 세션 프로필 조회 |
| PUT | `/api/v1/profile` | Bearer | 기본 프로필 전체 교체 |

## 세션 계약

`POST /api/v1/sessions`는 요청 본문이 없습니다. 응답은 201입니다.

```json
{
  "session_id": "6c665ed6-4918-4b64-a8f2-e29d0cfbd29c",
  "access_token": "생성 시 한 번만 반환하는 무작위 토큰",
  "token_type": "bearer",
  "expires_at": "2026-11-25T05:00:00+00:00"
}
```

보호된 API에 `Authorization: Bearer <access_token>`을 보냅니다. `session_id`는
접근 권한이 아닙니다. 다른 세션 ID를 지정하는 API는 제공하지 않습니다.
DB에는 토큰의 SHA-256 해시만 저장합니다. 기본 만료는 발급 시점부터 168시간이며
요청할 때 연장되지 않습니다. 만료·유효하지 않은 토큰은 401입니다.

프론트는 토큰을 URL·로그에 넣지 않고 우선 메모리에서 관리합니다. 탭을 닫으면
세션 복구를 제공하지 않는 MVP입니다. 영구 저장 또는 HttpOnly 쿠키 전환은 프론트
연결 때 함께 결정합니다. 토큰을 잃어버리면 새 세션을 시작해야 합니다.

## 기본 프로필 계약

```json
{
  "age": 27,
  "region": "대전광역시",
  "employment_status": "job_seeking",
  "housing_status": "renting",
  "interests": ["employment", "housing"]
}
```

GET·PUT 응답에는 같은 필드와 UTC `updated_at`이 있습니다.

| 필드 | 값 | 미응답 |
| --- | --- | --- |
| age | 정수 0~120. 정책의 대상 나이와 별도로 검증 | null |
| region | 1~50자 지역명. 공백 제거. 정책 지역 코드 변환은 후속 작업 | null |
| employment_status | student / employed / job_seeking / other | null |
| housing_status | with_family / renting / owning / other | null |
| interests | employment / housing / education / finance / participation / wellbeing | [] |

PUT은 전체 교체이므로 생략한 필드도 미응답 값으로 초기화됩니다. 기존 값을 유지하려면
GET 결과에서 `updated_at`을 제외한 전체 입력을 보냅니다. 명시하지 않은 필드는
추정하지 않습니다. 중복 관심사는 순서를 유지하며 제거합니다. 정의되지 않은
입력 필드는 422로 거부합니다. 소득·거주 자격·정책 수급 자격 판정은 포함하지 않습니다.

기본 프로필은 추천 필터용 정보입니다. I5 영역, 상태 체크 응답, 진단 점수는 저장하거나
계산하지 않습니다. 설문 버전·문항·부분 응답과 프로필 반영 규칙은 다음 작업입니다.

## 오류 계약

```json
{
  "error": {
    "code": "SESSION_EXPIRED",
    "message": "세션이 만료되었습니다. 새로 시작해주세요.",
    "request_id": "4f4388a8-1047-4b14-898e-d8918e7e380a"
  }
}
```

| 상태 | code | 프론트 처리 |
| --- | --- | --- |
| 401 | SESSION_INVALID / SESSION_EXPIRED | 새 시작 안내 |
| 422 | VALIDATION_ERROR | 입력 확인 |
| 404·405 등 | HTTP_ERROR | 경로·메서드 확인 |
| 503 | DATABASE_UNAVAILABLE | 일시 실패 안내 |
| 500 | INTERNAL_ERROR | 오류 안내 및 요청 ID 보관 |

모든 앱 응답은 `X-Request-ID`, `Cache-Control: no-store`를 반환합니다.
오류에 입력값·토큰·SQL·연결 정보를 포함하지 않습니다. 기본 Uvicorn 접근 로그에도
토큰을 노출하지 않도록 토큰은 헤더로만 전송합니다. 프록시 로그도 헤더·본문을 기록하지
않도록 별도 설정해야 합니다.

## 데이터 구조와 보관

`anonymous_sessions` 1개에 `profiles` 1개가 연결됩니다. 세션 ID는 UUID,
토큰 해시는 유일한 64자 값, 만료 시각은 인덱스를 둡니다. 날짜는 UTC로 처리합니다.
SQLite는 로컬 개발·테스트 전용이며 배포 환경 설정에서는 외부 PostgreSQL만 허용합니다.
스키마 변경은 Alembic으로 관리하며 서버 시작 시 테이블을 임의 생성하지 않습니다.

현재 세션 삭제 시 프로필도 삭제됩니다. 만료 시점부터 접근을 차단하고,
`uv run python -m app.cleanup`으로 만료 세션·프로필을 삭제합니다.
자동 실행은 아직 설정하지 않았습니다. 공개 배포 전 하루 1회 정리 작업과
저장 목적 안내를 연결해야 하며, 사용자 기록을 담기 전 보관·백업 정책을 확정합니다.

## 후속 작업의 경계

| 분담 가능한 작업 | 담당 파일 제안 | 선행 작업 |
| --- | --- | --- |
| A: 온통청년 수집·정규화·목록/상세 | app/api/policies.py, app/services/policies/ | 실제 API 필드·샘플 확인 |
| B: 설문 문항·버전·부분 응답·프로필 반영 | app/api/surveys.py, app/services/surveys/ | 문항·선택지·변환 규칙 확정 |
| 이후 A: 추천 | app/api/recommendations.py | 정책·프로필 연결 |
| 이후 B: LLM 대화·선택지·이력 | app/api/conversations.py | 제공업체·모델·응답 계약 |

공통 `models.py`, `schemas.py`, `main.py`, 설정과 마이그레이션은 변경 담당자를
조율합니다. 동시 개발 시 마이그레이션 revision 분기 충돌을 확인합니다.
정책·추천·대화의 경로와 JSON은 초안이며 아직 OpenAPI에 게시하지 않습니다.
실제 정책 조회·LLM·프론트 연결·배포 완료로 표시하지 않습니다.
