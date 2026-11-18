# 둘셋 · DOS TRES — Backend

청년 정책 탐색과 신청 준비를 돕는 둘셋의 Python + FastAPI 백엔드입니다.
AI 에이전트도 이 저장소 안에서 개발합니다.
프론트엔드: [dos-tres/frontend](https://github.com/dos-tres/frontend).

## 현재 구현

- FastAPI 앱, Swagger, 환경 설정, CORS, 요청 ID, 공통 오류 응답
- SQLAlchemy + Alembic. 로컬 SQLite / 배포용 PostgreSQL 연결 설정
- 익명 세션 생성·만료 확인·삭제, 세션별 기본 프로필 조회·전체 교체
- 만료 세션 정리 명령, 자동 테스트와 SQLite·PostgreSQL CI

설문 응답 저장, 정책 수집·추천, 실제 LLM 대화, 프론트 API 연결, 배포는 후속 작업입니다.
현재 프로필은 나이·지역·취업·주거·관심 분야만 다룹니다. I5 점수나 진단을 생성하지 않습니다.

## 로컬 실행

Python 3.12 또는 3.13, [uv](https://docs.astral.sh/uv/getting-started/installation/)가 필요합니다.
아래 명령은 macOS·Linux·WSL 기준이며 저장소 루트에서 실행합니다.

```bash
git clone https://github.com/dos-tres/backend.git
cd backend
uv sync --locked
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Windows PowerShell에서는 복사 명령만 `Copy-Item .env.example .env`로 바꿉니다.
`.env`와 실제 키·토큰·사용자 DB는 커밋하지 않습니다.

- Swagger: http://127.0.0.1:8000/docs
- 상태: http://127.0.0.1:8000/healthz
- DB 준비: http://127.0.0.1:8000/readyz

Swagger에서 `POST /api/v1/sessions` → 응답의 `access_token` 복사 → 상단
**Authorize**에 토큰만 입력 → `PUT /api/v1/profile` → `GET /api/v1/profile` 순서로
확인할 수 있습니다. 세션 삭제는 `DELETE /api/v1/sessions/current`입니다.
토큰 없이 프로필에 접근하면 401을 반환합니다.

## 설정

| 환경변수 | 기본값 / 의미 |
| --- | --- |
| APP_ENV | local. test / staging / production 지원 |
| ALLOWED_ORIGINS | JSON 배열. localhost:5173·127.0.0.1:5173 허용 |
| DATABASE_URL | sqlite:///./dulset.db. 배포는 postgresql+psycopg://… |
| SESSION_TTL_HOURS | 168시간. 발급 시점 기준 고정 만료 |
| PORT | 컨테이너 포트 8000. 로컬 CLI에서는 --port로 지정 |

staging·production에서는 외부 PostgreSQL과 명시한 HTTPS origin이 필요합니다.
DB는 현재 요청하는 환경에서 접근 가능해야 하며 운영 비밀값은 서버 환경에서 주입합니다.
`.env.example`을 그대로 운영에 사용하지 않습니다.

## 검증과 스키마 변경

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv run alembic check
```

테스트는 임시 SQLite DB를 사용합니다. CI는 PostgreSQL 16에서도 같은 테스트를 실행합니다.
`TEST_DATABASE_URL`을 지정하면 **테스트마다 그 DB의 앱 테이블을 삭제·재생성**하므로
폐기 가능한 전용 테스트 DB만 지정합니다. 실제 사용자 DB에는 지정하지 않습니다.

테이블을 바꿀 때 모델과 마이그레이션을 함께 변경합니다.

```bash
uv run alembic revision --autogenerate -m "describe schema change"
uv run alembic upgrade head
uv run python -m app.cleanup
```

cleanup은 만료 세션과 연결 프로필만 지웁니다. 현재 자동 실행은 설정하지 않았습니다.
토큰을 잃어버린 익명 세션은 복구할 수 없습니다.

## 컨테이너와 배포 준비

```bash
docker build -t dos-tres-backend .
docker run --rm --env-file .env dos-tres-backend uv run --no-sync alembic upgrade head
docker run --rm --env-file .env -p 8000:8000 dos-tres-backend
```

위 배포 흐름은 `.env`에 컨테이너에서 접근 가능한 **외부 PostgreSQL**이 설정된 경우입니다.
로컬 SQLite는 컨테이너 재생성 시 사라지므로 배포 데이터 저장에 사용하지 않습니다.
스키마 업그레이드는 배포 시 한 번 실행하고 서버 프로세스와 분리합니다.
컨테이너 빌드·실제 배포 검증은 아직 완료하지 않았습니다.
공개 배포 전 HTTPS·호출 제한·저장 안내·정기 만료 정리·운영 DB 보관 정책을 연결합니다.

## 코드와 협업

| 경로 | 역할 |
| --- | --- |
| app/api/ | 라우터 및 세션 접근 확인 |
| app/core/ | 설정, DB, 오류 |
| app/main.py | 앱 조립 |
| app/models.py | SQLAlchemy 테이블 |
| app/schemas.py | API 요청·응답 |
| app/cleanup.py | 만료 세션 정리 |
| migrations/ | Alembic 스키마 이력 |
| tests/ | API·설정·보관 검증 |

최신 main에서 목적별 `feat/<short-kebab-case>` 브랜치를 만들고 PR로 반영합니다.
커밋·PR 제목은 `type(scope): 설명` 형식을 사용합니다.
정책 수집과 설문 저장은 병렬 개발 가능하며 공통 모델·설정·마이그레이션 변경은 조율합니다.

- [현재 API 계약·다음 작업 분담](docs/API.md)
- [제품 요구사항](docs/requirements.md)
- [배포 기준과 구현 현황](docs/DEPLOYMENT.md)
