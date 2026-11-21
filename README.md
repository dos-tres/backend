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

- 구현 완료: 온통청년 정책 수집·청년센터 프로그램 크롤링·LLM 분류 파이프라인(`pipeline/`), `catalog_items` 테이블(migration 0002)과 적재, 변경 이력 `catalog_item_changes`(migration 0003, source_hash 비교로 created·updated·reopened·closed 기록), 상태 체크 문항·요약 API, 추천 API, 거주지 목록 API(옛 행정코드로 표시된 정책도 새 구에 연결). DB가 없거나 비어 있으면 `data/seed/`의 serving JSON으로 같은 계산을 합니다.
- 구현 완료(테이블만): 회원 테이블 `users`·`user_profiles`·`user_consents`·`checkin_responses`(migration 0004). 가입·로그인·프로필 저장 API와 인증은 아직 없습니다. 로그인 수단·세션 테이블은 로그인 방식이 정해지면 추가하며, 계획은 모델 파일 주석에 적어 두었습니다. 전체 테이블 설명은 [DB 테이블 안내](docs/DATABASE.md).
- 구현 완료(브랜치 `feat/ai-chat`, 리뷰 전): AI 비서 대화 `POST /api/chat`. 위기 신호는 규칙으로 먼저 확인해 109 등 연락처를 안내하고, LLM은 사용자 말에서 상태 체크 답·관심 분야·찾는 지원을 알아듣기만 합니다. 추천·검색 결과는 규칙 엔진과 DB에서 나옵니다. 말투는 일을 대신 해 주고 결과를 알려 주는 비서(해요체, 말풍선 여러 개, 결과 → 다음 행동 제안 버튼)이고, 결과 말풍선은 서버가 실제 결과로 만듭니다. 검증: 위기 표현 32/32 탐지·오탐 0, LLM 점검 28개 × 3회 84/84, 여러 턴 시나리오 19개([대화 시나리오](docs/CHAT_SCENARIOS.md)), 응답 중앙값 약 1.8초. 프롬프트·모델을 바꾸면 `python scripts/chat_eval.py`(LLM 호출 비용 있음)로 다시 확인합니다. 자세한 내용은 [대화 문서](docs/CHAT.md).
- 설계(구현 전, 시연·MVP용): 챗봇으로 신청하기. 신청 방식에 따라 네 갈래 — ① 구글폼은 조이가 채워 확인받고 제출(우리 테스트 폼만) ② 온라인 사이트·공공서비스예약은 준비·단계 안내, 로그인과 최종 제출은 사용자 ③ 전화·카톡 등은 대본·문구 초안 ④ 방문형은 일정 추가. DB migration 없음(payload에 추가). [신청 흐름](docs/APPLY.md).
- 계획: 매일 실행 스케줄러 연결, 운영 DB 적재, 로그인 방식 결정 후 인증·회원 API, 대화 저장(인증 이후)·사용량 상한, FE 연결. 서비스 세션·사용자 저장은 아직 없습니다.
- 배포: 하지 않았습니다.

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET | /api/regions | 거주지 시군구 목록 `{code, sido, sigungu, label}` 256개 ([지역 코드](docs/REGIONS.md)) |
| GET | /api/checkin/questions | 상태 체크 문항 |
| POST | /api/checkin/summary | 답변 → 영역 수준 요약 (점수·위험 등급 없음) |
| POST | /api/recommendations | 기본 정보 + 답변 → 정책 6 · 프로그램 4 |
| POST | /api/chat | 대화 한 턴 → 답장, 알아들은 상태 체크 답, 선택지, 추천·검색 결과 (LLM 키 필요, 위기 안내는 키 없이도) |
| POST | /api/apply/start | 챗봇 신청 시작: 테스트 구글폼을 읽어 채운 문항·물을 문항 ([신청 흐름](docs/APPLY.md)) |
| POST | /api/apply/draft | 신청서 긴 답 초안 (LLM 키 필요) |
| POST | /api/apply/submit | 사용자가 제출을 눌렀을 때 구글폼 제출 |

**FE 연결 안내: [docs/FRONTEND.md](docs/FRONTEND.md)** — 화면별 API, 실제 응답 예시, 오류 처리, FE와 맞춰야 하는 값 14가지.

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

