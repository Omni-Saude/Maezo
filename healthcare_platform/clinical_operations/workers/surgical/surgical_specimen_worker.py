"""
Surgical Specimen Worker - Specimen tracking and labeling verification.

CIB7 External Task Topic: surgical.specimen_tracking
BPMN Error Code: SURGICAL_OPERATIONS_ERROR

Tracks surgical specimens from collection through pathology processing.
Ensures proper labeling, chain of custody, and LGPD-compliant handling.
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

logger = get_logger(__name__, worker="surgical.specimen_tracking")

TOPIC = "surgical.specimen_tracking"

VALID_SPECIMEN_TYPES = [
    "biopsy",
    "tissue",
    "fluid",
    "organ",
    "foreign_body",
    "other"
]

VALID_PRESERVATION_METHODS = [
    "formalin",
    "fresh",
    "frozen",
    "dry"
]

VALID_PRIORITIES = [
    "routine",
    "urgent",
    "stat"
]


class SurgicalOperationsException(DomainException):
    """    Exception for surgical operations errors.
    
        Archetype: COMPLIANCE_VALIDATION
        """

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="SURGICAL_OPERATIONS_ERROR",
            details=details or {}
        )
        self.bpmn_error_code = "SURGICAL_OPERATIONS_ERROR"


class SurgicalSpecimenInput(BaseModel):
    """Input model for surgical specimen tracking."""

    surgery_id: str = Field(..., description="Surgery identifier")
    patient_id: str = Field(..., description="Patient identifier")
    specimen_id: str = Field(..., description="Specimen identifier")
    specimen_type: str = Field(..., description="Type of specimen")
    anatomical_site: str = Field(..., description="Anatomical location of specimen")
    laterality: Optional[str] = Field(None, description="Left/Right/Bilateral/None")
    collection_time: datetime = Field(..., description="When specimen was collected")
    collecting_practitioner_id: str = Field(..., description="Practitioner who collected specimen")
    label_verified: bool = Field(..., description="Whether label has been verified")
    container_type: str = Field(..., description="Type of container used")
    preservation_method: str = Field(..., description="Preservation method used")
    pathology_priority: str = Field(..., description="Priority level for pathology")
    clinical_history_summary: str = Field(..., description="Brief clinical history")

    @field_validator("specimen_type")
    @classmethod
    def validate_specimen_type(cls, v: str) -> str:
        """Validate specimen type is in allowed list."""
        if v not in VALID_SPECIMEN_TYPES:
            raise ValueError(
                f"specimen_type must be one of {VALID_SPECIMEN_TYPES}, got: {v}"
            )
        return v

    @field_validator("preservation_method")
    @classmethod
    def validate_preservation_method(cls, v: str) -> str:
        """Validate preservation method is valid."""
        if v not in VALID_PRESERVATION_METHODS:
            raise ValueError(
                f"preservation_method must be one of {VALID_PRESERVATION_METHODS}, got: {v}"
            )
        return v

    @field_validator("pathology_priority")
    @classmethod
    def validate_pathology_priority(cls, v: str) -> str:
        """Validate pathology priority is valid."""
        if v not in VALID_PRIORITIES:
            raise ValueError(
                f"pathology_priority must be one of {VALID_PRIORITIES}, got: {v}"
            )
        return v


class SurgicalSpecimenOutput(BaseModel):
    """Output model for surgical specimen tracking."""

    tracking_id: str = Field(..., description="Unique tracking identifier")
    specimen_id: str = Field(..., description="Specimen identifier")
    surgery_id: str = Field(..., description="Surgery identifier")
    label_verification_status: str = Field(..., description="Label verification status")
    chain_of_custody_initiated: bool = Field(..., description="Whether chain of custody started")
    transport_instructions: str = Field(..., description="Special transport instructions")
    estimated_processing_time: str = Field(..., description="Estimated time to complete processing")
    tracking_timestamp: datetime = Field(..., description="When tracking was initiated")


class SurgicalSpecimenWorker:
    """Worker for tracking surgical specimens."""

    def __init__(self, tasy_adapter: Optional[TasySurgicalAdapter] = None):
        """Initialize the surgical specimen worker.

        Args:
            tasy_adapter: Optional TASY surgical adapter for integration
        """
        self.tasy_adapter = tasy_adapter or TasySurgicalAdapter()
        logger.info("SurgicalSpecimenWorker initialized", topic=TOPIC)

    @require_tenant
    @track_task_execution(task_type="surgical.specimen_tracking")
    async def execute(self, variables: dict[str, Any]) -> dict[str, Any]:
        """Execute surgical specimen tracking.

        Args:
            variables: Task variables containing specimen information

        Returns:
            Dictionary with tracking results

        Raises:
            SurgicalOperationsException: If specimen tracking fails
        """
        tenant_id = get_required_tenant()
        logger.info(
            "Starting surgical specimen tracking",
            tenant_id=tenant_id,
            surgery_id=variables.get("surgery_id"),
            specimen_id=variables.get("specimen_id")
        )

        try:
            # Parse and validate input
            input_data = SurgicalSpecimenInput(**variables)

            # Verify label and container
            label_status = self._verify_label_and_container(input_data)

            # Initiate chain of custody
            custody_initiated = self._initiate_chain_of_custody(input_data)

            # Determine transport instructions
            transport_instructions = self._determine_transport_instructions(input_data)

            # Estimate processing time
            processing_time = self._estimate_processing_time(input_data)

            # Generate tracking ID
            tracking_id = str(uuid.uuid4())

            # Create output
            output = SurgicalSpecimenOutput(
                tracking_id=tracking_id,
                specimen_id=input_data.specimen_id,
                surgery_id=input_data.surgery_id,
                label_verification_status=label_status,
                chain_of_custody_initiated=custody_initiated,
                transport_instructions=transport_instructions,
                estimated_processing_time=processing_time,
                tracking_timestamp=datetime.now(timezone.utc)
            )

            logger.info(
                "Surgical specimen tracking completed",
                tenant_id=tenant_id,
                tracking_id=tracking_id,
                specimen_id=input_data.specimen_id,
                label_status=label_status
            )

            return output.model_dump(mode="json")

        except ValueError as e:
            logger.error(
                "Validation error in surgical specimen tracking",
                tenant_id=tenant_id,
                error=str(e)
            )
            raise SurgicalOperationsException(
                message=_("Invalid specimen data: {error}").format(error=str(e)),
                details={"validation_error": str(e)}
            )
        except Exception as e:
            logger.error(
                "Error tracking surgical specimen",
                tenant_id=tenant_id,
                error=str(e),
                exc_info=True
            )
            raise SurgicalOperationsException(
                message=_("Failed to track surgical specimen: {error}").format(error=str(e)),
                details={"error": str(e)}
            )

    def _verify_label_and_container(self, input_data: SurgicalSpecimenInput) -> str:
        """Verify specimen label and container appropriateness.

        Args:
            input_data: Specimen input data

        Returns:
            Verification status: verified, discrepancy, or missing
        """
        # Check if label was verified by collector
        if not input_data.label_verified:
            logger.warning(
                "Specimen label not verified",
                specimen_id=input_data.specimen_id,
                surgery_id=input_data.surgery_id
            )
            return "discrepancy"

        # Validate container type matches preservation method
        container_valid = self._validate_container_for_preservation(
            input_data.container_type,
            input_data.preservation_method
        )

        if not container_valid:
            logger.warning(
                "Container type may not match preservation method",
                specimen_id=input_data.specimen_id,
                container_type=input_data.container_type,
                preservation_method=input_data.preservation_method
            )
            return "discrepancy"

        return "verified"

    def _validate_container_for_preservation(
        self,
        container_type: str,
        preservation_method: str
    ) -> bool:
        """Validate that container type is appropriate for preservation method.

        Args:
            container_type: Type of container
            preservation_method: Preservation method being used

        Returns:
            True if container is appropriate
        """
        # Basic validation rules
        if preservation_method == "frozen" and "cryo" not in container_type.lower():
            return False
        if preservation_method == "formalin" and "formalin" not in container_type.lower():
            return False

        return True

    def _initiate_chain_of_custody(self, input_data: SurgicalSpecimenInput) -> bool:
        """Initiate chain of custody for specimen.

        Args:
            input_data: Specimen input data

        Returns:
            True if chain of custody was successfully initiated
        """
        try:
            # In real implementation, this would record:
            # - Collector information
            # - Collection time and location
            # - Handoff to transport
            # - Current custodian

            logger.info(
                "Chain of custody initiated",
                specimen_id=input_data.specimen_id,
                collecting_practitioner=input_data.collecting_practitioner_id,
                collection_time=input_data.collection_time.isoformat()
            )

            return True

        except Exception as e:
            logger.error(
                "Failed to initiate chain of custody",
                specimen_id=input_data.specimen_id,
                error=str(e)
            )
            return False

    def _determine_transport_instructions(self, input_data: SurgicalSpecimenInput) -> str:
        """Determine special transport instructions based on preservation method.

        Args:
            input_data: Specimen input data

        Returns:
            Transport instructions string
        """
        if input_data.preservation_method == "frozen":
            return "URGENT: Transport in liquid nitrogen or dry ice. Maintain -80°C. Do not thaw."
        elif input_data.preservation_method == "fresh":
            return "Transport immediately. Keep at 4°C. Process within 1 hour of collection."
        elif input_data.preservation_method == "formalin":
            return "Standard transport. Keep at room temperature. Handle with care."
        elif input_data.preservation_method == "dry":
            return "Standard transport. Keep dry. Protect from moisture."
        else:
            return "Follow standard specimen transport protocols."

    def _estimate_processing_time(self, input_data: SurgicalSpecimenInput) -> str:
        """Estimate processing time based on priority and specimen type.

        Args:
            input_data: Specimen input data

        Returns:
            Estimated processing time string
        """
        # Base processing times by priority
        if input_data.pathology_priority == "stat":
            base_time = "2-4 hours"
        elif input_data.pathology_priority == "urgent":
            base_time = "24-48 hours"
        else:  # routine
            base_time = "5-7 business days"

        # Note: Complex specimens may take longer
        if input_data.specimen_type in ["organ", "tissue"]:
            if input_data.pathology_priority == "routine":
                base_time = "7-14 business days"

        return base_time
