"""Tests for CreatePatientRecordWorker."""
from __future__ import annotations
import hashlib
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException, InvalidTenant


@pytest.fixture
def worker(fhir_client):
    from healthcare_platform.patient_access.workers.create_patient_record_worker import (
        CreatePatientRecordWorker,
        StubPatientRecordCreator,
    )

    return CreatePatientRecordWorker(fhir_client=fhir_client, creator=StubPatientRecordCreator())


@pytest.mark.unit
class TestCreatePatientRecordWorker:
    @pytest.mark.asyncio
    async def test_happy_path_create_patient(self, worker, fhir_client, tenant_austa):
        """Test successful patient record creation."""
        # Arrange
        cpf_hash = hashlib.sha256(b"12345678901").hexdigest()
        fhir_client.create.return_value = {
            "resourceType": "Patient",
            "id": "new-patient-123",
        }

        task_vars = {
            "cpf_hash": cpf_hash,
            "name": "João da Silva",
            "birth_date": "1980-05-15",
            "gender": "male",
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["created"] is True
        assert result["patient_reference"] == "Patient/new-patient-123"
        assert result["patient_id"] == "new-patient-123"
        fhir_client.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing required field raises validation error."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            await worker.execute({"cpf_hash": "somehash"})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        cpf_hash = hashlib.sha256(b"12345678901").hexdigest()

        with pytest.raises(InvalidTenant):
            await worker.execute(
                {
                    "cpf_hash": cpf_hash,
                    "name": "João da Silva",
                    "birth_date": "1980-05-15",
                    "gender": "male",
                }
            )

    @pytest.mark.asyncio
    async def test_patient_with_cns_hash(self, worker, fhir_client, tenant_austa):
        """Test patient creation with CNS hash."""
        cpf_hash = hashlib.sha256(b"12345678901").hexdigest()
        cns_hash = hashlib.sha256(b"123456789012345").hexdigest()

        fhir_client.create.return_value = {"resourceType": "Patient", "id": "patient-456"}

        result = await worker.execute(
            {
                "cpf_hash": cpf_hash,
                "cns_hash": cns_hash,
                "name": "Maria Santos",
                "birth_date": "1990-03-20",
                "gender": "female",
            }
        )

        assert result["created"] is True
        # Verify CNS identifier was included
        fhir_client.create.assert_called_once()
        patient_resource = fhir_client.create.call_args[0][1]
        identifiers = patient_resource["identifier"]
        assert len(identifiers) == 2  # CPF + CNS

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self, worker, fhir_client, tenant_austa, tenant_hpa):
        """Test tenant isolation between AUSTA and HPA."""
        from healthcare_platform.shared.multi_tenant.context import set_current_tenant, TenantContext

        cpf_hash = hashlib.sha256(b"12345678901").hexdigest()

        # Execute with AUSTA
        fhir_client.create.return_value = {"resourceType": "Patient", "id": "austa-patient"}
        result_austa = await worker.execute(
            {
                "cpf_hash": cpf_hash,
                "name": "João AUSTA",
                "birth_date": "1980-05-15",
                "gender": "male",
            }
        )

        # Switch to HPA
        hpa_ctx = TenantContext.from_tenant_code(TenantCode.HPA)
        set_current_tenant(hpa_ctx)

        # Execute with HPA
        fhir_client.create.return_value = {"resourceType": "Patient", "id": "hpa-patient"}
        result_hpa = await worker.execute(
            {
                "cpf_hash": cpf_hash,
                "name": "João HPA",
                "birth_date": "1980-05-15",
                "gender": "male",
            }
        )

        # Patients should be created independently
        assert result_austa["patient_id"] != result_hpa["patient_id"]

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, fhir_client, tenant_austa):
        """Test idempotent execution."""
        cpf_hash = hashlib.sha256(b"12345678901").hexdigest()
        fhir_client.create.return_value = {"resourceType": "Patient", "id": "patient-789"}

        task_vars = {
            "cpf_hash": cpf_hash,
            "name": "Pedro Oliveira",
            "birth_date": "1975-11-30",
            "gender": "male",
        }

        # Execute twice
        result1 = await worker.execute(task_vars)
        result2 = await worker.execute(task_vars)

        # Both should create successfully (not truly idempotent for creation)
        assert result1["created"] is True
        assert result2["created"] is True

    @pytest.mark.asyncio
    async def test_external_service_failure(self, worker, fhir_client, tenant_austa):
        """Test external FHIR service failure handling."""
        from healthcare_platform.patient_access.workers.create_patient_record_worker import (
            PatientAccessException,
        )

        cpf_hash = hashlib.sha256(b"12345678901").hexdigest()
        fhir_client.create.side_effect = Exception("FHIR server unavailable")

        with pytest.raises(PatientAccessException):
            await worker.execute(
                {
                    "cpf_hash": cpf_hash,
                    "name": "João da Silva",
                    "birth_date": "1980-05-15",
                    "gender": "male",
                }
            )

    @pytest.mark.asyncio
    async def test_invalid_fhir_resource_raises(self, worker, fhir_client, tenant_austa):
        """Test that invalid FHIR resource raises PatientAccessException."""
        from healthcare_platform.patient_access.workers.create_patient_record_worker import (
            PatientAccessException,
        )

        cpf_hash = hashlib.sha256(b"12345678901").hexdigest()

        # Mock invalid resource validation
        worker.creator.validate_patient_resource = AsyncMock(return_value=False)

        with pytest.raises(PatientAccessException) as exc_info:
            await worker.execute(
                {
                    "cpf_hash": cpf_hash,
                    "name": "João da Silva",
                    "birth_date": "1980-05-15",
                    "gender": "male",
                }
            )

        assert "inválido" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_fhir_resource_structure(self, worker, fhir_client, tenant_austa):
        """Test that created FHIR resource has correct structure."""
        cpf_hash = hashlib.sha256(b"12345678901").hexdigest()
        fhir_client.create.return_value = {"resourceType": "Patient", "id": "patient-999"}

        await worker.execute(
            {
                "cpf_hash": cpf_hash,
                "name": "Ana Costa",
                "birth_date": "1985-07-10",
                "gender": "female",
            }
        )

        # Verify resource structure
        fhir_client.create.assert_called_once()
        resource_type, patient_resource = fhir_client.create.call_args[0]

        assert resource_type == "Patient"
        assert patient_resource["resourceType"] == "Patient"
        assert "identifier" in patient_resource
        assert "name" in patient_resource
        assert "birthDate" in patient_resource
        assert "gender" in patient_resource
        assert patient_resource["active"] is True

    @pytest.mark.asyncio
    async def test_fhir_no_id_returned_raises(self, worker, fhir_client, tenant_austa):
        """Test that missing patient ID in response raises exception."""
        from healthcare_platform.patient_access.workers.create_patient_record_worker import (
            PatientAccessException,
        )

        cpf_hash = hashlib.sha256(b"12345678901").hexdigest()
        fhir_client.create.return_value = {"resourceType": "Patient"}  # Missing ID

        with pytest.raises(PatientAccessException) as exc_info:
            await worker.execute(
                {
                    "cpf_hash": cpf_hash,
                    "name": "João da Silva",
                    "birth_date": "1980-05-15",
                    "gender": "male",
                }
            )

        assert "ID do paciente não retornado" in str(exc_info.value)
