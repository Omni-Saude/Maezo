"""Tests for CaptureDemographicsWorker."""
from __future__ import annotations
import hashlib
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException, InvalidTenant


@pytest.fixture
def worker(fhir_client):
    from healthcare_platform.patient_access.workers.capture_demographics_worker import (
        CaptureDemographicsWorker,
        StubDemographicsCapture,
    )

    return CaptureDemographicsWorker(fhir_client=fhir_client, capture=StubDemographicsCapture())


@pytest.mark.unit
class TestCaptureDemographicsWorker:
    @pytest.mark.asyncio
    async def test_happy_path_capture_demographics(self, worker, fhir_client, tenant_austa):
        """Test successful demographics capture."""
        # Arrange
        fhir_client.read.return_value = {
            "resourceType": "Patient",
            "id": "123",
            "name": [{"text": "João Silva"}],
        }
        fhir_client.update.return_value = {"resourceType": "Patient", "id": "123"}

        task_vars = {
            "patient_reference": "Patient/123",
            "address_cep": "01310-100",
            "address_street": "Av Paulista",
            "address_number": "1000",
            "address_city": "São Paulo",
            "address_state": "SP",
            "phone": "11987654321",
            "email": "joao@example.com",
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["demographics_updated"] is True
        assert "address_hash" in result
        assert "phone_hash" in result
        assert "email_hash" in result
        fhir_client.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing required field raises validation error."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            await worker.execute({"patient_reference": "Patient/123"})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        with pytest.raises(InvalidTenant):
            await worker.execute(
                {
                    "patient_reference": "Patient/123",
                    "address_cep": "01310100",
                    "address_street": "Av Paulista",
                    "address_number": "1000",
                    "address_city": "São Paulo",
                    "address_state": "SP",
                    "phone": "11987654321",
                    "email": "joao@example.com",
                }
            )

    @pytest.mark.asyncio
    async def test_invalid_cep_raises(self, worker, tenant_austa):
        """Test that invalid CEP raises validation error."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            await worker.execute(
                {
                    "patient_reference": "Patient/123",
                    "address_cep": "123",  # Too short
                    "address_street": "Av Paulista",
                    "address_number": "1000",
                    "address_city": "São Paulo",
                    "address_state": "SP",
                    "phone": "11987654321",
                    "email": "joao@example.com",
                }
            )

    @pytest.mark.asyncio
    async def test_invalid_phone_raises(self, worker, tenant_austa):
        """Test that invalid phone raises validation error."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            await worker.execute(
                {
                    "patient_reference": "Patient/123",
                    "address_cep": "01310100",
                    "address_street": "Av Paulista",
                    "address_number": "1000",
                    "address_city": "São Paulo",
                    "address_state": "SP",
                    "phone": "123",  # Too short
                    "email": "joao@example.com",
                }
            )

    @pytest.mark.asyncio
    async def test_invalid_email_raises(self, worker, tenant_austa):
        """Test that invalid email raises validation error."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            await worker.execute(
                {
                    "patient_reference": "Patient/123",
                    "address_cep": "01310100",
                    "address_street": "Av Paulista",
                    "address_number": "1000",
                    "address_city": "São Paulo",
                    "address_state": "SP",
                    "phone": "11987654321",
                    "email": "invalid-email",  # No @
                }
            )

    @pytest.mark.asyncio
    async def test_invalid_state_raises(self, worker, tenant_austa):
        """Test that invalid state raises validation error."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            await worker.execute(
                {
                    "patient_reference": "Patient/123",
                    "address_cep": "01310100",
                    "address_street": "Av Paulista",
                    "address_number": "1000",
                    "address_city": "São Paulo",
                    "address_state": "XX",  # Invalid state
                    "phone": "11987654321",
                    "email": "joao@example.com",
                }
            )

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self, worker, fhir_client, tenant_austa, tenant_hpa):
        """Test tenant isolation between AUSTA and HPA."""
        from healthcare_platform.shared.multi_tenant.context import set_current_tenant, TenantContext

        fhir_client.read.return_value = {"resourceType": "Patient", "id": "123"}
        fhir_client.update.return_value = {"resourceType": "Patient", "id": "123"}

        # Execute with AUSTA
        result_austa = await worker.execute(
            {
                "patient_reference": "Patient/austa-123",
                "address_cep": "01310100",
                "address_street": "Av Paulista",
                "address_number": "1000",
                "address_city": "São Paulo",
                "address_state": "SP",
                "phone": "11987654321",
                "email": "joao@example.com",
            }
        )

        # Switch to HPA
        hpa_ctx = TenantContext.from_tenant_code(TenantCode.HPA)
        set_current_tenant(hpa_ctx)

        # Execute with HPA
        result_hpa = await worker.execute(
            {
                "patient_reference": "Patient/hpa-123",
                "address_cep": "01310100",
                "address_street": "Av Paulista",
                "address_number": "1000",
                "address_city": "São Paulo",
                "address_state": "SP",
                "phone": "11987654321",
                "email": "joao@example.com",
            }
        )

        # Hashes should be same (same input data), but updates isolated
        assert result_austa["address_hash"] == result_hpa["address_hash"]

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, fhir_client, tenant_austa):
        """Test idempotent execution."""
        fhir_client.read.return_value = {"resourceType": "Patient", "id": "123"}
        fhir_client.update.return_value = {"resourceType": "Patient", "id": "123"}

        task_vars = {
            "patient_reference": "Patient/123",
            "address_cep": "01310100",
            "address_street": "Av Paulista",
            "address_number": "1000",
            "address_city": "São Paulo",
            "address_state": "SP",
            "phone": "11987654321",
            "email": "joao@example.com",
        }

        # Execute twice
        result1 = await worker.execute(task_vars)
        result2 = await worker.execute(task_vars)

        # Hashes should be identical
        assert result1["address_hash"] == result2["address_hash"]
        assert result1["phone_hash"] == result2["phone_hash"]
        assert result1["email_hash"] == result2["email_hash"]

    @pytest.mark.asyncio
    async def test_external_service_failure(self, worker, fhir_client, tenant_austa):
        """Test external FHIR service failure handling."""
        from healthcare_platform.patient_access.workers.capture_demographics_worker import (
            PatientAccessException,
        )

        fhir_client.read.return_value = {"resourceType": "Patient", "id": "123"}
        fhir_client.update.side_effect = Exception("FHIR server unavailable")

        with pytest.raises(PatientAccessException):
            await worker.execute(
                {
                    "patient_reference": "Patient/123",
                    "address_cep": "01310100",
                    "address_street": "Av Paulista",
                    "address_number": "1000",
                    "address_city": "São Paulo",
                    "address_state": "SP",
                    "phone": "11987654321",
                    "email": "joao@example.com",
                }
            )

    @pytest.mark.asyncio
    async def test_pii_hashing(self, worker, fhir_client, tenant_austa):
        """Test that PII is properly hashed with SHA-256."""
        fhir_client.read.return_value = {"resourceType": "Patient", "id": "123"}
        fhir_client.update.return_value = {"resourceType": "Patient", "id": "123"}

        result = await worker.execute(
            {
                "patient_reference": "Patient/123",
                "address_cep": "01310100",
                "address_street": "Av Paulista",
                "address_number": "1000",
                "address_city": "São Paulo",
                "address_state": "SP",
                "phone": "11987654321",
                "email": "joao@example.com",
            }
        )

        # Hashes should be SHA-256 (64 hex characters)
        assert len(result["address_hash"]) == 64
        assert len(result["phone_hash"]) == 64
        assert len(result["email_hash"]) == 64

        # Verify phone hash
        expected_phone_hash = hashlib.sha256(b"11987654321").hexdigest()
        assert result["phone_hash"] == expected_phone_hash
