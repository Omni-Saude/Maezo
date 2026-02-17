"""
Clinical operations domain exception with BPMN error code.
    
        Archetype: CLINICAL_ALERT

Refactored to V2 pattern using BaseExternalTaskWorker.
Business rules delegated to DMN: clinical_safety/doctor_patient_recovery_alert_scoring.

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


class DoctorPatientRecoveryAlertWorker(BaseExternalTaskWorker):
    """
    Clinical operations domain exception with BPMN error code.

    Responsibilities (thin worker pattern):
    1. Parse input variables
    2. Evaluate DMN for clinical scoring and alerts
    3. Return structured output for BPMN routing

    All orchestration handled by BPMN.
    All business rules handled by DMN.
    """

    TOPIC = "clinical.doctor_patient_recovery_alert"
    DMN_DECISION_KEY = "doctor_patient_recovery_alert_scoring"
    DMN_CATEGORY = "clinical_safety"

    def execute(self, context: TaskContext) -> TaskResult:
        """
        Execute DoctorPatientRecoveryAlert operation.

        Args:
            context: Task context with input variables

        Returns:
            TaskResult with DMN outputs
        """
        try:
            variables = context.variables
            correlation_id = variables.get('process_instance_id', '')

            self.logger.info(
                "Processing DoctorPatientRecoveryAlert operation",
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
            self.logger.error(f"DoctorPatientRecoveryAlert operation failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="ERR_DOCTOR_NOTIFICATION",
                error_message=str(e),
                variables={"errorType": type(e).__name__},
            )
