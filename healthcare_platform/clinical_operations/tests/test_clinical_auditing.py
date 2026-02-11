"""Tests for ClinicalAuditingWorker."""
from __future__ import annotations

from datetime import datetime
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
    """ClinicalAuditingWorker fixture."""
    from healthcare_platform.clinical_operations.workers.clinical_auditing import ClinicalAuditingWorker
    return ClinicalAuditingWorker(fhir_client=fhir_client)


class TestClinicalAuditingWorker:
    """Test cases for ClinicalAuditingWorker."""

    @pytest.mark.asyncio
    async def test_happy_path_create_audit_trail(self, worker, fhir_client, tenant_hospital_a):
        """Test successful audit trail creation."""
        fhir_client.create.return_value = {
            "resourceType": "AuditEvent",
            "id": "audit-123",
            "recorded": "2025-01-15T10:00:00Z",
        }

        result = await worker.execute({
            "patient_id": "patient-456",
            "encounter_id": "encounter-789",
            "action": "access",
            "resource_type": "MedicationRequest",
            "resource_id": "medrq-001",
            "user_id": "practitioner-001",
        })

        assert result["status"] == "completed"
        assert result["audit_id"] == "audit-123"
        assert result["action"] == "access"
        fhir_client.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_action_raises(self, worker, tenant_hospital_a):
        """Test that missing action raises DomainException."""
        with pytest.raises(DomainException, match="action is required"):
            await worker.execute({
                "patient_id": "patient-456",
                "resource_type": "Patient",
            })

    @pytest.mark.asyncio
    async def test_audit_query_for_compliance(self, worker, fhir_client, tenant_hospital_a):
        """Test querying audit events for compliance reporting."""
        fhir_client.search.return_value = [
            {"resourceType": "AuditEvent", "id": "audit-1", "action": "access"},
            {"resourceType": "AuditEvent", "id": "audit-2", "action": "update"},
        ]

        result = await worker.execute({
            "query_type": "compliance-report",
            "patient_id": "patient-456",
            "period_start": "2025-01-01",
            "period_end": "2025-01-31",
        })

        assert result["total_events"] == 2
        assert "access_count" in result
        fhir_client.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that no tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({
                "action": "access",
                "resource_type": "Patient",
            })
