"""AuraFlow — Global error handler for AppError exceptions."""
from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.errors import AppError
from app.core.logging import logger


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Catch AppError and return a standardised JSON envelope."""
    request_id = getattr(request.state, "request_id", None)

    # Contextual fields for the log entry
    log_ctx = {
        "error_code": exc.code,
        "status_code": exc.status_code,
        "request_id": request_id,
        "path": request.url.path,
        "method": request.method,
    }

    # Attach user / org context when available
    user_id = getattr(request.state, "user_id", None)
    org_id = getattr(request.state, "org_id", None)
    if user_id:
        log_ctx["user_id"] = user_id
    if org_id:
        log_ctx["org_id"] = org_id

    if exc.status_code >= 500:
        logger.error(exc.message, **log_ctx)
    else:
        logger.warning(exc.message, **log_ctx)

    payload = {
        "error": {
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
        },
        "request_id": request_id,
    }

    return JSONResponse(status_code=exc.status_code, content=payload)
