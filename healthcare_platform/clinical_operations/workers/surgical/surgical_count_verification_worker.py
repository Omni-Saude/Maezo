"""
Surgical Count Verification Worker - Sponge and instrument count verification.

CIB7 External Task Topic: surgical.count_verification
BPMN Error Code: SURGICAL_OPERATIONS_ERROR

SAFETY-CRITICAL: Verifies surgical sponge, instrument, and needle counts.
Requires dual-count confirmation. Records all discrepancies.
Integrates with WHO Safe Surgery Checklist (Time Out and Sign Out phases).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.tasy_adapters.surgical_adapter import TasySurgicalAdapter
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__, worker="surgical.count_verification")

TOPIC = "surgical.count_verification"


class SurgicalOperationsException(DomainException):
    """Exception for surgical operations errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)
        self.bpmn_error_code = "SURGICAL_OPERATIONS_ERROR"


class CountItem(BaseModel):
    """Individual count item for surgical count verification."""

    item_type: str = Field(..., description="Type of item: sponge, instrument, needle, other")
    item_name: str = Field(..., description="Name/description of the item")
    initial_count: int = Field(..., ge=0, description="Initial count at start of surgery")
    final_count: int = Field(..., ge=0, description="Final count at verification point")
    counted_by_primary: str = Field(..., description="Practitioner ID who performed primary count")
    counted_by_secondary: str = Field(..., description="Practitioner ID who performed secondary count")
    count_confirmed: bool = Field(default=True, description="Both counters confirmed the count")

    @field_validator("counted_by_secondary")
    @classmethod
    def validate_dual_count(cls, v: str, info) -> str:
        """Ensure dual count requirement: secondary counter must be different from primary."""
        if "counted_by_primary" in info.data and v == info.data["counted_by_primary"]:
            raise ValueError(
                "Dual count requirement: counted_by_secondary must be different from counted_by_primary"
            )
        return v

    @field_validator("item_type")
    @classmethod
    def validate_item_type(cls, v: str) -> str:
        """Validate item type is one of the allowed values."""
        allowed_types = {"sponge", "instrument", "needle", "other"}
        if v.lower() not in allowed_types:
            raise ValueError(
                f"item_type must be one of: {', '.join(allowed_types)}"
            )
        return v.lower()


class SurgicalCountVerificationInput(BaseModel):
    """Input for surgical count verification."""

    surgery_id: str = Field(..., description="Unique surgery identifier")
    patient_id: str = Field(..., description="Patient identifier")
    count_phase: str = Field(..., description="Count phase: initial, closing, or final")
    items: List[CountItem] = Field(..., min_length=1, description="List of items to verify")
    who_checklist_phase: str = Field(
        default="sign_out",
        description="WHO Safe Surgery Checklist phase (time_out, sign_out)"
    )
    additional_notes: Optional[str] = Field(None, description="Additional verification notes")

    @field_validator("count_phase")
    @classmethod
    def validate_count_phase(cls, v: str) -> str:
        """Validate count phase is one of the allowed values."""
        allowed_phases = {"initial", "closing", "final"}
        if v.lower() not in allowed_phases:
            raise ValueError(
                f"count_phase must be one of: {', '.join(allowed_phases)}"
            )
        return v.lower()


class SurgicalCountVerificationOutput(BaseModel):
    """Output from surgical count verification."""

    verification_id: str = Field(..., description="Unique verification identifier")
    surgery_id: str = Field(..., description="Surgery identifier")
    count_phase: str = Field(..., description="Count phase verified")
    all_counts_correct: bool = Field(..., description="All counts match initial counts")
    dual_count_confirmed: bool = Field(..., description="All counts have dual confirmation")
    discrepancies: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of discrepancies found"
    )
    requires_xray: bool = Field(
        default=False,
        description="X-ray required due to sponge or needle discrepancy"
    )
    verification_timestamp: str = Field(..., description="ISO 8601 timestamp of verification")
    counted_by_pairs: List[Dict[str, str]] = Field(
        default_factory=list,
        description="List of counter pairs who performed verification"
    )


