"""Tests for RegisterDependentWorker."""
from __future__ import annotations
import pytest
from healthcare_platform.shared.domain.exceptions import DomainException


@pytest.fixture
def worker(fhir_client):
    from healthcare_platform.patient_access.workers.register_dependent_worker import RegisterDependentWorker
    return RegisterDependentWorker(fhir_client=fhir_client)


class TestRegisterDependentWorker:
    @pytest.mark.asyncio
    async def test_happy_path_registers_dependent(self, worker, fhir_client, tenant_hospital_a, mock_patient):
        """Test successful dependent registration."""
        dependent_patient = {**mock_patient, "id": "patient-456"}
        fhir_client.create.return_value = dependent_patient
        fhir_client.update.return_value = mock_patient

        result = await worker.execute({
            "subscriber_id": "patient-123",
            "dependent_data": dependent_patient
        })

        assert result["dependent_id"] == "patient-456"
        assert result["status"] == "registered"
        fhir_client.create.assert_called_once()
        fhir_client.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_hospital_a):
        """Test that missing subscriber_id raises DomainException."""
        with pytest.raises(DomainException):
            await worker.execute({})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({"subscriber_id": "patient-123"})

    @pytest.mark.asyncio
    async def test_invalid_relationship_raises(self, worker, tenant_hospital_a):
        """Test that invalid relationship type raises DomainException."""
        with pytest.raises(DomainException):
            await worker.execute({
                "subscriber_id": "patient-123",
                "dependent_data": {
                    "relationship": "invalid-relationship"
                }
            })
