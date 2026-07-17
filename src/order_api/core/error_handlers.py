import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from order_api.core.exceptions import AppError

logger = logging.getLogger(__name__)


def error_body(request: Request, code: str, message: str, details: object) -> dict:
    request.state.error_code = code
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": getattr(request.state, "request_id", None),
        }
    }


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(request, exc.code, exc.message, exc.details),
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {
            "location": ".".join(str(part) for part in error["loc"]),
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=error_body(request, "VALIDATION_ERROR", "Request validation failed.", details),
    )


async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content=error_body(
            request, "RESOURCE_CONFLICT", "The resource conflicts with existing data.", {}
        ),
    )


async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    codes = {
        401: "AUTHENTICATION_REQUIRED",
        403: "PERMISSION_DENIED",
        404: "RESOURCE_NOT_FOUND",
        409: "RESOURCE_CONFLICT",
    }
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(
            request,
            codes.get(exc.status_code, "HTTP_ERROR"),
            str(exc.detail),
            {},
        ),
        headers=exc.headers,
    )


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled request error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=error_body(request, "INTERNAL_ERROR", "An unexpected error occurred.", {}),
    )