서버는 스키마를 자동 생성·변경하지 않습니다. baseline 0001은 Alembic 버전 테이블만, 0002는 정책·프로그램 카탈로그 `catalog_items`를, 0003은 변경 이력 `catalog_item_changes`를, 0004는 회원 테이블(`users`, `user_profiles`, `user_consents`, `checkin_responses`)을 만듭니다. 테이블 설명은 [DB 테이블 안내](docs/DATABASE.md)에 모으고, 테이블을 바꾸면 함께 고칩니다. 이후 모델은 app.database.Base를 상속하고 migrations/env.py에 해당 모듈을 import한 뒤 아래 절차를 사용합니다.

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

## 2026-11-21 · 정책·프로그램 탐색 API (로컬 구현)

- GET /api/catalog/items와 /api/catalog/items/{item_id}를 추가했다. 목록 검색/지역/나이/종류/카테고리/마감 제외/정렬/페이지 및 상세 공고 필드를 제공한다.
- 기존 추천 응답에도 실제 카테고리/지역/키워드와 일관된 신청 상태·기간 필드를 추가했다. 기존 키는 유지하며 apply_period도 동일 기간 문구를 사용한다.
- DB 우선 source=db, 기존 파일 대체 시 source=file. 개인정보 저장·DB 스키마/데이터 변경 없음.
- 관련 테스트 24개 통과, 실제 DB HTTP 및 프론트 브라우저 연결 확인. main 반영/배포/커밋/푸시/PR 생성은 하지 않았다. 실제 AI API는 미구현이다.
- 계약: [카탈로그 탐색](docs/CATALOG_BROWSER.md).

## 2026-11-21 · 주변센터 실제 정보 연결 (로컬)

- 기존 가상 센터/거리/지도/운영 시간 및 작동하지 않는 위치 버튼을 실제 수집 센터 목록·상세로 교체했다. 서울 34곳이며 실시간 위치순 조회가 아니다.
- 백엔드 GET /api/centers?q=&district= 및 GET /api/centers/{id} 추가. runtime centers.csv가 있으면 활성 행, 없으면 기존 centers_seed.jsonl 사용. source=file, dataset=runtime/seed로 구분하며 DB 센터라고 표현하지 않는다.
- 이름·주소 검색/구 필터/빈 결과/오류 재시도와 8초 요청 제한을 제공한다. 센터명 공백을 제외한 정확 일치로 프로그램을 연결한다. 프로그램은 기존 DB 우선 조회 및 파일 대체를 따르며 programs_source=db/file을 별도 표시한다.
- 실제 브라우저: 전체 34곳, 강동구 1곳, 서울청년센터 강동 상세/주소/운영시간 미제공, DB 프로그램 4개, 선택 공고의 조이 이동, 검색 0건 안내 확인. 홈페이지 주소 없는 경우 미제공 표시, 외부 신청·문의 없음.
- 센터 파일의 전체/최신성은 보장하지 않는다. 좌표/거리/운영 시간·누락 홈페이지 보강은 후속 백엔드 데이터 작업. 프로그램 연결 0건은 운영 프로그램이 없다는 의미가 아님을 표시한다. DB 저장 센터 API·실시간 지도는 미구현.
- 검증: FE npm run build 통과(기존 청크 크기 경고). verify-centers 실제 FE→ASGI 계약/출처/지역/검색/빈 결과/503·timeout 전파 통과. backend tests.test_centers_api + tests.test_catalog_browser 4개 통과. 데스크톱 브라우저 검증, 모바일 센터 화면 별도 검증은 미완료.
- 기존 작업 보존. 두 작업 브랜치의 로컬 미커밋 구현이며 main 반영/PR 갱신/푸시/배포 없음. 서버 유지.

## 2026-11-21 · 센터 별칭으로 누락된 프로그램 복구

- 기존 공백 제거 정확 일치가 공식 센터명의 부가 이름을 처리하지 못해 관악·금천·서초 프로그램을 누락시켰다.
- 공식 서울청년센터 지점 이름을 키로 정규화한다. 관악의 신림동쓰리룸, 금천의 청춘삘딩, 서초의 괄호 공식명과 프로그램의 짧은 지점명을 연결한다. 같은 구의 별도 기관(관악청년청 등)에는 합치지 않는다.
- 수집 파일 기준 관악8/금천14/서초5건 복구, 실제 브라우저 관악 상세에서 DB공고8개 표시 확인. 센터 API2테스트 통과(별칭·기관 구분·연결 결과 회귀 포함). 서버 재시작·유지, 커밋/푸시/PR 변경 없음.
- 센터 ID가 serving 프로그램 필드에 남아 있지 않아 현재 공식 지점명으로 연결한다. 장기적으로 center_sns를 serving/DB 응답까지 유지하는 것이 필요하다. 기타 미수집 센터는 여전히 프로그램이 없을 수 있으며 기관 미운영으로 단정하지 않는다.

