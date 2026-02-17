"""Surgeon Preference Card Worker V2 - DMN-based preference management.

TOPIC: surgical.preference_card | BPMN Error: SURGICAL_OPERATIONS_ERROR
DMN: surgical/preference_setup_001, surgical/setup_time_calculation_001
ADR: 002, 003, 007, 013 | Refactored 321 -> ~120 LOC
Archetype: DATA_ENRICHMENT
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


class SurgeonPreferenceCardWorker(BaseExternalTaskWorker):
    """V2 surgeon preference card worker (thin worker pattern).

    Responsibilities:
    1. Parse surgeon preferences and procedure requirements
    2. Build setup checklist via DMN
    3. Calculate estimated setup time via DMN
    4. Generate preparation notes
    5. Return structured output for BPMN routing

    All orchestration handled by BPMN.
    All business rules handled by DMN.
    """

    TOPIC = "surgical.preference_card"
    DMN_SETUP_KEY = "preference_setup_checklist_001"
    DMN_TIME_KEY = "setup_time_estimation_001"
    DMN_CATEGORY = "surgical"

    def execute(self, context: TaskContext) -> TaskResult:
        """Execute surgeon preference card processing with DMN-based setup."""
        try:
            variables = context.variables
            correlation_id = variables.get('process_instance_id', '')
            surgery_id = variables.get("surgery_id", "")
            surgeon_id = variables.get("surgeon_id", "")
            procedure_code = variables.get("procedure_code", "")
            patient_position = variables.get("patient_position", "supine")
            preferred_instruments = variables.get("preferred_instruments", [])
            preferred_sutures = variables.get("preferred_sutures", [])
            preferred_supplies = variables.get("preferred_supplies", [])

            self.logger.info(
                "Processing surgeon preference card",
                extra={"correlation_id": correlation_id, "tenant_id": context.tenant_id,
                       "surgery_id": surgery_id, "surgeon_id": surgeon_id},
            )

            # Count items
            instrument_count = len(preferred_instruments)
            suture_count = len(preferred_sutures)
            supply_count = len(preferred_supplies)

            # 1. Build setup checklist via DMN
            setup_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_SETUP_KEY,
                variables={
                    "procedureCode": procedure_code,
                    "instrumentCount": instrument_count,
                    "sutureCount": suture_count,
                    "supplyCount": supply_count,
                },
                category=self.DMN_CATEGORY,
            )

            setup_checklist = []
            for item in preferred_instruments:
                setup_checklist.append({
                    "category": "instrument",
                    "item": item.get("item_name", ""),
                    "quantity": item.get("quantity", 1),
                    "status": "pending",
                })
            for item in preferred_sutures:
                setup_checklist.append({
                    "category": "suture",
                    "item": item.get("item_name", ""),
                    "quantity": item.get("quantity", 1),
                    "status": "pending",
                })
            for item in preferred_supplies:
                setup_checklist.append({
                    "category": "supply",
                    "item": item.get("item_name", ""),
                    "quantity": item.get("quantity", 1),
                    "status": "pending",
                })

            # 2. Calculate estimated setup time via DMN
            time_result = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_TIME_KEY,
                variables={
                    "instrumentCount": instrument_count,
                    "sutureCount": suture_count,
                    "supplyCount": supply_count,
                    "procedureComplexity": setup_result.get("complexity", "medium"),
                },
                category=self.DMN_CATEGORY,
            )

            estimated_setup_time = time_result.get("estimatedMinutes", 15)

            # 3. Generate preparation notes
            preparation_notes = [
                f"Position patient: {patient_position.replace('_', ' ').title()}",
                f"Prepare {instrument_count} instruments, {suture_count} sutures, {supply_count} supplies",
                setup_result.get("preparationNote", "Standard surgical preparation"),
            ]

            # Generate card ID
            card_id = f"PREF-{surgeon_id}-{procedure_code}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

            return TaskResult.success({
                "card_id": card_id,
                "surgery_id": surgery_id,
                "surgeon_id": surgeon_id,
                "procedure_code": procedure_code,
                "setup_checklist": setup_checklist,
                "preparation_notes": preparation_notes,
                "estimated_setup_time_minutes": estimated_setup_time,
                "card_timestamp": datetime.utcnow().isoformat(),
                "correlation_id": correlation_id,
            })

        except Exception as e:
            self.logger.error(f"Surgeon preference card processing failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="SURGICAL_OPERATIONS_ERROR",
                error_message=str(e),
                variables={"errorType": type(e).__name__},
            )
