from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from healthcare_platform.clinical_operations.workers.surgical.surgery_scheduling_worker import (
    ClinicalOperationsException,
    SurgerySchedulingInput,
    SurgerySchedulingOutput,
    SurgerySchedulingWorker,
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
    return SurgerySchedulingWorker()


@pytest.fixture
def valid_task_variables() -> dict[str, Any]:
    return {
        "patient_id": "Patient/12345",
        "procedure_code": "40301052",
        "procedure_name": "Apendicectomia laparoscópica",
        "surgeon_id": "Practitioner/MED-001",
        "preferred_date": "2024-02-15",
        "preferred_time": "08:00",
        "estimated_duration_minutes": 120,
        "urgency_level": "elective",
    }


@pytest.mark.unit
class TestSurgerySchedulingWorker:
    @pytest.mark.asyncio
    async def test_execute_success(
        self, worker, tenant_ctx, valid_task_variables
    ):
        result = await worker.execute(valid_task_variables)

        # Validate output model
        assert isinstance(result, dict)
        output = SurgerySchedulingOutput(**result)
        assert output.surgery_id is not None
        assert output.scheduled_date == "2024-02-15"
        assert output.scheduled_time == "08:00"
        assert output.operating_room is not None
        assert output.status in ["scheduled", "confirmed", "pending"]
        assert output.created_at is not None

    @pytest.mark.asyncio
    async def test_missing_required_field(
        self, worker, tenant_ctx, valid_task_variables
    ):
        del valid_task_variables["patient_id"]
        with pytest.raises(ClinicalOperationsException):
            await worker.execute(valid_task_variables)

    @pytest.mark.asyncio
    async def test_invalid_urgency_level(
        self, worker, tenant_ctx, valid_task_variables
    ):
        valid_task_variables["urgency_level"] = "invalid_level"
        with pytest.raises(ClinicalOperationsException):
            await worker.execute(valid_task_variables)

    def test_input_validation_direct(self):
        # Test Pydantic model directly
        valid_input = SurgerySchedulingInput(
            patient_id="Patient/12345",
            procedure_code="40301052",
            procedure_name="Apendicectomia laparoscópica",
            surgeon_id="Practitioner/MED-001",
            preferred_date="2024-02-15",
            preferred_time="08:00",
            estimated_duration_minutes=120,
            urgency_level="elective",
        )
        assert valid_input.patient_id == "Patient/12345"
        assert valid_input.urgency_level == "elective"

        # Test invalid urgency level
        with pytest.raises(ValidationError):
            SurgerySchedulingInput(
                patient_id="Patient/12345",
                procedure_code="40301052",
                procedure_name="Test procedure",
                surgeon_id="Practitioner/MED-001",
                preferred_date="2024-02-15",
                preferred_time="08:00",
                estimated_duration_minutes=120,
                urgency_level="invalid",
            )

    def test_output_model_structure(self):
        # Test output model
        output = SurgerySchedulingOutput(
            surgery_id="SRG-12345",
            scheduled_date="2024-02-15",
            scheduled_time="08:00",
            operating_room="OR-01",
            status="scheduled",
            created_at="2024-02-15T08:00:00Z",
        )
        assert output.surgery_id == "SRG-12345"
        assert output.operating_room == "OR-01"
        assert output.status == "scheduled"
        assert output.created_at is not None
