"""
Apply clinical protocols and guidelines based on diagnosis.

CIB7 External Task Topic: clinical.protocols
BPMN Error Codes: CLINICAL_ERROR

Refactored to V2 pattern using BaseExternalTaskWorker.
Business rules delegated to DMN: clinical_safety/clinical_protocols_assessment.

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


class ClinicalProtocolsWorker(BaseExternalTaskWorker):
    """
    Apply clinical protocols and guidelines based on diagnosis.

    Responsibilities (thin worker pattern):
    1. Parse input variables
    2. Evaluate DMN for clinical assessment and decision support
    3. Return structured output for BPMN routing

    All orchestration handled by BPMN.
    All business rules handled by DMN.
    
    Archetype: CLINICAL_SCORE
    """