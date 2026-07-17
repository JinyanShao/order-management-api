from typing import Any


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


def authentication_required(message: str = "Authentication is required.") -> AppError:
    return AppError("AUTHENTICATION_REQUIRED", message, status_code=401)


def permission_denied(message: str = "You do not have permission for this action.") -> AppError:
    return AppError("PERMISSION_DENIED", message, status_code=403)


def not_found(resource: str) -> AppError:
    return AppError("RESOURCE_NOT_FOUND", f"{resource} was not found.", status_code=404)


def conflict(message: str, details: dict[str, Any] | None = None) -> AppError:
    return AppError("RESOURCE_CONFLICT", message, status_code=409, details=details)
