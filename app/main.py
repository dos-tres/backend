import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware

from app.config import Settings

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
    api = FastAPI(title="DOS TRES API", version="0.1.0", debug=False)
    api.state.settings = settings

    @api.get("/healthz", response_model=HealthResponse, tags=["health"])
    async def healthz() -> HealthResponse:
        return HealthResponse()

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
