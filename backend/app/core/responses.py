import uuid
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorMeta(BaseModel):
    type: str


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "success"
    data: T | None = None
    request_id: str
    error: ErrorMeta | None = None


class AppError(Exception):
    def __init__(self, status_code: int, code: int, message: str, error_type: str = "request_failed") -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.error_type = error_type


def ok(data: T | None = None, message: str = "success") -> ApiResponse[T]:
    return ApiResponse[T](code=0, message=message, data=data, request_id=str(uuid.uuid4()))


def _stringify_errors(errors: list[dict]) -> list[dict]:
    """Make validation error payloads JSON-safe."""
    safe_errors: list[dict] = []
    for item in errors:
        safe: dict = {}
        for key, value in item.items():
            if key == "ctx" and isinstance(value, dict):
                safe[key] = {k: str(v) for k, v in value.items()}
            elif isinstance(value, (str, int, float, bool)) or value is None:
                safe[key] = value
            elif isinstance(value, (list, tuple)):
                safe[key] = [str(v) if not isinstance(v, (str, int, float, bool)) and v is not None else v for v in value]
            else:
                safe[key] = str(value)
        safe_errors.append(safe)
    return safe_errors


def install_exception_handlers(app) -> None:
    from fastapi import Request
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "data": None,
                "request_id": str(uuid.uuid4()),
                "error": {"type": exc.error_type},
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = _stringify_errors(exc.errors())
        first_message = "Request validation failed"
        if details:
            raw = str(details[0].get("msg", ""))
            first_message = raw.removeprefix("Value error, ").strip() or first_message
        return JSONResponse(
            status_code=422,
            content={
                "code": 42200,
                "message": first_message,
                "data": None,
                "request_id": str(uuid.uuid4()),
                "error": {"type": "validation_error"},
                "details": details,
            },
        )
