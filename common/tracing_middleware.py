"""FastAPI/Starlette middleware — one SERVER span per HTTP request."""
from __future__ import annotations

from opentelemetry import propagate, trace
from opentelemetry.trace import SpanKind, StatusCode
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_TRACER_NAME = "dox.http"


class TracingMiddleware(BaseHTTPMiddleware):
    """Records one SERVER span per HTTP request, propagating W3C traceparent."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        carrier = dict(request.headers)
        ctx = propagate.extract(carrier)
        tracer = trace.get_tracer(_TRACER_NAME)

        with tracer.start_as_current_span(
            f"{request.method} {request.url.path}",
            context=ctx,
            kind=SpanKind.SERVER,
        ) as span:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.route", request.url.path)
            span.set_attribute("http.url", str(request.url))

            response = await call_next(request)

            span.set_attribute("http.status_code", response.status_code)
            if response.status_code >= 500:
                span.set_status(StatusCode.ERROR)

            return response
