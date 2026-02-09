"""
EscalateToManagementWorker - Escalate difficult collection cases to management.

Business Rule: RN-COL-008.md
Regulatory Compliance: CDC Lei 8.078/90 Art. 42 (consumer protection), Art. 71 (contact compliance)
Migrated from: com.hospital.revenuecycle.delegates.collection.EscalateToManagementDelegate

This worker handles escalation of difficult collection cases to management,
including priority assignment, notification, and case routing.

Topic: escalate-to-management
BPMN Task: Task_Escalate_To_Management (Escalar para Gerência)
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

import structlog

from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


@worker(topic="escalate-to-management", max_jobs=8, lock_duration=30000)
class EscalateToManagementWorker(BaseWorker):
    """
    Zeebe worker for escalating collection cases to management.

    BPMN Task: Task_Escalate_To_Management
    Topic: escalate-to-management

    This worker:
    - Evaluates escalation criteria
    - Assigns priority levels
    - Routes to appropriate manager
    - Generates escalation reports
    - Triggers notifications

    Input Variables:
        - claimId: Claim identifier (required)
        - patientId: Patient identifier
        - debtAmount: Outstanding debt amount (Decimal)
        - collectionAttempts: Number of collection attempts
        - collectionStatus: Current collection status
        - escalationReason: Reason for escalation
        - failedPaymentPlan: Whether payment plan failed (optional)
        - daysPastDue: Days overdue (optional)

    Output Variables:
        - escalationId: Unique escalation identifier
        - escalatedToManager: Name/ID of assigned manager
        - escalationDate: When escalation occurred
        - escalationPriority: Priority level (CRITICAL/HIGH/MEDIUM/LOW)
        - escalationReason: Documented reason
        - estimatedResolutionDate: Target resolution date
    """

    # Priority escalation thresholds
    CRITICAL_THRESHOLD = Decimal("10000.00")  # Amount > 10k = CRITICAL
    HIGH_THRESHOLD = Decimal("5000.00")  # Amount > 5k = HIGH
    MEDIUM_THRESHOLD = Decimal("1000.00")  # Amount > 1k = MEDIUM

    def __init__(self, settings=None, **kwargs):
        """Initialize the worker."""
        super().__init__(settings=settings)

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "escalate_to_management"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the escalation task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with escalation details
        """
        self._logger.info(
            "Processing escalation to management",
            claim_id=variables.get("claimId"),
            reason=variables.get("escalationReason"),
        )

        try:
            claim_id = variables.get("claimId")
            patient_id = variables.get("patientId", "")
            debt_amount = Decimal(str(variables.get("debtAmount", 0)))
            collection_attempts = int(variables.get("collectionAttempts", 0))
            collection_status = variables.get("collectionStatus", "IN_PROGRESS")
            escalation_reason = variables.get("escalationReason", "COLLECTION_DIFFICULTY")
            failed_payment_plan = variables.get("failedPaymentPlan", False)
            days_past_due = int(variables.get("daysPastDue", 0))

            # Validate inputs
            if debt_amount <= 0:
                return WorkerResult.failure(
                    error_message="Debt amount must be positive",
                    retry=False,
                )

            # Generate escalation ID
            escalation_id = f"ESC-{claim_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

            # Determine escalation priority
            escalation_priority = self._determine_priority(
                debt_amount=debt_amount,
                days_past_due=days_past_due,
                collection_attempts=collection_attempts,
                failed_payment_plan=failed_payment_plan,
            )

            # Assign appropriate manager
            assigned_manager = self._assign_manager(escalation_priority)

            # Calculate estimated resolution date
            estimated_resolution_date = self._calculate_resolution_date(escalation_priority)

            # Build escalation context
            escalation_context = {
                "debtAmount": float(debt_amount),
                "collectionAttempts": collection_attempts,
                "daysPastDue": days_past_due,
                "failedPaymentPlan": failed_payment_plan,
            }

            output = {
                "escalationId": escalation_id,
                "escalatedToManager": assigned_manager,
                "escalationDate": datetime.utcnow().isoformat(),
                "escalationPriority": escalation_priority,
                "escalationReason": escalation_reason,
                "estimatedResolutionDate": estimated_resolution_date,
                "escalationContext": escalation_context,
                "collectionStatus": collection_status,
                "requiresLegalReview": escalation_priority in ["CRITICAL", "HIGH"],
            }

            self._logger.info(
                "Case escalated to management",
                claim_id=claim_id,
                escalation_id=escalation_id,
                manager=assigned_manager,
                priority=escalation_priority,
                reason=escalation_reason,
            )

            return WorkerResult.ok(output)

        except Exception as e:
            self._logger.error(
                "Error escalating to management",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Escalation failed: {e}",
                retry=True,
            )

    def _determine_priority(
        self,
        debt_amount: Decimal,
        days_past_due: int,
        collection_attempts: int,
        failed_payment_plan: bool,
    ) -> str:
        """
        Determine escalation priority based on multiple factors.

        Args:
            debt_amount: Outstanding debt amount
            days_past_due: Days overdue
            collection_attempts: Number of collection attempts
            failed_payment_plan: Whether payment plan failed

        Returns:
            Priority level: CRITICAL, HIGH, MEDIUM, or LOW
        """
        # Score-based approach
        score = 0

        # Amount-based scoring
        if debt_amount >= self.CRITICAL_THRESHOLD:
            score += 40
        elif debt_amount >= self.HIGH_THRESHOLD:
            score += 30
        elif debt_amount >= self.MEDIUM_THRESHOLD:
            score += 20
        else:
            score += 10

        # Age-based scoring
        if days_past_due > 120:
            score += 30
        elif days_past_due > 90:
            score += 25
        elif days_past_due > 60:
            score += 20
        elif days_past_due > 30:
            score += 10

        # Collection effort scoring
        if collection_attempts > 5:
            score += 20
        elif collection_attempts > 3:
            score += 15
        elif collection_attempts > 0:
            score += 10

        # Failed payment plan (highest priority indicator)
        if failed_payment_plan:
            score += 25

        # Determine priority from score
        if score >= 80:
            return "CRITICAL"
        elif score >= 60:
            return "HIGH"
        elif score >= 40:
            return "MEDIUM"
        else:
            return "LOW"

    def _assign_manager(self, escalation_priority: str) -> str:
        """
        Assign appropriate manager based on priority.

        Args:
            escalation_priority: Priority level

        Returns:
            Manager assignment (name or team)
        """
        manager_assignments = {
            "CRITICAL": "Director of Collections (CRITICAL_CASES)",
            "HIGH": "Senior Collections Manager (HIGH_PRIORITY)",
            "MEDIUM": "Collections Manager (MEDIUM_PRIORITY)",
            "LOW": "Collections Specialist (STANDARD)",
        }
        return manager_assignments.get(escalation_priority, "Collections Department")

    def _calculate_resolution_date(self, escalation_priority: str) -> str:
        """
        Calculate estimated resolution date based on priority.

        Args:
            escalation_priority: Priority level

        Returns:
            ISO formatted date string
        """
        from datetime import timedelta

        # Different SLA based on priority
        sla_days = {
            "CRITICAL": 5,  # 5 business days (1 week)
            "HIGH": 10,  # 10 business days (2 weeks)
            "MEDIUM": 15,  # 15 business days (3 weeks)
            "LOW": 30,  # 30 days (1 month)
        }

        days = sla_days.get(escalation_priority, 30)
        resolution_date = datetime.utcnow() + timedelta(days=days)
        return resolution_date.isoformat()
