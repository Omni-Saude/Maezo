"""Unit tests for PreSurgicalChecklistWorker."""
from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from healthcare_platform.clinical_operations.workers.surgical.pre_surgical_checklist_worker import (
    ClinicalOperationsException,
    PreSurgicalChecklistInput,
    PreSurgicalChecklistOutput,
    PreSurgicalChecklistWorker,
)
from healthcare_platform.shared.multi_tenant.context import (
    TenantContext,
    clear_tenant,
    set_current_tenant,
)


@pytest.fixture
def tenant_ctx():
    """Set up tenant context for tests."""
    ctx = TenantContext.from_tenant_id("austa-hospital")
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def worker():
    """Create worker instance."""
    return PreSurgicalChecklistWorker()


@pytest.fixture
def valid_task_variables() -> dict[str, Any]:
    """Valid task variables for testing."""
    return {
        "surgery_id": "SRG-12345",
        "patient_id": "Patient/12345",
        "phase": "sign_in",
        "checklist_items": [
            {
                "item_id": "patient_identity",
                "description": "Identidade do paciente confirmada",
                "checked": True,
                "checked_by": "NUR-001",
            },
            {
                "item_id": "site_marked",
                "description": "Sítio cirúrgico marcado",
                "checked": True,
                "checked_by": "MED-001",
            },
            {
                "item_id": "consent_signed",
                "description": "Consentimento assinado",
                "checked": True,
                "checked_by": "NUR-001",
            },
            {
                "item_id": "anesthesia_check",
                "description": "Verificação anestésica",
                "checked": True,
                "checked_by": "MED-002",
            },
            {
                "item_id": "pulse_oximeter",
                "description": "Oxímetro funcionando",
                "checked": True,
                "checked_by": "NUR-001",
            },
            {
                "item_id": "allergies_known",
                "description": "Alergias conhecidas",
                "checked": True,
                "checked_by": "MED-001",
            },
            {
                "item_id": "airway_risk",
                "description": "Risco de via aérea avaliado",
                "checked": True,
                "checked_by": "MED-002",
            },
            {
                "item_id": "blood_loss_risk",
                "description": "Risco de perda sanguínea avaliado",
                "checked": True,
                "checked_by": "MED-001",
            },
        ],
    }


