"""Tests for CareTeamCoordinationWorker."""
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
    """CareTeamCoordinationWorker fixture."""
    from platform.clinical_operations.workers.care_team_coordination import CareTeamCoordinationWorker
    return CareTeamCoordinationWorker(fhir_client=fhir_client)


class TestCareTeamCoordinationWorker:
    """Test cases for CareTeamCoordinationWorker."""

    @pytest.mark.asyncio
    async def test_happy_path_create_care_team(self, worker, fhir_client, tenant_austa):
        """Test successful care team creation."""
        fhir_client.create.return_value = {
            "resourceType": "CareTeam",
            "id": "careteam-123",
            "status": "active",
        }

        result = await worker.execute({
            "patient_id": "patient-456",
            "encounter_id": "encounter-789",
            "team_members": [
                {"practitioner_id": "prac-001", "role": "attending-physician"},
                {"practitioner_id": "prac-002", "role": "nurse"},
            ],
        })

        assert result["status"] == "completed"
        assert result["care_team_id"] == "careteam-123"
        assert len(result["team_members"]) == 2
        fhir_client.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_team_members_raises(self, worker, tenant_austa):
        """Test that missing team_members raises DomainException."""
        with pytest.raises(DomainException, match="team_members are required"):
            await worker.execute({
                "patient_id": "patient-456",
                "encounter_id": "encounter-789",
            })

    @pytest.mark.asyncio
    async def test_update_existing_care_team(self, worker, fhir_client, tenant_austa):
        """Test updating an existing care team."""
        fhir_client.search.return_value = [{"resourceType": "CareTeam", "id": "careteam-123"}]
        fhir_client.update.return_value = {"resourceType": "CareTeam", "id": "careteam-123", "status": "active"}

        result = await worker.execute({
            "patient_id": "patient-456",
            "care_team_id": "careteam-123",
            "team_members": [{"practitioner_id": "prac-003", "role": "specialist"}],
        })

        assert result["operation"] == "update"
        fhir_client.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that no tenant context raises InvalidTenant."""
        from platform.shared.domain.exceptions import InvalidTenant
        with pytest.raises(InvalidTenant):
            await worker.execute({
                "patient_id": "patient-456",
                "team_members": [{"practitioner_id": "prac-001"}],
            })
