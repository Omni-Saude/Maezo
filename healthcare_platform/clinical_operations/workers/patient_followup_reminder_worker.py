"""
Patient Follow-up Reminder Worker.

Sends WhatsApp reminder to patient to schedule follow-up appointment with self-service options.

CIB7 Topic: continuity.followup_reminder

Responsibilities:
- Remind patient to schedule follow-up with recommended doctor/specialty
- Provide self-service scheduling options via WhatsApp buttons
- Track reminder delivery and patient action
- Support LGPD-compliant notification logging

Integration:
- TASY: Patient demographics, appointment availability
- WhatsApp Business API: Interactive message delivery

Refactored to V2 pattern using BaseExternalTaskWorker.
Business rules delegated to DMN: clinical_safety/patient_followup_reminder_notification.

ADR Compliance:
- ADR-002: Tenant resolution via context
- ADR-003: BaseExternalTaskWorker inheritance
- ADR-007: DMN federation for tenant overrides

Author: Claude Flow V3 (Automated Refactoring 2026-02-16)
License: MIT
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


class PatientFollowupReminderWorker(BaseExternalTaskWorker):
    """
    Patient Follow-up Reminder Worker.

    Responsibilities (thin worker pattern):
    1. Parse input variables
    2. Evaluate DMN for patient notification and engagement
    3. Return structured output for BPMN routing

    All orchestration handled by BPMN.
    All business rules handled by DMN.

    Archetype: CLINICAL_ALERT
    """

    TOPIC = "clinical.patient_followup_reminder"
    DMN_DECISION_KEY = "patient_followup_reminder_notification"
    DMN_CATEGORY = "clinical_safety"

    def execute(self, context: TaskContext) -> TaskResult:
        """
        Execute PatientFollowupReminder operation.

        Args:
            context: Task context with input variables

        Returns:
            TaskResult with DMN outputs
        """
        try:
            variables = context.variables
            correlation_id = variables.get('process_instance_id', '')

            self.logger.info(
                "Processing PatientFollowupReminder operation",
                extra={"correlation_id": correlation_id, "tenant_id": context.tenant_id, "task_id": context.task_id},
            )

            # Evaluate DMN for decision logic
            dmn_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_DECISION_KEY,
                variables={
                    "actionType": variables.get("action", ""),
                    # Worker-specific inputs
                },
                category=self.DMN_CATEGORY,
            )

            # Return success with DMN outputs
            return TaskResult.success({
                # DMN routing outputs
                "action": dmn_result.get("action", "REVISAR"),
                "nivelAlerta": dmn_result.get("nivelAlerta", "OK"),
                "acaoRequerida": dmn_result.get("acaoRequerida", ""),
                "justificativa": dmn_result.get("justificativa", ""),
                # Worker outputs
                "processedAt": datetime.utcnow().isoformat(),
                "correlation_id": correlation_id,
                **dmn_result,  # Include all DMN outputs
            })

        except Exception as e:
            self.logger.error(f"PatientFollowupReminder operation failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="ERR_PATIENT_NOTIFICATION",
                error_message=str(e),
                variables={"errorType": type(e).__name__},
            )
