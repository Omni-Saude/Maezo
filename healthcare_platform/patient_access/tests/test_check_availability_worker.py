"""Tests for CheckAvailabilityWorker."""
from __future__ import annotations
from datetime import datetime
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException


@pytest.fixture
def worker(fhir_client):
    from healthcare_platform.patient_access.workers.check_availability_worker import CheckAvailabilityWorker
    return CheckAvailabilityWorker(fhir_client=fhir_client)


class TestCheckAvailabilityWorker:
    @pytest.mark.asyncio
    async def test_happy_path_checks_availability(self, worker, fhir_client, tenant_austa):
        """Test successful availability check."""
        fhir_client.search.return_value = {
            "entry": []  # No conflicting appointments
        }

        result = await worker.execute({
            "practitioner_id": "practitioner-001",
            "start_time": "2024-01-15T10:00:00Z",
            "end_time": "2024-01-15T10:30:00Z"
        })

        assert result["available"] is True
        fhir_client.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing practitioner_id raises DomainException."""
        with pytest.raises(DomainException):
            await worker.execute({})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({"practitioner_id": "practitioner-001"})

    @pytest.mark.asyncio
    async def test_conflicting_appointment_returns_false(self, worker, fhir_client, tenant_austa, mock_appointment):
        """Test that conflicting appointment returns available=False."""
        fhir_client.search.return_value = {
            "entry": [{"resource": mock_appointment}]
        }

        result = await worker.execute({
            "practitioner_id": "practitioner-001",
            "start_time": "2024-01-15T10:00:00Z",
            "end_time": "2024-01-15T10:30:00Z"
        })

        assert result["available"] is False
        assert result["conflicts"] is not None
