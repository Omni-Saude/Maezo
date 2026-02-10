"""Tests for ClinicalProtocolsWorker."""
from __future__ import annotations

from datetime import datetime
import pytest
from unittest.mock import AsyncMock

from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.multi_tenant.context import TenantContext, set_current_tenant, clear_tenant


@pytest.fixture
def tenant_austa():
    """Set up AUSTA tenant context."""
    ctx = TenantContext.from_tenant_code(TenantCode.AUSTA)
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def fhir_client():
    """Mock FHIR client fixture."""
    return AsyncMock()


@pytest.fixture
def worker(fhir_client):
    """ClinicalProtocolsWorker fixture."""
    from healthcare_platform.clinical_operations.workers.clinical_protocols import ClinicalProtocolsWorker
    return ClinicalProtocolsWorker(fhir_client=fhir_client)


class TestClinicalProtocolsWorker:
    """Test cases for ClinicalProtocolsWorker."""

    @pytest.mark.asyncio
    async def test_happy_path_apply_protocol(self, worker, fhir_client, tenant_austa):
        """Test successful protocol application."""
        fhir_client.search.return_value = [
            {"resourceType": "PlanDefinition", "id": "protocol-sepsis", "title": "Sepsis Protocol"}
        ]
        fhir_client.create.return_value = {
            "resourceType": "Task",
            "id": "task-123",
            "status": "requested",
        }

        result = await worker.execute({
            "patient_id": "patient-456",
            "encounter_id": "encounter-789",
            "protocol_code": "sepsis-bundle",
            "severity": "severe",
        })

        assert result["status"] == "completed"
        assert result["protocol_applied"] == "sepsis-bundle"
        assert "tasks_created" in result
        fhir_client.create.assert_called()

    @pytest.mark.asyncio
    async def test_missing_protocol_code_raises(self, worker, tenant_austa):
        """Test that missing protocol_code raises DomainException."""
        with pytest.raises(DomainException, match="protocol_code is required"):
            await worker.execute({
                "patient_id": "patient-456",
                "encounter_id": "encounter-789",
            })

    @pytest.mark.asyncio
    async def test_protocol_not_found_raises(self, worker, fhir_client, tenant_austa):
        """Test that non-existent protocol raises DomainException."""
        fhir_client.search.return_value = []

        with pytest.raises(DomainException, match="Protocol not found"):
            await worker.execute({
                "patient_id": "patient-456",
                "encounter_id": "encounter-789",
                "protocol_code": "nonexistent",
            })

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that no tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({
                "patient_id": "patient-456",
                "protocol_code": "sepsis-bundle",
            })
