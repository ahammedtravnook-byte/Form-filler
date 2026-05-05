"""Global exception handler middleware: maps domain errors to JSON HTTP responses."""

from __future__ import annotations

import traceback

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from api.core.exceptions import domain_exc_to_http
from api.core.logging import get_logger, request_id_var
from pdf_filler.exceptions import PdfFillerError

_log = get_logger("api.error_handler")


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: object) -> Response:
        try:
            return await call_next(request)  # type: ignore[arg-type]
        except PdfFillerError as exc:
            http_exc = domain_exc_to_http(exc)
            _log.warning(
                "Domain error [%s]: %s",
                type(exc).__name__,
                str(exc),
            )
            return JSONResponse(
                status_code=http_exc.status_code,
                content={"detail": http_exc.detail, "request_id": request_id_var.get("-")},
            )
        except Exception:
            _log.error("Unhandled exception:\n%s", traceback.format_exc())
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error.",
                    "request_id": request_id_var.get("-"),
                },
            )
