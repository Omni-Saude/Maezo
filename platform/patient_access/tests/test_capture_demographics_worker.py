"""Tests for CaptureDemographicsWorker."""
from __future__ import annotations
from datetime import datetime
import pytest
from unittest.mock import AsyncMock
from platform.shared.domain.enums import TenantCode
from platform.shared.domain.exceptions import DomainException


@pytest.fixture
def worker(fhir_client):
    from platform.patient_access.workers.capture_demographics_worker import CaptureDemographicsWorker
    return CaptureDemographicsWorker(fhir_client=fhir_client)


class TestCaptureDemographicsWorker:
    @pytest.mark.asyncio
    async def test_happy_path_captures_demographics(self, worker, fhir_client, tenant_austa, mock_patient):
        """Test successful demographics capture."""
        fhir_client.update.return_value = mock_patient

        result = await worker.execute({
            "patient_id": "patient-123",
            "demographics": {
                "race": "white",
                "ethnicity": "not-hispanic",
                "preferred_language": "pt-BR"
            }
        })

        assert result["patient_id"] == "patient-123"
        assert result["status"] == "updated"
        fhir_client.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing patient_id raises DomainException."""
        with pytest.raises(DomainException):
            await worker.execute({})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        from platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({"patient_id": "patient-123"})

    @pytest.mark.asyncio
    async def test_invalid_race_code_raises(self, worker, tenant_austa):
        """Test that invalid race code raises DomainException."""
        with pytest.raises(DomainException):
            await worker.execute({
                "patient_id": "patient-123",
                "demographics": {
                    "race": "invalid-race-code"
                }
            })
