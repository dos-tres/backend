# 개발 로그

## 2026-11-19 — 회원 테이블 (migration 0004)

- 브랜치: `feat/user-schema` (`main` f0a550c에서 생성)
- 목적: 회원 관리 DB 구조를 미리 만들어 둔다. 로그인 방식은 미정.
- 구현 완료와 배포 구분: 테이블·모델·migration·테스트·문서 완료. 가입·로그인·프로필 API, 인증은 만들지 않았다. 배포하지 않았다.

### 결정

- 로그인 방식과 상관없는 4개만 테이블로: `users`, `user_profiles`, `user_consents`, `checkin_responses`.
- 로그인 수단(`user_identities`)·세션(`auth_sessions`)은 `app/users/models.py`에 주석으로 설계만 남김(회원과 로그인 수단 분리, provider_subject 식별, 서버 세션 + 토큰 해시, 익명 시작 후 가입 연결).
- 회원 데이터는 모두 `users`를 CASCADE로 참조 → 회원 행 삭제 = 개인 데이터 삭제.
- 프로필은 추천 API profile과 같은 값, 나이 대신 출생연도. 상황(민감 정보)·상태 체크 응답·대화는 동의(`user_consents`)가 있을 때만 저장(서비스 코드에서 확인).
- 상태 체크 응답은 덮어쓰지 않고 쌓음. 문항 버전 `QUESTION_VERSION`(`app/checkin/questions.py`) 추가.
- 테이블 설명은 `docs/DATABASE.md` 한곳에 모음(카탈로그 상세는 RECOMMENDATION.md 링크).

### 실제 실행한 검증

- 개발 DB `alembic upgrade head` → 0004, `alembic check` 차이 없음.
- `python -m unittest discover -s tests`: 44개 통과(로컬 Docker PostgreSQL 17). 신규 `test_users_db.py`: 기본값(UUID·status·빈 배열), CHECK 제약 6종, 회원 삭제 시 프로필·동의·상태 체크 응답 삭제. `test_database.py` 0004 반영(upgrade/downgrade 왕복 포함).

### 남은 작업

- 로그인 방식 결정 → `user_identities`·`auth_sessions` migration, 가입·로그인·프로필·동의 API, 사용자별 접근 제어.
- 마이페이지 기록(`saved_items`·`activity_records`·`schedule_events`)과 대화 저장 테이블은 화면·기능 연결 때.
- 탈퇴 유예·보관 기간·동의 문구 버전 정책.

## 2026-11-19 — 페르소나 점검으로 찾은 추천 오류 수정

