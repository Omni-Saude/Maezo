"""
Patient Daily Care Plan Worker

CIB7 External Task Topic: inpatient.daily_plan
BPMN Error Code: CLINICAL_OPERATIONS_ERROR

Sends morning care plan update to inpatient with daily schedule,
procedures, and care team on duty.

Refactored to V2 pattern using BaseExternalTaskWorker.
Business rules delegated to DMN: clinical_safety/patient_daily_care_plan_notification.

ADR Compliance:
- ADR-002: Tenant resolution via context
- ADR-003: BaseExternalTaskWorker inheritance
- ADR-007: DMN federation for tenant overrides

Author: Claude Flow V3 (Automated Refactoring 2026-02-16)
License: MIT
"""

from __future__ import annotations


from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
)


class PatientDailyCarePlanWorker(BaseExternalTaskWorker):
    """
    Patient Daily Care Plan Worker

    Responsibilities (thin worker pattern):
    1. Parse input variables
    2. Evaluate DMN for patient notification and engagement
    3. Return structured output for BPMN routing

    All orchestration handled by BPMN.
    All business rules handled by DMN.
    
    Archetype: CLINICAL_SCORE
    """