"""
Patient Medication Adherence Worker - Phase 5.3 Post-Discharge Continuity.

CIB7 Topic: continuity.medication_adherence
Purpose: Daily check on post-discharge medication adherence.

This worker sends WhatsApp notifications to patients to check their medication
adherence after discharge. If the patient reports side effects or missed doses,
the response should be escalated to the care team via BPMN.

Refactored to V2 pattern using BaseExternalTaskWorker.
Business rules delegated to DMN: clinical_safety/patient_medication_adherence_notification.

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


class PatientMedicationAdherenceWorker(BaseExternalTaskWorker):
    """
    Patient Medication Adherence Worker - Phase 5.3 Post-Discharge Continuity.

    Responsibilities (thin worker pattern):
    1. Parse input variables
    2. Evaluate DMN for patient notification and engagement
    3. Return structured output for BPMN routing

    All orchestration handled by BPMN.
    All business rules handled by DMN.
    
    Archetype: CLINICAL_SCORE
    """