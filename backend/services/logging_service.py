"""
Structured logging utilities for Tsushin.

Provides:
- JsonFormatter: emits each log record as a single JSON line.
- request_id context variable: populated by RequestIdMiddleware.
"""

import json
import logging
import re
import traceback
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Per-request context
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")

# Only accept UUID-like values for X-Request-Id (alphanumeric + hyphens, 8-36 chars)
_REQUEST_ID_RE = re.compile(r"^[0-9a-fA-F-]{8,36}$")


class JsonFormatter(logging.Formatter):
    """Emit log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": "tsn-core",
        }

        rid = request_id_ctx.get("")
        if rid:
            payload["request_id"] = rid

        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = "".join(
                traceback.format_exception(*record.exc_info)
            )

        return json.dumps(payload, default=str)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Generates a UUID for every inbound HTTP request, stores it in a
    contextvar so log records can include it, and returns it as a
    response header (X-Request-Id).
    """

    async def dispatch(self, request: Request, call_next):
        incoming_rid = request.headers.get("X-Request-Id", "")
        rid = incoming_rid if _REQUEST_ID_RE.match(incoming_rid) else str(uuid.uuid4())
        token = request_id_ctx.set(rid)
        try:
            response = await call_next(request)
            # Don't overwrite X-Request-Id for /api/v1/ paths — the
            # ApiV1RateLimitMiddleware already sets a req_-prefixed ID.
            if not request.url.path.startswith("/api/v1/"):
                response.headers["X-Request-Id"] = rid
            return response
        finally:
            request_id_ctx.reset(token)
