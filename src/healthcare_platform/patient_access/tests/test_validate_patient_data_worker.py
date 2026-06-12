"""Tests for ValidatePatientDataWorker."""
from __future__ import annotations
import pytest
from healthcare_platform.shared.domain.exceptions import DomainException


@pytest.fixture
def worker(fhir_client):
    from healthcare_platform.patient_access.workers.validate_patient_data_worker import ValidatePatientDataWorker
    return ValidatePatientDataWorker(fhir_client=fhir_client)


class TestValidatePatientDataWorker:
    @pytest.mark.asyncio
    async def test_happy_path_validates_patient_data(self, worker, fhir_client, tenant_hospital_a, mock_patient):
        """Test successful patient data validation."""
        fhir_client.validate_resource.return_value = {"valid": True}

        result = await worker.execute({
            "patient_data": mock_patient
        })

        assert result["valid"] is True
        fhir_client.validate_resource.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_hospital_a):
        """Test that missing patient_data raises DomainException."""
        with pytest.raises(DomainException):
            await worker.execute({})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({"patient_data": {"name": "Test"}})

    @pytest.mark.asyncio
    async def test_invalid_cpf_format_raises(self, worker, tenant_hospital_a):
        """Test that invalid CPF format raises DomainException."""
        with pytest.raises(DomainException):
            await worker.execute({
                "patient_data": {
                    "cpf": "invalid-cpf"
                }
            })
