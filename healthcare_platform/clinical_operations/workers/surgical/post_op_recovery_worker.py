"""
Post-Operative Recovery Worker - PACU recovery monitoring.

CIB7 External Task Topic: surgical.post_op_recovery
BPMN Error Code: SURGICAL_OPERATIONS_ERROR

Monitors post-operative recovery in PACU using Aldrete scoring.
Integrates with WHO Safe Surgery Checklist Sign Out phase.
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

logger = get_logger(__name__, worker="surgical.post_op_recovery")

TOPIC = "surgical.post_op_recovery"


class SurgicalOperationsException(DomainException):
    """Exception raised for surgical operations errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "SURGICAL_OPERATIONS_ERROR",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """Initialize exception."""
        super().__init__(message, error_code, details)
        self.bpmn_error_code = "SURGICAL_OPERATIONS_ERROR"


class PostOpRecoveryInput(BaseModel):
    """Input DTO for post-operative recovery assessment."""

    surgery_id: str = Field(..., description="Surgery identifier")
    patient_id: str = Field(..., description="Patient identifier")
    pacu_bed_id: str = Field(..., description="PACU bed assignment")
    admission_time: datetime = Field(..., description="PACU admission timestamp")
    aldrete_activity: int = Field(..., ge=0, le=2, description="Aldrete activity score (0-2)")
    aldrete_respiration: int = Field(..., ge=0, le=2, description="Aldrete respiration score (0-2)")
    aldrete_circulation: int = Field(..., ge=0, le=2, description="Aldrete circulation score (0-2)")
    aldrete_consciousness: int = Field(..., ge=0, le=2, description="Aldrete consciousness score (0-2)")
    aldrete_oxygen_saturation: int = Field(..., ge=0, le=2, description="Aldrete oxygen saturation score (0-2)")
    pain_score: int = Field(..., ge=0, le=10, description="Pain score (0-10)")
    temperature: float = Field(..., description="Body temperature in Celsius")
    complications: List[str] = Field(default_factory=list, description="Observed complications")
    who_checklist_phase: str = Field(default="sign_out", description="WHO Safe Surgery Checklist phase")
    discharge_criteria_met: bool = Field(default=False, description="Whether discharge criteria are met")

    @field_validator("aldrete_activity", "aldrete_respiration", "aldrete_circulation", "aldrete_consciousness", "aldrete_oxygen_saturation")
    @classmethod
    def validate_aldrete_score(cls, v: int) -> int:
        """Validate Aldrete score is 0, 1, or 2."""
        if v not in [0, 1, 2]:
            raise ValueError(_("Aldrete score must be 0, 1, or 2"))
        return v


class PostOpRecoveryOutput(BaseModel):
    """Output DTO for post-operative recovery assessment."""

    assessment_id: str = Field(..., description="Unique assessment identifier")
    surgery_id: str = Field(..., description="Surgery identifier")
    aldrete_total_score: int = Field(..., ge=0, le=10, description="Total Aldrete score (0-10)")
    recovery_status: str = Field(..., description="Recovery status: stable/monitoring/critical")
    discharge_ready: bool = Field(..., description="Whether patient is ready for discharge")
    who_sign_out_completed: bool = Field(..., description="Whether WHO Sign Out phase is completed")
    assessment_timestamp: datetime = Field(..., description="Assessment timestamp")
    recommendations: List[str] = Field(default_factory=list, description="Clinical recommendations")


