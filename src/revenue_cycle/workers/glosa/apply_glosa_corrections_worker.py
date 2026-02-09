"""
ApplyGlosaCorrectionWorker - Applies corrections to claims based on glosa analysis.

This worker processes suggested corrections identified from glosa analysis,
applying automatic corrections below thresholds and flagging high-value
corrections for review.

Business Rule: RN-GLOSA-002-ApplyCorrections.md
Regulatory Compliance: ANS RN 424/2017 (correction tracking), CPC 25
Migrated from: com.hospital.revenuecycle.delegates.glosa.ApplyGlosaCorrectionDelegate
Topic: apply-glosa-corrections
BPMN Task: Task_Apply_Glosa_Corrections

Input Variables:
    glosaId (str): Glosa/denial identifier (required)
    claimId (str): Claim identifier (required)
    suggestedCorrections (list[dict], optional): List of suggested corrections
    autoApplyThreshold (Decimal, optional): Amount threshold for auto-apply (default: R$500)
    approvalRequired (bool, optional): Whether approval is required
    tenantId (str, optional): Multi-tenant identifier

Output Variables:
    correctionsApplied (bool): Whether corrections were applied
    applicableCorrections (list[dict]): Corrections that were applicable
    appliedCorrections (list[dict]): Corrections actually applied
    pendingReviewCorrections (list[dict]): Corrections pending review
    newClaimAmount (Decimal): Claim amount after corrections
    totalCorrectionAmount (Decimal): Total amount of corrections
    requiresReview (bool): Whether manual review is needed
    applicationDate (str): ISO format timestamp
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

import structlog
from pydantic import BaseModel, Field, ConfigDict, field_validator

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)

# Default auto-apply threshold (R$500)
DEFAULT_AUTO_APPLY_THRESHOLD = Decimal("500.00")
# Maximum amount to auto-approve without review
MAX_AUTO_APPROVE_AMOUNT = Decimal("1000.00")


class CorrectionStatus(str, Enum):
    """Status of a correction action."""
    APPLIED = "APPLIED"
    PENDING_REVIEW = "PENDING_REVIEW"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"


class CorrectionPriority(str, Enum):
    """Priority level for corrections."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# ============================================================================
# Pydantic Models
# ============================================================================


class Correction(BaseModel):
    """Model for a correction to be applied."""
    model_config = ConfigDict(populate_by_name=True)

    correction_id: str = Field(..., alias="correctionId")
    correction_type: str = Field(...)
    description: str
    amount: Decimal = Field(..., ge=0)
    reason: Optional[str] = None
    priority: str = Field(default="MEDIUM")
    charge_code: Optional[str] = Field(None, alias="chargeCode")
    implementation_steps: Optional[list[str]] = Field(
        None,
        alias="implementationSteps"
    )

    @field_validator('amount', mode='before')
    @classmethod
    def parse_amount(cls, v):
        """Parse amount from various formats."""
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v.replace(",", "."))
        return v


class AppliedCorrection(BaseModel):
    """Model for a correction that was applied."""
    model_config = ConfigDict(populate_by_name=True)

    correction_id: str = Field(..., alias="correctionId")
    status: str  # APPLIED, PENDING_REVIEW, REJECTED, DEFERRED
    amount: Decimal
    reason: Optional[str] = None
    applied_date: Optional[str] = Field(None, alias="appliedDate")
    applied_by: Optional[str] = Field(None, alias="appliedBy")


class ApplyGlosaCorrectionInput(BaseModel):
    """Input model for applying glosa corrections."""
    model_config = ConfigDict(populate_by_name=True)

    glosa_id: str = Field(..., alias="glosaId")
    claim_id: str = Field(..., alias="claimId")
    current_claim_amount: Decimal = Field(
        default=Decimal("0"),
        alias="currentClaimAmount",
        ge=0
    )
    suggested_corrections: list[Correction] = Field(
        default_factory=list,
        alias="suggestedCorrections"
    )
    auto_apply_threshold: Decimal = Field(
        DEFAULT_AUTO_APPLY_THRESHOLD,
        alias="autoApplyThreshold",
        ge=0
    )
    approval_required: bool = Field(default=False, alias="approvalRequired")
    tenant_id: Optional[str] = Field(None, alias="tenantId")

    @field_validator('current_claim_amount', mode='before')
    @classmethod
    def parse_claim_amount(cls, v):
        """Parse claim amount from various formats."""
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v.replace(",", "."))
        return v if v is not None else Decimal("0")


