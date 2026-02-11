"""Tests for AssignMedicalRecordNumberWorker."""
from __future__ import annotations
from datetime import datetime
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException


@pytest.fixture
def mrn_assigner():
    """Mock MRN assigner protocol."""
    return AsyncMock()


@pytest.fixture
def worker(fhir_client, mrn_assigner):
    from healthcare_platform.patient_access.workers.assign_medical_record_number_worker import AssignMedicalRecordNumberWorker
    return AssignMedicalRecordNumberWorker(fhir_client=fhir_client, mrn_assigner=mrn_assigner)


class TestAssignMedicalRecordNumberWorker:
    @pytest.mark.asyncio
    async def test_happy_path_assigns_mrn(self, worker, fhir_client, mrn_assigner, tenant_austa, mock_patient):
        """Test successful MRN assignment."""
        mrn_assigner.generate_mrn.return_value = "MRN123456"
        fhir_client.update.return_value = mock_patient

        result = await worker.execute({
            "patient_id": "patient-123"
        })

        assert result["mrn"] == "MRN123456"
        assert result["status"] == "assigned"
        mrn_assigner.generate_mrn.assert_called_once()
        fhir_client.update.assert_called_once()

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
    async def test_duplicate_mrn_raises(self, worker, fhir_client, mrn_assigner, tenant_hospital_a):
        """Test that duplicate MRN raises DomainException."""
        mrn_assigner.generate_mrn.return_value = "MRN123456"
        fhir_client.update.side_effect = DomainException("MRN already exists")

        with pytest.raises(DomainException):
            await worker.execute({
                "patient_id": "patient-123"
            })
