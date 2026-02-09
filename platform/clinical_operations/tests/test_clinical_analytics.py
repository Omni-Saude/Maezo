"""Tests for ClinicalAnalyticsWorker."""
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
    """ClinicalAnalyticsWorker fixture."""
    from platform.clinical_operations.workers.clinical_analytics import ClinicalAnalyticsWorker
    return ClinicalAnalyticsWorker(fhir_client=fhir_client)


class TestClinicalAnalyticsWorker:
    """Test cases for ClinicalAnalyticsWorker."""

    @pytest.mark.asyncio
    async def test_happy_path_perform_analytics(self, worker, fhir_client, tenant_austa):
        """Test successful clinical analytics execution."""
        fhir_client.search.return_value = [
            {"resourceType": "Observation", "id": "obs-1", "valueQuantity": {"value": 120}},
            {"resourceType": "Observation", "id": "obs-2", "valueQuantity": {"value": 130}},
            {"resourceType": "Observation", "id": "obs-3", "valueQuantity": {"value": 125}},
        ]

        result = await worker.execute({
            "analytics_type": "trend-analysis",
            "metric": "blood-pressure-systolic",
            "patient_id": "patient-456",
            "period_days": 30,
        })

        assert result["status"] == "completed"
        assert "mean" in result
        assert "trend" in result
        assert result["data_points"] == 3
        fhir_client.search.assert_called()

    @pytest.mark.asyncio
    async def test_missing_analytics_type_raises(self, worker, tenant_austa):
        """Test that missing analytics_type raises DomainException."""
        with pytest.raises(DomainException, match="analytics_type is required"):
            await worker.execute({
                "metric": "blood-pressure",
                "period_days": 30,
            })

    @pytest.mark.asyncio
    async def test_predictive_analytics(self, worker, fhir_client, tenant_austa):
        """Test predictive analytics for clinical outcomes."""
        fhir_client.search.return_value = [
            {"resourceType": "Observation", "id": f"obs-{i}", "valueQuantity": {"value": 100 + i}}
            for i in range(10)
        ]

        result = await worker.execute({
            "analytics_type": "predictive",
            "patient_id": "patient-456",
            "outcome": "readmission-risk",
            "factors": ["age", "comorbidities", "previous-admissions"],
        })

        assert "risk_score" in result
        assert "confidence" in result
        assert result["outcome"] == "readmission-risk"

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that no tenant context raises InvalidTenant."""
        from platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({
                "analytics_type": "trend-analysis",
                "metric": "blood-pressure",
            })
