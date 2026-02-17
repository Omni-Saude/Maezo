"""
Patient Care Team Introduction Worker

CIB7 External Task Topic: inpatient.care_team_intro
BPMN Error Code: CLINICAL_OPERATIONS_ERROR

Introduces care team members to patient on admission via WhatsApp.
Provides team composition, roles, and unit information.

Refactored to V2 pattern using BaseExternalTaskWorker.
Business rules delegated to DMN: clinical_safety/patient_care_team_intro_notification.

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


class PatientCareTeamIntroWorker(BaseExternalTaskWorker):
    """
    Patient Care Team Introduction Worker

    Responsibilities (thin worker pattern):
    1. Parse input variables
    2. Evaluate DMN for patient notification and engagement
    3. Return structured output for BPMN routing

    All orchestration handled by BPMN.
    All business rules handled by DMN.
    
    Archetype: CLINICAL_SCORE
    """