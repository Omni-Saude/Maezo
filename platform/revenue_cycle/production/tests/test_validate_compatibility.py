"""Tests for ValidateCompatibilityWorker."""
from __future__ import annotations

import pytest

from platform.shared.domain.enums import TenantCode
from platform.shared.domain.exceptions import IncompatibleCodes
from platform.shared.multi_tenant.context import TenantContext, set_current_tenant, clear_tenant

from revenue_cycle.production.workers.validate_compatibility_worker import ValidateCompatibilityWorker


@pytest.fixture
def tenant_ctx():
    ctx = TenantContext.from_tenant_code(TenantCode.AUSTA)
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def worker():
    return ValidateCompatibilityWorker()


class TestValidateCompatibilityWorker:
    @pytest.mark.asyncio
    async def test_compatible_procedures(self, worker, tenant_ctx):
        result = await worker.execute({
            "priced_procedures": [
                {"code": "40101010"},
                {"code": "31001010"},
            ],
        })
        assert result["all_compatible"] is True

    @pytest.mark.asyncio
    async def test_incompatible_pair_raises(self, worker, tenant_ctx):
        with pytest.raises(IncompatibleCodes):
            await worker.execute({
                "priced_procedures": [
                    {"code": "40101010"},
                    {"code": "40101028"},
                ],
            })

    @pytest.mark.asyncio
    async def test_frequency_limit_exceeded(self, worker, tenant_ctx):
        with pytest.raises(IncompatibleCodes):
            await worker.execute({
                "priced_procedures": [
                    {"code": "40101010"},
                    {"code": "40101010"},
                    {"code": "40101010"},
                    {"code": "40101010"},
                    {"code": "40101010"},  # 5 > max 4
                ],
            })

    @pytest.mark.asyncio
    async def test_gender_restriction(self, worker, tenant_ctx):
        with pytest.raises(IncompatibleCodes):
            await worker.execute({
                "priced_procedures": [{"code": "40601013"}],
                "patient_gender": "male",
            })

    @pytest.mark.asyncio
    async def test_age_restriction(self, worker, tenant_ctx):
        with pytest.raises(IncompatibleCodes):
            await worker.execute({
                "priced_procedures": [{"code": "40401010"}],
                "patient_age_years": 25,
            })