@pytest.mark.unit
class TestPreSurgicalChecklistWorker:
    """Test suite for PreSurgicalChecklistWorker."""

    @pytest.mark.asyncio
    async def test_execute_success_sign_in_phase(
        self, worker, tenant_ctx, valid_task_variables
    ):
        """Test successful execution for SIGN_IN phase with all items checked."""
        result = await worker.execute(valid_task_variables)

        assert result is not None
        assert result["surgery_id"] == "SRG-12345"
        assert result["phase"] == "sign_in"
        assert result["items_total"] == 8
        assert result["items_checked"] == 8
        assert result["all_complete"] is True
        assert result["completed_at"] is not None
        assert result["verified_by"] is not None
        assert result["checklist_id"] is not None

    @pytest.mark.asyncio
    async def test_execute_success_time_out_phase(
        self, worker, tenant_ctx, valid_task_variables
    ):
        """Test successful execution for TIME_OUT phase."""
        valid_task_variables["phase"] = "time_out"
        valid_task_variables["checklist_items"] = [
            {
                "item_id": "team_introduction",
                "description": "Apresentação da equipe",
                "checked": True,
                "checked_by": "NUR-001",
            },
            {
                "item_id": "patient_confirmed",
                "description": "Paciente confirmado",
                "checked": True,
                "checked_by": "MED-001",
            },
            {
                "item_id": "procedure_confirmed",
                "description": "Procedimento confirmado",
                "checked": True,
                "checked_by": "MED-001",
            },
            {
                "item_id": "site_confirmed",
                "description": "Sítio confirmado",
                "checked": True,
                "checked_by": "MED-001",
            },
            {
                "item_id": "antibiotic_given",
                "description": "Antibiótico administrado",
                "checked": True,
                "checked_by": "NUR-001",
            },
            {
                "item_id": "imaging_displayed",
                "description": "Imagens essenciais exibidas",
                "checked": True,
                "checked_by": "MED-001",
            },
        ]

        result = await worker.execute(valid_task_variables)

        assert result is not None
        assert result["phase"] == "time_out"
        assert result["all_complete"] is True
        assert result["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_incomplete_checklist(self, worker, tenant_ctx, valid_task_variables):
        """Test checklist with unchecked items."""
        valid_task_variables["checklist_items"][0]["checked"] = False
        valid_task_variables["checklist_items"][3]["checked"] = False

        result = await worker.execute(valid_task_variables)

        assert result is not None
        assert result["all_complete"] is False
        assert result["items_checked"] == 6  # 8 total - 2 unchecked
        assert result["completed_at"] is None

    @pytest.mark.asyncio
    async def test_missing_surgery_id(self, worker, tenant_ctx, valid_task_variables):
        """Test validation error when surgery_id is missing."""
        del valid_task_variables["surgery_id"]

        with pytest.raises(ClinicalOperationsException):
            await worker.execute(valid_task_variables)

    @pytest.mark.asyncio
    async def test_invalid_phase_value(self, worker, tenant_ctx, valid_task_variables):
        """Test validation error with invalid phase value."""
        valid_task_variables["phase"] = "invalid_phase"

        with pytest.raises(ClinicalOperationsException):
            await worker.execute(valid_task_variables)

    @pytest.mark.asyncio
    async def test_output_fields(self, worker, tenant_ctx, valid_task_variables):
        """Test all expected output fields are present."""
        result = await worker.execute(valid_task_variables)

        expected_fields = [
            "checklist_id",
            "surgery_id",
            "phase",
            "items_total",
            "items_checked",
            "all_complete",
            "completed_at",
            "verified_by",
        ]

        for field in expected_fields:
            assert field in result

    @pytest.mark.asyncio
    async def test_who_checklist_item_validation(
        self, worker, tenant_ctx, valid_task_variables
    ):
        """Test WHO checklist item structure validation."""
        # Add item with missing required field
        valid_task_variables["checklist_items"].append(
            {
                "item_id": "test_item",
                "description": "Test description",
                # Missing "checked" field
                "checked_by": "NUR-001",
            }
        )

        with pytest.raises(ClinicalOperationsException):
            await worker.execute(valid_task_variables)

    @pytest.mark.asyncio
    async def test_empty_checklist_items(self, worker, tenant_ctx, valid_task_variables):
        """Test with empty checklist items list."""
        valid_task_variables["checklist_items"] = []

        result = await worker.execute(valid_task_variables)

        assert result is not None
        assert result["all_complete"] is True
        assert result["items_total"] == 0
        assert result["items_checked"] == 0
        assert result["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_sign_out_phase(self, worker, tenant_ctx, valid_task_variables):
        """Test successful execution for SIGN_OUT phase."""
        valid_task_variables["phase"] = "sign_out"
        valid_task_variables["checklist_items"] = [
            {
                "item_id": "procedure_recorded",
                "description": "Procedimento registrado",
                "checked": True,
                "checked_by": "NUR-001",
            },
            {
                "item_id": "instrument_count",
                "description": "Contagem de instrumentos correta",
                "checked": True,
                "checked_by": "NUR-001",
            },
            {
                "item_id": "specimen_labeled",
                "description": "Espécime etiquetado",
                "checked": True,
                "checked_by": "NUR-001",
            },
            {
                "item_id": "equipment_issues",
                "description": "Problemas com equipamentos abordados",
                "checked": True,
                "checked_by": "NUR-001",
            },
            {
                "item_id": "recovery_plan",
                "description": "Plano de recuperação discutido",
                "checked": True,
                "checked_by": "MED-001",
            },
        ]

        result = await worker.execute(valid_task_variables)

        assert result is not None
        assert result["phase"] == "sign_out"
        assert result["all_complete"] is True
        assert result["completed_at"] is not None
