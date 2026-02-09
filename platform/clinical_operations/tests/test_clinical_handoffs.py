"""Tests for ClinicalHandoffsWorker."""
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
    """ClinicalHandoffsWorker fixture."""
    from platform.clinical_operations.workers.clinical_handoffs import ClinicalHandoffsWorker
    return ClinicalHandoffsWorker(fhir_client=fhir_client)


class TestClinicalHandoffsWorker:
    """Test cases for ClinicalHandoffsWorker."""

    @pytest.mark.asyncio
    async def test_happy_path_create_handoff(self, worker, fhir_client, tenant_austa):
        """Test successful clinical handoff creation."""
        fhir_client.create.return_value = {
            "resourceType": "Communication",
            "id": "comm-123",
            "status": "completed",
        }

        result = await worker.execute({
            "patient_id": "patient-456",
            "encounter_id": "encounter-789",
            "from_practitioner": "prac-001",
            "to_practitioner": "prac-002",
            "handoff_type": "shift-change",
            "summary": "Patient stable, vitals WNL, continue current treatment plan",
        })

        assert result["status"] == "completed"
        assert result["communication_id"] == "comm-123"
        assert result["handoff_type"] == "shift-change"
        fhir_client.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_practitioners_raises(self, worker, tenant_austa):
        """Test that missing practitioners raises DomainException."""
        with pytest.raises(DomainException, match="from_practitioner and to_practitioner are required"):
            await worker.execute({
                "patient_id": "patient-456",
                "handoff_type": "shift-change",
            })

    @pytest.mark.asyncio
    async def test_sbar_format_validation(self, worker, fhir_client, tenant_austa):
        """Test SBAR format validation for handoffs."""
        fhir_client.create.return_value = {"resourceType": "Communication", "id": "comm-123", "status": "completed"}

        result = await worker.execute({
            "patient_id": "patient-456",
            "from_practitioner": "prac-001",
            "to_practitioner": "prac-002",
            "handoff_type": "shift-change",
            "sbar": {
                "situation": "Post-op day 1 after appendectomy",
                "background": "No complications",
                "assessment": "Stable, pain controlled",
                "recommendation": "Continue antibiotics, monitor vitals",
            },
        })

        assert result["format"] == "SBAR"
        assert result["validated"] is True

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that no tenant context raises InvalidTenant."""
        from platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({
                "patient_id": "patient-456",
                "from_practitioner": "prac-001",
                "to_practitioner": "prac-002",
            })
