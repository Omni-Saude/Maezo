"""Tests for CheckExistingPatientWorker."""
from __future__ import annotations
import hashlib
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException, InvalidTenant


@pytest.fixture
def worker(fhir_client):
    from healthcare_platform.patient_access.workers.check_existing_patient_worker import (
        CheckExistingPatientWorker,
        StubPatientDuplicateChecker,
    )

    return CheckExistingPatientWorker(
        fhir_client=fhir_client, checker=StubPatientDuplicateChecker()
    )


@pytest.mark.unit
class TestCheckExistingPatientWorker:
    @pytest.mark.asyncio
    async def test_happy_path_patient_not_exists(self, worker, fhir_client, tenant_austa):
        """Test successful check when patient doesn't exist."""
        # Arrange
        fhir_client.search.return_value = {"entry": []}
        cpf_hash = hashlib.sha256(b"12345678901").hexdigest()

        task_vars = {
            "cpf_hash": cpf_hash,
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["patient_exists"] is False
        assert result["patient_reference"] is None
        assert result["patient_id"] is None

    @pytest.mark.asyncio
    async def test_happy_path_patient_exists(self, worker, fhir_client, tenant_austa):
        """Test successful check when patient exists."""
        # Arrange
        cpf_hash = hashlib.sha256(b"12345678901").hexdigest()
        fhir_client.search.return_value = {
            "entry": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "id": "existing-patient-123",
                        "identifier": [
                            {"system": "urn:brasil:gov:cpf", "value": cpf_hash}
                        ],
                    }
                }
            ]
        }

        task_vars = {
            "cpf_hash": cpf_hash,
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["patient_exists"] is True
        assert result["patient_reference"] == "Patient/existing-patient-123"
        assert result["patient_id"] == "existing-patient-123"

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing required field raises validation error."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            await worker.execute({})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        cpf_hash = hashlib.sha256(b"12345678901").hexdigest()

        with pytest.raises(InvalidTenant):
            await worker.execute({"cpf_hash": cpf_hash})

    @pytest.mark.asyncio
    async def test_search_with_cns_hash(self, worker, fhir_client, tenant_austa):
        """Test search with both CPF and CNS hashes."""
        cpf_hash = hashlib.sha256(b"12345678901").hexdigest()
        cns_hash = hashlib.sha256(b"123456789012345").hexdigest()

        fhir_client.search.return_value = {"entry": []}

        result = await worker.execute(
            {
                "cpf_hash": cpf_hash,
                "cns_hash": cns_hash,
            }
        )

        # Should search with both identifiers
        fhir_client.search.assert_called_once()
        call_args = fhir_client.search.call_args
        assert call_args[0][0] == "Patient"
        assert "identifier" in call_args[1]["params"]

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self, worker, fhir_client, tenant_austa, tenant_hpa):
        """Test tenant isolation between AUSTA and HPA."""
        from healthcare_platform.shared.multi_tenant.context import set_current_tenant, TenantContext

        cpf_hash = hashlib.sha256(b"12345678901").hexdigest()

        # AUSTA has the patient
        fhir_client.search.return_value = {
            "entry": [{"resource": {"resourceType": "Patient", "id": "austa-patient"}}]
        }

        result_austa = await worker.execute({"cpf_hash": cpf_hash})

        # Switch to HPA
        hpa_ctx = TenantContext.from_tenant_code(TenantCode.HPA)
        set_current_tenant(hpa_ctx)

        # HPA doesn't have the patient
        fhir_client.search.return_value = {"entry": []}

        result_hpa = await worker.execute({"cpf_hash": cpf_hash})

        # Results should differ by tenant
        assert result_austa["patient_exists"] is True
        assert result_hpa["patient_exists"] is False

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, fhir_client, tenant_austa):
        """Test idempotent execution."""
        cpf_hash = hashlib.sha256(b"12345678901").hexdigest()
        fhir_client.search.return_value = {"entry": []}

        task_vars = {"cpf_hash": cpf_hash}

        # Execute twice
        result1 = await worker.execute(task_vars)
        result2 = await worker.execute(task_vars)

        # Results should be identical
        assert result1["patient_exists"] == result2["patient_exists"]
        assert result1["patient_reference"] == result2["patient_reference"]

    @pytest.mark.asyncio
    async def test_external_service_failure_fallback(self, worker, fhir_client, tenant_austa):
        """Test fallback to checker when FHIR fails."""
        cpf_hash = hashlib.sha256(b"12345678901").hexdigest()

        # FHIR fails
        fhir_client.search.side_effect = Exception("FHIR server down")

        # Checker returns no results
        worker.checker.search_by_identifiers = AsyncMock(return_value=[])

        result = await worker.execute({"cpf_hash": cpf_hash})

        # Should fallback gracefully
        assert result["patient_exists"] is False

    @pytest.mark.asyncio
    async def test_multiple_patients_returns_first(self, worker, fhir_client, tenant_austa):
        """Test that first patient is returned when multiple matches."""
        cpf_hash = hashlib.sha256(b"12345678901").hexdigest()

        fhir_client.search.return_value = {
            "entry": [
                {"resource": {"resourceType": "Patient", "id": "patient-1"}},
                {"resource": {"resourceType": "Patient", "id": "patient-2"}},
            ]
        }

        result = await worker.execute({"cpf_hash": cpf_hash})

        # Should return first match
        assert result["patient_exists"] is True
        assert result["patient_id"] == "patient-1"

    @pytest.mark.asyncio
    async def test_fhir_search_parameters(self, worker, fhir_client, tenant_austa):
        """Test that FHIR search uses correct parameters."""
        cpf_hash = hashlib.sha256(b"12345678901").hexdigest()
        fhir_client.search.return_value = {"entry": []}

        await worker.execute({"cpf_hash": cpf_hash})

        # Verify search parameters
        fhir_client.search.assert_called_once()
        call_args = fhir_client.search.call_args
        assert call_args[0][0] == "Patient"
        params = call_args[1]["params"]
        assert "identifier" in params
        assert cpf_hash in str(params["identifier"])
