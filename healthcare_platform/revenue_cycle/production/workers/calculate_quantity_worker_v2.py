"""Calculate billable quantities for clinical procedures (Refactored).

TOPIC: production.calculate_quantity
ARCHETYPE: ADMIN_ADJUDICATION
DMN: pricing/quantity/quantity_calculation_adjudication

Refactored: replaced inline duration/max-qty rules with DMN call.

ADR Compliance:
- ADR-002: Tenant resolution via context
- ADR-003: BaseExternalTaskWorker inheritance
- ADR-007: DMN federation for tenant overrides
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict

from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


class CalculateQuantityWorker(BaseExternalTaskWorker):
    """Calculates billable quantity for each procedure using DMN rules.

    DMN handles: duration-based calculation, max quantity limits, method selection.
    Worker handles: input parsing, datetime math, result assembly.
    """

    TOPIC = "revenue_cycle.production.calculate_value"
    DMN_DECISION_KEY = "quantity_calculation_adjudication"
    DMN_CATEGORY = "pricing"

    def execute(self, context: TaskContext) -> TaskResult:
        """Calculate billable quantity for procedures."""
        try:
            variables = context.variables
            procedures = variables.get("enriched_procedures", [])
            encounter_start_str = variables.get("encounter_start")
            encounter_end_str = variables.get("encounter_end")

            if not procedures:
                return TaskResult.bpmn_error(
                    error_code="CODING_ERROR",
                    error_message="No procedures to calculate quantity",
                )

            duration_minutes = self._calc_duration(encounter_start_str, encounter_end_str)

            self.logger.info(
                f"Calculating quantities: {len(procedures)} procedures",
                extra={"tenant_id": context.tenant_id, "duration_minutes": duration_minutes},
            )

            quantified = []
            total_items = 0

            for proc in procedures:
                code = proc.get("code", "")
                existing_qty = proc.get("quantity", 1)

                dmn_result = self.evaluate_dmn(
                    context=context,
                    decision_key=self.DMN_DECISION_KEY,
                    variables={
                        "procedureCode": code,
                        "existingQuantity": existing_qty,
                        "durationMinutes": duration_minutes,
                    },
                    category=self.DMN_CATEGORY,
                )

                resultado = dmn_result.get("resultado", "PROSSEGUIR")
                calculated_qty = dmn_result.get("quantity", max(1, existing_qty))
                method = dmn_result.get("quantityMethod", "direct")
                capped = dmn_result.get("quantityCapped", False)

                if resultado == "BLOQUEAR":
                    return TaskResult.bpmn_error(
                        error_code="CODING_ERROR",
                        error_message=dmn_result.get("acao", f"Quantity blocked for {code}"),
                        variables={"blockedCode": code},
                    )

                result_proc = {**proc}
                result_proc["quantity"] = calculated_qty
                result_proc["quantity_method"] = method
                result_proc["quantity_capped"] = capped
                if duration_minutes is not None:
                    result_proc["duration_minutes"] = duration_minutes

                total_items += calculated_qty
                quantified.append(result_proc)

            return TaskResult.success({
                "quantified_procedures": quantified,
                "total_items": total_items,
            })

        except Exception as e:
            self.logger.error(f"Quantity calculation failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="CODING_ERROR",
                error_message=str(e),
            )

    def _calc_duration(self, start_str: str | None, end_str: str | None) -> float | None:
        """Calculate encounter duration in minutes."""
        if not start_str or not end_str:
            return None
        try:
            start = datetime.fromisoformat(start_str)
            end = datetime.fromisoformat(end_str)
            return (end - start).total_seconds() / 60
        except ValueError:
            return None
