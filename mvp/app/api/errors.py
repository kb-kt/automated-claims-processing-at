from __future__ import annotations

import logging

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
    raise error