- 브랜치: `feat/recommendation-pipeline` (PR #6에 이어서)
- 목적: 임의 페르소나 5명(관악 구직·은둔, 대전 기혼 회사원, 노원 대학생, 해운대 한부모·수급자, 곡성 농업)으로 설문 → 요약 → 추천을 개발 DB에서 실행해 보고 찾은 오류를 고친다.
- 구현 완료와 배포 구분: 코드·테스트 수정 완료. 배포하지 않았다.

### 찾은 문제와 수정

- 신청기간이 비어 있으면 사업이 끝났어도 추천됨(9건, 예: 9월에 끝난 은평청년축제가 노원 대학생에게 추천) → 신청기간이 없으면 사업 종료일(`bizPrdEndYmd`)을 마감일로 (`rows.policy_deadline`).
- 특정 대상 사업이 일반 사용자에게 추천됨(예: 지원망 high 응답자에게 자살시도자 치료비, 경계선지능청년지원) → 제목 기준 특정 대상 제외(`rules.SPECIAL_TARGET`). 자격 조건 원문은 '국가유공자 우대'처럼 여러 대상 중 하나로 적혀 오탐이 많아 쓰지 않았다.
- 옛 시군구 코드(곡성 `46720`, 광주·전남 통합 뒤 `12720`)를 받으면 조용히 0건 → 원본 코드 목록에 없으면 422 `Unknown sigungu_cd` (`repository.known_sigungu_codes`).
- 추천 응답에 정책 `income_condition`(소득 무관이면 null / 연소득 상한 / 원문 설명)과 `programs_notice`(프로그램 0건 이유: `no_program_data` / `no_program_match`)를 추가. 소득은 추천에서 거르지 않고 신청하려 할 때 FE가 확인하기로 함.
- 위 마감일 수정을 적재해 보니, 원본이 같으면 파생 컬럼(`deadline`)이 바뀌어도 DB에 쓰지 않던 upsert 조건을 발견 → 저장 컬럼 전부를 비교하도록 수정(이력·`updated_at`은 그대로).

### 실제 실행한 검증

- `python -m unittest discover -s tests`: 39개 통과(로컬 Docker PostgreSQL 17).
- 개발 DB에 seed 재적재 → 정책 마감일 1,904건이 새 규칙과 일치.
- 페르소나 5명 재실행: 지난 사업·특정 대상 사업 0건, 옛 코드 46720은 422, 새 코드 12720은 정상 추천.

### 남은 작업 (이번에 고치지 않음)

- 관심 분야 가중치(+10)가 영역 점수(30/18)보다 약해 고른 관심 분야가 결과에 안 나오는 경우(노원 대학생의 교육·해외) — 가중치 조정은 팀 결정 필요.
- 소득 조건 확인 화면(FE), 서울 밖 청년센터 프로그램 수집(지역 통합 플랫폼·사이트별 크롤러), 생애 단계만 겹쳐도 '내 상황에 맞는 지원' +10.

## 2026-11-19 — catalog 변경 감지와 변경 이력 (`catalog_item_changes`)

- 브랜치: `feat/recommendation-pipeline` (PR #6에 이어서)
- 목적: `source_hash`를 저장만 하고 비교하지 않아 매일 전 행을 덮어쓰고 `updated_at`이 '마지막 적재 시각'이 되던 문제를 고치고, 원본 변경을 이력으로 남긴다.
- 구현 완료와 배포 구분: 코드·마이그레이션·테스트 작성 완료. 운영 DB 적용·배포는 하지 않았다.

### 결정

- 해시는 serving 항목 전체의 SHA-256, 단 매일 바뀌는 정책 조회수 `inqCnt`는 뺀다. 조회수는 payload에는 계속 반영한다(추천 동점 정리에 씀).
- 변경 종류: created / updated / reopened / closed. updated·reopened는 이전 payload와 바뀐 최상위 필드를 남긴다. 찜·신청 항목 변경 알림을 위해 덮어쓰기만 하는 방식 대신 이력 저장을 선택했다.
- `updated_at`은 해시·상태가 바뀐 시각만 뜻한다.

### 주요 변경

- `app/catalog/rows.py`: `content_hash`, `changed_fields`, `VOLATILE_FIELDS`.
- `app/catalog/models.py`: `CatalogItemChange`. `migrations/versions/0003_catalog_item_changes.py`.
- `app/catalog/load.py`: `plan_changes`(순수 함수)로 분류 후 upsert. 완전히 같은 행은 쓰지 않고, 닫힘은 `RETURNING`으로 실제 닫힌 id만 이력에 남긴다. 반환값이 `{received, created, updated, reopened, unchanged, closed, previously_active}`로 바뀌었다.
- 테스트: `test_catalog_changes.py` 신규(DB 없이), `test_catalog_db.py`에 이력·조회수 케이스 추가, `test_database.py` 0003 반영.
- 문서: `docs/RECOMMENDATION.md` 2장, README, `docs/DEPLOYMENT.md`.

### 실제 실행한 검증

- 로컬 Docker Desktop(PostgreSQL 17 컨테이너 `db`·`db-test`)에서 실행.
- `python -m unittest discover -s tests -v`: 37개 전부 통과(DB 통합 테스트 포함, `alembic check` 차이 없음).
  - 처음 실행에서 `load.py`가 SQLAlchemy Result를 `dict.update`에 넘겨 실패한 것을 찾아 고쳤다(Result에 `keys()`가 있어 매핑으로 처리됨).
- 개발 DB: `alembic upgrade head` → 0003. `load_catalog --seed` 1회차 created 정책 2,335·프로그램 169, 같은 데이터 2회차 전부 unchanged(이력 추가 없음).

### 남은 작업

- 이력 보관 기간·정리 정책, 찜·신청 기능과 연결한 변경 알림.
- 해시 방식 변경 후 첫 적재에서 기존 행이 모두 `updated`(바뀐 필드 없음)로 한 번 기록된다. 운영 DB가 아직 없어 별도 처리는 하지 않았다.

## 2026-11-19 — 정책·센터 프로그램 추천 파이프라인과 API

- 브랜치: `feat/recommendation-pipeline` (origin/main `d11488c`에서 생성)
- 목적: 로컬 `ai_hackathon` 폴더에서 만든 정책 수집·센터 크롤링·LLM 분류·추천 로직을 저장소 구조로 옮기고, DB 적재와 API로 연결.
- 구현 완료와 배포 구분: 코드·seed 데이터·마이그레이션·API 구현 완료. 스케줄러 연결과 실제 배포·운영 DB 적재는 하지 않았다.

### 결정

- 상태 체크는 `docs/requirements.md` 방식(영역 5문항 + 만족도·바꾸고 싶은 영역·대면 부담·관심 분야). I5 또래 비교 점수는 쓰지 않는다. 진단처럼 보이지 않게, 점수·위험 등급 없이 사용자 답 그대로 영역 수준을 만든다.
- 저장은 PostgreSQL 테이블 하나(`catalog_items`) + JSONB. 필터 컬럼만 컬럼으로 두고 원본은 `payload`. 이유는 docs/RECOMMENDATION.md 2장.
- 추천 계산에는 LLM을 쓰지 않는다(분류만 하루 한 번, 캐시).

### 주요 변경

- `pipeline/`: 정책 fetch·classify, 프로그램 crawl(sync_centers·seoul_orang·gnuboard·merge)·classify, `llm.py`, `paths.py`, `load_catalog.py`, `run_daily.py`.
- `data/seed/`: serving JSON(정책 2,335·프로그램 169), 분류 캐시, 센터 목록. `data/runtime/`은 gitignore.
- `app/catalog/`(모델·행 변환·upsert·후보 조회), `migrations/versions/0002_catalog_items.py`.
- `app/checkin/`, `app/recommend/`, `app/main.py` 라우터 등록.
- `scripts/recommend_demo.py`, `tools/data_check/`.
- 테스트: `test_checkin.py`, `test_recommend_rules.py`, `test_recommend_api.py`, `test_catalog_db.py`, `test_database.py`(0002 반영).
- 문서: `docs/RECOMMENDATION.md` 신규, `POLICY_FIELDS.md`·`CENTER_FIELDS.md`·`DATA_FIELDS.md`·`CRAWLER.md`·`DATA_CHECK.md` 이관(경로 수정), README·`.env.example`·`requirements.txt`(requests, beautifulsoup4).

### 실제 실행한 검증

- 작업 환경에 FastAPI·SQLAlchemy가 없고 패키지 설치가 막혀 있어, 순수 로직 테스트만 로컬에서 실행: `test_checkin`·`test_recommend_rules` 14개 통과.
- `python pipeline/policies/classify.py --no-llm`: 캐시만으로 ok 2,335건 재현, 이전 결과와 같은 보정 건수. 프로그램 classify `--no-llm`: ok 169건.
- `sync_centers --from-seed` 동작, `run_daily` 키 없을 때 정책 단계 실패 후 프로그램 단계 계속 진행 확인.
- `scripts/recommend_demo.py`: 페르소나 5명 결과 확인(예: 관악 고립 페르소나 → 고립·은둔 상담, 심리상담 바우처, 소셜다이닝, 관악 센터 상담 프로그램).
- API·DB 테스트(마이그레이션 0002, upsert·closed 처리·50% 안전장치, DB/파일 결과 일치, API source)는 GitHub Actions PostgreSQL에서 확인한다. 결과는 PR 체크에 기록.

### 발견한 문제

- ok 정책 1,268건이 신청기간(`aplyYmd`)이 이미 지났다. 기본 필터에 마감일 비교를 넣었다.

### 남은 작업

- 매일 실행 스케줄러(서버 안 vs 외부 cron)는 배포 환경을 정한 뒤 결정.
- 프로그램 지역 편중(대부분 서울), 원본 오류 일부, v3 재사용 분류 재검토 옵션.
- AI 비서 대화와 추천 연결, 사용자 저장·인증.

## 2026-11-18 — PostgreSQL 공통 DB 기반

- 브랜치: `chore/database-foundation`
- 목적: 후속 정책 수집과 세션·설문 개발이 공유할 PostgreSQL 연결·요청별 DB 세션·마이그레이션 기반 마련.
- 시작 상태: PR #4 병합 후 최신 origin/main `3998209`에서 생성. 로컬 변경 없음. 이전 README·배포 기준·개발 로그·작업 규칙은 병합된 내용을 보존하고 이어서 갱신했다.
- 구현 완료와 배포 구분: 로컬 DB 기반 구현·검증 완료이며 실제 배포·운영 DB 구성은 수행하지 않았다. 서비스 세션·설문·정책·추천·AI 기능과 테이블은 추가하지 않았다.

### 주요 변경

- `compose.yaml`, `.env.example`: PostgreSQL 17 개발 DB(named volume)와 별도 테스트 DB(tmpfs), 로컬 전용 포트. 실제 비밀번호·URL은 무시되는 로컬 .env에만 생성했다.
- `requirements.txt`: SQLAlchemy, psycopg binary, Alembic 추가.
- `app/config.py`, `app/database.py`, `app/main.py`: SecretStr DATABASE_URL, PostgreSQL URL 검증, 연결 풀, 요청별 세션 의존성, 미커밋 rollback·close, lifespan 종료 dispose. 서버 시작 시 스키마를 변경하지 않음.
- `alembic.ini`, `migrations/`: 공통 Base.metadata 및 이름 규칙, 이후 모델 import와 autogenerate를 위한 환경. 빈 baseline 0001은 기능 테이블 없이 Alembic 버전만 관리.
- `tests/test_database.py`, `.github/workflows/backend.yml`: DB 단위·PostgreSQL 통합 테스트 및 CI 전용 PostgreSQL 서비스.
- `README.md`, `docs/DEPLOYMENT.md`, `AGENTS.md`: 두 팀원 실행 절차, 개발 순서 일치, CLI와 이 대화창의 역할 분담.

### API 변경

- 신규 `GET /readyz`: SELECT 1 성공 시 200 `{"status":"ok"}`, 미설정·연결 실패 시 503 `{"error":{"code":"DATABASE_UNAVAILABLE","message":"Database unavailable"}}`. URL·비밀번호·내부 예외는 응답에 노출하지 않음. 스키마 버전까지 검사하지는 않음.
- 기존 `GET /healthz`: DB 상태와 무관한 프로세스 상태 확인 200 유지. /docs와 OpenAPI에 readyz 포함.

### 실제 실행한 검증

- SQLAlchemy 2.0.58, psycopg 3.3.9, Alembic 1.20.1 설치 완료.
- `docker compose --profile test up -d --wait db-test`: PostgreSQL 17 healthy. 개발 DB는 시작하지 않고 별도 컨테이너·dos_tres_test DB·테스트 포트에서만 테스트했다.
- `python -m unittest discover -s tests -v`: 기존 5개와 신규 5개, 총 10개 통과(skip 없음).
- 통합 검증: 실제 DB 연결, readyz 200, 존재하지 않는 DB 역할 인증 실패와 readyz 503, 실패 응답 비밀값 미노출, DB 실패 시 healthz 200, 요청별 세션 분리, 예외 후 미커밋 트랜잭션 rollback·풀 반환, 앱 종료 dispose 확인.
- Alembic Python 명령 API로 upgrade head → check → downgrade base → upgrade head → 재upgrade 실행. 버전 0001, autogenerate 차이 없음, alembic_version 외 기능 테이블 없음 확인. 앱 시작 전후 테이블 목록 동일 확인.
- 실제 Uvicorn 서버도 전용 테스트 DB URL을 주입해 실행했다. 정상 연결과 인증 실패 각각 HTTP /readyz 200·503, /healthz 200, /docs 200, OpenAPI readyz 경로 확인 후 서버 종료. 개발 DB 데이터에는 접근하지 않았다.
- `python -m pip check`: 의존성 충돌 없음. `git diff --check`: 통과. .env·.venv·Python 캐시 제외 확인.
- 기존 Starlette TestClient의 httpx 사용 중단 예정 경고는 남아 있으며 테스트 성공과 별도로 추후 정비할 사항이다.
- GitHub CI는 PR 생성 후 해당 커밋의 체크에서 확인한다. 로컬 성공을 CI·배포 완료로 간주하지 않는다.

### 팀원 인수인계와 남은 작업

각자 Python 3.13 가상환경에 requirements-dev.txt를 설치한다. 기존 .env를 덮어쓰지 말고 예시에 추가된 개발·테스트 비밀번호, URL, 포트를 각각 채운다. 실제 값은 공유·커밋하지 않는다. `docker compose up -d --wait db` → `python -m alembic upgrade head` → `python -m alembic current` → Uvicorn 실행 순서다. 전용 DB 테스트는 `docker compose --profile test up -d --wait db-test` 후 unittest 명령으로 실행한다. TEST_DATABASE_URL이 없으면 통합 테스트 3개가 skip되므로 DB 검증 완료로 기록하면 안 된다. 종료는 API Ctrl+C, 각 DB는 compose stop을 사용한다. 상세 명령과 병렬 마이그레이션 협업 절차는 README를 따른다.

다음 순서는 **공통 DB·API 구조 → 정책 수집 / 세션·설문 병렬 개발 → 추천·AI 대화 → 프론트 연결·배포**다. 이번 PR 리뷰 반영과 기능 API 계약 합의 후 두 팀원이 병렬 개발한다. 인증·개인 기록 접근 제어, 기능별 모델·revision, 실제 AI 제공업체와 운영 배포는 후속 범위다. CLI는 구현·문서·검증·커밋·푸시·PR까지만 진행하며, 이 대화창에서 PR 검토·병합·다음 작업을 지정한다.

## 2026-11-18 — FastAPI 실행 기반 구축 및 PR 준비

- 브랜치: `chore/backend-bootstrap`
- 목적: 팀원이 동일한 절차로 backend를 설치·실행하고 프론트 연결을 준비할 수 있는 최소 실행 기반 마련.
- 시작 상태: README와 요구사항·배포 기준 문서만 존재. 기존 작업 트리 변경 없음. 최신 `origin/main`의 `bfc816c2e90234457136a4ef8bf57c25ce2dc50a`에서 브랜치 생성.

### 주요 변경 파일

| 파일 | 변경 |
| --- | --- |
| app/__init__.py, app/main.py | FastAPI 앱, healthz, CORS, HTTP·검증·서버 오류 처리 |
| app/config.py, .env.example | APP_ENV, JSON 배열 ALLOWED_ORIGINS, 환경변수 우선 적용 및 시작 시 검증 |
| requirements.txt, requirements-dev.txt, .gitignore | 실행 의존성 고정, 테스트용 httpx, 로컬 환경·캐시 제외 |
| tests/test_bootstrap.py, .github/workflows/backend.yml | 자동 테스트 및 Python 3.13 CI, pip check |
| README.md, docs/DEPLOYMENT.md | 실행 절차·구현 현황 정리, 과거 미구현 설명 수정, 후속 계획 분리 |
| AGENTS.md, docs/DEVELOPMENT_LOG.md | 문서 갱신·검증·커밋·푸시·PR·리뷰 대기 규칙 및 인수인계 기록 |

### API 변경

- `GET /healthz`: HTTP 200, `{"status":"ok"}`. 외부 서비스 상태나 설정값은 반환하지 않음.
- `GET /docs`: Swagger UI HTML, `GET /openapi.json`: OpenAPI 명세.
- 앱 오류: `{"error":{"code":"...","message":"..."}}`. HTTP 오류는 `HTTP_상태코드`, 검증 오류는 `VALIDATION_ERROR`(422), 내부 오류는 `INTERNAL_SERVER_ERROR`(500).
- HTTP 오류 헤더 보존. 검증 입력값과 내부 예외 내용은 응답에서 제외.
- 로컬 Vite origin 두 개만 기본 허용하며 credentials는 비활성화. CORS preflight 오류는 미들웨어의 400 텍스트 응답.

### 실제 검증과 결과

- Python 3.13.3 가상환경에서 `python -m pip install -r requirements-dev.txt` 설치 완료.
- `python -m unittest discover -s tests -v`: 5개 테스트 통과. healthz·문서·OpenAPI, CORS 허용/거부, 환경 설정 우선순위·검증, 404·405·422·500 및 헤더 보존 확인. PR 준비 시 재실행해 통과.
- `python -m pip check`: 의존성 충돌 없음. `git diff --check`: 통과.
- `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`으로 실제 서버 실행 후 httpx HTTP 요청 검증: /healthz 200 및 예상 JSON, /docs 200 HTML, /openapi.json 200 및 healthz 경로, 허용 origin OPTIONS 200과 CORS 헤더, 없는 경로 404 및 공통 JSON 확인. 검증 후 서버 정상 종료.
- `git check-ignore`로 .env, .env.local, .venv 및 Python 캐시 제외 확인. 커밋 대상은 소스·문서·예시 설정·CI만 포함.
- 테스트 성공과 별개로 Starlette TestClient의 httpx 사용 중단 예정 경고가 있음. 향후 테스트 클라이언트 의존성 정비 시 확인할 사항이며 이번에는 추가 라이브러리를 도입하지 않음.
- GitHub CI 결과는 PR의 해당 커밋 체크에서 확인한다. CI 성공은 배포 완료를 의미하지 않는다.

### 이어서 실행하는 절차

저장소 루트에서 Python 3.13으로 진행한다. 기존 .env가 있으면 덮어쓰지 말고 .env.example과 비교한다.

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
# 최초 설정 시에만 실행
cp .env.example .env
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

다른 터미널에서 /healthz와 /docs에 접속하고 README의 검증 명령을 실행한다. 프론트 포트가 다르면 ALLOWED_ORIGINS의 JSON 배열에 실제 origin을 넣고 서버를 재시작한다. 프로세스 환경변수가 .env보다 우선한다. 운영용 바인딩·포트 명령은 README에 별도로 기록했다.

### 남은 작업 및 상태

로컬 실행 기반 구현·검증 완료. 이 PR의 리뷰를 기다리고 리뷰 결과를 반영한 후 다음 개발을 시작한다. 대화 API 계약·프론트 공통 API 모듈, 실제 AI 제공업체·모델 연결, HTTPS 미리보기 배포, 인증·DB 및 개인 기록 저장은 후속 계획이다. DB·세션·설문·정책·AI 기능과 실제 배포는 이번 작업에 포함되지 않는다. 배포 제공업체·운영 URL은 미정이다.
