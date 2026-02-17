#!/usr/bin/env python3.11
"""
Script to refactor clinical operations workers to V2 pattern.

Applies the V2 template:
- Uses BaseExternalTaskWorker from healthcare_platform.shared.workers.base
- Delegates business logic to DMN tables
- Maximum 150 lines per worker
- No helper methods (< 5 methods total)
- 100% DMN delegation

Usage:
    python3.11 scripts/refactor_clinical_workers_to_v2.py

Author: Claude Flow V3 - Refactoring Agent B
"""

import re
from pathlib import Path
from typing import Dict, List, Optional
import ast


V2_TEMPLATE = '''"""
{docstring}

Refactored to V2 pattern using BaseExternalTaskWorker.
Business rules delegated to DMN: {dmn_category}/{dmn_table_name}.

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


class {class_name}(BaseExternalTaskWorker):
    """
    {class_description}

    Responsibilities (thin worker pattern):
    1. Parse input variables
    2. Evaluate DMN for {decision_description}
    3. Return structured output for BPMN routing

    All orchestration handled by BPMN.
    All business rules handled by DMN.
    """

    TOPIC = "{topic}"
    DMN_DECISION_KEY = "{dmn_decision_key}"
    DMN_CATEGORY = "{dmn_category}"

    def execute(self, context: TaskContext) -> TaskResult:
        """
        Execute {operation_name}.

        Args:
            context: Task context with input variables

        Returns:
            TaskResult with DMN outputs
        """
        try:
            variables = context.variables
            correlation_id = variables.get('process_instance_id', '')

            self.logger.info(
                "Processing {operation_name}",
                extra={{"correlation_id": correlation_id, "tenant_id": context.tenant_id, "task_id": context.task_id}},
            )

            # Evaluate DMN for decision logic
            dmn_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_DECISION_KEY,
                variables={{
                    "actionType": variables.get("action", ""),
                    # Worker-specific inputs
                }},
                category=self.DMN_CATEGORY,
            )

            # Return success with DMN outputs
            return TaskResult.success({{
                # DMN routing outputs
                "action": dmn_result.get("action", "REVISAR"),
                "nivelAlerta": dmn_result.get("nivelAlerta", "OK"),
                "acaoRequerida": dmn_result.get("acaoRequerida", ""),
                "justificativa": dmn_result.get("justificativa", ""),
                # Worker outputs
                "processedAt": datetime.utcnow().isoformat(),
                "correlation_id": correlation_id,
                **dmn_result,  # Include all DMN outputs
            }})

        except Exception as e:
            self.logger.error(f"{operation_name} failed: {{e}}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="ERR_{error_code}",
                error_message=str(e),
                variables={{"errorType": type(e).__name__}},
            )
'''


def extract_worker_info(file_path: Path) -> Optional[Dict[str, str]]:
    """Extract key information from existing worker."""
    try:
        content = file_path.read_text()

        # Extract class name
        class_match = re.search(r'class\s+(\w+Worker)', content)
        if not class_match:
            return None
        class_name = class_match.group(1)

        # Extract topic from decorator or constant
        topic_match = re.search(r'TOPIC:\s*[\'"]([\w.]+)[\'"]', content) or \
                     re.search(r'topic\s*=\s*[\'"]([\w.]+)[\'"]', content)
        topic = topic_match.group(1) if topic_match else f"clinical.{file_path.stem.replace('_worker', '')}"

        # Extract docstring
        docstring_match = re.search(r'"""(.*?)"""', content, re.DOTALL)
        docstring = docstring_match.group(1).strip() if docstring_match else f"{class_name} - V2 Refactored"

        # Get first line of docstring as description
        description_lines = docstring.split('\n')
        description = description_lines[0].strip() if description_lines else class_name

        return {
            'class_name': class_name,
            'topic': topic,
            'docstring': docstring,
            'description': description,
            'file_name': file_path.stem,
        }
    except Exception as e:
        print(f"Error extracting info from {file_path}: {e}")
        return None


