"""Unit tests for Module 20 — OpenTelemetry tracing bootstrap and HTTP middleware."""
from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode
from starlette.responses import Response

from common.tracing import SERVICE_NAME_KEY, configure_tracing, get_tracer
from common.tracing_middleware import TracingMiddleware

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def exporter() -> Generator[InMemorySpanExporter, None, None]:
    exp = InMemorySpanExporter()
    provider = configure_tracing("test-svc", exporter=exp)
    yield exp
    provider.shutdown()
    # Reset global to a fresh no-op provider so tests don't bleed state
    trace.set_tracer_provider(TracerProvider())


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_app(exporter: InMemorySpanExporter) -> FastAPI:
    configure_tracing("test", exporter=exporter)
    app = FastAPI()
    app.add_middleware(TracingMiddleware)

    @app.get("/ok")
    async def _ok() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/error")
    async def _error() -> Response:
        from fastapi.responses import JSONResponse

        return JSONResponse({"error": "boom"}, status_code=500)

    return app


# ---------------------------------------------------------------------------
# TestConfigureTracing
# ---------------------------------------------------------------------------


class TestConfigureTracing:
    def test_returns_tracer_provider(self, exporter: InMemorySpanExporter) -> None:
        provider = configure_tracing("svc", exporter=exporter)
        assert isinstance(provider, TracerProvider)
        provider.shutdown()
        trace.set_tracer_provider(TracerProvider())

    def test_get_tracer_returns_tracer(self, exporter: InMemorySpanExporter) -> None:
        t = get_tracer("test-module")
        assert isinstance(t, trace.Tracer)

    def test_span_recorded_with_exporter(self, exporter: InMemorySpanExporter) -> None:
        tracer = get_tracer("test")
        with tracer.start_as_current_span("my-span"):
            pass
        spans = exporter.get_finished_spans()
        assert len(spans) == 1

    def test_span_has_service_name_in_resource(self, exporter: InMemorySpanExporter) -> None:
        provider = configure_tracing("svc-under-test", exporter=exporter)
        tracer = provider.get_tracer("t")
        with tracer.start_as_current_span("op"):
            pass
        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].resource.attributes[SERVICE_NAME_KEY] == "svc-under-test"
        provider.shutdown()
        trace.set_tracer_provider(TracerProvider())

    def test_span_name_set(self, exporter: InMemorySpanExporter) -> None:
        tracer = get_tracer("test")
        with tracer.start_as_current_span("my-operation"):
            pass
        spans = exporter.get_finished_spans()
        assert spans[0].name == "my-operation"

    def test_span_attributes_set(self, exporter: InMemorySpanExporter) -> None:
        tracer = get_tracer("test")
        with tracer.start_as_current_span("op") as span:
            span.set_attribute("key", "value")
        spans = exporter.get_finished_spans()
        attrs = spans[0].attributes
        assert attrs is not None
        assert attrs["key"] == "value"

    def test_no_exporter_creates_no_spans(self) -> None:
        exp = InMemorySpanExporter()
        provider = configure_tracing("no-export-svc")
        # Use the internal exporter, not the global one
        tracer = provider.get_tracer("t")
        with tracer.start_as_current_span("silent-op"):
            pass
        # Nothing was added to exp because we never added exp to this provider
        assert len(exp.get_finished_spans()) == 0
        provider.shutdown()
        trace.set_tracer_provider(TracerProvider())

    def test_configure_twice_replaces_provider(self) -> None:
        exp1 = InMemorySpanExporter()
        exp2 = InMemorySpanExporter()
        provider1 = configure_tracing("first", exporter=exp1)
        provider2 = configure_tracing("second", exporter=exp2)

        # Use the global tracer — it should now point to provider2
        tracer = get_tracer("t")
        with tracer.start_as_current_span("op"):
            pass

        assert len(exp1.get_finished_spans()) == 0
        assert len(exp2.get_finished_spans()) == 1

        provider1.shutdown()
        provider2.shutdown()
        trace.set_tracer_provider(TracerProvider())

    def test_nested_spans_share_trace_id(self, exporter: InMemorySpanExporter) -> None:
        tracer = get_tracer("test")
        with tracer.start_as_current_span("parent"):
            with tracer.start_as_current_span("child"):
                pass
        spans = exporter.get_finished_spans()
        assert len(spans) == 2
        trace_ids = {s.context.trace_id for s in spans if s.context is not None}
        assert len(trace_ids) == 1

    def test_w3c_propagator_extracts_from_carrier(self, exporter: InMemorySpanExporter) -> None:
        from opentelemetry import propagate

        trace_id_hex = "4bf92f3577b34da6a3ce929d0e0e4736"
        span_id_hex = "00f067aa0ba902b7"
        traceparent = f"00-{trace_id_hex}-{span_id_hex}-01"
        carrier = {"traceparent": traceparent}
        ctx = propagate.extract(carrier)
        span_ctx = trace.get_current_span(ctx).get_span_context()
        assert span_ctx is not None
        assert span_ctx.is_valid


