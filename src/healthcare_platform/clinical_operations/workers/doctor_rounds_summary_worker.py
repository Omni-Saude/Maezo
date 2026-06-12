"""
Doctor Rounds Summary Worker

CIB7 External Task Topic: inpatient.rounds_summary
BPMN Error Code: CLINICAL_OPERATIONS_ERROR

Sends daily rounds summary at 6AM with patient list and pending items.

Refactored to V2 pattern using BaseExternalTaskWorker.
Business rules delegated to DMN: clinical_safety/doctor_rounds_summary_scoring.

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


class DoctorRoundsSummaryWorker(BaseExternalTaskWorker):
    """
    Doctor Rounds Summary Worker

    Responsibilities (thin worker pattern):
    1. Parse input variables
    2. Evaluate DMN for clinical scoring and alerts
    3. Return structured output for BPMN routing

    All orchestration handled by BPMN.
    All business rules handled by DMN.
    
    Archetype: CLINICAL_SCORE
    """