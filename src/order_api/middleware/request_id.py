import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("order_api.requests")


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started_at = time.perf_counter()
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            route = request.scope.get("route")
            route_path = getattr(route, "path", request.url.path)
            error_code = getattr(request.state, "error_code", None)
            if status_code >= 400 and error_code is None:
                error_code = "HTTP_ERROR"
            logger.info(
                "http_request_completed",
                extra={
                    "request_id": request_id,
                    "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
                    "http_method": request.method,
                    "route": route_path,
                    "status_code": status_code,
                    "user_id": getattr(request.state, "user_id", None),
                    "organization_id": getattr(request.state, "organization_id", None),
                    "error_code": error_code,
                },
            )