class PostOpRecoveryWorker:
    """Worker for post-operative recovery monitoring in PACU."""

    def __init__(self, tasy_adapter: Optional[TasySurgicalAdapter] = None) -> None:
        """
        Initialize worker.

        Args:
            tasy_adapter: TASY surgical adapter (defaults to TasySurgicalAdapter())
        """
        self.tasy_adapter = tasy_adapter or TasySurgicalAdapter()

    @require_tenant
    @track_task_execution(task_type="surgical.post_op_recovery")
    async def execute(self, variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute post-operative recovery assessment.

        Args:
            variables: Task variables containing assessment data

        Returns:
            Dictionary with assessment results

        Raises:
            SurgicalOperationsException: If assessment fails
        """
        try:
            # Parse input
            input_data = PostOpRecoveryInput(**variables)
            tenant = get_required_tenant()

            logger.info(
                "Processing post-operative recovery assessment",
                surgery_id=input_data.surgery_id,
                patient_id=input_data.patient_id,
                pacu_bed=input_data.pacu_bed_id,
                tenant_id=tenant.tenant_id,
            )

            # Calculate total Aldrete score
            aldrete_total = (
                input_data.aldrete_activity
                + input_data.aldrete_respiration
                + input_data.aldrete_circulation
                + input_data.aldrete_consciousness
                + input_data.aldrete_oxygen_saturation
            )

            # Determine recovery status
            recovery_status = self._determine_recovery_status(aldrete_total)

            # Check discharge readiness
            discharge_ready = self._check_discharge_readiness(
                aldrete_total=aldrete_total,
                pain_score=input_data.pain_score,
                complications=input_data.complications,
            )

            # Generate recommendations
            recommendations = self._generate_recommendations(
                aldrete_total=aldrete_total,
                pain_score=input_data.pain_score,
                temperature=input_data.temperature,
                complications=input_data.complications,
                recovery_status=recovery_status,
            )

            # Check WHO Sign Out completion
            who_sign_out_completed = input_data.who_checklist_phase == "sign_out"

            # Record assessment in TASY
            assessment_id = str(uuid.uuid4())
            await self._record_assessment(
                tenant=tenant,
                assessment_id=assessment_id,
                input_data=input_data,
                aldrete_total=aldrete_total,
                recovery_status=recovery_status,
                discharge_ready=discharge_ready,
            )

            # Build output
            output = PostOpRecoveryOutput(
                assessment_id=assessment_id,
                surgery_id=input_data.surgery_id,
                aldrete_total_score=aldrete_total,
                recovery_status=recovery_status,
                discharge_ready=discharge_ready,
                who_sign_out_completed=who_sign_out_completed,
                assessment_timestamp=datetime.now(timezone.utc),
                recommendations=recommendations,
            )

            logger.info(
                "Post-operative recovery assessment completed",
                assessment_id=assessment_id,
                aldrete_score=aldrete_total,
                status=recovery_status,
                discharge_ready=discharge_ready,
                tenant_id=tenant.tenant_id,
            )

            return output.model_dump(mode="json")

        except ValueError as e:
            logger.error("Validation error in post-operative recovery", error=str(e))
            raise SurgicalOperationsException(
                message=_("Invalid post-operative recovery data: {error}").format(error=str(e)),
                details={"validation_error": str(e)},
            ) from e
        except Exception as e:
            logger.error(
                "Failed to process post-operative recovery assessment",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise SurgicalOperationsException(
                message=_("Post-operative recovery assessment failed: {error}").format(error=str(e)),
                details={"error": str(e), "error_type": type(e).__name__},
            ) from e

    def _determine_recovery_status(self, aldrete_total: int) -> str:
        """
        Determine recovery status based on Aldrete score.

        Args:
            aldrete_total: Total Aldrete score

        Returns:
            Recovery status: stable/monitoring/critical
        """
        if aldrete_total >= 9:
            return "stable"
        elif aldrete_total >= 7:
            return "monitoring"
        else:
            return "critical"

    def _check_discharge_readiness(
        self,
        aldrete_total: int,
        pain_score: int,
        complications: List[str],
    ) -> bool:
        """
        Check if patient meets discharge criteria.

        Args:
            aldrete_total: Total Aldrete score
            pain_score: Pain score (0-10)
            complications: List of complications

        Returns:
            True if patient is ready for discharge
        """
        # Discharge criteria:
        # 1. Aldrete score >= 9
        # 2. Pain score <= 4
        # 3. No complications
        return aldrete_total >= 9 and pain_score <= 4 and len(complications) == 0

    def _generate_recommendations(
        self,
        aldrete_total: int,
        pain_score: int,
        temperature: float,
        complications: List[str],
        recovery_status: str,
    ) -> List[str]:
        """
        Generate clinical recommendations based on assessment.

        Args:
            aldrete_total: Total Aldrete score
            pain_score: Pain score
            temperature: Body temperature
            complications: List of complications
            recovery_status: Recovery status

        Returns:
            List of recommendations
        """
        recommendations = []

        # Status-based recommendations
        if recovery_status == "critical":
            recommendations.append("Immediate clinical review required")
            recommendations.append("Consider ICU transfer if no improvement")
            recommendations.append("Continuous monitoring of vital signs")

        if recovery_status == "monitoring":
            recommendations.append("Continue close observation in PACU")
            recommendations.append("Reassess in 30 minutes")

        # Aldrete score recommendations
        if aldrete_total < 9:
            recommendations.append(f"Aldrete score {aldrete_total}/10 - continue recovery in PACU")

        # Pain management
        if pain_score > 4:
            recommendations.append(f"Pain score {pain_score}/10 - consider additional analgesia")

        # Temperature monitoring
        if temperature < 36.0:
            recommendations.append(f"Hypothermia detected ({temperature}°C) - warming measures required")
        elif temperature > 38.0:
            recommendations.append(f"Fever detected ({temperature}°C) - investigate infection")

        # Complications
        if complications:
            recommendations.append(f"Active complications: {', '.join(complications)}")
            for complication in complications:
                if "nausea" in complication.lower():
                    recommendations.append("Consider antiemetic medication")
                if "bleeding" in complication.lower():
                    recommendations.append("Assess surgical site - consider surgical review")
                if "respiratory" in complication.lower():
                    recommendations.append("Assess airway and oxygenation - consider respiratory support")

        # Discharge readiness
        if aldrete_total >= 9 and pain_score <= 4 and not complications:
            recommendations.append("Patient meets discharge criteria from PACU")

        return recommendations

    async def _record_assessment(
        self,
        tenant: Any,
        assessment_id: str,
        input_data: PostOpRecoveryInput,
        aldrete_total: int,
        recovery_status: str,
        discharge_ready: bool,
    ) -> None:
        """
        Record assessment in TASY.

        Args:
            tenant: Tenant context
            assessment_id: Assessment identifier
            input_data: Input data
            aldrete_total: Total Aldrete score
            recovery_status: Recovery status
            discharge_ready: Discharge readiness
        """
        try:
            assessment_data = {
                "assessment_id": assessment_id,
                "surgery_id": input_data.surgery_id,
                "patient_id": input_data.patient_id,
                "pacu_bed_id": input_data.pacu_bed_id,
                "admission_time": input_data.admission_time.isoformat(),
                "aldrete_scores": {
                    "activity": input_data.aldrete_activity,
                    "respiration": input_data.aldrete_respiration,
                    "circulation": input_data.aldrete_circulation,
                    "consciousness": input_data.aldrete_consciousness,
                    "oxygen_saturation": input_data.aldrete_oxygen_saturation,
                    "total": aldrete_total,
                },
                "pain_score": input_data.pain_score,
                "temperature": input_data.temperature,
                "complications": input_data.complications,
                "recovery_status": recovery_status,
                "discharge_ready": discharge_ready,
                "who_checklist_phase": input_data.who_checklist_phase,
                "assessment_timestamp": datetime.now(timezone.utc).isoformat(),
            }

            await self.tasy_adapter.record_post_op_assessment(
                tenant_id=tenant.tenant_id,
                assessment_data=assessment_data,
            )

            logger.debug(
                "Recorded post-operative assessment in TASY",
                assessment_id=assessment_id,
                tenant_id=tenant.tenant_id,
            )

        except Exception as e:
            logger.warning(
                "Failed to record assessment in TASY (non-critical)",
                assessment_id=assessment_id,
                error=str(e),
            )
