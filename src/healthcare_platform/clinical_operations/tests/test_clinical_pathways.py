"""Tests for ClinicalPathwaysWorker."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.multi_tenant.context import TenantContext, set_current_tenant, clear_tenant


@pytest.fixture
def tenant_hospital_a():
    """Set up AUSTA tenant context."""
    ctx = TenantContext.from_tenant_code(TenantCode.HOSPITAL_A)
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def fhir_client():
    """Mock FHIR client fixture."""
    return AsyncMock()


@pytest.fixture
def worker(fhir_client):
    """ClinicalPathwaysWorker fixture."""
    from healthcare_platform.clinical_operations.workers.clinical_pathways import ClinicalPathwaysWorker
    return ClinicalPathwaysWorker(fhir_client=fhir_client)


class TestClinicalPathwaysWorker:
    """Test cases for ClinicalPathwaysWorker."""

    @pytest.mark.asyncio
    async def test_happy_path_activate_pathway(self, worker, fhir_client, tenant_hospital_a):
        """Test successful clinical pathway activation."""
        fhir_client.search.return_value = [
            {"resourceType": "PlanDefinition", "id": "pathway-stroke", "title": "Stroke Care Pathway"}
        ]
        fhir_client.create.return_value = {"resourceType": "CarePlan", "id": "cp-123", "status": "active"}

        result = await worker.execute({
            "patient_id": "patient-456",
            "encounter_id": "encounter-789",
            "pathway_code": "stroke-care",
            "onset_time": "2025-01-15T08:00:00Z",
        })

        assert result["status"] == "completed"
        assert result["pathway_activated"] == "stroke-care"
        assert result["care_plan_id"] == "cp-123"
        fhir_client.create.assert_called()

    @pytest.mark.asyncio
    async def test_missing_pathway_code_raises(self, worker, tenant_hospital_a):
        """Test that missing pathway_code raises DomainException."""
        with pytest.raises(DomainException, match="pathway_code is required"):
            await worker.execute({
                "patient_id": "patient-456",
                "encounter_id": "encounter-789",
            })

    @pytest.mark.asyncio
    async def test_pathway_milestone_tracking(self, worker, fhir_client, tenant_hospital_a):
        """Test tracking of pathway milestones."""
        fhir_client.search.return_value = [{"resourceType": "PlanDefinition", "id": "pathway-1"}]
        fhir_client.create.return_value = {"resourceType": "CarePlan", "id": "cp-123"}

        result = await worker.execute({
            "patient_id": "patient-456",
            "pathway_code": "stroke-care",
            "track_milestones": True,
        })

        assert "milestones" in result
        assert len(result["milestones"]) > 0

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that no tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({
                "patient_id": "patient-456",
                "pathway_code": "stroke-care",
            })
