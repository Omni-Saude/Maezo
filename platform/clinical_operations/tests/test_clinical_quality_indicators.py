"""Tests for ClinicalQualityIndicatorsWorker."""
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
    """ClinicalQualityIndicatorsWorker fixture."""
    from platform.clinical_operations.workers.clinical_quality_indicators import ClinicalQualityIndicatorsWorker
    return ClinicalQualityIndicatorsWorker(fhir_client=fhir_client)


class TestClinicalQualityIndicatorsWorker:
    """Test cases for ClinicalQualityIndicatorsWorker."""

    @pytest.mark.asyncio
    async def test_happy_path_calculate_quality_metrics(self, worker, fhir_client, tenant_austa):
        """Test successful quality indicator calculation."""
        fhir_client.search.return_value = [
            {"resourceType": "Observation", "id": "obs-1", "status": "final"},
            {"resourceType": "Observation", "id": "obs-2", "status": "final"},
        ]

        result = await worker.execute({
            "patient_id": "patient-456",
            "encounter_id": "encounter-789",
            "indicator_type": "sepsis-bundle-compliance",
            "period_start": "2025-01-01",
            "period_end": "2025-01-31",
        })

        assert result["status"] == "completed"
        assert "compliance_rate" in result
        assert "indicator_type" in result
        fhir_client.search.assert_called()

    @pytest.mark.asyncio
    async def test_missing_indicator_type_raises(self, worker, tenant_austa):
        """Test that missing indicator_type raises DomainException."""
        with pytest.raises(DomainException, match="indicator_type is required"):
            await worker.execute({
                "patient_id": "patient-456",
                "period_start": "2025-01-01",
            })

    @pytest.mark.asyncio
    async def test_multiple_indicators_calculated(self, worker, fhir_client, tenant_austa):
        """Test calculation of multiple quality indicators."""
        fhir_client.search.return_value = [{"resourceType": "Observation", "id": "obs-1"}]

        result = await worker.execute({
            "indicator_types": ["sepsis-bundle", "vte-prophylaxis", "handwashing-compliance"],
            "period_start": "2025-01-01",
            "period_end": "2025-01-31",
        })

        assert len(result["indicators"]) == 3
        assert all("compliance_rate" in ind for ind in result["indicators"])

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that no tenant context raises InvalidTenant."""
        from platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({
                "indicator_type": "sepsis-bundle-compliance",
                "period_start": "2025-01-01",
            })
