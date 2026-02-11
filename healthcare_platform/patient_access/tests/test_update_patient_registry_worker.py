"""Tests for UpdatePatientRegistryWorker."""
from __future__ import annotations
from datetime import datetime
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException


@pytest.fixture
def registry_updater():
    """Mock registry updater protocol."""
    return AsyncMock()


@pytest.fixture
def worker(fhir_client, tasy_client, mv_soul_client):
    from healthcare_platform.patient_access.workers.update_patient_registry_worker import UpdatePatientRegistryWorker
    # Using registry_updater protocol that wraps both clients
    registry_updater = AsyncMock()
    registry_updater.tasy_client = tasy_client
    registry_updater.mv_soul_client = mv_soul_client
    return UpdatePatientRegistryWorker(fhir_client=fhir_client, registry_updater=registry_updater)


class TestUpdatePatientRegistryWorker:
    @pytest.mark.asyncio
    async def test_happy_path_updates_registry(self, worker, fhir_client, tenant_hospital_a, mock_patient):
        """Test successful patient registry update."""
        fhir_client.read.return_value = mock_patient
        worker.registry_updater.update_tasy.return_value = {"status": "success"}
        worker.registry_updater.update_mv_soul.return_value = {"status": "success"}

        result = await worker.execute({
            "patient_id": "patient-123"
        })

        assert result["status"] == "updated"
        assert result["tasy_updated"] is True
        assert result["mv_soul_updated"] is True

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_hospital_a):
        """Test that missing patient_id raises DomainException."""
        with pytest.raises(DomainException):
            await worker.execute({})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({"patient_id": "patient-123"})

    @pytest.mark.asyncio
    async def test_partial_update_failure(self, worker, fhir_client, tenant_hospital_a, mock_patient):
        """Test handling of partial registry update failure."""
        fhir_client.read.return_value = mock_patient
        worker.registry_updater.update_tasy.return_value = {"status": "success"}
        worker.registry_updater.update_mv_soul.side_effect = Exception("MV Soul unavailable")

        result = await worker.execute({
            "patient_id": "patient-123"
        })

        assert result["tasy_updated"] is True
        assert result["mv_soul_updated"] is False
