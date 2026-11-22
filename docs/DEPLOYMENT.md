# 둘셋 · DOS TRES 배포를 고려한 개발 기준

결정일: 2026-11-18 (한국 시간)

## 1. 목표와 현재 상태

둘셋은 다른 사용자가 HTTPS 링크로 접속해 실제 AI 비서 기능을 이용하는 것을 목표로 개발한다. 로컬 실행, 화면 미리보기, 실제 AI가 연결된 배포를 구분한다.

2026-11-18 확인 기준(backend는 chore/database-foundation 작업 브랜치):
- frontend: React + TypeScript + Vite. 예시 데이터와 예시 대화 응답으로 동작한다.
- frontend: GitHub Actions에 npm ci 및 npm run build 검증이 있다.
- backend: Python + FastAPI 및 AI 에이전트를 같은 저장소에서 개발하기로 결정했다. FastAPI 실행 기반, healthz, 환경 설정, CORS, 공통 오류 응답과 자동 테스트를 구현하고 로컬 실행을 검증했다.
- 기본 DB는 PostgreSQL 17이다. SQLAlchemy 연결·요청별 세션, Alembic, /readyz를 구현했다. 정책·프로그램 카탈로그 테이블 `catalog_items`(0002), 변경 이력 `catalog_item_changes`(0003)와 추천 API를 구현했다(배포 전). 매일 수집 스케줄러 실행 위치는 배포 환경과 함께 정한다. AI 비서 대화 `POST /api/chat`을 구현했다(`feat/ai-chat`, 배포 전). 파이프라인 분류와 대화 모두 OpenAI(gpt-4.1-mini)를 쓴다(2026-11-22, SSAFY GMS 종료로 전환). 인증은 미정이다.

이 문서는 개발 기준이다. 배포 설정이나 실제 AI 연동이 구현됐다는 뜻은 아니다.

## 2. 기본 연결 구조

| 구성 | 역할 | 배포 기준 |
| --- | --- | --- |
| frontend | 화면, 입력, 선택지, 결과 표시 | 정적 빌드 dist를 HTTPS로 제공 |
| backend | API, AI 호출, 자격 확인 및 실행 업무 처리 | FastAPI를 실행하는 HTTPS API 서버 |
| AI 제공업체 | 실제 모델 추론 | backend에서만 호출 |
| 영속 저장소 | 회원, 상태 체크, 대화 및 실행 이력 | 사용자 저장 기능 구현 시 도입; 서버 재시작 후 유지 |
| 작업 실행기 | 시간이 긴 문의 등 외부 작업 | 실제 연동 필요 시 도입; 웹 요청과 수명 분리 |

초기에는 API와 AI 에이전트를 backend 안에서 함께 개발한다. 별도 AI 저장소나 서버 분리는 운영상 필요가 생겼을 때 검토한다.

## 3. 현재 공통 기반과 다음 기능 범위

FastAPI 실행 기반과 PostgreSQL 공통 기반을 구현했다. /healthz는 프로세스 상태, /readyz는 DB 연결 상태를 확인한다. SQLAlchemy 요청별 세션과 공통 오류 응답을 제공하며 Alembic은 서버와 분리해 명시적으로 실행한다. 0001 baseline 뒤에 0002가 `catalog_items`를, 0003이 `catalog_item_changes`를 만든다. 운영 DB에는 마이그레이션 후 `python -m pipeline.load_catalog`로 데이터를 넣는다.

이 PR 리뷰 후 공통 API 계약을 합의하고 정책 수집 / 세션·설문을 병렬 개발한다. 추천·AI 대화, 프론트 연결·배포는 그 다음 단계다. 개인 기록은 인증과 사용자별 접근 제어를 함께 구현한 뒤 저장한다.

이후 실제 AI와 프론트 연결 시에는 예시 응답을 실제 응답과 구분하고 요청 중·실패·시간 초과·재시도 상태를 제공한다. 첫 연결 검증에는 가상 입력과 테스트 계정을 사용한다. 정책 추천에는 공식 출처와 확인 시점을 함께 다루며 모델 응답만으로 자격이나 신청 완료를 확정하지 않는다.

