# 둘셋 (Dos Tres) — Backend & AI

**혼자 시작하기 막막한 청년을 위한 사회참여 AI 비서**

둘셋은 청년정책과 지역 청년센터 프로그램을 **찾는 것부터 신청 준비까지** 연결하는 서비스입니다. 사용자는 AI 비서 **조이(JOY)**와 대화하면서 상황을 정리하고, 실제 공고에 기반한 안내를 받아 다음 행동으로 이어갈 수 있습니다.

이 저장소는 **공고 수집·정제, 정책/프로그램 추천, AI 대화, 신청서 작성 지원 및 서비스 API**를 담당합니다.

[프론트엔드 저장소](https://github.com/dos-tres/frontend) · [데이터 파이프라인 상세](docs/CRAWLER.md) · [AI 대화 설계](docs/CHAT.md) · [신청 지원 설계](docs/APPLY.md)

---

## 1. 왜 둘셋인가요?

청년정책과 지역 활동 정보는 여러 기관에 흩어져 있고, 자격 조건과 신청 과정도 복잡합니다. 도움을 찾고 싶어도 **무엇을 검색해야 하는지, 어디에 문의해야 하는지**부터 막막할 수 있습니다.

둘셋은 **막연한 고민 → 상황 이해 → 근거 있는 정책·활동 탐색 → 신청 준비 → 일정 관리**를 한 흐름으로 연결합니다. AI는 사람의 말을 이해하고 안내하며, 실제 정책 데이터와 조건 판단은 별도의 데이터·규칙 계층에서 처리합니다.

## 2. 주요 기능과 백엔드 역할

| 기능 | 구현 내용 |
| --- | --- |
| **AI 비서 조이** | `POST /api/chat`으로 사용자 입력·대화 맥락을 분석해 추가 질문, 실제 공고 탐색, 선택한 공고에 대한 설명과 다음 행동을 제공합니다. |
| **맞춤 정책·프로그램 추천** | 연령·거주지·현재 상태·생활 점검 응답을 규칙과 카탈로그 데이터에 적용해 근거 있는 추천 후보와 안내 문구를 반환합니다. |
| **정책·센터 데이터 제공** | 청년정책·센터 프로그램 목록, 개별 공고 상세, 지역 코드, 청년센터 위치·시설·공지·운영 프로그램 정보를 API로 제공합니다. |
| **생활 점검** | 사용자가 선택한 답변을 바탕으로 영역별 상태를 요약합니다. 의료·심리 진단이나 공인 위험 등급을 계산하지 않습니다. |
| **신청서 작성 지원** | 지원 가능한 Google Form 문항 읽기, 문항별 AI 답변 초안 및 검토 과정을 지원합니다. 실제 제출은 승인된 팀 소유 복제 테스트 폼으로 제한합니다. |
| **데이터 수집 파이프라인** | 정책 API와 센터 공고를 수집·정제하고, AI 기반 분류·정보 추출 후 서비스용 데이터와 PostgreSQL 적재를 지원합니다. |

### 사용자 시나리오

1. 사용자가 조이에게 “취업 준비 중인데 어떤 지원을 받을 수 있어?”라고 말합니다.
2. 조이가 대화의 맥락을 해석하고, 필요한 거주지·연령·현재 상태를 확인합니다.
3. 서버가 수집한 **정책·프로그램 데이터에서** 후보를 검색하고, 규칙에 따라 추천 이유 및 추가 확인 조건을 제시합니다.
4. 사용자가 특정 공고를 선택하면 공고에 대한 후속 질문에 답하고 신청서의 질문·답변 작성을 도와줍니다.
5. 사용자가 공식 링크를 확인하거나, 허용된 테스트 시나리오에서 최종 제출을 검토합니다. 일정·개인 기록은 프론트엔드에서 관리합니다.

## 3. 기술 구성과 설계 원칙

| 계층 | 기술·역할 |
| --- | --- |
| API 서버 | **Python 3.13 · FastAPI · Pydantic · Uvicorn** |
| AI | **OpenAI API** (기본 모델 `gpt-4.1-mini`), 대화 이해·공고 분류/정보 추출·서술형 초안 |
| 추천·검색 | Python 규칙 엔진, 공고 카탈로그 검색, 지역·연령·상태 조건 적용 |
| 데이터베이스 | **PostgreSQL 17 · SQLAlchemy 2 · Alembic** |
| 데이터 파이프라인 | Python, Requests, BeautifulSoup, 온통청년 API·청년센터 웹 수집 |
| 운영·검증 | Docker, Docker Compose, unittest, 환경변수 기반 설정, 헬스체크 |
| 프론트엔드 | 별도 [React + TypeScript + Vite 저장소](https://github.com/dos-tres/frontend) |

### 시스템 아키텍처

```text
사용자 (PC · 모바일 웹)
        │
        ▼
React + TypeScript Frontend
├─ 조이 대화 · 정책/프로그램 · 청년센터 · 신청 도우미
├─ 생활 점검 · 마이페이지 · 일정/기록
└─ 브라우저 localStorage · Kakao Maps SDK(선택)
        │ /api/*
        ▼
FastAPI Backend
├─ /api/chat ─────────────── OpenAI API
├─ 추천·카탈로그·지역 ────── 검색·추천 규칙
│                            └─ PostgreSQL / serving 데이터
├─ 생활 점검 ─────────────── 응답 기반 요약
└─ /api/apply/* ─────────── 신청서 문항 확인·AI 초안
                             └─ 승인된 팀 소유 테스트 폼만 제출

온통청년 정책 API · 청년센터 공식 웹
        │
        ▼
Python 수집 → 정제 → AI 분류·공고 정보 추출
        └───────────────── PostgreSQL + 서비스 데이터
```

**LLM과 규칙 엔진을 분리했습니다.** 조이는 요청을 이해하고 공고의 내용을 설명하지만, 없는 정책을 자유 생성해 목록에 넣지 않습니다. 실제 후보는 수집한 데이터와 검색·추천 로직에서 가져옵니다. 자격 조건도 확정적으로 단정하지 않고 공고 근거와 추가 확인 사항을 구분합니다.

## 4. 데이터 파이프라인

```text
온통청년 정책 API ────────────────┐
                                  ├─ 수집 → 정제 → 분류/정보 추출
서울청년센터·개별 센터 공고 ──────┘
                                              │
                              ┌───────────────┴───────────────┐
                              ▼                               ▼
                       serving JSON                     PostgreSQL
                       (기본 데이터)                 (목록·변경 이력)
                              └───────────┬───────────────────┘
                                          ▼
                                검색·추천·상세 API
```

- **정책:** 온통청년 API로 청년정책을 수집하고 연령·지역·지원 조건 등 서비스에 필요한 정보를 정리합니다.
- **프로그램·센터:** 서울청년센터 및 일부 개별 센터 웹사이트에서 공식 공고·센터 정보를 수집합니다.
- **분류·정보 추출:** AI와 검증 로직으로 카테고리·활동 내용·기간·장소·신청 정보 등을 구조화합니다. 원문에서 확인되지 않는 사실은 임의로 채우지 않습니다.
- **갱신·안전장치:** 단계별 실패 격리, LLM 분류 캐시, 증분 수집, 적재량 급감 방지, 공고 변경 이력 기록을 적용합니다.
- **장애 대응:** DB를 사용할 수 없거나 서비스 데이터가 없는 경우 준비된 serving 데이터를 활용하는 대체 경로가 있습니다. 응답의 `source`로 데이터 출처를 구분합니다.

데이터 수집 범위는 전국의 모든 청년센터를 완전히 포괄하는 것이 아니며, 공고의 최종 자격·모집 상태는 공식 출처에서 확인해야 합니다.

## 5. 주요 API

| Method | Endpoint | 역할 |
| --- | --- | --- |
| `GET` | `/healthz` | 서버 상태 확인 |
| `GET` | `/readyz` | DB 연결 확인 |
| `GET` | `/api/regions` | 거주 지역 코드 목록 |
| `GET` | `/api/checkin/questions` | 생활 점검 문항 |
| `POST` | `/api/checkin/summary` | 생활 점검 요약 |
| `POST` | `/api/recommendations` | 프로필·생활 점검 기반 추천 |
| `POST` | `/api/chat` | 조이 AI 대화 |
| `GET` | `/api/catalog/items` | 정책·프로그램 목록/검색 |
| `GET` | `/api/catalog/items/{item_id}` | 공고 상세 |
| `GET` | `/api/centers` | 청년센터 목록 |
| `GET` | `/api/centers/{center_id}` | 센터 상세·프로그램 |
| `POST` | `/api/apply/start` | 신청서 문항 확인 |
| `POST` | `/api/apply/draft` | 서술형 답변 초안 |
| `POST` | `/api/apply/submit` | 승인된 테스트 폼만 제출 |

상세 요청·응답 계약은 [추천](docs/RECOMMENDATION.md), [AI 대화](docs/CHAT.md), [신청 지원](docs/APPLY.md), [프론트 연동](docs/FRONTEND.md) 문서와 FastAPI의 `/docs`에서 확인할 수 있습니다.

## 6. AI 활용과 안전장치

- **대화 입력:** 자유 입력의 의도와 관심사를 정리하고 필요한 경우 추가 질문을 생성합니다. 기존 대화와 선택 공고 식별자를 활용해 문맥을 이어갑니다.
- **공고 근거:** 추천할 공고는 서버 데이터에서 조회하고, 설명은 조회한 공고의 공개 정보에 기반합니다.
- **자격 안내:** 연령·지역 등 확인 가능한 조건과 소득·재산처럼 사용자가 추가 확인해야 할 조건을 구분합니다.
- **신청 범위 제한:** 일반 기관 Google Form은 읽기·작성 지원까지만 제공합니다. 서버의 `test_only`, 별도 `submission_form_url`, `submission_enabled` 조건을 충족하는 **팀 소유 복제 폼**만 제출할 수 있고, 제출 전 문항 변경도 검사합니다.
- **개인정보 최소화:** AI 초안 생성 시 이름·연락처 등 식별 정보를 가리는 처리를 사용합니다. 신청 답변·대화 내용은 사용자 계정 DB에 적재하지 않도록 구성했습니다.
- **호출 제어:** 서버에서 AI 키를 보관하고 요청 빈도·사용량 제한, 오류 응답, 위험 신호에 대한 별도 안내 경로를 둡니다.

조이는 실제 기관에 전화를 걸거나 임의로 신청을 완료하는 자동 대행 서비스가 아닙니다.

## 7. 로컬 실행

**환경:** Python 3.13. PostgreSQL을 포함한 개발 환경에서는 Docker Desktop 또는 Docker Engine + Compose가 필요합니다.

```bash
git clone https://github.com/dos-tres/backend.git
cd backend

python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env

python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- API 문서: **http://127.0.0.1:8000/docs**
- 서버 상태: **http://127.0.0.1:8000/healthz**
- DB를 연결하지 않으면 `/readyz`는 503일 수 있으며, 카탈로그·추천 기능은 서비스 데이터 경로를 사용할 수 있습니다.
- 실제 AI 대화와 초안에는 `backend/.env`의 `OPENAI_API_KEY`가 필요합니다. 키가 없으면 일반 AI 요청은 `AI_UNAVAILABLE` 응답을 반환합니다.

### PostgreSQL 사용 시

`.env`에 `POSTGRES_PASSWORD`, `DATABASE_URL` 등 로컬 DB 설정을 지정합니다. 연결 URL은 `.env.example`의 형식을 참고합니다.

```bash
docker compose up -d --wait db
python -m alembic upgrade head
python -m pipeline.load_catalog --seed
```

이후 API 서버를 실행합니다. 개발 DB는 Docker volume에 보관되므로 일반 종료 시 `docker compose down -v`를 실행하지 않도록 주의합니다.

### 프론트엔드 연결

[Frontend 저장소](https://github.com/dos-tres/frontend)에서 `npm ci`, `npm run dev -- --host 127.0.0.1 --port 5173`을 실행합니다. Vite 개발 프록시가 `/api` 요청을 백엔드의 8000 포트로 전달합니다.

## 8. 환경변수와 보안

필요한 항목은 `.env.example`에 설명되어 있습니다.

| 변수 | 용도 |
| --- | --- |
| `OPENAI_API_KEY` | 조이 대화·공고 분류·AI 초안용 서버 비밀키 |
| `LLM_MODEL` | 사용 모델 (기본 `gpt-4.1-mini`) |
| `DATABASE_URL` | PostgreSQL 연결 URL |
| `ALLOWED_ORIGINS` | 프론트엔드의 허용 origin |
| `YOUTH_POLICY_API_KEY`, `YOUTH_CENTER_API_KEY` | 공식 청년정책·센터 데이터 수집 |
| `APPLY_FORMS_PATH`, `APPLY_FORMS_JSON` | 서버가 승인한 테스트 폼 설정 |
| `SCHEDULER_ENABLED` | 실행 환경에서 데이터 갱신 스케줄러 사용 여부 |

**실제 `.env`, 개인 정보, API 키, 테스트 폼의 비공개 설정을 Git에 올리지 않습니다.** `VITE_*`처럼 브라우저로 노출되는 프론트 환경변수에 서버 비밀값을 넣지 않습니다.

## 9. 프로젝트 구성과 검증

```text
app/
├─ main.py              # FastAPI 앱·예외·헬스체크
├─ chat/                # 조이 대화·공고 선별·AI·안전 처리
├─ recommend/           # 추천 API·규칙 엔진
├─ catalog/             # 정책·프로그램·센터 카탈로그
├─ checkin/             # 생활 점검 문항·요약
├─ apply/               # 신청 문항·초안·테스트 폼 제출
├─ users/               # 사용자 관련 DB 모델
└─ database.py          # DB 연결·세션
pipeline/               # 정책 API/센터 크롤링·분류·적재
migrations/             # Alembic 스키마
data/seed/              # 재현 가능한 서비스 기본 데이터
tests/                  # API·추천·대화·신청·DB 테스트
docs/                   # 상세 설계·데이터 계약·배포 안내
```

```bash
python -m unittest discover -s tests -v
python -m pip check
```

DB 연동 테스트는 `.env`의 **별도 테스트 DB** 설정을 요구할 수 있습니다. 테스트 DB용 Compose 프로필과 운영·개발 데이터의 분리 방법은 [DB 가이드](docs/DATABASE.md)를 참고하세요.

배포용 단일 Docker 이미지(프론트 빌드 + FastAPI) 구성과 환경별 실행 절차는 [배포 가이드](docs/DEPLOYMENT.md)에 정리되어 있습니다.

## 10. 함께 보기

- **[Frontend](https://github.com/dos-tres/frontend)** — 사용자 화면, 조이 대화 UI, 지도, 신청서 작성, 일정·기록
- **[데이터 수집](docs/CRAWLER.md)** · **[추천 설계](docs/RECOMMENDATION.md)** · **[공고 정보 추출](docs/PROGRAM_FACTS.md)**
- **[AI 대화](docs/CHAT.md)** · **[신청 지원](docs/APPLY.md)** · **[DB 구성](docs/DATABASE.md)** · **[배포](docs/DEPLOYMENT.md)**

---

**둘셋의 목표는 더 많은 정보를 보여주는 것이 아니라, 청년이 자신에게 맞는 첫 행동을 시작하도록 돕는 것입니다.**
