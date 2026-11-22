# 둘셋 배포 이미지 1개: FE 빌드(dist) + FastAPI (docs/DEPLOYMENT.md "배포 방법")
#
# frontend·backend 는 다른 저장소라, 두 폴더를 함께 둔 작업 폴더(dos-tres)에서 빌드한다:
#   docker build -f backend/Dockerfile -t dostres .
# 빌드에 넣지 않는 파일(.env, *.local.json, node_modules 등)은 backend/Dockerfile.dockerignore
# 비밀값(API 키·DB 주소·테스트 폼 주소)은 이미지에 넣지 않고 실행 환경변수로 준다.

# ---- 1. FE 빌드 ----
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/ ./
# postinstall 이 assets/images.json 에서 이미지를 복원하므로 소스를 먼저 복사한다
RUN npm ci --no-audit --no-fund && npm run build

# ---- 2. 서버 ----
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    TZ=Asia/Seoul \
    APP_ENV=production \
    WEB_DIR=/app/web \
    PORT=8000
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist ./web
# 매일 갱신 결과(data/runtime)를 쓸 수 있게 일반 사용자로 실행
RUN useradd --create-home --uid 10001 app && mkdir -p data/runtime && chown -R app:app /app
USER app
EXPOSE 8000
# Lightsail 은 HTTPS 를 앞단에서 끝내고 HTTP 로 넘긴다 → 프록시 헤더로 실제 접속 주소(사용량 제한)를 읽는다
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
