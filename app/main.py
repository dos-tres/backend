from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.api import profile, sessions
from app.core.config import Settings
from app.core.database import build_engine
from app.core.errors import ApiError, error_response, register_error_handlers
from app.schemas import ErrorResponse


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = build_engine(settings.database_url.get_secret_value())
        app.state.engine = engine
        app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(
        title="둘셋 API",
        version="0.1.0",
        lifespan=lifespan,
        responses={status: {"model": ErrorResponse} for status in (401, 404, 422, 500, 503)},
    )
    app.state.settings = settings
    register_error_handlers(app)

    @app.middleware("http")
    async def request_metadata(request: Request, call_next):
        request.state.request_id = str(uuid4())
        try:
            response = await call_next(request)
        except Exception:
            response = error_response(
                request, 500, "INTERNAL_ERROR", "요청 처리 중 오류가 발생했습니다."
            )
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Request-ID"],
    )

    @app.get("/healthz", tags=["health"])
    def health():
        return {"status": "ok"}

    @app.get("/readyz", tags=["health"])
    def ready(request: Request):
        try:
            with request.app.state.engine.connect() as connection:
                connection.execute(text("SELECT 1 FROM profiles LIMIT 1"))
        except SQLAlchemyError:
            raise ApiError(503, "DATABASE_UNAVAILABLE", "데이터베이스를 준비 중입니다.") from None
        return {"status": "ready"}

    app.include_router(sessions.router, prefix="/api/v1")
    app.include_router(profile.router, prefix="/api/v1")
    return app


app = create_app()
