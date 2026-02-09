"""Tests for CaptureProcedureWorker."""
from __future__ import annotations

from datetime import datetime

import pytest
from unittest.mock import AsyncMock

from platform.shared.domain.enums import TenantCode
from platform.shared.domain.exceptions import CodingException, ExternalServiceException
from platform.shared.integrations.tasy_client import TasyProcedureDTO
from platform.shared.integrations.mv_soul_client import MvSoulBillingItemDTO
from platform.shared.multi_tenant.context import TenantContext, set_current_tenant, clear_tenant

from revenue_cycle.production.workers.capture_procedure_worker import CaptureProcedureWorker


@pytest.fixture
def tenant_austa():
    ctx = TenantContext.from_tenant_code(TenantCode.AUSTA)
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def tenant_amh_sp():
    ctx = TenantContext.from_tenant_code(TenantCode.AMH_SP)
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def tasy_client():
    return AsyncMock()


@pytest.fixture
def mv_soul_client():
    return AsyncMock()


@pytest.fixture
def worker(tasy_client, mv_soul_client):
    return CaptureProcedureWorker(
        tasy_client=tasy_client,
        mv_soul_client=mv_soul_client,
    )


class TestCaptureProcedureWorker:
    @pytest.mark.asyncio
    async def test_tasy_capture(self, worker, tasy_client, tenant_austa):
        tasy_client.get_procedures.return_value = [
            TasyProcedureDTO(
                procedure_id="proc-1",
                tenant_id="austa-hospital",
                encounter_id="enc-1",
                patient_id="pat-1",
                code="40101010",
                display="Consulta",
                status="completed",
            )
        ]

        result = await worker.execute({"encounter_reference": "Encounter/enc-1"})

        assert result["erp_system"] == "tasy"
        assert result["procedure_count"] == 1
        assert result["captured_procedures"][0]["code"] == "40101010"

    @pytest.mark.asyncio
    async def test_mv_soul_capture(self, worker, mv_soul_client, tenant_amh_sp):
        mv_soul_client.get_billing_items.return_value = [
            MvSoulBillingItemDTO(
                item_id="item-1",
                tenant_id="amh-sp-morumbi",
                encounter_id="enc-1",
                item_code="40101010",
                item_description="Consulta",
                quantity=1.0,
                unit_price=150.0,
                total_price=150.0,
                service_date="2024-01-01",
                status="approved",
                created_at="2024-01-01",
            )
        ]

        result = await worker.execute({"encounter_reference": "Encounter/enc-1"})

        assert result["erp_system"] == "mv_soul"
        assert result["procedure_count"] == 1

    @pytest.mark.asyncio
    async def test_missing_encounter_raises(self, worker, tenant_austa):
        with pytest.raises(CodingException):
            await worker.execute({"encounter_reference": ""})

    @pytest.mark.asyncio
    async def test_no_procedures_raises(self, worker, tasy_client, tenant_austa):
        tasy_client.get_procedures.return_value = []

        with pytest.raises(CodingException):
            await worker.execute({"encounter_reference": "Encounter/enc-1"})
