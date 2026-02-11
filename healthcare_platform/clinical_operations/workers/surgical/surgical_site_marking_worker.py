"""
Surgical Site Marking Worker - WHO surgical site marking verification.

CIB7 External Task Topic: surgical.site_marking
BPMN Error Code: SURGICAL_OPERATIONS_ERROR

Verifies surgical site marking per WHO Safe Surgery Checklist Sign In phase.
Requires laterality verification (left/right) and photo confirmation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.tasy_adapters.surgical_adapter import TasySurgicalAdapter
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__, worker="surgical.site_marking")


class SurgicalOperationsException(DomainException):
    """Exception for surgical operations errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "SURGICAL_OPERATIONS_ERROR",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """Initialize surgical operations exception.

        Args:
            message: Error message
            error_code: BPMN error code
            details: Additional error details
        """
        super().__init__(message, details)
        self.bpmn_error_code = error_code


class SurgicalSiteMarkingInput(BaseModel):
    """Input for surgical site marking verification."""

    surgery_id: str = Field(..., description="Unique surgery identifier")
    patient_id: str = Field(..., description="Patient identifier")
    procedure_code: str = Field(..., description="Procedure code (e.g., TUSS)")
    procedure_description: str = Field(..., description="Human-readable procedure name")
    surgical_site: str = Field(..., description="Anatomical site of surgery")
    laterality: str = Field(
        ...,
        description="Laterality: left, right, bilateral, or not_applicable"
    )
    marking_practitioner_id: str = Field(
        ...,
        description="ID of practitioner who performed marking"
    )
    photo_reference: Optional[str] = Field(
        None,
        description="Reference to photo documentation of marking"
    )
    marking_confirmed: bool = Field(
        ...,
        description="Marking practitioner confirmed correct site"
    )
    patient_confirmed: bool = Field(
        ...,
        description="Patient confirmed correct site and procedure"
    )
    who_checklist_phase: str = Field(
        default="sign_in",
        description="WHO Safe Surgery Checklist phase (sign_in/time_out/sign_out)"
    )

    @field_validator("laterality")
    @classmethod
    def validate_laterality(cls, v: str) -> str:
        """Validate laterality value.

        Args:
            v: Laterality value

        Returns:
            Validated laterality value

        Raises:
            ValueError: If laterality is not valid
        """
        valid_lateralities = {"left", "right", "bilateral", "not_applicable"}
        if v not in valid_lateralities:
            raise ValueError(
                f"Laterality must be one of {valid_lateralities}, got: {v}"
            )
        return v

    @field_validator("photo_reference")
    @classmethod
    def validate_photo_for_lateral_procedures(
        cls, v: Optional[str], info
    ) -> Optional[str]:
        """Validate photo is provided for lateral procedures.

        Args:
            v: Photo reference value
            info: Validation info containing other fields

        Returns:
            Validated photo reference

        Raises:
            ValueError: If photo required but not provided
        """
        if "laterality" in info.data:
            laterality = info.data["laterality"]
            if laterality in {"left", "right", "bilateral"} and not v:
                raise ValueError(
                    f"Photo documentation required for laterality '{laterality}'"
                )
        return v


class SurgicalSiteMarkingOutput(BaseModel):
    """Output from surgical site marking verification."""

    verification_id: str = Field(..., description="Unique verification identifier")
    surgery_id: str = Field(..., description="Surgery identifier")
    site_verified: bool = Field(
        ...,
        description="Overall site verification status"
    )
    laterality_verified: bool = Field(
        ...,
        description="Laterality verification status"
    )
    photo_confirmed: bool = Field(
        ...,
        description="Photo documentation confirmed"
    )
    patient_identity_confirmed: bool = Field(
        ...,
        description="Patient identity confirmed"
    )
    who_phase_completed: str = Field(
        ...,
        description="WHO checklist phase completed"
    )
    verification_timestamp: str = Field(
        ...,
        description="ISO 8601 timestamp of verification"
    )
    discrepancies: List[str] = Field(
        default_factory=list,
        description="List of any discrepancies found"
    )


