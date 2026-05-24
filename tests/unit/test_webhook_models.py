"""Module 8 — Notify: webhook model tests."""
from __future__ import annotations

from uuid import uuid4

from common.models.webhook import WebhookEndpoint


def _make_webhook(**kw: object) -> WebhookEndpoint:
    defaults = dict(
        id=uuid4(),
        tenant_id="tenant-acme",
        url="https://example.com/hook",
        secret="supersecretkey1234",
    )
    defaults.update(kw)
    return WebhookEndpoint(**defaults)


class TestWebhookDefaults:
    def test_is_active_defaults_to_true(self) -> None:
        w = _make_webhook()
        assert w.is_active is True

    def test_event_types_defaults_to_wildcard(self) -> None:
        w = _make_webhook()
        assert w.event_types == ["*"]

    def test_description_defaults_to_empty(self) -> None:
        w = _make_webhook()
        assert w.description == ""

    def test_failure_count_defaults_to_zero(self) -> None:
        w = _make_webhook()
        assert w.failure_count == 0

    def test_last_delivered_at_not_set(self) -> None:
        w = _make_webhook()
        assert w.last_delivered_at is None

    def test_explicit_event_types_preserved(self) -> None:
        w = _make_webhook(event_types=["tool_misuse", "drift"])
        assert w.event_types == ["tool_misuse", "drift"]

    def test_explicit_is_active_false(self) -> None:
        w = _make_webhook(is_active=False)
        assert w.is_active is False


class TestWebhookFields:
    def test_url_stored(self) -> None:
        w = _make_webhook(url="https://hooks.example.com/alerts")
        assert w.url == "https://hooks.example.com/alerts"

    def test_tenant_id_stored(self) -> None:
        w = _make_webhook(tenant_id="tenant-xyz")
        assert w.tenant_id == "tenant-xyz"

    def test_secret_stored(self) -> None:
        w = _make_webhook(secret="my-secret-key-16chars")
        assert w.secret == "my-secret-key-16chars"
