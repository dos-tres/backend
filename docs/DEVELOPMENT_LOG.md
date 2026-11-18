# 개발 로그

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
