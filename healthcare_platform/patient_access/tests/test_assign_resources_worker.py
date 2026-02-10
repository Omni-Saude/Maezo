"""Tests for AssignResourcesWorker."""
from __future__ import annotations
from datetime import datetime
import pytest
from unittest.mock import AsyncMock
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException


@pytest.fixture
def worker(fhir_client):
    from healthcare_platform.patient_access.workers.assign_resources_worker import AssignResourcesWorker
    return AssignResourcesWorker(fhir_client=fhir_client)


class TestAssignResourcesWorker:
    @pytest.mark.asyncio
    async def test_happy_path_assigns_resources(self, worker, fhir_client, tenant_austa, mock_appointment):
        """Test successful resource assignment."""
        fhir_client.read.return_value = mock_appointment
        fhir_client.search.return_value = {
            "entry": [
                {"resource": {"resourceType": "Location", "id": "room-001"}},
                {"resource": {"resourceType": "Device", "id": "equipment-001"}}
            ]
        }
        fhir_client.update.return_value = mock_appointment

        result = await worker.execute({
            "appointment_id": "appointment-789",
            "required_resources": ["examination_room", "ultrasound_device"]
        })

        assert result["resources_assigned"] is True
        assert len(result["assigned_resources"]) == 2
        fhir_client.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing appointment_id raises DomainException."""
        with pytest.raises(DomainException):
            await worker.execute({})

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({"appointment_id": "appointment-789"})

    @pytest.mark.asyncio
    async def test_insufficient_resources_raises(self, worker, fhir_client, tenant_austa, mock_appointment):
        """Test that insufficient resources raises DomainException."""
        fhir_client.read.return_value = mock_appointment
        fhir_client.search.return_value = {"entry": []}

        with pytest.raises(DomainException):
            await worker.execute({
                "appointment_id": "appointment-789",
                "required_resources": ["examination_room", "ultrasound_device"]
            })
