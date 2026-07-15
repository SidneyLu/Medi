from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "success"
    data: T | None = None


class AppError(Exception):
    def __init__(self, status_code: int, code: int, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message


def ok(data: T | None = None, message: str = "success") -> ApiResponse[T]:
    return ApiResponse[T](code=0, message=message, data=data)


def install_exception_handlers(app) -> None:
    from fastapi import Request
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "data": None},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"code": 42200, "message": "Request validation failed", "data": exc.errors()},
        )
