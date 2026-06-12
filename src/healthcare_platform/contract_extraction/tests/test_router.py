"""Router/API tests for FastAPI endpoints (tests 12-16)."""
import uuid
from datetime import date, datetime
from unittest.mock import MagicMock

import anyio
import httpx
from fastapi import FastAPI

from healthcare_platform.contract_extraction.models import (
    RuleArchetype,
    RuleCategory,
    RuleStatus,
)

_RULE_ID = str(uuid.uuid4())
_TENANT = "tenant1"

_RULE_PAYLOAD = {
    "payer_id": "payer-001",
    "category": "PRICING",
    "archetype": "PRICING",
    "rule_definition": {"code": "A001"},
    "version": "1.0.0",
    "effective_date": "2025-01-01",
}


def _build_router_app(mock_svc):
    """Build a FastAPI app with mocked ContractService dependency."""
    from healthcare_platform.contract_extraction.router import router
    from healthcare_platform.contract_extraction.dependencies import get_contract_service

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_contract_service] = lambda: mock_svc
    return app


def _make_stub():
    stub = MagicMock()
    stub.id = uuid.UUID(_RULE_ID)
    stub.tenant_id = _TENANT
    stub.payer_id = "payer-001"
    stub.category = RuleCategory.PRICING
    stub.archetype = RuleArchetype.PRICING
    stub.rule_definition = {"code": "A001"}
    stub.version = "1.0.0"
    stub.effective_date = date(2025, 1, 1)
    stub.expiry_date = None
    stub.status = RuleStatus.DRAFT
    stub.created_at = datetime(2025, 1, 1)
    stub.updated_at = datetime(2025, 1, 1)
    return stub


def _make_mock_svc(stub):
    mock_svc = MagicMock()
    mock_svc.create_rule.return_value = stub
    mock_svc.list_rules.return_value = [stub]
    mock_svc.get_rule.return_value = stub
    mock_svc.delete_rule.return_value = None
    active_stub = MagicMock()
    active_stub.id = stub.id
    active_stub.tenant_id = _TENANT
    active_stub.status = RuleStatus.ACTIVE
    active_stub.version = "1.0.0"
    mock_svc.deploy_rule.return_value = {
        "rule_id": str(stub.id),
        "tenant_id": _TENANT,
        "status": RuleStatus.ACTIVE.value,
        "dmn_path": "test.dmn",
        "version": "1.0.0",
        "deployed_at": datetime(2025, 1, 1).isoformat(),
    }
    return mock_svc


# ---------------------------------------------------------------------------
# Tests 12-16: FastAPI router tests
# ---------------------------------------------------------------------------


def test_post_rule_returns_201():
    """POST /contracts/{tenant_id}/rules/ returns 201 with rule data."""
    stub = _make_stub()
    app = _build_router_app(_make_mock_svc(stub))

    async def _go():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as c:
            return await c.post(f"/contracts/{_TENANT}/rules/", json=_RULE_PAYLOAD)

    r = anyio.run(_go)
    assert r.status_code == 201
    assert r.json()["payer_id"] == "payer-001"


def test_get_rules_returns_200_list():
    """GET /contracts/{tenant_id}/rules/ returns 200 with a list."""
    stub = _make_stub()
    app = _build_router_app(_make_mock_svc(stub))

    async def _go():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as c:
            return await c.get(f"/contracts/{_TENANT}/rules/")

    r = anyio.run(_go)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) >= 1


def test_get_missing_rule_returns_404():
    """GET with unknown rule_id returns 404."""
    mock_svc = _make_mock_svc(_make_stub())
    mock_svc.get_rule.side_effect = KeyError("not found")
    app = _build_router_app(mock_svc)

    async def _go():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as c:
            return await c.get(f"/contracts/{_TENANT}/rules/{_RULE_ID}")

    r = anyio.run(_go)
    assert r.status_code == 404


def test_delete_rule_returns_204():
    """DELETE /contracts/{tenant_id}/rules/{rule_id} returns 204."""
    app = _build_router_app(_make_mock_svc(_make_stub()))

    async def _go():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as c:
            return await c.delete(f"/contracts/{_TENANT}/rules/{_RULE_ID}")

    r = anyio.run(_go)
    assert r.status_code == 204


def test_deploy_endpoint_returns_active():
    """POST /contracts/{tenant_id}/rules/{rule_id}/deploy returns ACTIVE status."""
    app = _build_router_app(_make_mock_svc(_make_stub()))

    async def _go():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as c:
            return await c.post(f"/contracts/{_TENANT}/rules/{_RULE_ID}/deploy")

    r = anyio.run(_go)
    assert r.status_code == 200
    assert r.json()["status"] == "ACTIVE"
