"""
Module 0 — Project Foundation
Tests for config, logging, and exceptions.
All tests are pure unit tests with no external dependencies.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import structlog.testing

from common.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    DoxException,
    EntitlementError,
    NotFoundError,
    QuotaExceededError,
    RateLimitError,
    ValidationError,
)
from common.logging import bind_service, bind_trace_id, clear_context, configure_logging, get_logger

# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestSettingsLoad:
    def test_settings_load_from_env_variables(self) -> None:
        """Settings instantiate correctly when all required env vars are present."""
        with patch.dict(
            os.environ,
            {
                "DOX_ENVIRONMENT": "staging",
                "DOX_DATABASE__URL": "postgresql+asyncpg://test:test@localhost/testdb",
            },
        ):
            from importlib import reload

            import common.config as cfg_module

            reload(cfg_module)
            s = cfg_module.Settings()
            assert s.environment == "staging"
            assert s.database.url == "postgresql+asyncpg://test:test@localhost/testdb"

    def test_env_variable_overrides_default(self) -> None:
        """An environment variable overrides the field default."""
        with patch.dict(
            os.environ,
            {
                "DOX_ENVIRONMENT": "prod",
                "DOX_DATABASE__URL": "postgresql+asyncpg://x:x@localhost/x",
            },
        ):
            from common.config import Settings

            s = Settings()
            assert s.environment == "prod"

    def test_missing_database_url_raises_on_instantiation(self) -> None:
        """Settings raises ValidationError if database.url is missing."""
        env = {k: v for k, v in os.environ.items() if not k.startswith("DOX_DATABASE")}
        with patch.dict(os.environ, env, clear=True):
            from pydantic import ValidationError as PydanticValidationError

            from common.config import Settings

            with pytest.raises(PydanticValidationError) as exc_info:
                Settings()
            errors = exc_info.value.errors()
            locations = [e["loc"] for e in errors]
            assert any("database" in str(loc) for loc in locations)

    def test_invalid_environment_value_raises(self) -> None:
        """Environment must be one of dev|test|staging|prod."""
        with patch.dict(
            os.environ,
            {
                "DOX_ENVIRONMENT": "production",
                "DOX_DATABASE__URL": "postgresql+asyncpg://x:x@localhost/x",
            },
        ):
            from pydantic import ValidationError as PydanticValidationError

            from common.config import Settings

            with pytest.raises(PydanticValidationError) as exc_info:
                Settings()
            assert "environment" in str(exc_info.value)

    def test_double_underscore_nesting_resolves_correctly(self) -> None:
        """DOX_DATABASE__POOL_SIZE sets database.pool_size."""
        with patch.dict(
            os.environ,
            {
                "DOX_DATABASE__URL": "postgresql+asyncpg://x:x@localhost/x",
                "DOX_DATABASE__POOL_SIZE": "25",
            },
        ):
            from common.config import Settings

            s = Settings()
            assert s.database.pool_size == 25

    def test_sentinel_run_mode_default_is_async(self) -> None:
        with patch.dict(
            os.environ,
            {"DOX_DATABASE__URL": "postgresql+asyncpg://x:x@localhost/x"},
        ):
            from common.config import Settings

            s = Settings()
            assert s.sentinel.run_mode == "async"

    def test_adapter_defaults_are_local(self) -> None:
        with patch.dict(
            os.environ,
            {"DOX_DATABASE__URL": "postgresql+asyncpg://x:x@localhost/x"},
        ):
            from common.config import Settings

            s = Settings()
            assert s.adapters.event_bus == "redis_streams"
            assert s.adapters.object_store == "local_fs"
            assert s.adapters.secret_store == "env"

    def test_env_example_documents_all_settings_keys(self) -> None:
        """Every environment variable key known to the Settings model must appear
        in .env.example so developers know it exists."""
        env_example_path = Path(__file__).parent.parent.parent / ".env.example"
        assert env_example_path.exists(), ".env.example file not found"
        content = env_example_path.read_text()

        required_keys = [
            "DOX_ENVIRONMENT",
            "DOX_SECRET_KEY",
            "DOX_DATABASE__URL",
            "DOX_DATABASE__POOL_SIZE",
            "DOX_REDIS__URL",
            "DOX_ADAPTERS__EVENT_BUS",
            "DOX_ADAPTERS__OBJECT_STORE",
            "DOX_ADAPTERS__SECRET_STORE",
            "DOX_ADAPTERS__METRICS",
            "DOX_SENTINEL__ENABLED",
            "DOX_SENTINEL__RUN_MODE",
            "DOX_RETENTION__HOT_DAYS",
            "DOX_RETENTION__WARM_DAYS",
            "DOX_RETENTION__COLD_DAYS",
            "DOX_RETENTION__DELETE_AFTER_DAYS",
            "DOX_PLATFORM__SIGNING_KEY_PRIVATE",
            "DOX_PLATFORM__SIGNING_KEY_PUBLIC",
        ]
        for key in required_keys:
            assert key in content, f"{key} missing from .env.example"


# ---------------------------------------------------------------------------
# Logging tests
# ---------------------------------------------------------------------------


class TestLogging:
    def setup_method(self) -> None:
        # Ensure clean context before every logging test.
        clear_context()
        configure_logging(environment="dev", service="test")

    def teardown_method(self) -> None:
        clear_context()

    def test_get_logger_returns_bound_logger(self) -> None:
        logger = get_logger("test_service")
        assert logger is not None
        # Must not raise — verifies the processor chain is valid.
        with structlog.testing.capture_logs():
            logger.info("test message")

    def test_structured_log_includes_service_name(self) -> None:
        # capture_logs() strips the processor chain so we verify binding directly
        # via get_contextvars(); actual rendering is covered by integration tests.
        bind_service("ingestion")
        ctx = structlog.contextvars.get_contextvars()
        assert ctx["service"] == "ingestion"
        # Also verify the log call succeeds with correct kwargs.
        with structlog.testing.capture_logs() as cap:
            get_logger("ingestion").info("event_received", count=5)
        assert cap[0]["event"] == "event_received"
        assert cap[0]["count"] == 5

    def test_structured_log_includes_log_level(self) -> None:
        with structlog.testing.capture_logs() as cap:
            get_logger("test").warning("something_odd")
        assert cap[0]["log_level"] == "warning"

    def test_bind_trace_id_stored_in_contextvars(self) -> None:
        bind_trace_id("trace-abc-123")
        ctx = structlog.contextvars.get_contextvars()
        assert ctx["trace_id"] == "trace-abc-123"

    def test_empty_trace_id_not_added_to_log(self) -> None:
        # Binding empty string should not add trace_id key.
        bind_trace_id("")
        with structlog.testing.capture_logs() as cap:
            get_logger("test").info("no_trace")
        assert "trace_id" not in cap[0]

    def test_trace_id_isolated_across_tasks(self) -> None:
        """asyncio.gather wraps each coroutine in a Task which gets its own copy
        of the current context, so bindings in one task must not bleed into another."""

        results: dict[str, str] = {}

        async def task_a() -> None:
            structlog.contextvars.clear_contextvars()
            bind_trace_id("AAA")
            await asyncio.sleep(0)
            results["a"] = structlog.contextvars.get_contextvars().get("trace_id", "")

        async def task_b() -> None:
            structlog.contextvars.clear_contextvars()
            bind_trace_id("BBB")
            await asyncio.sleep(0)
            results["b"] = structlog.contextvars.get_contextvars().get("trace_id", "")

        async def run() -> None:
            await asyncio.gather(task_a(), task_b())

        asyncio.run(run())
        assert results["a"] == "AAA"
        assert results["b"] == "BBB"

    def test_logging_does_not_raise_on_complex_payload(self) -> None:
        with structlog.testing.capture_logs():
            get_logger("test").info(
                "complex", nested={"key": [1, 2, 3]}, none_val=None, flag=True
            )


# ---------------------------------------------------------------------------
# Exception tests
# ---------------------------------------------------------------------------


class TestExceptions:
    def test_dox_exception_carries_code_and_detail(self) -> None:
        e = DoxException(detail="something went wrong", code="test_error")
        assert e.detail == "something went wrong"
        assert e.code == "test_error"
        assert str(e) == "something went wrong"

    def test_configuration_error_has_correct_code(self) -> None:
        e = ConfigurationError("bad adapter config")
        assert e.code == "configuration_error"
        assert e.detail == "bad adapter config"

    def test_validation_error_has_correct_code(self) -> None:
        e = ValidationError("invalid payload")
        assert e.code == "validation_error"

    def test_not_found_error_has_correct_code(self) -> None:
        e = NotFoundError("trace not found")
        assert e.code == "not_found"

    def test_authentication_error_has_correct_code(self) -> None:
        e = AuthenticationError("invalid api key")
        assert e.code == "authentication_error"

    def test_authorization_error_has_correct_code(self) -> None:
        e = AuthorizationError("insufficient role")
        assert e.code == "authorization_error"

    def test_rate_limit_error_carries_retry_after(self) -> None:
        e = RateLimitError("too many requests", retry_after=5)
        assert e.code == "rate_limit_exceeded"
        assert e.retry_after == 5

    def test_rate_limit_error_default_retry_after(self) -> None:
        e = RateLimitError("too many requests")
        assert e.retry_after == 1

    def test_quota_exceeded_error_has_correct_code(self) -> None:
        e = QuotaExceededError("monthly event quota reached")
        assert e.code == "quota_exceeded"

    def test_entitlement_error_carries_feature_name(self) -> None:
        e = EntitlementError("feature not available", feature="drift_engine")
        assert e.code == "feature_not_available"
        assert e.feature == "drift_engine"

    def test_all_exception_classes_inherit_from_dox_exception(self) -> None:
        exception_classes = [
            ConfigurationError,
            ValidationError,
            NotFoundError,
            AuthenticationError,
            AuthorizationError,
            RateLimitError,
            QuotaExceededError,
            EntitlementError,
        ]
        for cls in exception_classes:
            assert issubclass(cls, DoxException), f"{cls.__name__} must inherit DoxException"

    def test_exceptions_are_catchable_as_dox_exception(self) -> None:
        with pytest.raises(DoxException):
            raise AuthorizationError("not allowed")


# ---------------------------------------------------------------------------
# Package import tests
# ---------------------------------------------------------------------------


class TestPackageImports:
    def test_common_package_importable(self) -> None:
        import common  # noqa: F401

    def test_common_config_importable(self) -> None:
        from common.config import Settings  # noqa: F401

    def test_common_logging_importable(self) -> None:
        from common.logging import bind_trace_id, get_logger  # noqa: F401

    def test_common_exceptions_importable(self) -> None:
        from common.exceptions import AuthorizationError, DoxException  # noqa: F401

    def test_common_models_importable(self) -> None:
        from common.models import Base, TimestampMixin  # noqa: F401

    def test_sqlalchemy_base_has_metadata(self) -> None:
        from common.models.base import Base

        assert Base.metadata is not None

    def test_timestamp_mixin_has_expected_columns(self) -> None:
        import inspect

        from common.models.base import TimestampMixin

        annotations = {}
        for cls in inspect.getmro(TimestampMixin):
            annotations.update(getattr(cls, "__annotations__", {}))

        assert "created_at" in annotations
        assert "updated_at" in annotations