class ApplyGlosaCorrectionOutput(BaseModel):
    """Output model for glosa correction application."""
    model_config = ConfigDict(populate_by_name=True)

    corrections_applied: bool = Field(..., alias="correctionsApplied")
    glosa_id: str = Field(..., alias="glosaId")
    claim_id: str = Field(..., alias="claimId")
    original_claim_amount: Decimal = Field(
        ...,
        alias="originalClaimAmount"
    )
    new_claim_amount: Decimal = Field(..., alias="newClaimAmount")
    total_correction_amount: Decimal = Field(
        ...,
        alias="totalCorrectionAmount"
    )
    applicable_corrections_count: int = Field(
        ...,
        alias="applicableCorrectionsCount"
    )
    applied_corrections: list[dict[str, Any]] = Field(
        default_factory=list,
        alias="appliedCorrections"
    )
    pending_review_corrections: list[dict[str, Any]] = Field(
        default_factory=list,
        alias="pendingReviewCorrections"
    )
    requires_review: bool = Field(..., alias="requiresReview")
    application_date: str = Field(..., alias="applicationDate")


# ============================================================================
# Worker Implementation
# ============================================================================


@worker(
    topic="apply-glosa-corrections",
    max_jobs=12,
    lock_duration=45000,  # 45 seconds
)
class ApplyGlosaCorrectionWorker(BaseWorker):
    """
    Worker for applying corrections identified from glosa analysis.

    Responsibilities:
    - Process suggested corrections from glosa analysis
    - Apply automatic corrections below threshold
    - Flag high-value corrections for review
    - Recalculate claim amounts after corrections
    - Track all corrections applied
    - Determine if additional review is needed

    Business Logic:
    1. VALIDATE input data and corrections
    2. FILTER applicable corrections
    3. SEPARATE auto-apply vs. review corrections
    4. APPLY automatic corrections
    5. COMPILE review list for high-value corrections
    6. RECALCULATE claim amount
    7. DETERMINE if review needed
    8. RETURN application results
    """

    def __init__(self, settings=None, **kwargs):
        """
        Initialize the worker.

        Args:
            settings: Application settings
            **kwargs: Additional arguments for BaseWorker
        """
        super().__init__(settings=settings)

    @property
    def operation_name(self) -> str:
        return "apply_glosa_corrections"

    @property
    def requires_idempotency(self) -> bool:
        # Corrections should be idempotent - same input produces same result
        return True

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Execute the glosa correction application.

        Args:
            job: Camunda external task
            variables: Job variables

        Returns:
            WorkerResult with corrections applied
        """
        self._logger.info(
            "Starting glosa correction application",
            business_key=variables.get("businessKey"),
            glosa_id=variables.get("glosaId"),
            claim_id=variables.get("claimId"),
        )

        try:
            # 1. Extract and validate input
            glosa_id = self.get_required_variable(variables, "glosaId", str)
            claim_id = self.get_required_variable(variables, "claimId", str)
            current_claim_amount = self.get_required_amount_variable(
                variables,
                "currentClaimAmount"
            )
            auto_apply_threshold = self.get_variable(
                variables,
                "autoApplyThreshold",
                Decimal,
                DEFAULT_AUTO_APPLY_THRESHOLD
            )
            approval_required = self.get_variable(
                variables,
                "approvalRequired",
                bool,
                False
            )

            # Get corrections list
            corrections_data = self.get_variable(
                variables,
                "suggestedCorrections",
                list,
                []
            )

            # Parse corrections
            corrections = []
            if corrections_data:
                try:
                    for corr in corrections_data:
                        if isinstance(corr, dict):
                            corrections.append(Correction(**corr))
                except Exception as e:
                    self._logger.warning(
                        "Error parsing corrections",
                        error=str(e)
                    )

            self._logger.info(
                "Corrections received",
                correction_count=len(corrections),
                auto_apply_threshold=str(auto_apply_threshold)
            )

            # 2. Separate corrections for auto-apply vs. review
            auto_apply_corrections = []
            review_corrections = []

            total_correction_amount = Decimal("0")

            for correction in corrections:
                total_correction_amount += correction.amount

                # Determine if correction should be auto-applied
                if self._should_auto_apply(
                    correction,
                    auto_apply_threshold,
                    approval_required,
                ):
                    auto_apply_corrections.append(correction)
                else:
                    review_corrections.append(correction)

            # 3. Apply automatic corrections
            applied_corrections = []
            for correction in auto_apply_corrections:
                applied = AppliedCorrection(
                    correction_id=correction.correction_id,
                    status=CorrectionStatus.APPLIED.value,
                    amount=correction.amount,
                    reason=correction.reason,
                    applied_date=datetime.utcnow().isoformat(),
                    applied_by="SYSTEM_AUTO"
                )
                applied_corrections.append(applied)

            # 4. Recalculate claim amount
            total_applied = sum(
                Decimal(str(c.amount)) for c in applied_corrections
            )
            new_claim_amount = current_claim_amount - total_applied

            # Ensure non-negative
            new_claim_amount = max(Decimal("0"), new_claim_amount)

            # 5. Determine if review is needed
            requires_review = bool(review_corrections) or approval_required

            # 6. Build output
            output = ApplyGlosaCorrectionOutput(
                corrections_applied=bool(applied_corrections),
                glosa_id=glosa_id,
                claim_id=claim_id,
                original_claim_amount=current_claim_amount,
                new_claim_amount=new_claim_amount,
                total_correction_amount=total_applied,
                applicable_corrections_count=len(corrections),
                applied_corrections=[
                    c.model_dump(by_alias=True, exclude_none=True)
                    for c in applied_corrections
                ],
                pending_review_corrections=[
                    {
                        "correctionId": c.correction_id,
                        "correctionType": c.correction_type,
                        "amount": str(c.amount),
                        "description": c.description,
                        "priority": c.priority,
                        "reason": c.reason,
                        "chargeCode": c.charge_code,
                    }
                    for c in review_corrections
                ],
                requires_review=requires_review,
                application_date=datetime.utcnow().isoformat(),
            )

            self._logger.info(
                "Glosa corrections application complete",
                claim_id=claim_id,
                applied_count=len(applied_corrections),
                pending_count=len(review_corrections),
                original_amount=str(current_claim_amount),
                new_amount=str(new_claim_amount),
                requires_review=requires_review,
            )

            return WorkerResult.ok(
                output.model_dump(by_alias=True, exclude_none=True)
            )

        except Exception as e:
            self._logger.error(
                "Error applying glosa corrections",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Correction application failed: {e}",
                retry=True,
            )

    def _should_auto_apply(
        self,
        correction: Correction,
        threshold: Decimal,
        approval_required: bool,
    ) -> bool:
        """
        Determine if correction should be auto-applied.

        Rules:
        - Amount must be below auto-apply threshold
        - If approval_required is true, no auto-apply
        - Low priority corrections below threshold are auto-applied
        - Critical/High priority always require review

        Args:
            correction: Correction to evaluate
            threshold: Auto-apply threshold amount
            approval_required: Whether approval is globally required

        Returns:
            True if correction should be auto-applied
        """
        # If global approval required, don't auto-apply
        if approval_required:
            return False

        # Critical and High priority always require review
        if correction.priority in (
            CorrectionPriority.CRITICAL.value,
            CorrectionPriority.HIGH.value,
        ):
            return False

        # Amount must be below threshold
        if correction.amount > threshold:
            return False

        return True

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """
        Extract parameters for idempotency key generation.

        For corrections, use glosaId, claimId, and correction IDs.

        Args:
            variables: Job variables

        Returns:
            String representation of key parameters
        """
        glosa_id = variables.get("glosaId", "")
        claim_id = variables.get("claimId", "")
        process_instance = variables.get("processInstanceKey", "")

        # Include correction IDs in idempotency key
        corrections = variables.get("suggestedCorrections", [])
        correction_ids = "-".join([
            c.get("correctionId", "") for c in corrections
            if isinstance(c, dict)
        ])

        return f"{process_instance}:{glosa_id}:{claim_id}:{correction_ids}"