## 4. 환경별 설정 원칙

APP_ENV, ALLOWED_ORIGINS, DATABASE_URL은 현재 backend가 읽는다. 나머지는 후속 구현을 위한 계획이며 현재 backend 설정이 아니다. 설정 우선순위와 실행 절차는 README를 따른다.

| 위치 | 이름 | 용도·구현 상태 |
| --- | --- | --- |
| frontend | VITE_API_BASE_URL | 공개 가능한 backend 주소; frontend 공통 API 모듈 연결은 후속 작업 |
| backend | APP_ENV | local / staging / production 구분; 구현 완료 |
| backend | ALLOWED_ORIGINS | 허용할 frontend origin의 JSON 문자열 배열; 구현 완료 |
| backend | OPENAI_API_KEY(예전 GMS_KEY), OPENAI_BASE_URL, LLM_MODEL | OpenAI 호환 LLM 키·주소·모델. 서버 비밀 설정에서만 주입. 파이프라인 분류와 /api/chat이 함께 사용; 구현 완료(키가 없으면 /api/chat 503) |
| backend | 다른 제공업체(AI_PROVIDER 등) | OpenAI 호환이 아닌 제공업체를 쓸 때; 미구현 |
| backend | DATABASE_URL | 서버 전용 PostgreSQL psycopg 연결 URL; 구현 완료 |

- frontend 코드에 localhost나 특정 운영 주소를 직접 넣지 않는다.
- VITE_ 환경변수와 브라우저 번들은 공개 정보로 취급한다. AI 키·DB 비밀번호·서명 비밀은 넣지 않는다.
- 저장소에는 값이 비어 있거나 가상 예시인 .env.example과 설명만 둔다. 실제 .env와 비밀값은 커밋하지 않는다.
- 로컬·미리보기·운영 환경의 API 주소와 비밀 설정을 분리한다.
- CORS는 실제 사용할 frontend origin만 허용한다. 인증 도입 시 쿠키·토큰 방식과 함께 검증한다.

## 5. 서버와 AI 처리 기준

- 서버는 실행 환경에서 제공하는 포트와 외부 접속용 바인딩을 지원한다. Uvicorn의 --host와 --port로 지정하며, 검증한 명령은 README에 기록했다.
- 서버 로컬 디스크나 메모리를 사용자 기록의 영구 저장소로 사용하지 않는다.
- AI 제공업체 호출에 시간 제한과 오류 처리를 적용한다. 재시도는 횟수를 제한하며 중복 실행을 고려한다.
- 요청 크기·호출 빈도·사용량 상한을 두어 공개 시연 중 과도한 비용을 막는다.
- AI 연결 실패 시 예시 답변을 실제 처리 결과처럼 대신 보여주지 않는다.
- 로그는 요청 식별자·상태·처리 시간 중심으로 남기고 API 키, 인증 토큰, 상태 체크 응답과 대화 원문을 기본 로그에 남기지 않는다.
- 전화 문의 대행은 별도 후속 단계다. 기관·번호·질문·전달 정보에 대한 사용자 확인과 실제 연동 검증 전에는 통화 완료로 표시하지 않는다.

## 6. 배포까지 진행 순서

| 단계 | 완료 기준 |
| --- | --- |
| 1. 공통 DB·API 구조 | FastAPI, PostgreSQL 연결·세션, Alembic, healthz/readyz 및 공통 API 계약 |
| 2. 정책 수집 / 세션·설문 병렬 개발 | 두 팀원이 기능별 수집·저장·API를 병렬 구현하고 마이그레이션 통합 검증; 개인 기록은 인증·접근 제어와 함께 구현 |
| 3. 추천·AI 대화 | 확인된 정책 데이터 기반 추천과 실제 모델 연결, 오류·시간 초과 처리 검증 |
| 4. 프론트 연결·배포 | 프론트 API 연결 후 HTTPS 미리보기에서 실제 요청, 모바일·실패 상태 검증 후 운영 배포 |

