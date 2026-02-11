"""Tests for UpdateSchedulingSystemWorker."""
from __future__ import annotations
from datetime import datetime
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException


@pytest.fixture
def system_updater():
    """Mock system updater protocol."""
    return AsyncMock()


@pytest.fixture
def worker(fhir_client, tasy_client, mv_soul_client):
    from healthcare_platform.patient_access.workers.update_scheduling_system_worker import UpdateSchedulingSystemWorker
    # Using system_updater protocol that wraps both clients
    system_updater = AsyncMock()
    system_updater.tasy_client = tasy_client
    system_updater.mv_soul_client = mv_soul_client
    return UpdateSchedulingSystemWorker(fhir_client=fhir_client, system_updater=system_updater)


class TestUpdateSchedulingSystemWorker:
    @pytest.mark.asyncio
    async def test_happy_path_updates_systems(self, worker, fhir_client, tenant_hospital_a, mock_appointment):
        """Test successful scheduling system updates."""
        fhir_client.read.return_value = mock_appointment
        worker.system_updater.update_tasy.return_value = {"status": "success"}
        worker.system_updater.update_mv_soul.return_value = {"status": "success"}

        result = await worker.execute({
            "appointment_id": "appointment-789"
        })

        assert result["status"] == "updated"
        assert result["tasy_updated"] is True
        assert result["mv_soul_updated"] is True

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_hospital_a):
        """Test that missing appointment_id raises DomainException."""
        with pytest.raises(DomainException):
            await worker.execute({})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({"appointment_id": "appointment-789"})

    @pytest.mark.asyncio
    async def test_partial_update_failure(self, worker, fhir_client, tenant_hospital_a, mock_appointment):
        """Test handling of partial system update failure."""
        fhir_client.read.return_value = mock_appointment
        worker.system_updater.update_tasy.return_value = {"status": "success"}
        worker.system_updater.update_mv_soul.side_effect = Exception("MV Soul unavailable")

        result = await worker.execute({
            "appointment_id": "appointment-789"
        })

        assert result["tasy_updated"] is True
        assert result["mv_soul_updated"] is False
        assert "error" in result
