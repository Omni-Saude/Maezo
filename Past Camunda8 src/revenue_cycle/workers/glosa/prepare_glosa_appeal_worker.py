"""
PrepareGlosaAppealWorker - Zeebe worker for preparing glosa dispute appeals.

This worker compiles documentation, evidence, and legal arguments to prepare
a complete appeal package for denial disputes.

Business Rule: RN-GLOSA-006-PrepareAppeal.md
Regulatory Compliance: ANS RN 424/2017 (30-day appeal deadline), ANS RN 395/2016 (documentation)
Migrated from: com.hospital.revenuecycle.delegates.glosa.PrepareGlosaAppealDelegate
Topic: prepare-glosa-appeal
BPMN Task: Task_Prepare_Glosa_Appeal (Preparar Recurso de Glosa)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import structlog

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


@worker(topic="prepare-glosa-appeal", max_jobs=8, lock_duration=45000)
class PrepareGlosaAppealWorker(BaseWorker):
    """
    Zeebe worker for preparing glosa appeal documentation.

    BPMN Task: Task_Prepare_Glosa_Appeal
    Topic: prepare-glosa-appeal

    This worker prepares:
    - Appeal documentation
    - Evidence compilation
    - Legal arguments
    - Regulatory references

    Input Variables:
        - claimId: Claim identifier (required)
        - denialReason: Reason for original denial
        - evidenceList: List of supporting evidence
        - regulatoryReferences: Applicable regulations
        - glosaDate: Date glosa was issued (ISO format, for ANS RN 424/2017 validation)

    Output Variables:
        - appealPackageId: Unique appeal package identifier
        - appealPrepared: Whether appeal is ready to submit
        - documentationComplete: Percentage of documentation complete
        - submissionDate: Recommended submission date

    Regulatory Compliance:
        - ANS RN 424/2017: Validates 30-day appeal deadline
    """

    def __init__(self, settings=None, **kwargs):
        """Initialize the worker."""
        super().__init__(settings=settings)

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "prepare_glosa_appeal"

    def _validate_appeal_deadline(self, glosa_date: datetime) -> None:
        """
        Validate ANS RN 424/2017 30-day appeal deadline.

        Per ANS Normativa 424/2017, health insurers must allow beneficiaries
        to appeal denials (glosas) within 30 days of notification.

        Args:
            glosa_date: Date when glosa was issued

        Raises:
            BpmnErrorException: If appeal deadline exceeded
        """
        deadline = glosa_date + timedelta(days=30)
        if datetime.utcnow() > deadline:
            raise BpmnErrorException(
                error_code="APPEAL_DEADLINE_EXCEEDED",
                message=(
                    f"Appeal deadline exceeded per ANS RN 424/2017. "
                    f"Glosa date: {glosa_date.isoformat()}, "
                    f"Deadline: {deadline.isoformat()}"
                )
            )

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the appeal preparation task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with appeal package details
        """
        self._logger.info(
            "Processing glosa appeal preparation",
            claim_id=variables.get("claimId"),
        )

        try:
            claim_id = variables.get("claimId")
            denial_reason = variables.get("denialReason", "")
            evidence_list = variables.get("evidenceList", [])
            regulatory_references = variables.get("regulatoryReferences", [])

            # Validate ANS RN 424/2017 30-day appeal deadline
            glosa_date_str = variables.get("glosaDate")
            if glosa_date_str:
                glosa_date = datetime.fromisoformat(glosa_date_str.replace("Z", "+00:00"))
                self._validate_appeal_deadline(glosa_date)

            # Generate appeal package ID
            appeal_package_id = f"APP-{claim_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

            # Compile appeal documentation checklist
            documentation_items = [
                "Original claim",
                "Denial letter",
                "Supporting evidence",
                "Regulatory references",
                "Legal arguments",
            ]

            # Calculate documentation completeness
            items_complete = min(
                3 + len(evidence_list) + len(regulatory_references),
                len(documentation_items)
            )
            documentation_complete = (
                (items_complete / len(documentation_items)) * 100
                if documentation_items
                else 0
            )

            # Determine if appeal is ready
            appeal_prepared = (
                len(evidence_list) > 0 and
                len(regulatory_references) > 0 and
                documentation_complete >= 80
            )

            output = {
                "appealPackageId": appeal_package_id,
                "appealPrepared": appeal_prepared,
                "documentationComplete": round(documentation_complete, 1),
                "submissionDate": (
                    datetime.utcnow().isoformat()
                    if appeal_prepared
                    else None
                ),
                "denialReason": denial_reason,
                "evidenceCount": len(evidence_list),
                "regulatoryReferencesCount": len(regulatory_references),
            }

            self._logger.info(
                "Appeal preparation completed",
                claim_id=claim_id,
                appeal_package_id=appeal_package_id,
                appeal_prepared=appeal_prepared,
                documentation_complete=documentation_complete,
            )

            return WorkerResult.ok(output)

        except BpmnErrorException as e:
            self._logger.warning(
                "BPMN error during appeal preparation",
                error_code=e.error_code,
                error=str(e),
            )
            return WorkerResult.bpmn_error(
                error_code=e.error_code,
                error_message=e.message,
            )

        except Exception as e:
            self._logger.error(
                "Error preparing glosa appeal",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Appeal preparation failed: {e}",
                retry=True,
            )
