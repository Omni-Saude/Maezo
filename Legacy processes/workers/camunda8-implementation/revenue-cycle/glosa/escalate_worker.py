"""
EscalateWorker - Zeebe worker for escalating glosa disputes to higher authority.

This worker escalates unresolved denial disputes to management or regulatory bodies
for higher-level review and decision-making.

Business Rule: RN-GLOSA-004-Escalate.md
Regulatory Compliance: ANS RN 424/2017 (escalation for regulatory review)
Migrated from: com.hospital.revenuecycle.delegates.glosa.EscalateWorkerDelegate
Topic: escalate
BPMN Task: Task_Escalate (Escalar Glosa)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import structlog

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


@worker(topic="escalate", max_jobs=8, lock_duration=30000)
class EscalateWorker(BaseWorker):
    """
    Zeebe worker for escalating glosa disputes.

    BPMN Task: Task_Escalate
    Topic: escalate

    This worker escalates disputes by:
    - Creating escalation cases
    - Notifying management
    - Setting priority levels
    - Recording escalation history

    Input Variables:
        - claimId: Claim identifier (required)
        - glosaCaseId: Glosa case identifier
        - escalationReason: Reason for escalation
        - currentLevel: Current escalation level
        - glosaDate: Date glosa was issued (ISO format, for ANS RN 424/2017 validation)

    Output Variables:
        - escalationId: Unique escalation identifier
        - escalationLevel: New escalation level
        - assignedTo: Manager or authority assigned
        - escalationDate: Date of escalation

    Regulatory Compliance:
        - ANS RN 424/2017: Validates 30-day appeal deadline
    """

    def __init__(self, settings=None, **kwargs):
        """Initialize the worker."""
        super().__init__(settings=settings)

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "escalate_glosa"

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
        Process the escalation task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with escalation details
        """
        self._logger.info(
            "Processing escalation",
            claim_id=variables.get("claimId"),
            reason=variables.get("escalationReason"),
        )

        try:
            claim_id = variables.get("claimId")
            glosa_case_id = variables.get("glosaCaseId", "")
            escalation_reason = variables.get("escalationReason", "")
            current_level = variables.get("currentLevel", 1)

            # Validate ANS RN 424/2017 30-day appeal deadline
            glosa_date_str = variables.get("glosaDate")
            if glosa_date_str:
                glosa_date = datetime.fromisoformat(glosa_date_str.replace("Z", "+00:00"))
                self._validate_appeal_deadline(glosa_date)

            # Determine new escalation level
            new_level = current_level + 1
            if new_level > 3:
                new_level = 3

            # Assign to appropriate authority
            level_assignments = {
                1: "Department Manager",
                2: "Director",
                3: "Chief Executive",
            }
            assigned_to = level_assignments.get(new_level, "Management")

            # Generate escalation ID
            escalation_id = f"ESC-{claim_id}-{new_level}"

            output = {
                "escalationId": escalation_id,
                "escalationLevel": new_level,
                "assignedTo": assigned_to,
                "escalationDate": datetime.utcnow().isoformat(),
                "previousLevel": current_level,
            }

            self._logger.info(
                "Escalation processed",
                claim_id=claim_id,
                escalation_id=escalation_id,
                new_level=new_level,
                assigned_to=assigned_to,
            )

            return WorkerResult.ok(output)

        except BpmnErrorException as e:
            self._logger.warning(
                "BPMN error during escalation",
                error_code=e.error_code,
                error=str(e),
            )
            return WorkerResult.bpmn_error(
                error_code=e.error_code,
                error_message=e.message,
            )

        except Exception as e:
            self._logger.error(
                "Error escalating dispute",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Escalation failed: {e}",
                retry=True,
            )