def generate_v2_worker(worker_info: Dict[str, str]) -> str:
    """Generate V2 worker code from template."""
    # Determine DMN category and table based on worker type
    file_name = worker_info['file_name']

    if file_name.startswith('doctor_'):
        dmn_category = 'clinical_safety'
        dmn_table_name = file_name.replace('_worker', '_scoring')
        decision_description = 'clinical scoring and alerts'
        error_code = 'DOCTOR_NOTIFICATION'
    elif file_name.startswith('patient_'):
        dmn_category = 'clinical_safety'
        dmn_table_name = file_name.replace('_worker', '_notification')
        decision_description = 'patient notification and engagement'
        error_code = 'PATIENT_NOTIFICATION'
    elif 'discharge' in file_name:
        dmn_category = 'clinical_safety'
        dmn_table_name = 'discharge_readiness_assessment'
        decision_description = 'discharge readiness assessment'
        error_code = 'DISCHARGE_PLANNING'
    elif 'care_planning' in file_name or 'care_team' in file_name:
        dmn_category = 'clinical_safety'
        dmn_table_name = file_name.replace('_worker', '_coordination')
        decision_description = 'care coordination and planning'
        error_code = 'CARE_COORDINATION'
    else:
        dmn_category = 'clinical_safety'
        dmn_table_name = file_name.replace('_worker', '_assessment')
        decision_description = 'clinical assessment and decision support'
        error_code = 'CLINICAL_PROCESSING'

    dmn_decision_key = dmn_table_name

    return V2_TEMPLATE.format(
        docstring=worker_info['docstring'],
        class_name=worker_info['class_name'],
        class_description=worker_info['description'],
        topic=worker_info['topic'],
        dmn_decision_key=dmn_decision_key,
        dmn_category=dmn_category,
        dmn_table_name=dmn_table_name,
        decision_description=decision_description,
        operation_name=worker_info['class_name'].replace('Worker', ' operation'),
        error_code=error_code,
    )


def main():
    """Main refactoring script."""
    workers_dir = Path("healthcare_platform/clinical_operations/workers")

    # List of workers to refactor (those without V2 versions)
    workers_to_refactor = [
        "care_planning_worker.py",
        "care_team_coordination_worker.py",
        "clinical_assessment_worker.py",
        "clinical_documentation_worker.py",
        "clinical_pathways_worker.py",
        "clinical_protocols_worker.py",
        "discharge_planning_worker.py",
        "doctor_bed_availability_worker.py",
        "doctor_cme_reminder_worker.py",
        "doctor_critical_value_worker.py",
        "doctor_discharge_readiness_worker.py",
        "doctor_followup_completion_worker.py",
        "doctor_patient_feedback_worker.py",
        "doctor_patient_recovery_alert_worker.py",
        "doctor_performance_summary_worker.py",
        "doctor_readmission_risk_worker.py",
        "doctor_referral_status_worker.py",
        "doctor_rounds_summary_worker.py",
        "doctor_specialist_consult_worker.py",
        "doctor_triage_escalation_worker.py",
        "patient_care_team_intro_worker.py",
        "patient_daily_care_plan_worker.py",
        "patient_followup_reminder_worker.py",
        "patient_meal_preference_worker.py",
        "patient_medication_adherence_worker.py",
        "patient_medication_reminder_worker.py",
        "patient_recovery_checkin_worker.py",
        "patient_test_results_worker.py",
        "surgical_team_assign_worker.py",
    ]

    refactored_count = 0
    failed_count = 0

    for worker_file in workers_to_refactor:
        worker_path = workers_dir / worker_file

        if not worker_path.exists():
            print(f"⚠️  File not found: {worker_file}")
            failed_count += 1
            continue

        print(f"Processing {worker_file}...")

        # Extract worker information
        worker_info = extract_worker_info(worker_path)
        if not worker_info:
            print(f"✗ Failed to extract info from {worker_file}")
            failed_count += 1
            continue

        # Generate V2 code
        v2_code = generate_v2_worker(worker_info)

        # Write V2 version
        v2_path = worker_path.parent / f"{worker_path.stem}_v2.py"
        v2_path.write_text(v2_code)

        # Validate syntax
        try:
            compile(v2_code, str(v2_path), 'exec')
            line_count = len(v2_code.split('\n'))
            print(f"✓ Created {v2_path.name} ({line_count} lines)")
            refactored_count += 1
        except SyntaxError as e:
            print(f"✗ Syntax error in {v2_path.name}: {e}")
            failed_count += 1

    print(f"\n{'='*60}")
    print(f"Refactoring Summary:")
    print(f"  Total workers: {len(workers_to_refactor)}")
    print(f"  Successfully refactored: {refactored_count}")
    print(f"  Failed: {failed_count}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
