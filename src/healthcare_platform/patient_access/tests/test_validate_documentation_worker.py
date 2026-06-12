"""Tests for ValidateDocumentationWorker."""
from __future__ import annotations
import pytest
from healthcare_platform.shared.domain.exceptions import DomainException


@pytest.fixture
def worker(fhir_client):
    from healthcare_platform.patient_access.workers.validate_documentation_worker import ValidateDocumentationWorker
    return ValidateDocumentationWorker(fhir_client=fhir_client)


class TestValidateDocumentationWorker:
    @pytest.mark.asyncio
    async def test_happy_path_validates_documentation(self, worker, fhir_client, tenant_hospital_a):
        """Test successful documentation validation."""
        fhir_client.search.return_value = {
            "entry": [
                {"resource": {"resourceType": "DocumentReference", "status": "current"}}
            ]
        }

        result = await worker.execute({
            "patient_id": "patient-123",
            "required_documents": ["identity_card", "proof_of_address"]
        })

        assert result["valid"] is True
        assert result["missing_documents"] == []
        fhir_client.search.assert_called_once()

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
    async def test_missing_documents_returns_list(self, worker, fhir_client, tenant_hospital_a):
        """Test that missing documents are returned in list."""
        fhir_client.search.return_value = {"entry": []}

        result = await worker.execute({
            "patient_id": "patient-123",
            "required_documents": ["identity_card", "proof_of_address"]
        })

        assert result["valid"] is False
        assert len(result["missing_documents"]) == 2
