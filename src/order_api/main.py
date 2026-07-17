from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from order_api.api.v1.router import readiness, router
from order_api.core.config import get_settings
from order_api.core.database import get_db
from order_api.core.error_handlers import (
    app_error_handler,
    http_error_handler,
    integrity_error_handler,
    unexpected_error_handler,
    validation_error_handler,
)
from order_api.core.exceptions import AppError
from order_api.core.logging import configure_logging
from order_api.middleware.request_id import RequestIDMiddleware

configure_logging()
settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.0.0")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
)
app.add_middleware(RequestIDMiddleware)
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(IntegrityError, integrity_error_handler)
app.add_exception_handler(StarletteHTTPException, http_error_handler)
app.add_exception_handler(Exception, unexpected_error_handler)
app.include_router(router, prefix="/api/v1")


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}


@app.get("/ready", tags=["health"])
def ready(db: Session = Depends(get_db)):
    try:
        readiness(db)
    except Exception as exc:
        raise AppError("SERVICE_UNAVAILABLE", "Database unavailable.", status_code=503) from exc
    return {"status": "ready"}