## 2026-11-21 · 센터 프로그램 건수 및 카카오 위치 지도 준비

- 센터 목록 API가 동일 연결 기준으로 program_count/open_program_count를 계산한다. 총 수집 수는 마감 공고 포함, 모집 중은 open/always_open만 포함한다. 프로그램 출처는 programs_source=db/file이다.
- 목록에서 수집 수/모집 중 수를 구분한다. 실제 브라우저 DB 연결: 관악8/8, 금천14/13, 서초5/5 확인. 미수집 센터는 ‘프로그램 수집 정보 없음’으로 표시한다.
- 센터 상세에 Kakao JavaScript SDK + services.Geocoder로 주소→좌표→지도/핀 표시를 구현했다. SDK10초/주소검색8초 제한, 실패 재시도, 센터 변경 취소, 반응형 크기 재조정을 제공한다. 주소 미발견/키 미설정/네트워크 실패 시 임의 좌표를 표시하지 않으며 공개 센터 주소 카카오맵 링크를 제공한다. 사용자 위치는 요청하지 않는다.
- 현재 로컬 키가 없어 실제 SDK 지도·좌표·핀 성공은 미검증이다. 브라우저는 키 미설정 안내/주소/지도 외부 링크를 확인했다. 키는 채팅·소스·로그에 출력하지 않았다.
- npm run build 및 verify-centers 통과. backend tests.test_centers_api 3개 통과(전체 센터 목록 수=상세 수, 모집 중 수의 일치 포함). 기존 빌드 청크 경고 유지.
- 커밋/푸시/PR/배포 없음. 로컬 서버 유지.

## 2026-11-21 · 센터 정렬·프로그램 필터·공식 공간 소개

- 정렬 선택을 가까운순/기본순 두 개로 제공한다. 두 모드 모두 연결된 프로그램이 있는 센터를 먼저 두고 각 그룹 안에서 거리순 또는 기존 기본순을 유지한다. 지역이 없으면 기본순, 가까운순 선택은 지역 등록/선택 후 가능하다.
- ‘프로그램 안내 있는 센터만’ 필터를 추가했다(연결 공고 program_count>0 기준). 화면 건수는 필터 결과와 일치한다. 목록의 총 프로그램 수/수집 정보 없음/0개 표시는 제거하고, 모집 중 공고가 있는 센터만 ‘현재 모집 중 n개’를 표시한다. 마감된 공고만 있는 센터도 프로그램 안내 그룹에 포함되지만 모집 중 배지는 없다.
- backend app/catalog/center_guides.json에 공식 기관·지자체 소개를 근거로 공간 용도/시설/이용 안내/출처 URL·확인일을 추가했다. 17개 개별 공간 안내와 17개 서울청년센터의 공식 공통 서비스 안내로 현재34곳을 제공한다. 임의로 프로그램 미운영 기관이라고 분류하지 않는다. 관악청년청은 카페·공유주방뿐 아니라 프로그램도 운영한다는 공식 안내를 반영했다.
- 센터 상세는 ‘어떤 곳인가요?/이용할 수 있는 것/이용 전에/공식 공간 안내’가 먼저다. 연결 프로그램이 없으면 프로그램0개·미수집 경고 대신 공간 이용 안내를 보여준다. 소개는 DB 생성값이 아니라 공식 출처를 정리한 서버 파일이며 주소/프로그램 DB 출처와 구분한다.
- 성북구 공식 페이지의 2026-05-15 수정 안내에 따라 길이음 주소를 삼양로29 성북 청년 스마트창업센터1층으로 보정했다. 관악청년청 운영 시간은 관악문화재단 공식 안내로 제공한다. 나머지 미확인 운영 시간은 추정하지 않는다.
- 앞선 주소 수정도 포함: 원주소로 좌표가 없으면 층/건물 설명을 제거한 도로명·건물번호로 재검색한다. 지도와 거리 계산이 같은 geocodeAddress를 사용한다. 앞선 브라우저에서 관악청년청의 지도/핀 표시를 확인했다.
- 검증: npm run build 통과(기존 청크 크기 경고 유지). verify-center-display 실제 React 정적 렌더에서0개/미수집 문구 제거, 모집중 수, 소개/출처, 정렬2개·필터 확인. verify-center-distance의 두 모드 그룹 우선/거리/필터/원본 보존 검사, verify-center-address와 verify-centers 계약 검사 통과. backend tests.test_centers_api + tests.test_catalog_browser 총7개 통과.
- 실제 HTTP: http://127.0.0.1:5173/api/centers 200, 34곳 모두 guide 포함, programs_source=db. 관악청년청 상세는 program_count0이지만 공식 청년카페·시설 안내가 제공됨 확인. HTTP응답 전체/키/개인정보는 출력하지 않았다.
- 이번 정렬/필터/소개 변경 후 실제 브라우저 상호작용·반응형 재검증은 도구 연결 불가로 미검증. 정적 React 렌더/빌드/실제HTTP 결과와 구분한다.
- 기존 작업 보존. 프론트 test/checkin-response-audit/백엔드 feat/catalog-browser-api 로컬 미커밋 변경이며 main·기존PR 반영/커밋/푸시/병합/배포 없음. FE5173/BE8000 서버 재실행 후 유지.

