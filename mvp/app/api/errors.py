from __future__ import annotations

import logging

try:
    from fastapi import HTTPException
except ModuleNotFoundError:  # pragma: no cover
    HTTPException = None  # type: ignore[assignment]

from mvp.app.core.errors import MvpError


logger = logging.getLogger("mvp.api.errors")


def raise_http_error(error: MvpError) -> None:
    logger.warning(
        "MVP API error converted to HTTP response",
        extra={
            "error_code": error.code,
            "status_code": error.status_code,
            "details_count": len(error.details),
        },
    )
    if HTTPException is None:  # pragma: no cover
        raise error
    raise HTTPException(
        status_code=error.status_code,
        detail={
            "error": {
                "code": error.code,
                "message": error.message,
                "details": error.details,
            }
        },
    )
