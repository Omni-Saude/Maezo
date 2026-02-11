from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from healthcare_platform.clinical_operations.workers.surgical.or_turnover_worker import (
    ClinicalOperationsException,
    ORTurnoverInput,
    ORTurnoverOutput,
    ORTurnoverWorker,
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
    return ORTurnoverWorker()


@pytest.fixture
def valid_task_variables() -> dict[str, Any]:
    return {
        "operating_room_id": "OR-01",
        "previous_surgery_id": "SRG-12344",
        "next_surgery_id": "SRG-12345",
        "turnover_type": "standard",
    }


@pytest.mark.unit
class TestORTurnoverWorker:
    @pytest.mark.asyncio
    async def test_execute_success(
        self, worker, tenant_ctx, valid_task_variables
    ):
        result = await worker.execute(valid_task_variables)

        # Validate output model
        assert isinstance(result, dict)
        output = ORTurnoverOutput(**result)
        assert output.operating_room_id == "OR-01"
        assert output.turnover_id is not None
        assert output.estimated_completion is not None
        assert output.status in ["cleaning", "ready", "delayed"]
        assert output.started_at is not None

    @pytest.mark.asyncio
    async def test_missing_required_field(
        self, worker, tenant_ctx, valid_task_variables
    ):
        del valid_task_variables["operating_room_id"]
        with pytest.raises(ClinicalOperationsException):
            await worker.execute(valid_task_variables)

    @pytest.mark.asyncio
    async def test_invalid_turnover_type(
        self, worker, tenant_ctx, valid_task_variables
    ):
        valid_task_variables["turnover_type"] = "invalid_type"
        with pytest.raises(ClinicalOperationsException):
            await worker.execute(valid_task_variables)

    def test_input_validation_direct(self):
        # Test Pydantic model directly
        valid_input = ORTurnoverInput(
            operating_room_id="OR-01",
            previous_surgery_id="SRG-12344",
            next_surgery_id="SRG-12345",
            turnover_type="standard",
        )
        assert valid_input.operating_room_id == "OR-01"
        assert valid_input.turnover_type == "standard"

        # Test invalid turnover type
        with pytest.raises(ValidationError):
            ORTurnoverInput(
                operating_room_id="OR-01",
                previous_surgery_id="SRG-12344",
                next_surgery_id="SRG-12345",
                turnover_type="invalid",
            )

    def test_output_model_structure(self):
        # Test output model
        output = ORTurnoverOutput(
            operating_room_id="OR-01",
            turnover_id="TURN-001",
            estimated_completion="2024-02-15T09:30:00Z",
            status="cleaning",
            started_at="2024-02-15T09:00:00Z",
        )
        assert output.operating_room_id == "OR-01"
        assert output.turnover_id == "TURN-001"
        assert output.status == "cleaning"
        assert output.estimated_completion is not None
        assert output.started_at is not None
