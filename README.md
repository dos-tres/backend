# 둘셋 · DOS TRES — Backend

둘셋(DOS TRES)의 백엔드 및 AI 에이전트 저장소입니다.

## 기술 스택

2026-11-18 결정 기준입니다.

| 구분 | 언어 | 프레임워크·도구 |
| --- | --- | --- |
| 프론트엔드 | TypeScript | React + Vite |
| 백엔드 API | Python | FastAPI |
| AI 에이전트 | Python | 백엔드 저장소 내부에서 함께 개발 |

프론트엔드는 [dos-tres/frontend](https://github.com/dos-tres/frontend)에서 관리합니다. AI 모델·에이전트 라이브러리·DB·인증 방식·전화 연동 서비스는 아직 미정입니다.

## 요구사항

[백엔드 및 AI 비서 요구사항](docs/requirements.md)

- 회원가입·첫 이용 시 선택형 현재 상태 체크
- 짧은 말과 선택지로 진행하는 AI 비서 대화
- 정책·프로그램 탐색과 조건 확인
- 전화 문의 대행, 신청 준비, 일정·참여 이력 관리

## 현재 상태

FastAPI 실행 기반을 구현했습니다. GET /healthz, Swagger UI(/docs), 환경 설정, 개발용 CORS와 공통 오류 응답을 제공합니다. DB·세션·설문·정책·AI 연동은 아직 구현하지 않았습니다.

## 설치와 로컬 실행

Python 3.13을 사용합니다. 저장소 루트에서 실행합니다.

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

실행만 필요한 환경은 `requirements.txt`를 설치합니다. 실행 의존성은 FastAPI, ASGI 서버 Uvicorn, 설정 및 .env 로딩용 pydantic-settings이며, httpx는 테스트에만 사용합니다. 종료는 Ctrl+C입니다.

외부 접속과 실행 환경의 포트가 필요한 경우 reload 없이 실행합니다. HOST·PORT는 아래 셸 명령에서 읽으며 .env의 앱 설정과 별개입니다.

```bash
python -m uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
```

## 환경 설정과 프론트 연결

설정 우선순위는 프로세스 환경변수 → 저장소 루트의 .env → 기본값입니다. 설정 변경 후 서버를 재시작합니다. 실제 .env는 Git에서 제외합니다.

| 변수 | 기본값 | 형식 |
| --- | --- | --- |
| APP_ENV | local | local / staging / production |
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

자동 테스트는 healthz·문서·OpenAPI, 환경변수 우선순위·검증, CORS 허용/거부, 404·405·422·500 오류를 확인합니다. GitHub Actions에서도 같은 명령을 실행하도록 구성했습니다.

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

1. backend-bootstrap PR 리뷰를 받고 리뷰 결과를 반영합니다.
2. 대화 API 계약과 프론트 공통 API 모듈을 합의·구현합니다.
3. 제공업체·모델을 선정한 뒤 실제 AI 호출과 실패·시간 초과 처리를 구현합니다.
4. 로컬 실제 연결 검증 후 HTTPS 미리보기 배포를 준비합니다.
5. 인증·DB 도입과 함께 상태 체크와 개인 이력 저장을 설계합니다.

위 단계는 계획이며 이번 실행 기반 구현에 포함되지 않습니다. 작업 기록과 인수인계 절차는 [개발 로그](docs/DEVELOPMENT_LOG.md), 저장소 작업 규칙은 [AGENTS.md](AGENTS.md)를 확인합니다.
