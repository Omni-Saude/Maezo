"""Tests for ClinicalReportingWorker."""
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
    """ClinicalReportingWorker fixture."""
    from healthcare_platform.clinical_operations.workers.clinical_reporting import ClinicalReportingWorker
    return ClinicalReportingWorker(fhir_client=fhir_client)


class TestClinicalReportingWorker:
    """Test cases for ClinicalReportingWorker."""

    @pytest.mark.asyncio
    async def test_happy_path_generate_report(self, worker, fhir_client, tenant_austa):
        """Test successful clinical report generation."""
        fhir_client.search.return_value = [
            {"resourceType": "Encounter", "id": "enc-1", "status": "finished"},
            {"resourceType": "Encounter", "id": "enc-2", "status": "finished"},
        ]

        result = await worker.execute({
            "report_type": "monthly-statistics",
            "period_start": "2025-01-01",
            "period_end": "2025-01-31",
            "department": "emergency",
        })

        assert result["status"] == "completed"
        assert result["report_type"] == "monthly-statistics"
        assert "total_encounters" in result
        fhir_client.search.assert_called()

    @pytest.mark.asyncio
    async def test_missing_report_type_raises(self, worker, tenant_austa):
        """Test that missing report_type raises DomainException."""
        with pytest.raises(DomainException, match="report_type is required"):
            await worker.execute({
                "period_start": "2025-01-01",
                "period_end": "2025-01-31",
            })

    @pytest.mark.asyncio
    async def test_patient_specific_report(self, worker, fhir_client, tenant_austa):
        """Test patient-specific clinical report."""
        fhir_client.search.return_value = [
            {"resourceType": "Observation", "id": "obs-1"},
            {"resourceType": "MedicationRequest", "id": "med-1"},
        ]

        result = await worker.execute({
            "report_type": "patient-summary",
            "patient_id": "patient-456",
            "include_medications": True,
            "include_vitals": True,
        })

        assert result["patient_id"] == "patient-456"
        assert "medications" in result
        assert "vital_signs" in result

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that no tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({
                "report_type": "monthly-statistics",
                "period_start": "2025-01-01",
            })