현재는 1단계 DB 공통 기반까지 구현한 상태이며 공통 기능 API 계약과 2~4단계는 후속 계획이다. 개발·테스트 DB를 분리하고, 운영 DB에도 마이그레이션은 서버 시작과 분리해 명시적으로 실행한다. /readyz는 DB 연결만 검사하며 스키마 버전 검증을 대신하지 않는다.

배포 대상은 위 요구사항과 예산을 기준으로 선택한다. 제공업체 계정 연결·요금제·실제 URL은 결정 후 기록한다.

## 7. 변경과 배포 검증

- 최신 main에서 목적별 브랜치를 만들고 PR로 검토한다. 진행 중인 frontend 홈 디자인 브랜치와 작업은 보존한다.
- frontend 변경은 기존 npm ci 및 npm run build 검증을 통과시킨다.
- 현재 backend CI는 Python 3.13에서 자동 테스트와 pip check를 실행한다. AI 오류 검증은 실제 AI 연동 구현 시 추가한다.
- 코드·설정에서 비밀값이 노출되지 않는지 확인한다.
- 미리보기 URL에서 실제 API 연결, 허용 origin, 새로고침과 정적 에셋 로딩을 확인한다.
- 운영 반영 시 배포 커밋과 되돌릴 이전 배포를 기록한다.
- 실제 배포를 확인하기 전에는 README나 화면에 운영 중이라고 표시하지 않는다.

## 8. 다음 구현 작업

공통 DB·API 구조 → 정책 수집 / 세션·설문 병렬 개발 → 추천·AI 대화 → 프론트 연결·배포 순서를 따른다.

이번 DB 기반 PR 리뷰를 먼저 반영한다. 이후 기능별 API 계약을 합의하고 두 팀원이 정책 수집과 세션·설문을 병렬 개발한다. 기능별 모델과 Alembic revision을 함께 리뷰하며 복수 head가 생기면 통합 revision을 검토한다. 추천·AI 대화는 그 다음 단계이고, 프론트 연결과 실제 배포는 마지막 단계다. CLI는 구현·검증·PR까지 수행하고, PR 검토·병합·다음 작업 지정은 이 대화창에서 진행한다.

## 9. 배포 방법 (AWS Lightsail 컨테이너, 2026-11-21)

팀 결정(노션 「배포 및 운영 결정」): Lightsail 컨테이너 Micro(시드니 — 2026-11-22 서울에서 변경, 아래 9-0), Docker 이미지 1개(FE 화면 + API), 앱 안 스케줄러, 비밀값은 배포 환경변수로만.

### 9-0. 리전: 시드니 (2026-11-22 변경)

배포 계정은 AWS 조직의 멤버 계정이고, 조직의 리전 제한 정책(SCP `AdvancedModeRegionRestrictionSecurityControlPolicy`)이 시드니(`ap-southeast-2`)·버지니아·오리건 밖의 리전을 막는다. 서울(`ap-northeast-2`)은 Lightsail 조회부터 거부되고, 시드니는 Lightsail이 정상 동작한다. 그래서 컨테이너와 DB를 모두 시드니에 둔다. 마감 전날 보안 정책을 고치는 위험을 피하려는 선택이며, 한국에서 접속할 때 응답 지연은 약 0.1초 늘어난다.

- 2026-11-22 생성(실제): DB `dostres-db`(PostgreSQL 17, `micro_2_0` 월 $15, 비공개 모드, DB 이름·사용자 `dostres`, 비밀번호는 AWS 자동 생성), 컨테이너 서비스 `dostres`(micro, scale 1, 월 $10). 이미지 배포는 아직이다.

### 9-1. 이미지에 들어 있는 것

