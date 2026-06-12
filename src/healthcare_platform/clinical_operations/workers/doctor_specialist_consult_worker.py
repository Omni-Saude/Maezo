"""
Doctor Specialist Consult Worker

CIB7 External Task Topic: emergency.specialist_consult
BPMN Error Code: CLINICAL_OPERATIONS_ERROR

Requests specialist consultation via WhatsApp with patient summary.
Includes interactive buttons: [Accept] [Decline] [Call Back].

Refactored to V2 pattern using BaseExternalTaskWorker.
Business rules delegated to DMN: clinical_safety/doctor_specialist_consult_scoring.

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


class DoctorSpecialistConsultWorker(BaseExternalTaskWorker):
    """
    Doctor Specialist Consult Worker

    Responsibilities (thin worker pattern):
    1. Parse input variables
    2. Evaluate DMN for clinical scoring and alerts
    3. Return structured output for BPMN routing

    All orchestration handled by BPMN.
    All business rules handled by DMN.
    
    Archetype: CLINICAL_SCORE
    """