class SurgicalCountVerificationWorker:
    """
    Worker for surgical count verification.

    Verifies that all surgical items (sponges, instruments, needles) are accounted for
    through dual-count verification. Critical safety measure to prevent retained surgical items.
    """

    def __init__(self, tasy_adapter: Optional[TasySurgicalAdapter] = None):
        """
        Initialize the surgical count verification worker.

        Args:
            tasy_adapter: Optional TASY surgical adapter for external system integration
        """
        self.tasy_adapter = tasy_adapter or TasySurgicalAdapter()

    @require_tenant
    @track_task_execution("surgical.count_verification")
    async def execute(self, variables: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute surgical count verification.

        Args:
            variables: Task variables containing count verification input

        Returns:
            Dictionary containing verification results

        Raises:
            SurgicalOperationsException: If verification fails or data is invalid
        """
        tenant_id = get_required_tenant()

        try:
            input_data = SurgicalCountVerificationInput(**variables)
        except Exception as e:
            logger.error(
                "Invalid surgical count verification input",
                error=str(e),
                tenant_id=tenant_id,
                variables=variables
            )
            raise SurgicalOperationsException(
                _("Invalid input for surgical count verification"),
                details={"validation_error": str(e)}
            )

        logger.info(
            "Starting surgical count verification",
            surgery_id=input_data.surgery_id,
            patient_id=input_data.patient_id,
            count_phase=input_data.count_phase,
            item_count=len(input_data.items),
            tenant_id=tenant_id
        )

        # Generate verification ID
        verification_id = str(uuid.uuid4())

        # Verify counts and identify discrepancies
        all_counts_correct = True
        dual_count_confirmed = True
        discrepancies: List[Dict[str, Any]] = []
        requires_xray = False
        counted_by_pairs: List[Dict[str, str]] = []

        for item in input_data.items:
            # Track counter pairs
            pair = {
                "primary": item.counted_by_primary,
                "secondary": item.counted_by_secondary,
                "item": item.item_name
            }
            if pair not in counted_by_pairs:
                counted_by_pairs.append(pair)

            # Check if counts match
            if item.initial_count != item.final_count:
                all_counts_correct = False
                difference = item.initial_count - item.final_count

                discrepancy = {
                    "item_type": item.item_type,
                    "item_name": item.item_name,
                    "initial_count": item.initial_count,
                    "final_count": item.final_count,
                    "difference": difference,
                    "counted_by_primary": item.counted_by_primary,
                    "counted_by_secondary": item.counted_by_secondary
                }
                discrepancies.append(discrepancy)

                # CRITICAL: Log discrepancy at CRITICAL level
                logger.critical(
                    "SURGICAL COUNT DISCREPANCY DETECTED",
                    surgery_id=input_data.surgery_id,
                    patient_id=input_data.patient_id,
                    item_type=item.item_type,
                    item_name=item.item_name,
                    initial_count=item.initial_count,
                    final_count=item.final_count,
                    difference=difference,
                    tenant_id=tenant_id
                )

                # Check if X-ray is required (sponge or needle discrepancy)
                if item.item_type in {"sponge", "needle"}:
                    requires_xray = True
                    logger.critical(
                        "X-RAY REQUIRED: Sponge or needle count discrepancy",
                        surgery_id=input_data.surgery_id,
                        patient_id=input_data.patient_id,
                        item_type=item.item_type,
                        item_name=item.item_name,
                        tenant_id=tenant_id
                    )

            # Check dual count confirmation
            if not item.count_confirmed:
                dual_count_confirmed = False
                logger.warning(
                    "Dual count not confirmed",
                    surgery_id=input_data.surgery_id,
                    item_name=item.item_name,
                    tenant_id=tenant_id
                )

        # Create output
        verification_timestamp = datetime.now(timezone.utc).isoformat()

        output = SurgicalCountVerificationOutput(
            verification_id=verification_id,
            surgery_id=input_data.surgery_id,
            count_phase=input_data.count_phase,
            all_counts_correct=all_counts_correct,
            dual_count_confirmed=dual_count_confirmed,
            discrepancies=discrepancies,
            requires_xray=requires_xray,
            verification_timestamp=verification_timestamp,
            counted_by_pairs=counted_by_pairs
        )

        # Log verification result
        if all_counts_correct and dual_count_confirmed:
            logger.info(
                "Surgical count verification PASSED",
                verification_id=verification_id,
                surgery_id=input_data.surgery_id,
                count_phase=input_data.count_phase,
                tenant_id=tenant_id
            )
        else:
            logger.warning(
                "Surgical count verification FAILED",
                verification_id=verification_id,
                surgery_id=input_data.surgery_id,
                count_phase=input_data.count_phase,
                all_counts_correct=all_counts_correct,
                dual_count_confirmed=dual_count_confirmed,
                discrepancy_count=len(discrepancies),
                requires_xray=requires_xray,
                tenant_id=tenant_id
            )

        # Store verification in TASY (if adapter available)
        try:
            if self.tasy_adapter:
                await self.tasy_adapter.record_surgical_count_verification(
                    tenant_id=tenant_id,
                    verification_id=verification_id,
                    surgery_id=input_data.surgery_id,
                    patient_id=input_data.patient_id,
                    count_phase=input_data.count_phase,
                    all_counts_correct=all_counts_correct,
                    discrepancies=discrepancies,
                    requires_xray=requires_xray,
                    who_checklist_phase=input_data.who_checklist_phase,
                    notes=input_data.additional_notes
                )
        except Exception as e:
            logger.error(
                "Failed to record verification in TASY",
                verification_id=verification_id,
                surgery_id=input_data.surgery_id,
                error=str(e),
                tenant_id=tenant_id
            )
            # Don't fail the verification if TASY recording fails

        return output.model_dump()
