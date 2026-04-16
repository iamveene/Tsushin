"""
Prometheus metrics definitions and middleware for Tsushin.

Guarded by TSN_METRICS_ENABLED (default: true).
When disabled, the /metrics endpoint returns 404 and the middleware is a no-op.
"""

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

import settings

# ---------------------------------------------------------------------------
# Metric definitions (created only when metrics are enabled)
# ---------------------------------------------------------------------------

if settings.METRICS_ENABLED:
    from prometheus_client import Counter, Histogram, Gauge, Info, generate_latest, CONTENT_TYPE_LATEST

    SERVICE_INFO = Info("tsn_service", "Tsushin service metadata")
    SERVICE_INFO.info({
        "version": settings.SERVICE_VERSION,
        "service": settings.SERVICE_NAME,
    })

    HTTP_REQUESTS_TOTAL = Counter(
        "http_requests_total",
        "Total HTTP requests",
        ["method", "path_template", "status"],
    )

    HTTP_REQUEST_DURATION = Histogram(
        "http_request_duration_seconds",
        "HTTP request duration in seconds",
        ["method", "path_template"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
    )

    # Item 38: Channel Health Monitor metrics
    TSN_CIRCUIT_BREAKER_TRANSITIONS_TOTAL = Counter(
        "tsn_circuit_breaker_transitions_total",
        "Total circuit breaker state transitions",
        ["channel_type", "from_state", "to_state"],
    )

    TSN_CIRCUIT_BREAKER_STATE = Gauge(
        "tsn_circuit_breaker_state",
        "Current circuit breaker state (0=closed, 1=open, 2=half_open)",
        ["channel_type", "instance_id"],
    )

    TSN_CHANNEL_HEALTH_CHECK_DURATION = Histogram(
        "tsn_channel_health_check_duration_seconds",
        "Channel health check duration in seconds",
        ["channel_type"],
        buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
    )

    TSN_CHANNEL_HEALTH_CHECK_FAILURES_TOTAL = Counter(
        "tsn_channel_health_check_failures_total",
        "Total channel health check failures",
        ["channel_type", "reason"],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_path(path: str) -> str:
    """
    Collapse numeric / UUID path segments to keep cardinality low.
    e.g. /api/agents/42/chat -> /api/agents/{id}/chat
    """
    import re
    parts = path.rstrip("/").split("/")
    normalised = []
    for part in parts:
        if re.fullmatch(r"\d+", part):
            normalised.append("{id}")
        elif re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            part,
            re.IGNORECASE,
        ):
            normalised.append("{uuid}")
        else:
            normalised.append(part)
    return "/".join(normalised) or "/"


# ---------------------------------------------------------------------------
# /metrics endpoint
# ---------------------------------------------------------------------------

async def metrics_endpoint(request: Request) -> Response:
    """Prometheus scrape endpoint.

    If TSN_METRICS_SCRAPE_TOKEN is set, requires Bearer token auth.
    If not set, allows unauthenticated access (local dev).
    """
    if not settings.METRICS_ENABLED:
        return Response(status_code=404, content="Metrics disabled")

    import os
    scrape_token = os.environ.get("TSN_METRICS_SCRAPE_TOKEN")
    if scrape_token:
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer ") or auth_header[7:] != scrape_token:
            return Response(status_code=401, content="Unauthorized")

    body = generate_latest()
    return Response(content=body, media_type=CONTENT_TYPE_LATEST)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class PrometheusMiddleware(BaseHTTPMiddleware):
    """Record request count and duration for every HTTP request."""

    async def dispatch(self, request: Request, call_next):
        if not settings.METRICS_ENABLED:
            return await call_next(request)

        method = request.method
        path = _normalise_path(request.url.path)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration = time.perf_counter() - start
            HTTP_REQUESTS_TOTAL.labels(method=method, path_template=path, status="500").inc()
            HTTP_REQUEST_DURATION.labels(method=method, path_template=path).observe(duration)
            raise
        duration = time.perf_counter() - start

        status = str(response.status_code)
        HTTP_REQUESTS_TOTAL.labels(method=method, path_template=path, status=status).inc()
        HTTP_REQUEST_DURATION.labels(method=method, path_template=path).observe(duration)

        return response