| 구성 | 설명 |
| --- | --- |
| `Dockerfile` | 1단계 FE 빌드(`npm ci && npm run build`) → 2단계 Python 3.13 + 백엔드 + `web/`(FE dist). 일반 사용자(uid 10001)로 실행, 시간대 Asia/Seoul |
| 화면 제공 (`app/web.py`) | `WEB_DIR=/app/web`. `/api/*`·`/healthz`가 먼저, 없는 `/api/*`는 JSON 404, 그 밖의 경로는 `index.html` (새로고침 OK) |
| 스케줄러 (`app/scheduler.py`) | `SCHEDULER_ENABLED=true`면 시작 60초 뒤 1번 + 매일 `SCHEDULER_HOUR`(기본 4시) `pipeline.run_daily`. DB 주소가 없으면 `--no-load`, LLM 키가 없으면 `--no-llm`. 실패해도 서버는 마지막 정상 데이터로 동작 |
| 기본 데이터 | `data/seed/serving` (정책 2,335 · 프로그램 137). 재시작하면 `data/runtime`은 비고 seed로 시작 → 스케줄러가 다시 채움 |
| 운영 DB 준비 (`DB_AUTO_MIGRATE`) | `DATABASE_URL`이 있고 `DB_AUTO_MIGRATE=true`면 시작할 때 `alembic upgrade head` + 비어 있을 때만 기본 데이터 적재(`load_catalog --seed --if-empty`). 스케줄러 첫 실행 전에 같은 스레드에서 해서 겹치지 않음. 실패하면 서비스는 파일로 계속 |
| 사용량 제한 (`app/limits.py`) | LLM 요청(대화·초안): 접속자당 1분 10회·하루 100회, 서버 전체 하루 2,000회 → 429 `RATE_LIMITED`. 위기 안내는 제한 없음 |
| 넣지 않는 것 (`Dockerfile.dockerignore`) | `.env`, `*.local.json`(테스트 폼 주소), `node_modules`, `.venv`, `data/runtime`, 테스트 |

### 9-2. 로컬에서 이미지 만들고 확인

frontend·backend를 같이 둔 작업 폴더(`dos-tres`)에서:

```
docker build -f backend/Dockerfile -t dostres:local .
docker run --rm -p 127.0.0.1:8080:8000 dostres:local
```

`http://127.0.0.1:8080` 화면, `/healthz` 200, `/readyz`는 DB 없으면 503(정상). 2026-11-21 확인: 이미지 299MB, 화면·새로고침·API·추천(`source: file`)·위기 안내·429·`APPLY_FORMS_JSON`으로 신청 시작, 컨테이너 안 정책 파이프라인(`--no-load --no-llm`, 41초, 정책 2,314) 동작, 이미지 안 `.env`·`*.local.json` 없음.

### 9-3. 운영 DB: Lightsail 관리형 PostgreSQL (2026-11-21 결정)

확장성(회원·기록 저장, 변경 이력)을 실제 운영에서 보여 주려고 운영 DB를 쓴다. DB에 문제가 생기면 서비스는 이미지의 데이터 파일로 자동 대체한다(추천 계산 같음).

1. Lightsail 콘솔 → 데이터베이스 → **PostgreSQL**, 리전 **시드니(ap-southeast-2)**, 가장 작은 요금제(AWS 문서 기준 월 $15부터 — 콘솔에서 금액 확인), 표준(고가용성 아님). 데이터베이스 이름 `dostres` 등으로 지정, 사용자 이름·비밀번호는 콘솔에서 확인(비밀번호는 강하게, 레포·채팅에 쓰지 않음).
2. 만들어지면 **엔드포인트**를 확인해 `DATABASE_URL`을 만든다: `postgresql+psycopg://<사용자>:<URL 인코딩한 비밀번호>@<엔드포인트>:5432/<DB 이름>`
3. 컨테이너 환경변수에 `DATABASE_URL`과 `DB_AUTO_MIGRATE=true`를 넣고 배포 → 첫 시작에 테이블 생성 + 기본 데이터 적재, 이후 매일 스케줄러가 적재·변경 이력 기록.
4. 배포 뒤 `https://…/readyz`가 **200이면 DB 연결 성공**. 503이면 연결 실패(서비스는 파일로 동작 중):
   - Lightsail DB는 기본이 **비공개 모드**(같은 계정의 Lightsail 리소스만 접속)인데, 공식 문서에는 비공개 모드에 접속할 수 있는 대상으로 "인스턴스, 로드 밸런서 등"만 적혀 있고 **컨테이너 서비스가 되는지는 나와 있지 않다**.
   - 503이면 DB의 네트워킹 탭에서 **공개 모드**를 켠다. 공개 모드는 엔드포인트·사용자·비밀번호를 아는 누구나 접속할 수 있으므로 비밀번호를 강하게 하고, **심사가 끝나면 DB를 삭제**한다(AWS도 공개 모드를 오래 켜 두지 말라고 권함).
   - 2026-11-21 로컬 확인: 빈 PostgreSQL + `DB_AUTO_MIGRATE=true`로 컨테이너 시작 → 테이블 생성, 정책 2,335·프로그램 137 적재, `/readyz` 200, 추천 `source: db`. 재시작하면 적재를 건너뜀(`--if-empty`).

