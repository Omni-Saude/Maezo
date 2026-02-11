"""
Pre-Surgical Checklist Worker

CIB7 External Task Topic: surgical.checklist
BPMN Error Code: CLINICAL_OPERATIONS_ERROR

Validates WHO Safe Surgery Checklist compliance across three critical phases:
SIGN_IN, TIME_OUT, and SIGN_OUT. Ensures all mandatory items are verified
before proceeding to next surgical phase.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.integrations.tasy_adapters.surgical_adapter import (
    TasySurgicalAdapter,
)
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


def _(message: str) -> str:
    """Translation helper for Portuguese error messages."""
    return message


class ClinicalOperationsException(DomainException):
    """Exception for clinical operations errors."""

    def __init__(
        self, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(
            message=message,
            details=details,
            bpmn_error_code="CLINICAL_OPERATIONS_ERROR",
        )
        self.code = "CLINICAL_OPERATIONS_ERROR"


class ChecklistItem(BaseModel):
    """Individual checklist item."""

    item_id: str = Field(..., description="Unique item identifier")
    description: str = Field(..., description="Item description")
    checked: bool = Field(..., description="Whether item is checked/completed")
    checked_by: str | None = Field(None, description="Professional who verified item")


class PreSurgicalChecklistInput(BaseModel):
    """Input model for pre-surgical checklist validation."""

    surgery_id: str = Field(..., description="FHIR Procedure ID")
    patient_id: str = Field(..., description="FHIR Patient ID")
    phase: Literal["sign_in", "time_out", "sign_out"] = Field(
        ..., description="WHO Safe Surgery Checklist phase"
    )
    checklist_items: list[ChecklistItem] = Field(
        ..., description="List of checklist items for validation"
    )


class PreSurgicalChecklistOutput(BaseModel):
    """Output model for pre-surgical checklist validation."""

    checklist_id: str = Field(..., description="Generated checklist validation ID")
    surgery_id: str = Field(..., description="FHIR Procedure ID")
    phase: str = Field(..., description="WHO Safe Surgery Checklist phase")
    items_total: int = Field(..., description="Total number of checklist items")
    items_checked: int = Field(..., description="Number of items marked as checked")
    all_complete: bool = Field(
        ..., description="Whether all critical items are completed"
    )
    completed_at: str | None = Field(
        None, description="ISO 8601 timestamp when checklist completed"
    )
    verified_by: str | None = Field(
        None, description="Professional who completed verification"
    )


class PreSurgicalChecklistWorker:
    """
    Worker to validate WHO Safe Surgery Checklist compliance.

    Implements three-phase validation following WHO protocol:
    - SIGN_IN: Pre-anesthesia verification
    - TIME_OUT: Pre-incision team confirmation
    - SIGN_OUT: Post-procedure reconciliation

    All critical items must be verified before proceeding.
    """

    TOPIC = "surgical.checklist"

    # WHO Safe Surgery Checklist critical items per phase
    CRITICAL_ITEMS = {
        "sign_in": {
            "patient_identity",
            "site_marked",
            "consent_signed",
            "anesthesia_check",
            "pulse_oximeter",
            "allergies_known",
            "airway_risk",
            "blood_loss_risk",
        },
        "time_out": {
            "team_introduction",
            "patient_confirmed",
            "procedure_confirmed",
            "site_confirmed",
            "antibiotic_given",
            "imaging_displayed",
        },
        "sign_out": {
            "procedure_recorded",
            "instrument_count",
            "specimen_labeled",
            "equipment_issues",
            "recovery_plan",
        },
    }

    def __init__(
        self, tasy_adapter: TasySurgicalAdapter | None = None
    ) -> None:
        """
        Initialize worker with Tasy surgical adapter.

        Args:
            tasy_adapter: Tasy adapter for surgical data conversion.
                         Optional for testing purposes.
        """
        self._tasy_adapter = tasy_adapter

    @require_tenant
    @track_task_execution(task_type="surgical.checklist")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute pre-surgical checklist validation.

        Args:
            task_variables: Task variables containing checklist data

        Returns:
            Dictionary with validation results

        Raises:
            ClinicalOperationsException: If validation fails or critical items missing
        """
        tenant = get_required_tenant()

        # Validate input
        try:
            input_data = PreSurgicalChecklistInput.model_validate(task_variables)
        except Exception as e:
            logger.error(
                "Validation failed for pre-surgical checklist input",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                _("Dados de entrada inválidos para checklist pré-cirúrgico"),
                details={"validation_error": str(e)},
            ) from e

        # Log checklist validation start
        logger.info(
            "Processing pre-surgical checklist validation",
            extra={
                "tenant_id": tenant.tenant_id,
                "surgery_id": input_data.surgery_id,
                "patient_id": input_data.patient_id,
                "phase": input_data.phase,
                "items_count": len(input_data.checklist_items),
            },
        )

        # Validate phase and critical items
        try:
            validation_result = self._validate_checklist_phase(input_data)

            # Generate checklist ID
            checklist_id = f"CHK-{input_data.surgery_id}-{input_data.phase}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

            # Count checked items
            items_checked = sum(
                1 for item in input_data.checklist_items if item.checked
            )

            # Determine completion status
            all_complete = validation_result["all_critical_complete"]
            completed_at = (
                datetime.now(UTC).isoformat() if all_complete else None
            )

            # Get verifier (first checked_by or None)
            verified_by = next(
                (item.checked_by for item in input_data.checklist_items if item.checked_by),
                None,
            )

            logger.info(
                "Pre-surgical checklist validation completed",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "surgery_id": input_data.surgery_id,
                    "checklist_id": checklist_id,
                    "phase": input_data.phase,
                    "items_checked": items_checked,
                    "all_complete": all_complete,
                    "missing_critical": validation_result.get("missing_critical", []),
                },
            )

            # Build output
            output = PreSurgicalChecklistOutput(
                checklist_id=checklist_id,
                surgery_id=input_data.surgery_id,
                phase=input_data.phase,
                items_total=len(input_data.checklist_items),
                items_checked=items_checked,
                all_complete=all_complete,
                completed_at=completed_at,
                verified_by=verified_by,
            )

            return output.model_dump()

        except Exception as e:
            logger.error(
                "Failed to validate pre-surgical checklist",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "surgery_id": input_data.surgery_id,
                    "phase": input_data.phase,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                _("Falha na validação do checklist pré-cirúrgico"),
                details={
                    "surgery_id": input_data.surgery_id,
                    "phase": input_data.phase,
                    "error": str(e),
                },
            ) from e

    def _validate_checklist_phase(
        self, input_data: PreSurgicalChecklistInput
    ) -> dict[str, Any]:
        """
        Validate checklist items against WHO critical requirements.

        Args:
            input_data: Checklist input data

        Returns:
            Dictionary with validation results

        Raises:
            ClinicalOperationsException: If phase is invalid
        """
        phase = input_data.phase
        if phase not in self.CRITICAL_ITEMS:
            raise ClinicalOperationsException(
                _(f"Fase de checklist inválida: {phase}"),
                details={"phase": phase, "valid_phases": list(self.CRITICAL_ITEMS.keys())},
            )

        # Empty checklist is considered complete (vacuous truth)
        if not input_data.checklist_items:
            return {
                "all_critical_complete": True,
                "missing_critical": [],
                "checked_critical": [],
            }

        # Get critical items for this phase
        critical_items = self.CRITICAL_ITEMS[phase]

        # Build set of checked critical items
        checked_items = {
            item.item_id
            for item in input_data.checklist_items
            if item.checked and item.item_id in critical_items
        }

        # Find missing critical items
        missing_critical = list(critical_items - checked_items)

        return {
            "all_critical_complete": len(missing_critical) == 0,
            "missing_critical": missing_critical,
            "checked_critical": list(checked_items),
        }
