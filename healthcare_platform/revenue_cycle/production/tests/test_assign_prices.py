"""Tests for AssignPricesWorker."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import ContractRuleViolation
from healthcare_platform.shared.multi_tenant.context import TenantContext, set_current_tenant, clear_tenant

from revenue_cycle.production.workers.assign_prices_worker import AssignPricesWorker


@pytest.fixture
def tenant_ctx():
    ctx = TenantContext.from_tenant_code(TenantCode.HOSPITAL_A)
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def fhir_client():
    return AsyncMock()


@pytest.fixture
def worker(fhir_client):
    return AssignPricesWorker(fhir_client=fhir_client)


class TestAssignPricesWorker:
    @pytest.mark.asyncio
    async def test_prices_assigned(self, worker, fhir_client, tenant_ctx):
        fhir_client.search.return_value = [
            {
                "code": {"coding": [{"code": "40101010"}]},
                "propertyGroup": [{"priceComponent": [{"type": "base", "amount": {"value": 150.00}}]}],
            }
        ]

        result = await worker.execute({
            "quantified_procedures": [{"code": "40101010", "quantity": 2}],
        })

        assert result["currency"] == "BRL"
        assert result["priced_procedures"][0]["price_source"] != "missing"

    @pytest.mark.asyncio
    async def test_missing_price_raises(self, worker, fhir_client, tenant_ctx):
        fhir_client.search.return_value = []

        with pytest.raises(ContractRuleViolation):
            await worker.execute({
                "quantified_procedures": [{"code": "99999999", "quantity": 1}],
            })