### 9-4. Lightsail 배포 (처음 한 번)

준비: AWS CLI(`winget install --id Amazon.AWSCLI -e`), Lightsail 플러그인 `lightsailctl`(AWS 문서의 설치 안내), `aws configure`(본인 키, 리전 `ap-southeast-2`). **키를 레포·채팅에 쓰지 않는다.**

```
aws lightsail create-container-service --service-name dostres --power micro --scale 1 --region ap-southeast-2
aws lightsail push-container-image --region ap-southeast-2 --service-name dostres --label app --image dostres:local
```

`push`가 알려 주는 이미지 이름(예: `:dostres.app.1`)을 `deploy/containers.json`에 넣는다. `deploy/containers.example.json`을 복사해 비밀값을 채운다(**`containers.json`은 Git 제외**). 콘솔의 배포 화면에서 환경변수를 직접 넣어도 된다.

```
aws lightsail create-container-service-deployment --region ap-southeast-2 --service-name dostres --containers file://deploy/containers.json --public-endpoint file://deploy/public-endpoint.json
aws lightsail get-container-services --region ap-southeast-2 --service-name dostres
```

`state`가 `RUNNING`이 되면 `url`(https://…amazonlightsail.com)이 서비스 주소다.

| 환경변수 | 값 | 비고 |
| --- | --- | --- |
| `APP_ENV` | `production` | 이미지 기본값 |
| `SCHEDULER_ENABLED` | `true` | 매일 갱신 |
| `YOUTH_POLICY_API_KEY`, `YOUTH_CENTER_API_KEY` | 온통청년 키 | 없으면 갱신만 실패, 서비스는 seed로 동작 |
| `GMS_KEY`(또는 `OPENAI_API_KEY`), `OPENAI_BASE_URL`, `LLM_MODEL` | LLM | 없으면 대화·초안 503 |
| `APPLY_FORMS_JSON` | 테스트 폼 목록 JSON | 없으면 신청은 `not_supported` |
| `DATABASE_URL` | 운영 DB 주소 (9-3) | 비우면 DB 없이 파일로 운영 (추천은 같은 계산) |
| `DB_AUTO_MIGRATE` | `true` | 첫 시작에 테이블 생성·기본 데이터 적재 |
| `ALLOWED_ORIGINS` | 비움 | 화면과 API가 같은 주소라 필요 없음 |

### 9-5. 다시 배포 (코드 변경 후)

`docker build …` → `push-container-image`(새 번호) → `containers.json`의 `image` 번호만 바꿔 `create-container-service-deployment`. 이전 배포는 콘솔에서 되돌릴 수 있다.

### 9-6. 제출 후

- 11/23 제출 버전을 git 태그로 고정하고 심사 기간(11/24~30)에는 기능 변경을 멈춘다.
- UptimeRobot 등에 `https://…/healthz` 등록(다운 알림).
- **심사가 끝나면 컨테이너 서비스와 DB를 삭제**한다(`aws lightsail delete-container-service --service-name dostres --region ap-southeast-2`, DB는 콘솔에서 삭제). 비활성화는 요금이 계속 나간다.
