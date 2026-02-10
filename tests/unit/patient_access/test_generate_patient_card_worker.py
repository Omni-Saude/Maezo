"""Tests for GeneratePatientCardWorker."""
from __future__ import annotations
import hashlib
import json
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException, InvalidTenant


@pytest.fixture
def worker():
    from healthcare_platform.patient_access.workers.generate_patient_card_worker import (
        GeneratePatientCardWorker,
        StubPatientCardGenerator,
    )

    return GeneratePatientCardWorker(generator=StubPatientCardGenerator())


@pytest.mark.unit
class TestGeneratePatientCardWorker:
    @pytest.mark.asyncio
    async def test_happy_path_generate_card(self, worker, tenant_austa):
        """Test successful patient card generation."""
        # Arrange
        task_vars = {
            "patient_id": "patient-123",
            "mrn": "2077485-000001",
            "patient_name": "João da Silva",
            "facility_name": "Hospital AUSTA",
            "facility_cnes_code": "2077485",
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["patient_id"] == "patient-123"
        assert "card_data" in result
        assert result["card_data"]["mrn"] == "2077485-000001"
        assert result["card_data"]["card_number"].startswith("2077485-")
        assert result["card_url"] is not None
        assert result["qr_code_url"] is not None

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing required field raises validation error."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            await worker.execute({"patient_id": "patient-123"})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        with pytest.raises(InvalidTenant):
            await worker.execute(
                {
                    "patient_id": "patient-123",
                    "mrn": "2077485-000001",
                    "patient_name": "João da Silva",
                    "facility_name": "Hospital AUSTA",
                    "facility_cnes_code": "2077485",
                }
            )

    @pytest.mark.asyncio
    async def test_qr_code_content_structure(self, worker, tenant_austa):
        """Test QR code content is valid JSON with required fields."""
        result = await worker.execute(
            {
                "patient_id": "patient-456",
                "mrn": "2077485-000002",
                "patient_name": "Maria Santos",
                "facility_name": "Hospital AUSTA",
                "facility_cnes_code": "2077485",
            }
        )

        # Parse QR code content
        qr_content = json.loads(result["card_data"]["qr_code_content"])

        assert "patient_id_hash" in qr_content
        assert "mrn" in qr_content
        assert "card_number" in qr_content
        assert "version" in qr_content
        assert qr_content["mrn"] == "2077485-000002"

    @pytest.mark.asyncio
    async def test_patient_id_hashing(self, worker, tenant_austa):
        """Test that patient ID is properly hashed in card data."""
        patient_id = "patient-789"

        result = await worker.execute(
            {
                "patient_id": patient_id,
                "mrn": "2077485-000003",
                "patient_name": "Pedro Oliveira",
                "facility_name": "Hospital AUSTA",
                "facility_cnes_code": "2077485",
            }
        )

        # Verify hash
        expected_hash = hashlib.sha256(patient_id.encode("utf-8")).hexdigest()
        assert result["card_data"]["patient_id_hash"] == expected_hash
        assert len(result["card_data"]["patient_id_hash"]) == 64  # SHA-256 is 64 hex chars

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self, worker, tenant_austa, tenant_hpa):
        """Test tenant isolation between AUSTA and HPA."""
        from healthcare_platform.shared.multi_tenant.context import set_current_tenant, TenantContext

        # Execute with AUSTA
        result_austa = await worker.execute(
            {
                "patient_id": "patient-austa",
                "mrn": "2077485-000001",
                "patient_name": "João AUSTA",
                "facility_name": "Hospital AUSTA",
                "facility_cnes_code": "2077485",
            }
        )

        # Switch to HPA
        hpa_ctx = TenantContext.from_tenant_code(TenantCode.HPA)
        set_current_tenant(hpa_ctx)

        # Execute with HPA
        result_hpa = await worker.execute(
            {
                "patient_id": "patient-hpa",
                "mrn": "3088572-000001",
                "patient_name": "João HPA",
                "facility_name": "Hospital HPA",
                "facility_cnes_code": "3088572",
            }
        )

        # Cards should be independent
        assert result_austa["card_data"]["card_number"] != result_hpa["card_data"]["card_number"]

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, tenant_austa):
        """Test idempotent execution."""
        task_vars = {
            "patient_id": "patient-999",
            "mrn": "2077485-000004",
            "patient_name": "Ana Costa",
            "facility_name": "Hospital AUSTA",
            "facility_cnes_code": "2077485",
        }

        # Execute twice
        result1 = await worker.execute(task_vars)
        result2 = await worker.execute(task_vars)

        # Patient ID hash should be consistent
        assert result1["card_data"]["patient_id_hash"] == result2["card_data"]["patient_id_hash"]
        # But card numbers will be different (sequential generation)
        assert result1["card_data"]["card_number"] != result2["card_data"]["card_number"]

    @pytest.mark.asyncio
    async def test_external_service_failure(self, worker, tenant_austa):
        """Test external service failure handling."""
        from healthcare_platform.patient_access.workers.generate_patient_card_worker import (
            PatientAccessException,
        )

        # Mock failure
        worker.generator.generate_digital_card = AsyncMock(
            side_effect=Exception("Card generation service unavailable")
        )

        with pytest.raises(PatientAccessException):
            await worker.execute(
                {
                    "patient_id": "patient-123",
                    "mrn": "2077485-000001",
                    "patient_name": "João da Silva",
                    "facility_name": "Hospital AUSTA",
                    "facility_cnes_code": "2077485",
                }
            )

    @pytest.mark.asyncio
    async def test_card_number_format(self, worker, tenant_austa):
        """Test card number follows CNES-SEQUENCE format."""
        result = await worker.execute(
            {
                "patient_id": "patient-111",
                "mrn": "2077485-000005",
                "patient_name": "Carlos Mendes",
                "facility_name": "Hospital AUSTA",
                "facility_cnes_code": "2077485",
            }
        )

        card_number = result["card_data"]["card_number"]

        # Should be in format CNES-SEQUENCE
        assert "-" in card_number
        cnes_part, seq_part = card_number.split("-")
        assert cnes_part == "2077485"
        assert len(seq_part) == 8  # Padded to 8 digits

    @pytest.mark.asyncio
    async def test_digital_card_urls(self, worker, tenant_austa):
        """Test that digital card and QR code URLs are generated."""
        result = await worker.execute(
            {
                "patient_id": "patient-222",
                "mrn": "2077485-000006",
                "patient_name": "Fernanda Lima",
                "facility_name": "Hospital AUSTA",
                "facility_cnes_code": "2077485",
            }
        )

        # URLs should be present
        assert result["card_url"] is not None
        assert result["qr_code_url"] is not None

        # URLs should contain card number
        card_number = result["card_data"]["card_number"]
        assert card_number in result["card_url"]
        assert card_number in result["qr_code_url"]

    @pytest.mark.asyncio
    async def test_card_data_issue_date(self, worker, tenant_austa):
        """Test that card data includes issue date."""
        from datetime import datetime

        result = await worker.execute(
            {
                "patient_id": "patient-333",
                "mrn": "2077485-000007",
                "patient_name": "Roberto Silva",
                "facility_name": "Hospital AUSTA",
                "facility_cnes_code": "2077485",
            }
        )

        # Issue date should be present
        assert "issue_date" in result["card_data"]

        # Should be a valid ISO datetime
        issue_date = result["card_data"]["issue_date"]
        datetime.fromisoformat(issue_date.replace("Z", "+00:00"))
