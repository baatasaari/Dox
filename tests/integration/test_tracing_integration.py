"""Integration tests for Module 20 — OTel tracing through the full Dox app."""
from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.main import create_app
from common.tracing import SERVICE_NAME_KEY, configure_tracing

# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
async def traced_client() -> AsyncGenerator[tuple[AsyncClient, InMemorySpanExporter], None]:
    exp = InMemorySpanExporter()
    provider = configure_tracing("dox-integration-test", exporter=exp)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, exp
    provider.shutdown()
    trace.set_tracer_provider(TracerProvider())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTracingIntegration:
    async def test_healthz_request_produces_span(
        self, traced_client: tuple[AsyncClient, InMemorySpanExporter]
    ) -> None:
        client, exp = traced_client
        await client.get("/healthz")
        spans = exp.get_finished_spans()
        assert any(
            s.attributes is not None and "/healthz" in str(s.attributes.get("http.route", ""))
            for s in spans
        )

    async def test_span_service_name_is_dox(
        self, traced_client: tuple[AsyncClient, InMemorySpanExporter]
    ) -> None:
        client, exp = traced_client
        await client.get("/healthz")
        spans = exp.get_finished_spans()
        assert len(spans) >= 1
        assert spans[0].resource.attributes[SERVICE_NAME_KEY] == "dox-integration-test"

    async def test_multiple_requests_produce_multiple_spans(
        self, traced_client: tuple[AsyncClient, InMemorySpanExporter]
    ) -> None:
        client, exp = traced_client
        await client.get("/healthz")
        await client.get("/healthz")
        await client.get("/healthz")
        spans = exp.get_finished_spans()
        assert len(spans) >= 3

    async def test_span_has_http_status_code(
        self, traced_client: tuple[AsyncClient, InMemorySpanExporter]
    ) -> None:
        client, exp = traced_client
        await client.get("/healthz")
        spans = exp.get_finished_spans()
        healthz_spans = [
            s for s in spans
            if s.attributes is not None and s.attributes.get("http.route") == "/healthz"
        ]
        assert len(healthz_spans) >= 1
        assert healthz_spans[0].attributes is not None
        assert healthz_spans[0].attributes["http.status_code"] == 200

    async def test_spans_cleared_between_fixtures(
        self, traced_client: tuple[AsyncClient, InMemorySpanExporter]
    ) -> None:
        client, exp = traced_client
        await client.get("/healthz")
        assert len(exp.get_finished_spans()) >= 1
        exp.clear()
        assert len(exp.get_finished_spans()) == 0