class SurgicalSiteMarkingWorker:
    """Worker for surgical site marking verification per WHO Safe Surgery Checklist."""

    def __init__(
        self,
        tasy_adapter: Optional[TasySurgicalAdapter] = None,
    ) -> None:
        """Initialize surgical site marking worker.

        Args:
            tasy_adapter: TASY surgical adapter (defaults to new instance)
        """
        self.tasy_adapter = tasy_adapter or TasySurgicalAdapter()
        self.logger = logger

    @require_tenant
    @track_task_execution(task_type="surgical.site_marking")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Execute surgical site marking verification.

        Verifies surgical site marking according to WHO Safe Surgery Checklist
        requirements. Checks:
        - Site marking confirmation by practitioner
        - Patient confirmation of site and procedure
        - Laterality verification (left/right/bilateral)
        - Photo documentation for lateral procedures
        - Patient identity confirmation

        Args:
            task_variables: Task variables from CIB7 external task

        Returns:
            dict containing SurgicalSiteMarkingOutput

        Raises:
            SurgicalOperationsException: If validation fails or critical error occurs
        """
        tenant = get_required_tenant()

        try:
            # Parse and validate input
            input_data = SurgicalSiteMarkingInput.model_validate(task_variables)

            self.logger.info(
                "Starting surgical site marking verification",
                extra={
                    "surgery_id": input_data.surgery_id,
                    "tenant_id": tenant.tenant_id,
                    "procedure_code": input_data.procedure_code,
                    "laterality": input_data.laterality,
                    "who_phase": input_data.who_checklist_phase,
                },
            )

            # Verify surgical site marking
            verification_result = await self._verify_site_marking(input_data, tenant)

            self.logger.info(
                "Surgical site marking verification completed",
                extra={
                    "surgery_id": input_data.surgery_id,
                    "site_verified": verification_result.site_verified,
                    "discrepancies_count": len(verification_result.discrepancies),
                    "verification_id": verification_result.verification_id,
                },
            )

            return verification_result.model_dump()

        except ValueError as e:
            self.logger.error(
                "Validation error in surgical site marking",
                extra={
                    "error": str(e),
                    "tenant_id": tenant.tenant_id,
                },
            )
            raise SurgicalOperationsException(
                message=_("Validation error: {error}").format(error=str(e)),
                error_code="SURGICAL_OPERATIONS_ERROR",
                details={"validation_error": str(e)},
            ) from e

        except Exception as e:
            self.logger.error(
                "Unexpected error in surgical site marking",
                extra={
                    "error": str(e),
                    "tenant_id": tenant.tenant_id,
                },
            )
            raise SurgicalOperationsException(
                message=_("Surgical site marking verification failed: {error}").format(
                    error=str(e)
                ),
                error_code="SURGICAL_OPERATIONS_ERROR",
                details={"error": str(e)},
            ) from e

    async def _verify_site_marking(
        self,
        input_data: SurgicalSiteMarkingInput,
        tenant,
    ) -> SurgicalSiteMarkingOutput:
        """Verify surgical site marking.

        Args:
            input_data: Validated input data
            tenant: Tenant context

        Returns:
            Verification output with results
        """
        discrepancies: List[str] = []
        verification_id = str(uuid.uuid4())

        # Check marking confirmation
        marking_confirmed = input_data.marking_confirmed
        if not marking_confirmed:
            discrepancies.append(
                _("Marking practitioner has not confirmed surgical site marking")
            )

        # Check patient confirmation
        patient_confirmed = input_data.patient_confirmed
        if not patient_confirmed:
            discrepancies.append(
                _("Patient has not confirmed surgical site and procedure")
            )

        # Check laterality verification
        laterality_verified = True
        if input_data.laterality in {"left", "right", "bilateral"}:
            # Lateral procedures require photo
            if not input_data.photo_reference:
                discrepancies.append(
                    _(
                        "Photo documentation missing for lateral procedure "
                        "(laterality: {laterality})"
                    ).format(laterality=input_data.laterality)
                )
                laterality_verified = False

        # Check photo confirmation
        photo_confirmed = bool(input_data.photo_reference)
        if input_data.laterality in {"left", "right", "bilateral"} and not photo_confirmed:
            laterality_verified = False

        # Overall verification status
        site_verified = (
            marking_confirmed
            and patient_confirmed
            and laterality_verified
            and len(discrepancies) == 0
        )

        # Create verification output
        verification_timestamp = datetime.now(timezone.utc).isoformat()

        return SurgicalSiteMarkingOutput(
            verification_id=verification_id,
            surgery_id=input_data.surgery_id,
            site_verified=site_verified,
            laterality_verified=laterality_verified,
            photo_confirmed=photo_confirmed,
            patient_identity_confirmed=patient_confirmed,
            who_phase_completed=input_data.who_checklist_phase,
            verification_timestamp=verification_timestamp,
            discrepancies=discrepancies,
        )
