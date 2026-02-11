from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from healthcare_platform.clinical_operations.workers.surgical.surgical_team_assignment_worker import (
    ClinicalOperationsException,
    SurgicalTeamAssignmentInput,
    SurgicalTeamAssignmentOutput,
    SurgicalTeamAssignmentWorker,
)
from healthcare_platform.shared.multi_tenant.context import (
    TenantContext,
    clear_tenant,
    set_current_tenant,
)


@pytest.fixture
def tenant_ctx():
    ctx = TenantContext.from_tenant_id("austa-hospital")
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def worker():
    return SurgicalTeamAssignmentWorker()


@pytest.fixture
def valid_task_variables() -> dict[str, Any]:
    return {
        "surgery_id": "SRG-12345",
        "surgeon_id": "Practitioner/MED-001",
        "team_members": [
            {"role": "surgeon", "practitioner_id": "MED-001"},
            {"role": "anesthesiologist", "practitioner_id": "MED-002"},
            {"role": "scrub_nurse", "practitioner_id": "NUR-001"},
        ],
        "surgery_date": "2024-02-15",
    }


@pytest.mark.unit
class TestSurgicalTeamAssignmentWorker:
    @pytest.mark.asyncio
    async def test_execute_success(
        self, worker, tenant_ctx, valid_task_variables
    ):
        result = await worker.execute(valid_task_variables)

        # Validate output model
        assert isinstance(result, dict)
        output = SurgicalTeamAssignmentOutput(**result)
        assert output.surgery_id == "SRG-12345"
        assert output.team_id is not None
        assert len(output.team_members_confirmed) >= 3
        assert output.assignment_status in ["complete", "partial", "failed"]
        assert output.assigned_at is not None

    @pytest.mark.asyncio
    async def test_missing_required_field(
        self, worker, tenant_ctx, valid_task_variables
    ):
        del valid_task_variables["surgery_id"]
        with pytest.raises(ClinicalOperationsException):
            await worker.execute(valid_task_variables)

    @pytest.mark.asyncio
    async def test_empty_team_members(
        self, worker, tenant_ctx, valid_task_variables
    ):
        valid_task_variables["team_members"] = []
        with pytest.raises(ClinicalOperationsException):
            await worker.execute(valid_task_variables)

    def test_input_validation_direct(self):
        # Test Pydantic model directly
        valid_input = SurgicalTeamAssignmentInput(
            surgery_id="SRG-12345",
            surgeon_id="Practitioner/MED-001",
            team_members=[
                {"role": "surgeon", "practitioner_id": "MED-001"},
                {"role": "anesthesiologist", "practitioner_id": "MED-002"},
            ],
            surgery_date="2024-02-15",
        )
        assert valid_input.surgery_id == "SRG-12345"
        assert len(valid_input.team_members) == 2

        # Test empty team members
        with pytest.raises(ValidationError):
            SurgicalTeamAssignmentInput(
                surgery_id="SRG-12345",
                surgeon_id="Practitioner/MED-001",
                team_members=[],
                surgery_date="2024-02-15",
            )

    def test_output_model_structure(self):
        # Test output model
        output = SurgicalTeamAssignmentOutput(
            surgery_id="SRG-12345",
            team_id="TEAM-001",
            team_members_confirmed=[
                {"role": "surgeon", "practitioner_id": "MED-001", "confirmed": True},
                {"role": "anesthesiologist", "practitioner_id": "MED-002", "confirmed": True},
            ],
            assignment_status="complete",
            assigned_at="2024-02-15T08:00:00Z",
        )
        assert output.surgery_id == "SRG-12345"
        assert output.team_id == "TEAM-001"
        assert len(output.team_members_confirmed) == 2
        assert output.assignment_status == "complete"
        assert output.assigned_at is not None
