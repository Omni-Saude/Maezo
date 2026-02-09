"""
LegalReferralWorker - Refer cases to legal for litigation or specialized handling.

Business Rule: RN-COL-006.md
Regulatory Compliance: CDC Lei 8.078/90 Art. 42, Art. 71 (legal process compliance)
Migrated from: com.hospital.revenuecycle.delegates.collection.LegalReferralDelegate

This worker handles the referral of uncollectible or high-value claims to the legal
department for litigation or specialized handling.

Topic: legal-referral
BPMN Task: Task_Legal_Referral (Referencia Legal)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

import structlog

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


class CdcLegalNoticeError(BpmnErrorException):
    """Raised when attempting legal action without required 48-hour notice (CDC)."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="CDC_LEGAL_NOTICE_REQUIRED",
            message=message,
            details=details,
        )


@worker(topic="legal-referral", max_jobs=8, lock_duration=40000)
class LegalReferralWorker(BaseWorker):
    """
    Zeebe worker for referring cases to legal department.

    BPMN Task: Task_Legal_Referral
    Topic: legal-referral

    This worker:
    - Creates legal case files
    - Compiles evidence
    - Sets litigation priorities
    - Tracks legal progress

    Input Variables:
        - claimId: Claim identifier (required)
        - claimAmount: Amount in dispute
        - daysPastDue: Days overdue
        - referralReason: Reason for legal referral

    Output Variables:
        - legalCaseId: Unique legal case identifier
        - referralProcessed: Whether referral was successful
        - assignedTo: Assigned lawyer or department
        - referralDate: Date of referral
    """

    def __init__(self, settings=None, **kwargs):
        """Initialize the worker."""
        super().__init__(settings=settings)

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "legal_referral"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the legal referral task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with referral details
        """
        self._logger.info(
            "Processing legal referral",
            claim_id=variables.get("claimId"),
            reason=variables.get("referralReason"),
        )

        try:
            claim_id = variables.get("claimId")
            claim_amount = Decimal(str(variables.get("claimAmount", 0)))
            days_past_due = int(variables.get("daysPastDue", 0))
            referral_reason = variables.get("referralReason", "UNCOLLECTIBLE")
            last_contact_date_str = variables.get("lastContactDate")

            # Validate CDC 48-hour legal notice requirement
            if last_contact_date_str:
                last_contact_date = datetime.fromisoformat(last_contact_date_str.replace("Z", "+00:00"))
                self._validate_cdc_legal_notice(last_contact_date)

            # Determine case priority based on amount
            if claim_amount >= Decimal("50000"):
                priority = "HIGH"
                assigned_to = "Senior Legal Counsel"
            elif claim_amount >= Decimal("10000"):
                priority = "MEDIUM"
                assigned_to = "Legal Department"
            else:
                priority = "LOW"
                assigned_to = "Junior Legal Counsel"

            # Generate legal case ID
            legal_case_id = f"LEG-{claim_id}-{datetime.utcnow().strftime('%Y%m%d')}"

            output = {
                "legalCaseId": legal_case_id,
                "referralProcessed": True,
                "assignedTo": assigned_to,
                "referralDate": datetime.utcnow().isoformat(),
                "priority": priority,
                "referralReason": referral_reason,
                "claimAmount": float(claim_amount),
                "daysPastDue": days_past_due,
            }

            self._logger.info(
                "Legal referral processed",
                claim_id=claim_id,
                legal_case_id=legal_case_id,
                priority=priority,
                assigned_to=assigned_to,
            )

            return WorkerResult.ok(output)

        except CdcLegalNoticeError as e:
            self._logger.error("CDC legal notice violation - insufficient notice period", error=str(e))
            return WorkerResult.bpmn_error(
                error_code="CDC_LEGAL_NOTICE_REQUIRED",
                error_message=e.message,
            )

        except Exception as e:
            self._logger.error(
                "Error processing legal referral",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Legal referral failed: {e}",
                retry=True,
            )

    def _validate_cdc_legal_notice(self, last_contact_date: datetime) -> None:
        """
        Validate 48-hour notice before legal action per CDC.

        Brazilian Consumer Defense Code (CDC) requires that consumers
        be given adequate notice (48 hours) before legal collection
        action is initiated.

        Args:
            last_contact_date: Date of last consumer contact

        Raises:
            CdcLegalNoticeError: If 48-hour notice period has not elapsed
        """
        notice_deadline = last_contact_date + timedelta(hours=48)
        current_time = datetime.now(notice_deadline.tzinfo) if notice_deadline.tzinfo else datetime.utcnow()

        if current_time < notice_deadline:
            hours_remaining = (notice_deadline - current_time).total_seconds() / 3600
            self._logger.error(
                "CDC legal notice requirement not met - insufficient notice period",
                last_contact_date=last_contact_date.isoformat(),
                notice_deadline=notice_deadline.isoformat(),
                current_time=current_time.isoformat(),
                hours_remaining=hours_remaining,
            )
            raise CdcLegalNoticeError(
                f"CDC requires 48-hour notice before legal action. "
                f"Last contact: {last_contact_date.isoformat()}. "
                f"Legal action permitted after: {notice_deadline.isoformat()}. "
                f"Hours remaining: {hours_remaining:.1f}. "
                f"AVISO LEGAL: Ação judicial prematura viola CDC.",
                details={
                    "last_contact_date": last_contact_date.isoformat(),
                    "notice_deadline": notice_deadline.isoformat(),
                    "hours_remaining": hours_remaining,
                    "legal_reference": "CDC Lei 8.078/90 - Notice Requirement",
                    "required_notice_hours": 48,
                },
            )
