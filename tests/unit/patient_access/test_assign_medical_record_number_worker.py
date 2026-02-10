"""Tests for AssignMedicalRecordNumberWorker."""
from __future__ import annotations
from datetime import datetime
import hashlib
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException, InvalidTenant


@pytest.fixture
def worker():
    from healthcare_platform.patient_access.workers.assign_medical_record_number_worker import (
        AssignMedicalRecordNumberWorker,
        StubMRNAssigner,
    )

    return AssignMedicalRecordNumberWorker(assigner=StubMRNAssigner())


@pytest.mark.unit
class TestAssignMedicalRecordNumberWorker:
    @pytest.mark.asyncio
    async def test_happy_path_mrn_assignment(self, worker, tenant_austa):
        """Test successful MRN assignment."""
        # Arrange
        cpf_hash = hashlib.sha256(b"12345678901").hexdigest()
        task_vars = {
            "patient_id": "patient-123",
            "facility_cnes_code": "2077485",
            "patient_cpf_hash": cpf_hash,
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["patient_id"] == "patient-123"
        assert result["mrn"] == "2077485-000001"
        assert result["facility_cnes_code"] == "2077485"
        assert result["sequence_number"] == 1
        assert result["formatted_mrn"] == "2077485-000001"

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing required field raises DomainException."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            await worker.execute({"patient_id": "patient-123"})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        cpf_hash = hashlib.sha256(b"12345678901").hexdigest()
        with pytest.raises(InvalidTenant):
            await worker.execute(
                {
                    "patient_id": "patient-123",
                    "facility_cnes_code": "2077485",
                    "patient_cpf_hash": cpf_hash,
                }
            )

    @pytest.mark.asyncio
    async def test_invalid_cnes_code_raises(self, worker, tenant_austa):
        """Test that invalid CNES code raises PatientAccessException."""
        from healthcare_platform.patient_access.workers.assign_medical_record_number_worker import (
            PatientAccessException,
        )

        cpf_hash = hashlib.sha256(b"12345678901").hexdigest()

        # Mock assigner to return invalid CNES
        worker.assigner.validate_cnes_code = AsyncMock(return_value=(False, "CNES inválido"))

        with pytest.raises(PatientAccessException):
            await worker.execute(
                {
                    "patient_id": "patient-123",
                    "facility_cnes_code": "123",  # Too short
                    "patient_cpf_hash": cpf_hash,
                }
            )

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self, worker, fhir_client, tenant_austa, tenant_hpa):
        """Test tenant isolation between AUSTA and HPA."""
        cpf_hash = hashlib.sha256(b"12345678901").hexdigest()

        # Execute with AUSTA
        result_austa = await worker.execute(
            {
                "patient_id": "patient-austa",
                "facility_cnes_code": "2077485",
                "patient_cpf_hash": cpf_hash,
            }
        )

        # Switch to HPA
        from healthcare_platform.shared.multi_tenant.context import set_current_tenant, TenantContext

        hpa_ctx = TenantContext.from_tenant_code(TenantCode.HPA)
        set_current_tenant(hpa_ctx)

        # Execute with HPA
        result_hpa = await worker.execute(
            {
                "patient_id": "patient-hpa",
                "facility_cnes_code": "2077485",
                "patient_cpf_hash": cpf_hash,
            }
        )

        # MRN sequences should be independent per tenant
        assert result_austa["mrn"] != result_hpa["mrn"]

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, tenant_austa):
        """Test idempotent execution - same CPF gets same MRN."""
        cpf_hash = hashlib.sha256(b"12345678901").hexdigest()
        task_vars = {
            "patient_id": "patient-123",
            "facility_cnes_code": "2077485",
            "patient_cpf_hash": cpf_hash,
        }

        # Execute twice
        result1 = await worker.execute(task_vars)
        result2 = await worker.execute(task_vars)

        # Should get same MRN
        assert result1["mrn"] == result2["mrn"]
        assert result1["sequence_number"] == result2["sequence_number"]

    @pytest.mark.asyncio
    async def test_sequential_mrn_generation(self, worker, tenant_austa):
        """Test that MRNs are generated sequentially."""
        cpf_hash1 = hashlib.sha256(b"11111111111").hexdigest()
        cpf_hash2 = hashlib.sha256(b"22222222222").hexdigest()

        result1 = await worker.execute(
            {
                "patient_id": "patient-1",
                "facility_cnes_code": "2077485",
                "patient_cpf_hash": cpf_hash1,
            }
        )

        result2 = await worker.execute(
            {
                "patient_id": "patient-2",
                "facility_cnes_code": "2077485",
                "patient_cpf_hash": cpf_hash2,
            }
        )

        assert result2["sequence_number"] == result1["sequence_number"] + 1

    @pytest.mark.asyncio
    async def test_mrn_format_validation(self, worker, tenant_austa):
        """Test MRN format is CNES-SEQUENCE."""
        cpf_hash = hashlib.sha256(b"12345678901").hexdigest()

        result = await worker.execute(
            {
                "patient_id": "patient-123",
                "facility_cnes_code": "2077485",
                "patient_cpf_hash": cpf_hash,
            }
        )

        # MRN should be in format CNES-SEQUENCE
        assert "-" in result["mrn"]
        cnes_part, seq_part = result["mrn"].split("-")
        assert cnes_part == "2077485"
        assert len(seq_part) == 6  # Padded to 6 digits

    @pytest.mark.asyncio
    async def test_mrn_collision_raises_error(self, worker, tenant_austa):
        """Test that MRN collision raises PatientAccessException."""
        from healthcare_platform.patient_access.workers.assign_medical_record_number_worker import (
            PatientAccessException,
        )

        cpf_hash = hashlib.sha256(b"12345678901").hexdigest()

        # Mock to simulate collision
        worker.assigner.check_mrn_exists = AsyncMock(return_value=True)

        with pytest.raises(PatientAccessException) as exc_info:
            await worker.execute(
                {
                    "patient_id": "patient-123",
                    "facility_cnes_code": "2077485",
                    "patient_cpf_hash": cpf_hash,
                }
            )

        assert "Colisão de MRN" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_different_facilities_different_sequences(self, worker, tenant_austa):
        """Test that different facilities have independent MRN sequences."""
        cpf_hash1 = hashlib.sha256(b"11111111111").hexdigest()
        cpf_hash2 = hashlib.sha256(b"22222222222").hexdigest()

        # Facility 1
        result1 = await worker.execute(
            {
                "patient_id": "patient-1",
                "facility_cnes_code": "2077485",
                "patient_cpf_hash": cpf_hash1,
            }
        )

        # Facility 2
        result2 = await worker.execute(
            {
                "patient_id": "patient-2",
                "facility_cnes_code": "3088572",
                "patient_cpf_hash": cpf_hash2,
            }
        )

        # Both should start at sequence 1
        assert result1["sequence_number"] == 1
        assert result2["sequence_number"] == 1
        assert result1["mrn"] != result2["mrn"]
