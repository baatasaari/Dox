from __future__ import annotations

import logging
import sys

import structlog
import structlog.contextvars


def configure_logging(environment: str = "dev", service: str = "dox") -> None:
    # Seed default service into structlog contextvars so every log line carries it.
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(service=service)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if environment == "dev":
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer(colors=False)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]


def bind_trace_id(trace_id: str) -> None:
    """Bind a trace_id into structlog's contextvars for the current coroutine."""
    if trace_id:
        structlog.contextvars.bind_contextvars(trace_id=trace_id)
    else:
        structlog.contextvars.unbind_contextvars("trace_id")


def bind_service(service: str) -> None:
    structlog.contextvars.bind_contextvars(service=service)


def clear_context() -> None:
    """Clear all structlog contextvars. Call between requests and in test teardown."""
    structlog.contextvars.clear_contextvars()