## 2026-11-21 · 사용자 요청에 따른 커밋·PR·병합 정리

- 사용자가 여기까지의 변경을 한국어 커밋/PR로 기록하고 main 병합 및 완료 브랜치 정리를 명시적으로 요청했다. 기존 프론트 PR #10은 이미 병합된 상태임을 확인했고, 이번 후속 기능은 최신 frontend main b65dd42에서 feat/catalog-centers-chat로 분리한다.
- backend 최신 main b2686fb의 챗봇/신청/지역 보완을 기존 작업에 병합했다. 이들 다른 작업자의 기능을 보존하며, 이번 프론트 조이는 공고 기반 안내이고 새 /api/chat·실제 신청 API 연결은 후속 작업이다. 이전 기록의 ‘백엔드 대화 API 없음’은 당시 상태이며 현재 main에 API가 추가돼 있다.
- 프론트 npm ci/npm run build와 센터 표시·거리·주소·API, 정책 탐색, 대화형 프로필, 기존 설정/저장소/점검/이력/지역 검증 스크립트를 모두 재실행해 통과했다. 큰 청크 경고는 남는다.
- 백엔드는 main 반영 후 비DB 포함88개 검사와 전용 dos_tres_test 전체106개 검사를 통과했다. pip check도 통과했다. 전용 테스트 DB만 시작해 마이그레이션 검사를 수행했으며 개발 DB는 보존했다.
- 새로 포함할31개 프론트/13개 백엔드 후보 파일에서 로컬 비밀값·휴대전화 패턴·구글폼 링크를 검사해 검출0건을 확인했다. .env/.env.local과 실제 키는 Git에 포함하지 않는다.
- 실제 화면의 최종 소개/정렬/필터 변경은 React 렌더와 계약/HTTP로 검증했으며, 브라우저 도구 연결 불가로 마지막 시각 재확인은 미완료다. 앞선 지도/거리 브라우저 검증과 구분한다.
- PR의 검증/남은 작업을 명시하고 사용자 요청 범위에서 squash 병합한다. 배포는 하지 않는다. 병합 완료 여부와 링크는 PR 자체가 최종 근거다.

### 공식 센터 공간소개·공지사항

`python -m pipeline.programs.crawl.seoul_centers`로 서울청년센터 공식 디렉터리의 17개 센터별 공간소개·실제 운영시간·오시는 길·이용방법과 최근 공지 10개씩을 수집합니다. API는 센터명 정규화로 정확히 연결된 센터에만 `official`을 추가합니다. 공지 제목·등록일·공식 원문 링크를 제공하며 공지 전문·연락처·폼 링크는 저장하지 않습니다. runtime을 우선 사용하며 seed 스냅샷으로 재현할 수 있습니다. 일일 파이프라인에 포함되며 HTTP 요청 중에 외부 사이트를 크롤링하지 않습니다. 이 변경은 로컬 구현이며 배포하지 않았습니다.

개별 청년공간 17곳의 공식 기관/지자체 안내를 재검토해 운영시간 12곳, 공지 게시판 링크 9곳과 시설·이용방법을 보완했습니다. 서울청년센터를 포함한 운영시간은 29/34곳에서 확인됐으며, 미확인 5곳은 추정하지 않습니다. 기관별 게시판 9곳은 직접 링크이며 서울청년센터 공지 170건 수집과 구분합니다.
