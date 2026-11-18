from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message


def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": request.state.request_id,
            }
        },
        headers={"WWW-Authenticate": "Bearer"} if status == 401 else None,
    )


def register_error_handlers(app):
    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError):
        return error_response(request, exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _exc: RequestValidationError):
        # 입력값, 토큰, 원문을 오류 응답에 되돌려 보내지 않습니다.
        return error_response(request, 422, "VALIDATION_ERROR", "요청 형식을 확인해주세요.")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error_response(request, exc.status_code, "HTTP_ERROR", "요청을 처리할 수 없습니다.")

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, _exc: SQLAlchemyError):
        return error_response(request, 503, "DATABASE_UNAVAILABLE", "잠시 후 다시 시도해주세요.")

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, _exc: Exception):
        return error_response(request, 500, "INTERNAL_ERROR", "요청 처리 중 오류가 발생했습니다.")
