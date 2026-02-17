"""Surgical Equipment Worker V2 - DMN-based equipment validation.

TOPIC: surgical.equipment_check | BPMN Error: SURGICAL_OPERATIONS_ERROR
DMN: surgical/equipment_availability_001, surgical/sterilization_validation_001
ADR: 002, 003, 007, 013 | Refactored 263 -> ~135 LOC
Archetype: COMPLIANCE_VALIDATION
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List

from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


class SurgicalEquipmentWorker(BaseExternalTaskWorker):
    """V2 surgical equipment worker (thin worker pattern).

    Responsibilities:
    1. Parse required equipment list
    2. Check availability via DMN
    3. Validate sterilization status via DMN
    4. Determine equipment readiness
    5. Return structured output for BPMN routing

    All orchestration handled by BPMN.
    All business rules handled by DMN.
    """

    TOPIC = "surgical.equipment_check"
    DMN_AVAILABILITY_KEY = "equipment_availability_check_001"
    DMN_STERILIZATION_KEY = "sterilization_status_validation_001"
    DMN_CATEGORY = "surgical"

    def execute(self, context: TaskContext) -> TaskResult:
        """Execute equipment check with DMN-based validation."""
        try:
            variables = context.variables
            correlation_id = variables.get('process_instance_id', '')
            surgery_id = variables.get("surgery_id", "")
            operating_room_id = variables.get("operating_room_id", "")
            required_equipment = variables.get("required_equipment", [])

            self.logger.info(
                "Processing surgical equipment check",
                extra={"correlation_id": correlation_id, "tenant_id": context.tenant_id,
                       "surgery_id": surgery_id, "equipment_count": len(required_equipment)},
            )

            all_equipment_available = True
            all_sterilization_valid = True
            missing_equipment: List[str] = []
            expired_sterilization: List[str] = []

            for equipment in required_equipment:
                equipment_id = equipment.get("equipment_id", "")
                equipment_name = equipment.get("name", "")
                sterilization_status = equipment.get("sterilization_status", "")
                expiration_date = equipment.get("expiration_date", "")

                # 1. Check availability via DMN
                availability_result = self.evaluate_dmn(
                    context=context,
                    decision_key=self.DMN_AVAILABILITY_KEY,
                    variables={
                        "equipmentId": equipment_id,
                        "equipmentName": equipment_name,
                        "available": equipment.get("available", False),
                    },
                    category=self.DMN_CATEGORY,
                )

                if not availability_result.get("isAvailable", False):
                    all_equipment_available = False
                    missing_equipment.append(equipment_name)

                # 2. Validate sterilization via DMN
                sterilization_result = self.evaluate_dmn(
                    context=context,
                    decision_key=self.DMN_STERILIZATION_KEY,
                    variables={
                        "sterilizationStatus": sterilization_status,
                        "expirationDate": expiration_date,
                        "currentDate": datetime.utcnow().isoformat(),
                    },
                    category=self.DMN_CATEGORY,
                )

                if not sterilization_result.get("isValid", False):
                    all_sterilization_valid = False
                    if sterilization_result.get("isExpired", False):
                        expired_sterilization.append(equipment_name)

            # Overall readiness
            equipment_ready = all_equipment_available and all_sterilization_valid

            # WHO Time Out equipment confirmation
            who_timeout_equipment_confirmed = (
                equipment_ready and variables.get("who_checklist_phase") == "time_out"
            )

            # Generate check ID
            check_id = f"EQP-{surgery_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

            return TaskResult.success({
                "check_id": check_id,
                "surgery_id": surgery_id,
                "operating_room_id": operating_room_id,
                "all_equipment_available": all_equipment_available,
                "all_sterilization_valid": all_sterilization_valid,
                "equipment_ready": equipment_ready,
                "missing_equipment": missing_equipment,
                "expired_sterilization": expired_sterilization,
                "who_timeout_equipment_confirmed": who_timeout_equipment_confirmed,
                "check_timestamp": datetime.utcnow().isoformat(),
                "correlation_id": correlation_id,
            })

        except Exception as e:
            self.logger.error(f"Equipment check failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="SURGICAL_OPERATIONS_ERROR",
                error_message=str(e),
                variables={"errorType": type(e).__name__},
            )
