"""Tests for CreatePatientRecordWorker."""
from __future__ import annotations
from datetime import datetime
import pytest
from unittest.mock import AsyncMock
from platform.shared.domain.enums import TenantCode
from platform.shared.domain.exceptions import DomainException


@pytest.fixture
def worker(fhir_client):
    from platform.patient_access.workers.create_patient_record_worker import CreatePatientRecordWorker
    return CreatePatientRecordWorker(fhir_client=fhir_client)


class TestCreatePatientRecordWorker:
    @pytest.mark.asyncio
    async def test_happy_path_creates_patient_record(self, worker, fhir_client, tenant_austa, mock_patient):
        """Test successful patient record creation."""
        fhir_client.create.return_value = mock_patient

        result = await worker.execute({
            "patient_data": mock_patient
        })

        assert result["patient_id"] == "patient-123"
        assert result["status"] == "created"
        fhir_client.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing patient_data raises DomainException."""
        with pytest.raises(DomainException):
            await worker.execute({})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        from platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({"patient_data": {"name": "Test"}})

    @pytest.mark.asyncio
    async def test_duplicate_patient_raises(self, worker, fhir_client, tenant_austa, mock_patient):
        """Test that duplicate patient creation raises DomainException."""
        fhir_client.create.side_effect = DomainException("Patient already exists")

        with pytest.raises(DomainException):
            await worker.execute({
                "patient_data": mock_patient
            })
