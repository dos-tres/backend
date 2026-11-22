import logging
import threading
from contextlib import asynccontextmanager
from http import HTTPStatus

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware

from app.config import Settings
from app.database import Database, DatabaseNotConfigured, get_db
from app.chat.llm import LLMUnavailable, OpenAICompatible
from app.apply.router import router as apply_router
from app.chat.router import router as chat_router
from app.recommend.router import router as recommend_router
from app.limits import RateLimited, UsageLimiter
from app.scheduler import DailyPipeline, pipeline_args, prepare_database
from app.web import web_files

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: str = "ok"


def error_response(status: int, code: str, message: str, headers=None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
        headers=headers,
    )


def create_app(settings: Settings | None = None) -> CORSMiddleware:
    settings = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(api: FastAPI):
        url = settings.database_url.get_secret_value()
        database = Database(url) if url else None
        api.state.database = database
        daily = None
        prepare = prepare_database if (url and settings.db_auto_migrate) else None
        if settings.scheduler_enabled:
            daily = DailyPipeline(pipeline_args(bool(url), bool(settings.llm_api_key.get_secret_value())),
                                  settings.scheduler_hour, prepare=prepare)
            daily.start()
        elif prepare is not None:
            # 서버가 먼저 뜨도록(헬스체크) 뒤에서 한다. 끝나기 전 요청은 서비스 JSON 으로 응답
            threading.Thread(target=prepare, name="db-prepare", daemon=True).start()
        api.state.daily_pipeline = daily
        try:
            yield
        finally:
            if daily is not None:
                daily.shutdown()
            if database is not None:
                database.dispose()
            api.state.database = None

    api = FastAPI(title="DOS TRES API", version="0.1.0", debug=False, lifespan=lifespan)
    api.state.settings = settings
    api.state.database = None
    llm_key = settings.llm_api_key.get_secret_value()
    api.state.limiter = UsageLimiter(settings.llm_limit_per_minute, settings.llm_limit_per_day,
                                     settings.llm_limit_total_per_day)
    api.state.chat_model = (OpenAICompatible(llm_key, settings.llm_base_url, settings.llm_model,
                                             settings.llm_timeout_seconds) if llm_key else None)

    @api.get("/healthz", response_model=HealthResponse, tags=["health"])
    async def healthz() -> HealthResponse:
        return HealthResponse()

    @api.exception_handler(DatabaseNotConfigured)
    async def database_missing(request: Request, exc: DatabaseNotConfigured) -> JSONResponse:
        return error_response(503, "DATABASE_UNAVAILABLE", "Database unavailable")

    @api.get("/readyz", response_model=HealthResponse, tags=["health"], responses={503: {"description": "Database unavailable"}})
    def readyz(session: Session = Depends(get_db)):
        try:
            session.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return error_response(503, "DATABASE_UNAVAILABLE", "Database unavailable")
        return HealthResponse()

    api.include_router(recommend_router)
    api.include_router(chat_router)
    api.include_router(apply_router)

    web = web_files(settings.web_dir)
    if web is not None:
        api.mount("/", web, name="web")   # 라우터 뒤에 둬서 /api·/healthz 가 먼저 받는다

    @api.exception_handler(RateLimited)
    async def rate_limited(request: Request, exc: RateLimited) -> JSONResponse:
        message = ("Too many requests today" if exc.scope in ("day", "total") else "Too many requests, try again shortly")
        return error_response(429, "RATE_LIMITED", message, {"Retry-After": str(exc.retry_after)})

    @api.exception_handler(LLMUnavailable)
    async def llm_unavailable(request: Request, exc: LLMUnavailable) -> JSONResponse:
        # 예시 답변으로 대신하지 않는다. 위기 안내는 LLM 없이 이미 처리됐다
        return error_response(503, "AI_UNAVAILABLE", "AI assistant unavailable")

    @api.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error_response(
            exc.status_code, f"HTTP_{exc.status_code}",
            str(exc.detail) if exc.detail else HTTPStatus(exc.status_code).phrase,
            exc.headers,
        )

    @api.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(422, "VALIDATION_ERROR", "Request validation failed")

    @api.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        # Do not include exception text or request contents in the response/log.
        logger.error("Unhandled application error: %s", type(exc).__name__)
        return error_response(500, "INTERNAL_SERVER_ERROR", "Internal server error")

    # Wrap the whole application so even unhandled error responses include CORS.
    return CORSMiddleware(
        api,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )


app = create_app()
