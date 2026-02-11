from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from healthcare_platform.clinical_operations.workers.surgical.surgical_materials_worker import (
    ClinicalOperationsException,
    SurgicalMaterialsInput,
    SurgicalMaterialsOutput,
    SurgicalMaterialsWorker,
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
    return SurgicalMaterialsWorker()


@pytest.fixture
def valid_task_variables() -> dict[str, Any]:
    return {
        "surgery_id": "SRG-12345",
        "procedure_code": "40301052",
        "materials": [
            {"material_code": "MAT-001", "quantity": 2},
            {"material_code": "MAT-002", "quantity": 1},
        ],
        "priority": "routine",
    }


@pytest.mark.unit
class TestSurgicalMaterialsWorker:
    @pytest.mark.asyncio
    async def test_execute_success(
        self, worker, tenant_ctx, valid_task_variables
    ):
        result = await worker.execute(valid_task_variables)

        # Validate output model
        assert isinstance(result, dict)
        output = SurgicalMaterialsOutput(**result)
        assert output.surgery_id == "SRG-12345"
        assert output.request_id is not None
        assert len(output.materials_reserved) >= 2
        assert isinstance(output.all_available, bool)
        assert output.reserved_at is not None

    @pytest.mark.asyncio
    async def test_missing_required_field(
        self, worker, tenant_ctx, valid_task_variables
    ):
        del valid_task_variables["surgery_id"]
        with pytest.raises(ClinicalOperationsException):
            await worker.execute(valid_task_variables)

    @pytest.mark.asyncio
    async def test_empty_materials_list(
        self, worker, tenant_ctx, valid_task_variables
    ):
        valid_task_variables["materials"] = []
        with pytest.raises(ClinicalOperationsException):
            await worker.execute(valid_task_variables)

    def test_input_validation_direct(self):
        # Test Pydantic model directly
        valid_input = SurgicalMaterialsInput(
            surgery_id="SRG-12345",
            procedure_code="40301052",
            materials=[
                {"material_code": "MAT-001", "quantity": 2},
                {"material_code": "MAT-002", "quantity": 1},
            ],
            priority="routine",
        )
        assert valid_input.surgery_id == "SRG-12345"
        assert len(valid_input.materials) == 2
        assert valid_input.priority == "routine"

        # Test empty materials list
        with pytest.raises(ValidationError):
            SurgicalMaterialsInput(
                surgery_id="SRG-12345",
                procedure_code="40301052",
                materials=[],
                priority="routine",
            )

    def test_output_model_structure(self):
        # Test output model
        output = SurgicalMaterialsOutput(
            surgery_id="SRG-12345",
            request_id="REQ-001",
            materials_reserved=[
                {"material_code": "MAT-001", "quantity": 2, "available": True},
                {"material_code": "MAT-002", "quantity": 1, "available": True},
            ],
            all_available=True,
            reserved_at="2024-02-15T08:00:00Z",
        )
        assert output.surgery_id == "SRG-12345"
        assert output.request_id == "REQ-001"
        assert len(output.materials_reserved) == 2
        assert output.all_available is True
        assert output.reserved_at is not None
