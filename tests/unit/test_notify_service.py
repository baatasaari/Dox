"""Module 8 — Notify: service layer tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from common.exceptions import NotFoundError
from common.models.webhook import WebhookEndpoint
from common.schemas.webhook import DispatchRequest, WebhookCreate
from services.notify.service import NotificationService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_webhook(
    tenant_id: str = "tenant-acme",
    event_types: list[str] | None = None,
    is_active: bool = True,
    failure_count: int = 0,
) -> WebhookEndpoint:
    return WebhookEndpoint(
        id=uuid4(),
        tenant_id=tenant_id,
        url="https://example.com/hook",
        secret="supersecretkey1234",
        event_types=event_types or ["*"],
        is_active=is_active,
        failure_count=failure_count,
    )


def _scalar_result(obj: object) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = obj
    return r


def _scalars_result(items: list[object]) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _make_session(*execute_results: MagicMock) -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock(side_effect=list(execute_results))
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


def _mock_http(status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRegisterWebhook:
    async def test_adds_and_commits(self) -> None:
        session = _make_session()
        service = NotificationService(session)  # type: ignore[arg-type]
        create = WebhookCreate(
            tenant_id="t",
            url="https://example.com/hook",
            secret="a" * 16,
        )
        await service.register_webhook(create)
        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    async def test_returns_webhook_endpoint(self) -> None:
        session = _make_session()
        service = NotificationService(session)  # type: ignore[arg-type]
        create = WebhookCreate(
            tenant_id="t",
            url="https://example.com/hook",
            secret="a" * 16,
        )
        result = await service.register_webhook(create)
        assert isinstance(result, WebhookEndpoint)

    async def test_fields_match_create(self) -> None:
        session = _make_session()
        service = NotificationService(session)  # type: ignore[arg-type]
        create = WebhookCreate(
            tenant_id="tenant-acme",
            url="https://hooks.example.com/dox",
            secret="supersecretkey1234",
            event_types=["tool_misuse", "drift"],
            description="My webhook",
        )
        w = await service.register_webhook(create)
        assert w.tenant_id == "tenant-acme"
        assert w.url == "https://hooks.example.com/dox"
        assert w.event_types == ["tool_misuse", "drift"]
        assert w.description == "My webhook"


class TestGetWebhook:
    async def test_returns_webhook_when_found(self) -> None:
        webhook = _make_webhook()
        session = _make_session(_scalar_result(webhook))
        service = NotificationService(session)  # type: ignore[arg-type]
        result = await service.get_webhook(webhook.id)
        assert result is webhook

    async def test_raises_not_found_when_missing(self) -> None:
        session = _make_session(_scalar_result(None))
        service = NotificationService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await service.get_webhook(uuid4())


class TestListWebhooks:
    async def test_returns_list(self) -> None:
        webhooks = [_make_webhook(), _make_webhook()]
        session = _make_session(_scalars_result(webhooks))
        service = NotificationService(session)  # type: ignore[arg-type]
        result = await service.list_webhooks("tenant-acme")
        assert len(result) == 2

    async def test_empty_returns_empty_list(self) -> None:
        session = _make_session(_scalars_result([]))
        service = NotificationService(session)  # type: ignore[arg-type]
        result = await service.list_webhooks("unknown")
        assert result == []


class TestDeactivateWebhook:
    async def test_sets_is_active_false(self) -> None:
        webhook = _make_webhook(is_active=True)
        session = _make_session(_scalar_result(webhook))
        service = NotificationService(session)  # type: ignore[arg-type]
        result = await service.deactivate_webhook(webhook.id)
        assert result.is_active is False

    async def test_commits_after_deactivation(self) -> None:
        webhook = _make_webhook()
        session = _make_session(_scalar_result(webhook))
        service = NotificationService(session)  # type: ignore[arg-type]
        await service.deactivate_webhook(webhook.id)
        session.commit.assert_awaited_once()

    async def test_raises_not_found_when_missing(self) -> None:
        session = _make_session(_scalar_result(None))
        service = NotificationService(session)  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await service.deactivate_webhook(uuid4())


class TestSignPayload:
    def test_returns_sha256_prefixed_string(self) -> None:
        sig = NotificationService.sign_payload(b"hello", "secret-key-1234567")
        assert sig.startswith("sha256=")

    def test_same_body_same_signature(self) -> None:
        body = b'{"event": "test"}'
        sig1 = NotificationService.sign_payload(body, "key-1234567890ab")
        sig2 = NotificationService.sign_payload(body, "key-1234567890ab")
        assert sig1 == sig2

    def test_different_body_different_signature(self) -> None:
        secret = "key-1234567890ab"
        sig1 = NotificationService.sign_payload(b"body-one", secret)
        sig2 = NotificationService.sign_payload(b"body-two", secret)
        assert sig1 != sig2

    def test_different_secret_different_signature(self) -> None:
        body = b"same body"
        sig1 = NotificationService.sign_payload(body, "secret-key-aaaa")
        sig2 = NotificationService.sign_payload(body, "secret-key-bbbb")
        assert sig1 != sig2

    def test_signature_is_64_hex_chars_after_prefix(self) -> None:
        sig = NotificationService.sign_payload(b"data", "secret-key-1234567")
        hex_part = sig.removeprefix("sha256=")
        assert len(hex_part) == 64
        assert all(c in "0123456789abcdef" for c in hex_part)


class TestDispatch:
    async def test_no_webhooks_returns_empty_result(self) -> None:
        session = _make_session(_scalars_result([]))
        service = NotificationService(session)  # type: ignore[arg-type]
        result = await service.dispatch(
            DispatchRequest(tenant_id="t", sentinel_type="drift", payload={})
        )
        assert result.successful == 0
        assert result.failed == 0
        assert result.deliveries == []

    async def test_wildcard_webhook_receives_any_event(self) -> None:
        webhook = _make_webhook(event_types=["*"])
        session = _make_session(_scalars_result([webhook]))
        http = _mock_http(200)
        service = NotificationService(session, http_client=http)  # type: ignore[arg-type]
        result = await service.dispatch(
            DispatchRequest(tenant_id="t", sentinel_type="tool_misuse", payload={})
        )
        assert len(result.deliveries) == 1
        assert result.successful == 1

    async def test_filtered_webhook_receives_matching_type_only(self) -> None:
        webhook = _make_webhook(event_types=["drift"])
        session = _make_session(_scalars_result([webhook]))
        http = _mock_http(200)
        service = NotificationService(session, http_client=http)  # type: ignore[arg-type]
        result = await service.dispatch(
            DispatchRequest(tenant_id="t", sentinel_type="tool_misuse", payload={})
        )
        assert len(result.deliveries) == 0

    async def test_filtered_webhook_receives_matching_event(self) -> None:
        webhook = _make_webhook(event_types=["drift"])
        session = _make_session(_scalars_result([webhook]))
        http = _mock_http(200)
        service = NotificationService(session, http_client=http)  # type: ignore[arg-type]
        result = await service.dispatch(
            DispatchRequest(tenant_id="t", sentinel_type="drift", payload={})
        )
        assert result.successful == 1

    async def test_http_500_counts_as_failure(self) -> None:
        webhook = _make_webhook()
        session = _make_session(_scalars_result([webhook]))
        http = _mock_http(500)
        service = NotificationService(session, http_client=http)  # type: ignore[arg-type]
        result = await service.dispatch(
            DispatchRequest(tenant_id="t", sentinel_type="drift", payload={})
        )
        assert result.failed == 1
        assert result.successful == 0

    async def test_successful_delivery_resets_failure_count(self) -> None:
        webhook = _make_webhook(failure_count=3)
        session = _make_session(_scalars_result([webhook]))
        http = _mock_http(200)
        service = NotificationService(session, http_client=http)  # type: ignore[arg-type]
        await service.dispatch(
            DispatchRequest(tenant_id="t", sentinel_type="drift", payload={})
        )
        assert webhook.failure_count == 0

    async def test_failed_delivery_increments_failure_count(self) -> None:
        webhook = _make_webhook(failure_count=1)
        session = _make_session(_scalars_result([webhook]))
        http = _mock_http(503)
        service = NotificationService(session, http_client=http)  # type: ignore[arg-type]
        await service.dispatch(
            DispatchRequest(tenant_id="t", sentinel_type="drift", payload={})
        )
        assert webhook.failure_count == 2

    async def test_delivery_result_contains_webhook_id(self) -> None:
        webhook = _make_webhook()
        session = _make_session(_scalars_result([webhook]))
        http = _mock_http(200)
        service = NotificationService(session, http_client=http)  # type: ignore[arg-type]
        result = await service.dispatch(
            DispatchRequest(tenant_id="t", sentinel_type="drift", payload={"k": "v"})
        )
        assert result.deliveries[0].webhook_id == webhook.id

    async def test_delivery_includes_signature_header(self) -> None:
        webhook = _make_webhook()
        session = _make_session(_scalars_result([webhook]))
        http = _mock_http(200)
        service = NotificationService(session, http_client=http)  # type: ignore[arg-type]
        await service.dispatch(
            DispatchRequest(tenant_id="t", sentinel_type="drift", payload={})
        )
        _, kwargs = http.post.call_args
        assert "X-Dox-Signature-256" in kwargs["headers"]
        assert kwargs["headers"]["X-Dox-Signature-256"].startswith("sha256=")

    async def test_no_http_client_records_failure(self) -> None:
        webhook = _make_webhook()
        session = _make_session(_scalars_result([webhook]))
        service = NotificationService(session)  # type: ignore[arg-type]
        result = await service.dispatch(
            DispatchRequest(tenant_id="t", sentinel_type="drift", payload={})
        )
        assert result.deliveries[0].success is False

    async def test_network_error_counts_as_failure(self) -> None:
        webhook = _make_webhook()
        session = _make_session(_scalars_result([webhook]))
        http = MagicMock()
        http.post = AsyncMock(side_effect=ConnectionError("refused"))
        service = NotificationService(session, http_client=http)  # type: ignore[arg-type]
        result = await service.dispatch(
            DispatchRequest(tenant_id="t", sentinel_type="drift", payload={})
        )
        assert result.failed == 1
        assert "refused" in (result.deliveries[0].error or "")
