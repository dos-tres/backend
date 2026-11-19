# 둘셋 · DOS TRES — Backend

둘셋(DOS TRES)의 백엔드 및 AI 에이전트 저장소입니다.

## 기술 스택

2026-11-18 결정 기준입니다.

| 구분 | 언어 | 프레임워크·도구 |
| --- | --- | --- |
| 프론트엔드 | TypeScript | React + Vite |
| 백엔드 API | Python | FastAPI |
| AI 에이전트 | Python | 백엔드 저장소 내부에서 함께 개발 |

프론트엔드는 [dos-tres/frontend](https://github.com/dos-tres/frontend)에서 관리합니다. 기본 DB는 PostgreSQL 17입니다. AI 모델·에이전트 라이브러리·인증 방식·전화 연동 서비스와 운영 DB 제공업체는 아직 미정입니다.

## 요구사항

[백엔드 및 AI 비서 요구사항](docs/requirements.md)

- 회원가입·첫 이용 시 선택형 현재 상태 체크
- 짧은 말과 선택지로 진행하는 AI 비서 대화
- 정책·프로그램 탐색과 조건 확인
- 전화 문의 대행, 신청 준비, 일정·참여 이력 관리

## 현재 상태

FastAPI 실행 기반을 구현했습니다. GET /healthz, Swagger UI(/docs), 환경 설정, 개발용 CORS와 공통 오류 응답을 제공합니다. PostgreSQL·SQLAlchemy 연결, 요청별 DB 세션, Alembic과 DB 준비 상태 확인 GET /readyz를 추가했습니다.

정책·센터 프로그램 추천을 구현했습니다(브랜치 `feat/recommendation-pipeline`, 리뷰 대기). 자세한 내용은 [추천 문서](docs/RECOMMENDATION.md)에 있습니다.

- 구현 완료: 온통청년 정책 수집·청년센터 프로그램 크롤링·LLM 분류 파이프라인(`pipeline/`), `catalog_items` 테이블(migration 0002)과 적재, 변경 이력 `catalog_item_changes`(migration 0003, source_hash 비교로 created·updated·reopened·closed 기록), 상태 체크 문항·요약 API, 추천 API. DB가 없거나 비어 있으면 `data/seed/`의 serving JSON으로 같은 계산을 합니다.
- 계획: 매일 실행 스케줄러 연결, 운영 DB 적재, AI 비서 대화 연결. 서비스 세션·사용자 저장·인증은 아직 없습니다.
- 배포: 하지 않았습니다.

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET | /api/checkin/questions | 상태 체크 문항 |
| POST | /api/checkin/summary | 답변 → 영역 수준 요약 (점수·위험 등급 없음) |
| POST | /api/recommendations | 기본 정보 + 답변 → 정책 6 · 프로그램 4 |

### 데이터 파이프라인

정책(온통청년 API)과 청년센터 프로그램(크롤링)을 모아 LLM으로 분류하고, 서비스용 JSON과 DB(`catalog_items`)로 만듭니다. 운영(최종) 기준을 먼저 적고, 개발할 때 쓰는 임시 방법을 뒤에 적습니다.

#### 운영 기준 (최종)

```text
[배포할 때 한 번]  python -m alembic upgrade head          (서버 시작과 분리해 명시적으로)
[매일 한 번]       python -m pipeline.run_daily
   정책  1 fetch → 2 classify ─────────────────────┐
   센터  3 sync_centers → 4 seoul_orang → 5 gnuboard │→ data/runtime/serving/*.json → 8 load_catalog → PostgreSQL
         → 6 merge → 7 classify ─────────────────────┘                                  (catalog_items + 변경 이력)
[요청마다]         POST /api/recommendations → DB 조회 (DB가 없거나 비면 serving JSON으로 같은 계산)
```

| 순서 | 단계 (`run_daily`가 순서대로 실행) | 필요한 키 | 결과 (`data/runtime/` 아래) |
| --- | --- | --- | --- |
| 1 | 정책 수집 `pipeline/policies/fetch.py` | 정책 | `policies/policies_raw.jsonl`(API 원본), `policies.csv`(정리본), `policy_regions.csv`, `policy_codes.csv`, `fill_rate.csv` |
| 2 | 정책 분류 `pipeline/policies/classify.py` | LLM | `policies/policy_tags.csv`, **`serving/policies_serving.json`** |
| 3 | 센터 목록 `pipeline/programs/crawl/sync_centers.py` | 센터 | `programs/centers.csv`, `centers_changes.csv` |
| 4 | 서울청년센터 `pipeline/programs/crawl/seoul_orang.py` | 없음 | `programs/seoul_orang/programs.csv` |
| 5 | 그누보드 센터 `pipeline/programs/crawl/gnuboard.py` | 없음 | `programs/gnuboard/sites.csv`, `boards.csv`, `posts.csv` |
| 6 | 프로그램 통합 `pipeline/programs/crawl/merge.py` | 없음 | `programs/programs.csv` |
| 7 | 프로그램 분류 `pipeline/programs/classify.py` | LLM | `programs/program_tags.csv`, **`serving/programs_serving.json`** |
| 8 | DB 적재 `python -m pipeline.load_catalog` | 없음 | DB `catalog_items`, `catalog_item_changes` |

| 키 (`.env` 또는 배포 환경의 비밀 설정) | 쓰는 단계 |
| --- | --- |
| `YOUTH_POLICY_API_KEY` | 1 정책 수집 (온통청년 청년정책 API) |
| `YOUTH_CENTER_API_KEY` | 3 센터 목록 (온통청년 청년공간 API) |
| `GMS_KEY`(또는 `OPENAI_API_KEY`). 선택: `OPENAI_BASE_URL`(비우면 GMS 주소), `LLM_MODEL`(비우면 gpt-4.1-mini) | 2·7 분류 |
| `DATABASE_URL` | 8 DB 적재 (앱과 같은 설정) |

운영에서 지켜지는 것 (구현 완료):

- 실패 격리: 한 단계가 실패하면 그 묶음(정책 / 프로그램)의 뒤 단계와 DB 적재를 건너뛰고, DB에는 마지막으로 성공한 데이터가 남습니다. 종료 코드는 실패가 있으면 1입니다.
- 적재 안전장치: 종류별 한 트랜잭션. 오늘 건수가 기존 활성 건수의 50% 미만이면 수집 이상으로 보고 적재하지 않습니다(`load_catalog --force`로만 무시).
- 변경 감지: `source_hash`로 새로 생김·내용 바뀜·다시 열림·닫힘을 나눠 `catalog_item_changes`에 기록합니다. 오늘 목록에 없는 항목은 지우지 않고 `closed`로 둡니다.
- 비용: LLM 분류는 캐시(`cache/*_tags_cache.jsonl`)로 새 글·바뀐 글만 호출합니다. 처음에는 `data/seed/cache/`에서 시작합니다.
- 증분 수집: 서울청년센터·그누보드는 이미 본 글을 건너뜁니다. 서울청년센터 결과 파일이 없으면(첫 실행) 자동으로 목록 전체를 받습니다.

배포 때 정할 것 (아직 없음): 매일 실행 위치(서버 안 스케줄러 vs 외부 cron), 운영 DB, `data/runtime/`을 실행 사이에 유지할 저장소(지워지면 분류 캐시·증분 기준이 사라져 LLM 비용과 수집 시간이 늘어남), 실패 알림. 자세한 기준은 [배포 문서](docs/DEPLOYMENT.md).

프로그램은 서울청년센터 통합 사이트와 그누보드로 만든 센터 홈페이지만 수집해서 대부분 서울입니다([추천 문서](docs/RECOMMENDATION.md) 7장). 필드 정의는 [DATA_FIELDS](docs/DATA_FIELDS.md), 원본 API 필드는 [POLICY_FIELDS](docs/POLICY_FIELDS.md)·[CENTER_FIELDS](docs/CENTER_FIELDS.md), 크롤러는 [CRAWLER](docs/CRAWLER.md)에 있습니다.

#### 개발할 때 (임시)

키·비용·시간을 아끼거나 한 단계만 확인할 때 씁니다. 운영 매일 실행에는 쓰지 않습니다. 설치(아래 "설치와 로컬 실행")와 DB 시작(`docker compose up -d --wait db`, `python -m alembic upgrade head`)은 먼저 해 둡니다.

```bash
# 키 없이: 저장소에 포함된 결과(data/seed/serving, 정책 2,335 · 프로그램 169, 2026-11-19 기준)를 DB에
python -m pipeline.load_catalog --seed
python scripts/recommend_demo.py                         # 페르소나 5명 추천 결과

# 전체를 돌리되 일부만
python -m pipeline.run_daily --no-llm                    # LLM 없이 분류 캐시로만 (새 글은 분류 안 됨)
python -m pipeline.run_daily --skip-crawl                # 센터 크롤링 빼고 정책만 갱신
python -m pipeline.run_daily --no-load                   # DB 적재 없이 파일만

# 한 단계씩
python pipeline/policies/classify.py --limit 40          # 40건만 LLM 분류해 결과 확인
python pipeline/policies/classify.py --dry-run           # LLM 호출 없이 프롬프트만 출력
python pipeline/programs/crawl/sync_centers.py --from-seed   # 센터 API 키 없이 centers.csv 만들기 (4·5단계 준비)
python pipeline/programs/crawl/seoul_orang.py --branch joonggu --max-detail 20   # 서울 한 지점만
python pipeline/programs/crawl/gnuboard.py --site ch2030youth.kr                 # 그누보드 사이트 하나만
python -m pipeline.load_catalog --kind program           # 한 종류만 적재
```

- 모든 명령은 저장소 루트에서 실행합니다. 결과는 `data/runtime/`(Git 제외)에 쌓이고 `data/seed/`는 바꾸지 않습니다.
- `data/seed/`는 첫 실행·CI·DB 없는 환경용입니다. 갱신이 필요하면 `data/runtime/serving/`과 `cache/`에서 복사해 PR로 올립니다.
- Windows PowerShell에서는 가상환경을 `.venv\Scripts\Activate.ps1`로 켜고, 위 명령의 경로 구분자는 그대로(`/`) 써도 됩니다.

#### DB에서 결과 보기

```bash
# 종류·상태별 건수
docker compose exec db psql -U dos_tres -d dos_tres -c "SELECT kind, status, count(*) FROM catalog_items GROUP BY 1, 2 ORDER BY 1, 2"
# 정책 몇 건 (필터 컬럼)
docker compose exec db psql -U dos_tres -d dos_tres -c "SELECT id, title, age_min, age_max, deadline, domains FROM catalog_items WHERE kind = 'policy' LIMIT 10"
# 원본 전체(payload) 한 건
docker compose exec db psql -U dos_tres -d dos_tres -c "SELECT jsonb_pretty(payload) FROM catalog_items WHERE kind = 'program' LIMIT 1"
# 최근 변경 이력 (created / updated / reopened / closed)
docker compose exec db psql -U dos_tres -d dos_tres -c "SELECT changed_at::date, kind, change_type, count(*) FROM catalog_item_changes GROUP BY 1, 2, 3 ORDER BY 1 DESC"
```

DBeaver·pgAdmin 같은 도구로 보려면 `127.0.0.1:5432`, DB·사용자 `dos_tres`, 비밀번호는 각자 `.env`의 `POSTGRES_PASSWORD`로 접속합니다. 테이블 컬럼 설명은 [추천 문서](docs/RECOMMENDATION.md) 2장에 있습니다.

## 설치와 로컬 실행

Python 3.13을 사용합니다. 저장소 루트에서 실행합니다.

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
# .env가 없는 최초 설치 시에만 복사
cp .env.example .env
# 아래 DB 설정·실행·마이그레이션 절차를 먼저 진행
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

실행만 필요한 환경은 `requirements.txt`를 설치합니다. 실행 의존성은 FastAPI, ASGI 서버 Uvicorn, 설정 및 .env 로딩용 pydantic-settings, SQLAlchemy, PostgreSQL 드라이버 psycopg, 마이그레이션 도구 Alembic이며, httpx는 테스트에만 사용합니다. 종료는 Ctrl+C입니다.

외부 접속과 실행 환경의 포트가 필요한 경우 reload 없이 실행합니다. HOST·PORT는 아래 셸 명령에서 읽으며 .env의 앱 설정과 별개입니다.

```bash
python -m uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
```

## 로컬 PostgreSQL과 마이그레이션

두 팀원 모두 각자 PC에서 같은 절차로 진행합니다. Docker Desktop 또는 Docker Engine + Compose가 필요합니다. 실제 비밀번호와 URL은 각자의 .env에만 저장하고 공유·커밋하지 않습니다. 기존 .env는 보존하고 .env.example에서 추가된 키만 옮깁니다.

1. `python -c 'import secrets; print(secrets.token_hex(24))'`로 서로 다른 개발·테스트용 로컬 비밀번호를 생성합니다.
2. .env의 `POSTGRES_PASSWORD`, `POSTGRES_TEST_PASSWORD`에 각각 넣습니다. `DATABASE_URL`과 `TEST_DATABASE_URL`도 .env.example에 주석으로 적힌 형식대로 작성합니다. 특수문자가 있는 비밀번호는 URL 인코딩합니다. DB 이름·사용자는 개발용 dos_tres, 테스트용 dos_tres_test입니다.
3. 아래 명령으로 개발 DB를 시작하고 스키마 버전을 적용한 뒤 API 서버를 실행합니다.

```bash
docker compose up -d --wait db
python -m alembic upgrade head
python -m alembic current
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

개발 포트는 POSTGRES_PORT(기본 5432), 테스트 포트는 POSTGRES_TEST_PORT(기본 55432)입니다. 포트를 바꾸면 해당 URL도 함께 바꿉니다. 두 포트 모두 로컬 인터페이스에만 노출합니다. Compose 변수는 컨테이너 설정용이며 앱은 DATABASE_URL을 읽습니다. DATABASE_URL이 비어 있으면 /healthz는 200, /readyz는 503입니다. 잘못된 URL 형식은 시작 시 거부합니다. APP_ENV는 환경 식별자이며 DB나 CORS 값을 자동 전환하지 않습니다.

개발 DB 데이터는 Docker named volume에 유지됩니다. `docker compose stop db`로 중지하고 `docker compose up -d --wait db`로 재개합니다. 초기화된 볼륨의 비밀번호는 .env 수정만으로 바뀌지 않으므로 기존 자격 증명을 유지하거나 별도 DB 변경 절차를 사용합니다. `down -v`는 데이터를 삭제하므로 일반 종료에 사용하지 않습니다.

서버는 스키마를 자동 생성·변경하지 않습니다. baseline 0001은 Alembic 버전 테이블만, 0002는 정책·프로그램 카탈로그 `catalog_items`를, 0003은 변경 이력 `catalog_item_changes`를 만듭니다. 이후 모델은 app.database.Base를 상속하고 migrations/env.py에 해당 모듈을 import한 뒤 아래 절차를 사용합니다.

```bash
python -m alembic revision --autogenerate -m "describe schema change"
# 생성된 upgrade/downgrade 코드를 검토한 뒤 실행
python -m alembic upgrade head
python -m alembic check
```

정책 담당자와 세션·설문 담당자는 기능별 브랜치에서 모델·마이그레이션을 함께 관리합니다. PR 반영 후 main의 마이그레이션 head를 확인하고, 동시 변경으로 head가 갈라지면 팀 리뷰를 통해 merge revision을 추가합니다. 이미 공유한 revision을 임의 수정하지 않습니다. 운영 마이그레이션은 백업·검토 후 명시적으로 실행합니다.

동기 SQLAlchemy 세션은 `Depends(app.database.get_db)`로 요청마다 생성합니다. 동기 DB 작업은 `def` 라우트/의존성에서 실행해 이벤트 루프를 막지 않습니다. 성공한 쓰기는 서비스 계층에서 명시적으로 commit해야 하며, 의존성은 종료 시 close와 미커밋 트랜잭션 rollback을 수행합니다. 앱 정상 종료 시 engine을 dispose합니다. 연결·풀 대기·쿼리 시간 제한은 각각 3초이며, 전체 readiness 요청의 엄밀한 3초 제한은 아닙니다.

## 전용 DB 테스트

```bash
docker compose --profile test up -d --wait db-test
python -m unittest discover -s tests -v
python -m pip check
git diff --check
docker compose --profile test stop db-test
```

테스트 DB는 별도 컨테이너와 tmpfs를 사용하며 중지 시 데이터가 사라집니다. 개발 DB는 테스트 중 시작할 필요가 없습니다. TEST_DATABASE_URL은 반드시 전용 dos_tres_test DB를 가리켜야 하고 개발 URL과 같으면 테스트를 거부합니다. 테스트는 baseline upgrade → downgrade → 재upgrade, 스키마 차이 없음, 실제 연결 성공·인증 실패, readyz 200/503, 세션 분리·rollback·연결 반환, 종료 시 dispose를 확인합니다. CI의 trust 인증은 폐기되는 테스트 서비스에만 사용하며 개발·배포에 적용하지 않습니다.

`/readyz`는 SELECT 1 성공 시 200 `{"status":"ok"}`, 실패 시 503 `{"error":{"code":"DATABASE_UNAVAILABLE","message":"Database unavailable"}}`를 반환합니다. 실패 응답에는 URL·비밀번호·내부 예외를 포함하지 않습니다. `/healthz`는 기존 프로세스 상태 확인이며 DB가 없어도 200입니다. `/readyz`는 스키마 버전이나 기능 데이터까지 검사하지 않으므로 배포 시 Alembic 적용 확인은 별도로 필요합니다.

## 환경 설정과 프론트 연결

설정 우선순위는 프로세스 환경변수 → 저장소 루트의 .env → 기본값입니다. 설정 변경 후 서버를 재시작합니다. 실제 .env는 Git에서 제외합니다.

| 변수 | 기본값 | 형식 |
| --- | --- | --- |
| APP_ENV | local | local / staging / production |
| DATABASE_URL | 빈 문자열 | postgresql+psycopg URL; 서버 전용 비밀 설정 |
| ALLOWED_ORIGINS | localhost:5173 및 127.0.0.1:5173의 HTTP origin | JSON 문자열 배열 |

```dotenv
APP_ENV=local
ALLOWED_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
```

origin에는 프로토콜·호스트·포트만 넣습니다. 경로·끝 슬래시·와일드카드는 허용하지 않습니다. 잘못된 설정은 시작 시 오류로 처리합니다. 프론트의 실제 Vite 포트가 달라지면 해당 origin을 명시적으로 추가합니다. 미리보기 환경에서도 실제 프론트 origin만 지정합니다. `[]`는 모든 cross-origin 허용을 끕니다. 쿠키 등 credentials는 허용하지 않으며 인증 도입 시 다시 결정합니다. CORS는 브라우저 정책이며 API 접근 인증 수단은 아닙니다.

프론트는 공개 설정 `VITE_API_BASE_URL=http://127.0.0.1:8000`을 공통 API 모듈에서 사용합니다. 이번 변경에는 프론트 코드 수정이나 배포가 포함되지 않습니다.

## 확인과 테스트

서버 실행 후 별도 터미널에서 확인합니다.

```bash
curl -i http://127.0.0.1:8000/healthz
curl -i http://127.0.0.1:8000/readyz
curl -i http://127.0.0.1:8000/docs
curl -i http://127.0.0.1:8000/openapi.json
curl -i -X OPTIONS http://127.0.0.1:8000/healthz \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: GET'
python -m unittest discover -s tests -v
python -m pip check
git diff --check
```

healthz는 HTTP 200 및 `{"status":"ok"}`를 반환합니다. 외부 서비스 상태나 비밀 설정은 포함하지 않습니다. /docs는 HTTP 200 HTML을 제공하며, 브라우저에서 Swagger UI를 사용할 수 있습니다(기본 Swagger 정적 리소스는 CDN에서 로드). /openapi.json은 API 명세를 제공합니다. 허용 origin의 preflight는 200과 `Access-Control-Allow-Origin`을 반환합니다. 허용하지 않은 origin에는 허용 헤더가 붙지 않습니다.

자동 테스트는 healthz·문서·OpenAPI, 환경변수 우선순위·검증, CORS 허용/거부, 404·405·422·500 오류를 확인합니다. DB 테스트는 TEST_DATABASE_URL(프로세스 환경변수 우선, 없으면 .env)을 사용합니다. 미설정 시 DB 통합 테스트 3개가 skip되므로 DB 검증 완료로 취급하지 않습니다. GitHub Actions는 전용 PostgreSQL 서비스에서 DB 통합 테스트까지 실행합니다.

## 공통 오류 응답

앱의 HTTP 오류(404·405 등), 요청 검증 오류(422), 처리되지 않은 서버 오류(500)는 다음 JSON 형식을 사용하며 HTTP 상태 코드를 유지합니다.

```json
{"error":{"code":"HTTP_404","message":"Not Found"}}
```

요청 검증 오류는 `VALIDATION_ERROR` / `Request validation failed`, 서버 오류는 `INTERNAL_SERVER_ERROR` / `Internal server error`입니다. 검증 입력값·내부 예외 내용은 응답에 넣지 않습니다. HTTP 예외의 Allow·WWW-Authenticate 같은 헤더는 보존합니다. CORS preflight 실패는 CORS 미들웨어의 HTTP 400 텍스트 응답이며 이 JSON 계약에서 제외합니다.

구현 기준: FastAPI 공식 문서의 [환경 설정](https://fastapi.tiangolo.com/advanced/settings/), [CORS](https://fastapi.tiangolo.com/tutorial/cors/), [오류 처리](https://fastapi.tiangolo.com/tutorial/handling-errors/).

## 배포를 고려한 개발

[배포를 고려한 개발 기준](docs/DEPLOYMENT.md)을 따릅니다. 로컬에서 실제 AI 대화 연결을 먼저 검증한 뒤 HTTPS 미리보기 배포로 확장합니다. 서버 비밀 설정과 공개 frontend 환경변수를 분리하고, 개인 기록 저장은 인증·영속 저장소와 함께 구현합니다.

현재 배포 제공업체와 운영 URL은 미정이며, 배포나 실제 AI 연동이 완료된 상태는 아닙니다.

## 다음 개발 단계

공통 DB·API 구조 → 정책 수집 / 세션·설문 병렬 개발 → 추천·AI 대화 → 프론트 연결·배포 순서로 진행합니다.

1. 이번 공통 DB 기반 PR을 리뷰하고 결과를 반영합니다. 공통 API 계약은 기능 구현 전에 합의합니다.
2. 정책 수집과 세션·설문을 두 팀원이 병렬 개발합니다. 저장되는 개인 기록에는 인증과 사용자별 접근 제어를 함께 설계합니다.
3. 추천과 실제 AI 대화, 실패·시간 초과 처리를 구현합니다.
4. 프론트 연결을 검증하고 HTTPS 미리보기·운영 배포로 확장합니다.

위 단계는 계획이며 이번 실행 기반 구현에 포함되지 않습니다. 작업 기록과 인수인계 절차는 [개발 로그](docs/DEVELOPMENT_LOG.md), 저장소 작업 규칙은 [AGENTS.md](AGENTS.md)를 확인합니다.
