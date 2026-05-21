"""Module 10 — Policy Engine: HTTP route tests."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from common.exceptions import NotFoundError
from common.models.policy import Policy
from common.schemas.enums import InterventionAction, SentinelType, Severity
from common.schemas.policy import MatchedPolicy, PolicyEvaluationResult
from services.policy.deps import get_policy_evaluator
from services.policy.router import router
from services.policy.service import PolicyEvaluatorService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_policy(
    *,
    name: str = "block-tool-misuse",
    sentinel_type: str = SentinelType.tool_misuse,
    severity: str = Severity.high,
    action: str = InterventionAction.block_tool_call,
    is_active: bool = True,
) -> Policy:
    return Policy(
        id=uuid4(),
        tenant_id="tenant-acme",
        name=name,
        description="test policy",
        sentinel_type=sentinel_type,
        severity=severity,
        action=action,
        is_active=is_active,
        config={},
        created_at=datetime.now(UTC),
    )


def _make_mock_service(
    policy: Policy | None = None,
    evaluation: PolicyEvaluationResult | None = None,
) -> MagicMock:
    svc = MagicMock(spec=PolicyEvaluatorService)
    p = policy or _make_policy()
    svc.get_policy = AsyncMock(return_value=p)
    svc.update_policy = AsyncMock(return_value=p)
    if evaluation is None:
        evaluation = PolicyEvaluationResult(
            tenant_id="tenant-acme",
            sentinel_type=SentinelType.tool_misuse,
            severity=Severity.high,
            matched_count=1,
            matched_policies=[MatchedPolicy(id=p.id, name=p.name, action=p.action)],
            action=InterventionAction.block_tool_call,
            is_blocked=True,
        )
    svc.evaluate = AsyncMock(return_value=evaluation)
    return svc


@pytest.fixture()
async def client() -> AsyncGenerator[tuple[AsyncClient, MagicMock], None]:
    app = FastAPI()
    app.include_router(router)
    mock_svc = _make_mock_service()

    async def override() -> PolicyEvaluatorService:
        return mock_svc  # type: ignore[return-value]

    app.dependency_overrides[get_policy_evaluator] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, mock_svc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# GET /v1/policies/{policy_id}
# ---------------------------------------------------------------------------


class TestGetPolicyEndpoint:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.get(f"/v1/policies/{uuid4()}")
        assert r.status_code == 200

    async def test_response_has_policy_fields(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.get(f"/v1/policies/{uuid4()}")
        body = r.json()
        assert "id" in body
        assert "name" in body
        assert "sentinel_type" in body
        assert "action" in body
        assert "is_active" in body

    async def test_returns_404_when_not_found(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        mock_svc.get_policy = AsyncMock(side_effect=NotFoundError("not found"))
        r = await ac.get(f"/v1/policies/{uuid4()}")
        assert r.status_code == 404

    async def test_calls_service_with_correct_id(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        policy_id = uuid4()
        await ac.get(f"/v1/policies/{policy_id}")
        mock_svc.get_policy.assert_awaited_once_with(policy_id)


# ---------------------------------------------------------------------------
# PUT /v1/policies/{policy_id}
# ---------------------------------------------------------------------------


class TestUpdatePolicyEndpoint:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.put(f"/v1/policies/{uuid4()}", json={"name": "updated"})
        assert r.status_code == 200

    async def test_response_is_policy_response(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.put(f"/v1/policies/{uuid4()}", json={"name": "updated"})
        body = r.json()
        assert "name" in body
        assert "action" in body

    async def test_returns_404_when_not_found(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        mock_svc.update_policy = AsyncMock(side_effect=NotFoundError("not found"))
        r = await ac.put(f"/v1/policies/{uuid4()}", json={"name": "x"})
        assert r.status_code == 404

    async def test_empty_body_is_valid(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.put(f"/v1/policies/{uuid4()}", json={})
        assert r.status_code == 200

    async def test_calls_service_with_update(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        policy_id = uuid4()
        await ac.put(f"/v1/policies/{policy_id}", json={"is_active": False})
        mock_svc.update_policy.assert_awaited_once()
        call_args = mock_svc.update_policy.call_args
        assert call_args[0][0] == policy_id
        assert call_args[0][1].is_active is False


# ---------------------------------------------------------------------------
# POST /v1/policies/evaluate
# ---------------------------------------------------------------------------


class TestEvaluatePoliciesEndpoint:
    async def test_returns_200(self, client: tuple[AsyncClient, MagicMock]) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/policies/evaluate",
            json={
                "tenant_id": "tenant-acme",
                "sentinel_type": "tool_misuse",
                "severity": "high",
            },
        )
        assert r.status_code == 200

    async def test_response_has_evaluation_fields(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/policies/evaluate",
            json={
                "tenant_id": "tenant-acme",
                "sentinel_type": "tool_misuse",
                "severity": "high",
            },
        )
        body = r.json()
        assert "action" in body
        assert "is_blocked" in body
        assert "matched_count" in body
        assert "matched_policies" in body

    async def test_is_blocked_true_in_response(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/policies/evaluate",
            json={
                "tenant_id": "tenant-acme",
                "sentinel_type": "tool_misuse",
                "severity": "high",
            },
        )
        assert r.json()["is_blocked"] is True

    async def test_invalid_sentinel_type_returns_422(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/policies/evaluate",
            json={
                "tenant_id": "t",
                "sentinel_type": "not_a_type",
                "severity": "high",
            },
        )
        assert r.status_code == 422

    async def test_invalid_severity_returns_422(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/policies/evaluate",
            json={
                "tenant_id": "t",
                "sentinel_type": "tool_misuse",
                "severity": "extreme",
            },
        )
        assert r.status_code == 422

    async def test_missing_tenant_id_returns_422(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, _ = client
        r = await ac.post(
            "/v1/policies/evaluate",
            json={"sentinel_type": "tool_misuse", "severity": "high"},
        )
        assert r.status_code == 422

    async def test_calls_service_with_correct_request(
        self, client: tuple[AsyncClient, MagicMock]
    ) -> None:
        ac, mock_svc = client
        await ac.post(
            "/v1/policies/evaluate",
            json={
                "tenant_id": "my-tenant",
                "sentinel_type": "drift",
                "severity": "medium",
            },
        )
        mock_svc.evaluate.assert_awaited_once()
        req = mock_svc.evaluate.call_args[0][0]
        assert req.tenant_id == "my-tenant"
        assert req.sentinel_type == SentinelType.drift
        assert req.severity == Severity.medium
