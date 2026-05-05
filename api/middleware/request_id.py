"""Middleware that assigns a UUID to every request and exposes it in logs and response headers."""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from api.core.logging import request_id_var


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: object) -> Response:
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_var.set(rid)
        try:
            response: Response = await call_next(request)  # type: ignore[arg-type]
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        return response
