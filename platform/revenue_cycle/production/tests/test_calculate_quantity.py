"""Tests for CalculateQuantityWorker."""
from __future__ import annotations

import pytest

from platform.shared.domain.enums import TenantCode
from platform.shared.domain.exceptions import CodingException
from platform.shared.multi_tenant.context import TenantContext, set_current_tenant, clear_tenant

from revenue_cycle.production.workers.calculate_quantity_worker import CalculateQuantityWorker


@pytest.fixture
def tenant_ctx():
    ctx = TenantContext.from_tenant_code(TenantCode.AUSTA)
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def worker():
    return CalculateQuantityWorker()


class TestCalculateQuantityWorker:
    @pytest.mark.asyncio
    async def test_simple_quantity(self, worker, tenant_ctx):
        result = await worker.execute({
            "enriched_procedures": [{"code": "40101010", "quantity": 1}],
        })
        assert result["quantified_procedures"][0]["quantity"] == 1
        assert result["total_items"] == 1

    @pytest.mark.asyncio
    async def test_duration_based_anesthesia(self, worker, tenant_ctx):
        result = await worker.execute({
            "enriched_procedures": [{"code": "20101012", "quantity": 1}],
            "encounter_start": "2024-01-01T08:00:00",
            "encounter_end": "2024-01-01T10:00:00",
        })
        # 120 min / 15 min = 8 blocks
        assert result["quantified_procedures"][0]["quantity"] == 8
        assert result["quantified_procedures"][0]["quantity_method"] == "duration"

    @pytest.mark.asyncio
    async def test_quantity_capped(self, worker, tenant_ctx):
        result = await worker.execute({
            "enriched_procedures": [{"code": "40101010", "quantity": 10}],
        })
        # Max 4 per day for 40101010
        assert result["quantified_procedures"][0]["quantity"] == 4
