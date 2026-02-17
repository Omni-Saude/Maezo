"""Tenant isolation smoke tests (ADR-002)."""
import pytest

VALID_TENANTS = ["austa-hospital", "amh-sp-morumbi", "amh-rj-barra", "amh-mg-bh"]


def test_tenant_markers_in_deployments(http_client, camunda_base_url):
    """All deployments should have a tenant ID."""
    resp = http_client.get(f"{camunda_base_url}/deployment")
    assert resp.status_code == 200
    deployments = resp.json()
    for dep in deployments:
        tenant = dep.get("tenantId")
        assert tenant in VALID_TENANTS, (
            f"Deployment {dep.get('id')} has invalid tenantId: {tenant}"
        )


def test_cross_tenant_isolation(http_client, camunda_base_url):
    """Tenant A process instances should not be visible to tenant B."""
    for tenant in VALID_TENANTS[:2]:
        resp = http_client.get(
            f"{camunda_base_url}/process-instance",
            params={"tenantIdIn": tenant, "maxResults": 5},
        )
        assert resp.status_code == 200
        instances = resp.json()
        for inst in instances:
            assert inst.get("tenantId") == tenant, (
                f"Instance {inst.get('id')} leaked: expected tenant {tenant}, "
                f"got {inst.get('tenantId')}"
            )