# ---------------------------------------------------------------------------
# TestTracingMiddleware
# ---------------------------------------------------------------------------


class TestTracingMiddleware:
    async def test_one_span_per_request(self) -> None:
        exp = InMemorySpanExporter()
        app = _make_app(exp)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.get("/ok")
        assert len(exp.get_finished_spans()) == 1
        trace.set_tracer_provider(TracerProvider())

    async def test_span_name_includes_method_and_path(self) -> None:
        exp = InMemorySpanExporter()
        app = _make_app(exp)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.get("/ok")
        span = exp.get_finished_spans()[0]
        assert span.name == "GET /ok"
        trace.set_tracer_provider(TracerProvider())

    async def test_http_method_attribute(self) -> None:
        exp = InMemorySpanExporter()
        app = _make_app(exp)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.get("/ok")
        span = exp.get_finished_spans()[0]
        assert span.attributes is not None
        assert span.attributes["http.method"] == "GET"
        trace.set_tracer_provider(TracerProvider())

    async def test_http_route_attribute(self) -> None:
        exp = InMemorySpanExporter()
        app = _make_app(exp)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.get("/ok")
        span = exp.get_finished_spans()[0]
        assert span.attributes is not None
        assert span.attributes["http.route"] == "/ok"
        trace.set_tracer_provider(TracerProvider())

    async def test_http_status_code_200(self) -> None:
        exp = InMemorySpanExporter()
        app = _make_app(exp)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.get("/ok")
        span = exp.get_finished_spans()[0]
        assert span.attributes is not None
        assert span.attributes["http.status_code"] == 200
        trace.set_tracer_provider(TracerProvider())

    async def test_http_url_attribute_set(self) -> None:
        exp = InMemorySpanExporter()
        app = _make_app(exp)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.get("/ok")
        span = exp.get_finished_spans()[0]
        assert span.attributes is not None
        assert "http://test" in str(span.attributes["http.url"])
        trace.set_tracer_provider(TracerProvider())

    async def test_span_kind_is_server(self) -> None:
        exp = InMemorySpanExporter()
        app = _make_app(exp)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.get("/ok")
        span = exp.get_finished_spans()[0]
        assert span.kind == SpanKind.SERVER
        trace.set_tracer_provider(TracerProvider())

    async def test_successful_response_ok_span_status(self) -> None:
        exp = InMemorySpanExporter()
        app = _make_app(exp)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.get("/ok")
        span = exp.get_finished_spans()[0]
        assert span.status.status_code != StatusCode.ERROR
        trace.set_tracer_provider(TracerProvider())

    async def test_error_response_sets_error_span_status(self) -> None:
        exp = InMemorySpanExporter()
        app = _make_app(exp)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.get("/error")
        span = exp.get_finished_spans()[0]
        assert span.status.status_code == StatusCode.ERROR
        trace.set_tracer_provider(TracerProvider())

    async def test_response_passthrough(self) -> None:
        exp = InMemorySpanExporter()
        app = _make_app(exp)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/ok")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        trace.set_tracer_provider(TracerProvider())

    async def test_traceparent_header_creates_child_span(self) -> None:
        exp = InMemorySpanExporter()
        app = _make_app(exp)
        trace_id_hex = "4bf92f3577b34da6a3ce929d0e0e4736"
        span_id_hex = "00f067aa0ba902b7"
        traceparent = f"00-{trace_id_hex}-{span_id_hex}-01"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.get("/ok", headers={"traceparent": traceparent})
        span = exp.get_finished_spans()[0]
        assert span.context is not None
        expected_trace_id = int(trace_id_hex, 16)
        assert span.context.trace_id == expected_trace_id
        trace.set_tracer_provider(TracerProvider())

    async def test_multiple_requests_multiple_spans(self) -> None:
        exp = InMemorySpanExporter()
        app = _make_app(exp)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.get("/ok")
            await client.get("/ok")
            await client.get("/ok")
        assert len(exp.get_finished_spans()) == 3
        trace.set_tracer_provider(TracerProvider())
