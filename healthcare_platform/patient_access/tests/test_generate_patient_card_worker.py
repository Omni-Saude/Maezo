"""Tests for GeneratePatientCardWorker."""
from __future__ import annotations
from datetime import datetime
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException


@pytest.fixture
def card_generator():
    """Mock card generator protocol."""
    return AsyncMock()


@pytest.fixture
def worker(fhir_client, card_generator):
    from healthcare_platform.patient_access.workers.generate_patient_card_worker import GeneratePatientCardWorker
    return GeneratePatientCardWorker(fhir_client=fhir_client, card_generator=card_generator)


class TestGeneratePatientCardWorker:
    @pytest.mark.asyncio
    async def test_happy_path_generates_card(self, worker, fhir_client, card_generator, tenant_austa, mock_patient):
        """Test successful patient card generation."""
        fhir_client.read.return_value = mock_patient
        card_generator.generate.return_value = {
            "card_id": "CARD-123",
            "pdf_url": "https://example.com/cards/CARD-123.pdf"
        }

        result = await worker.execute({
            "patient_id": "patient-123"
        })

        assert result["card_id"] == "CARD-123"
        assert result["pdf_url"] is not None
        card_generator.generate.assert_called_once()

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
    async def test_card_generation_failure_raises(self, worker, fhir_client, card_generator, tenant_austa, mock_patient):
        """Test that card generation failure raises DomainException."""
        fhir_client.read.return_value = mock_patient
        card_generator.generate.side_effect = Exception("PDF generation failed")

        with pytest.raises(DomainException):
            await worker.execute({
                "patient_id": "patient-123"
            })
