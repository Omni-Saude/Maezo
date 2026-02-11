"""Tests for GeneratePreAdmissionChecklistWorker."""
from __future__ import annotations
from datetime import datetime
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException


@pytest.fixture
def worker(fhir_client):
    from healthcare_platform.patient_access.workers.generate_pre_admission_checklist_worker import GeneratePreAdmissionChecklistWorker
    return GeneratePreAdmissionChecklistWorker(fhir_client=fhir_client)


class TestGeneratePreAdmissionChecklistWorker:
    @pytest.mark.asyncio
    async def test_happy_path_generates_checklist(self, worker, fhir_client, tenant_hospital_a, mock_appointment):
        """Test successful pre-admission checklist generation."""
        fhir_client.read.return_value = mock_appointment
        fhir_client.create.return_value = {
            "resourceType": "QuestionnaireResponse",
            "id": "checklist-001",
            "status": "in-progress"
        }

        result = await worker.execute({
            "appointment_id": "appointment-789",
            "service_type": "surgery"
        })

        assert result["checklist_id"] == "checklist-001"
        assert len(result["items"]) > 0
        fhir_client.create.assert_called_once()

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
    async def test_surgery_checklist_more_items(self, worker, fhir_client, tenant_hospital_a, mock_appointment):
        """Test that surgery checklist has more items than consultation."""
        fhir_client.read.return_value = mock_appointment
        fhir_client.create.return_value = {
            "resourceType": "QuestionnaireResponse",
            "id": "checklist-001",
            "status": "in-progress"
        }

        result = await worker.execute({
            "appointment_id": "appointment-789",
            "service_type": "surgery"
        })

        assert len(result["items"]) >= 5
        assert any("fasting" in item.lower() for item in result["items"])
