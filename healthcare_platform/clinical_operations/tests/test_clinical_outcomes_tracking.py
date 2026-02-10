"""Tests for ClinicalOutcomesTrackingWorker."""
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
    """ClinicalOutcomesTrackingWorker fixture."""
    from healthcare_platform.clinical_operations.workers.clinical_outcomes_tracking import ClinicalOutcomesTrackingWorker
    return ClinicalOutcomesTrackingWorker(fhir_client=fhir_client)


class TestClinicalOutcomesTrackingWorker:
    """Test cases for ClinicalOutcomesTrackingWorker."""

    @pytest.mark.asyncio
    async def test_happy_path_track_outcome(self, worker, fhir_client, tenant_austa):
        """Test successful clinical outcome tracking."""
        fhir_client.create.return_value = {
            "resourceType": "Observation",
            "id": "outcome-123",
            "status": "final",
        }

        result = await worker.execute({
            "patient_id": "patient-456",
            "encounter_id": "encounter-789",
            "outcome_type": "patient-reported-outcome",
            "measure": "pain-scale",
            "value": 3,
            "scale": "0-10",
        })

        assert result["status"] == "completed"
        assert result["outcome_id"] == "outcome-123"
        assert result["value"] == 3
        fhir_client.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_outcome_type_raises(self, worker, tenant_austa):
        """Test that missing outcome_type raises DomainException."""
        with pytest.raises(DomainException, match="outcome_type is required"):
            await worker.execute({
                "patient_id": "patient-456",
                "value": 5,
            })

    @pytest.mark.asyncio
    async def test_trend_analysis(self, worker, fhir_client, tenant_austa):
        """Test outcome trend analysis over time."""
        fhir_client.search.return_value = [
            {"resourceType": "Observation", "id": "out-1", "valueInteger": 7},
            {"resourceType": "Observation", "id": "out-2", "valueInteger": 5},
            {"resourceType": "Observation", "id": "out-3", "valueInteger": 3},
        ]

        result = await worker.execute({
            "patient_id": "patient-456",
            "analysis_type": "trend",
            "outcome_type": "pain-scale",
            "period_days": 7,
        })

        assert result["trend"] == "improving"
        assert result["data_points"] == 3

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that no tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({
                "patient_id": "patient-456",
                "outcome_type": "pain-scale",
            })
