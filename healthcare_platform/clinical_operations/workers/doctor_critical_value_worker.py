"""
Doctor Critical Value Worker

CIB7 External Task Topic: clinical.critical_value
BPMN Error Code: CLINICAL_OPERATIONS_ERROR

URGENT notification for critical lab values requiring immediate attention.
PRIORITY: HIGHEST - bypasses ALL frequency limits.

Refactored to V2 pattern using BaseExternalTaskWorker.
Business rules delegated to DMN: clinical_safety/doctor_critical_value_scoring.

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


class DoctorCriticalValueWorker(BaseExternalTaskWorker):
    """
    Doctor Critical Value Worker

    Responsibilities (thin worker pattern):
    1. Parse input variables
    2. Evaluate DMN for clinical scoring and alerts
    3. Return structured output for BPMN routing

    All orchestration handled by BPMN.
    All business rules handled by DMN.
    
    Archetype: CLINICAL_SCORE
    """