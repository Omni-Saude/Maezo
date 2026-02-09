"""
CreateAlertWorker - Zeebe worker for creating system alerts.

This worker creates and distributes alerts for important events in the
revenue cycle including payment status changes, claim issues, and deadlines.

This is the Python equivalent of the Java CreateAlertDelegate.

Business Rule: Benchmark - Alert management and notification standards
Regulatory Compliance: SOX 404 (event logging requirements), internal audit standards for notifications
Migrated from: com.hospital.revenuecycle.delegates.CreateAlertDelegate

Section references:
- Alert severity classification and escalation
- Deadline-based alerts (payment, appeals, collection)
- Alert lifecycle and expiration management
- Event notification and logging

BPMN Task: Task_Create_Alert in Alert_Management_Workflow
Topic: create-alert
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import structlog

from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


@worker(topic="create-alert", max_jobs=8, lock_duration=30000)
class CreateAlertWorker(BaseWorker):
    """
    Zeebe worker for creating system alerts.

    BPMN Task: Task_Create_Alert
    Topic: create-alert

    This worker creates alerts for:
    - Payment deadline approaching
    - Claim denied
    - Collection escalation
    - Dispute filed
    - Service issues

    Input Variables:
        - claimId: Claim identifier (required)
        - alertType: Type of alert (DEADLINE/DENIAL/ESCALATION/DISPUTE/OTHER)
        - severity: Alert severity (LOW/MEDIUM/HIGH/CRITICAL)
        - message: Alert message

    Output Variables:
        - alertId: Unique alert identifier
        - alertCreated: Whether alert was created successfully
        - createdAt: Timestamp of alert creation
        - expiresAt: When alert expires
    """

    def __init__(self, settings=None, **kwargs):
        """Initialize the worker."""
        super().__init__(settings=settings)

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "create_alert"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the alert creation task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with alert details
        """
        self._logger.info(
            "Processing alert creation",
            claim_id=variables.get("claimId"),
            alert_type=variables.get("alertType"),
        )

        try:
            claim_id = variables.get("claimId")
            alert_type = variables.get("alertType", "OTHER")
            severity = variables.get("severity", "MEDIUM")
            message = variables.get("message", "")

            # Generate alert ID
            alert_id = f"ALT-{claim_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

            # Determine alert expiration based on severity
            if severity == "CRITICAL":
                expires_at = datetime.utcnow() + timedelta(hours=1)
            elif severity == "HIGH":
                expires_at = datetime.utcnow() + timedelta(hours=24)
            elif severity == "MEDIUM":
                expires_at = datetime.utcnow() + timedelta(days=7)
            else:
                expires_at = datetime.utcnow() + timedelta(days=30)

            output = {
                "alertId": alert_id,
                "alertCreated": True,
                "createdAt": datetime.utcnow().isoformat(),
                "expiresAt": expires_at.isoformat(),
                "alertType": alert_type,
                "severity": severity,
                "message": message,
                "claimId": claim_id,
            }

            self._logger.info(
                "Alert created",
                claim_id=claim_id,
                alert_id=alert_id,
                alert_type=alert_type,
                severity=severity,
            )

            return WorkerResult.ok(output)

        except Exception as e:
            self._logger.error(
                "Error creating alert",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Alert creation failed: {e}",
                retry=True,
            )
