"""AuraFlow — Standardized application error classes."""
from typing import Any, Dict, Optional


class AppError(Exception):
    """Base application error with structured fields."""

    def __init__(
        self,
        code: str = "INTERNAL_ERROR",
        message: str = "An unexpected error occurred",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class NotFoundError(AppError):
    def __init__(
        self,
        message: str = "Resource not found",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code="NOT_FOUND",
            message=message,
            status_code=404,
            details=details,
        )


class ValidationError(AppError):
    def __init__(
        self,
        message: str = "Validation failed",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            status_code=422,
            details=details,
        )


class ForbiddenError(AppError):
    def __init__(
        self,
        message: str = "Access denied",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code="FORBIDDEN",
            message=message,
            status_code=403,
            details=details,
        )


class ConflictError(AppError):
    def __init__(
        self,
        message: str = "Resource conflict",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code="CONFLICT",
            message=message,
            status_code=409,
            details=details,
        )


class ServiceUnavailableError(AppError):
    def __init__(
        self,
        message: str = "Service temporarily unavailable",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code="SERVICE_UNAVAILABLE",
            message=message,
            status_code=503,
            details=details,
        )
