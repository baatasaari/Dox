"""OpenTelemetry tracing bootstrap for Dox."""
from __future__ import annotations

import opentelemetry.trace as _trace_module
from opentelemetry import propagate, trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

SERVICE_NAME_KEY = "service.name"


def _force_set_tracer_provider(provider: TracerProvider) -> None:
    """Bypass the OTel 'set once' guard so tests can replace the global provider."""
    _trace_module._TRACER_PROVIDER_SET_ONCE._done = False
    _trace_module._TRACER_PROVIDER = None
    trace.set_tracer_provider(provider)


def configure_tracing(
    service_name: str = "dox",
    exporter: SpanExporter | None = None,
) -> TracerProvider:
    """Set up the global OTel tracer provider and W3C TraceContext propagator.

    Pass an InMemorySpanExporter for tests, an OTLP exporter for production.
    Without an exporter, spans are created but silently discarded.
    Returns the TracerProvider so the caller can call provider.shutdown().
    """
    resource = Resource({SERVICE_NAME_KEY: service_name})
    provider = TracerProvider(resource=resource)
    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    _force_set_tracer_provider(provider)
    propagate.set_global_textmap(TraceContextTextMapPropagator())
    return provider


def get_tracer(name: str) -> trace.Tracer:
    """Return a named tracer from the global provider."""
    return trace.get_tracer(name)
