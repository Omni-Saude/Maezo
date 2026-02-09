"""Tests for ClinicalComplianceWorker."""
from __future__ import annotations

from datetime import datetime
import pytest
from unittest.mock import AsyncMock

from platform.shared.domain.enums import TenantCode
from platform.shared.domain.exceptions import DomainException
from platform.shared.multi_tenant.context import TenantContext, set_current_tenant, clear_tenant


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
    """ClinicalComplianceWorker fixture."""
    from platform.clinical_operations.workers.clinical_compliance import ClinicalComplianceWorker
    return ClinicalComplianceWorker(fhir_client=fhir_client)


class TestClinicalComplianceWorker:
    """Test cases for ClinicalComplianceWorker."""

    @pytest.mark.asyncio
    async def test_happy_path_check_compliance(self, worker, fhir_client, tenant_austa):
        """Test successful compliance check."""
        fhir_client.search.return_value = [
            {"resourceType": "Observation", "id": "obs-1", "status": "final"},
            {"resourceType": "Procedure", "id": "proc-1", "status": "completed"},
        ]

        result = await worker.execute({
            "patient_id": "patient-456",
            "encounter_id": "encounter-789",
            "compliance_type": "sepsis-bundle",
            "timeframe_hours": 6,
        })

        assert result["status"] == "completed"
        assert "compliance_rate" in result
        assert result["compliance_type"] == "sepsis-bundle"
        fhir_client.search.assert_called()

    @pytest.mark.asyncio
    async def test_missing_compliance_type_raises(self, worker, tenant_austa):
        """Test that missing compliance_type raises DomainException."""
        with pytest.raises(DomainException, match="compliance_type is required"):
            await worker.execute({
                "patient_id": "patient-456",
                "timeframe_hours": 6,
            })

    @pytest.mark.asyncio
    async def test_non_compliant_triggers_alert(self, worker, fhir_client, tenant_austa):
        """Test that non-compliance triggers alerts."""
        fhir_client.search.return_value = []

        result = await worker.execute({
            "patient_id": "patient-456",
            "compliance_type": "vte-prophylaxis",
            "timeframe_hours": 24,
        })

        assert result["compliant"] is False
        assert result["alert_triggered"] is True
        assert "missing_elements" in result

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that no tenant context raises InvalidTenant."""
        from platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({
                "patient_id": "patient-456",
                "compliance_type": "sepsis-bundle",
            })
