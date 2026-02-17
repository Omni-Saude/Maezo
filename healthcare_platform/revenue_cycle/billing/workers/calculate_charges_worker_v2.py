"""
Calculate Charges Worker (Refactored)
Purpose: Calculate billing charges for procedures with modifiers

TOPIC: billing.calculate_charges

Refactored using Keep & Augment DMN strategy:
- Business rules extracted to DMN: charge_calculation_validation.dmn
- Worker focuses on: DMN evaluation + charge calculations
- No inline business rules

Author: Claude Flow V3 (Phase 3 Billing Refactoring 2026-02-14)
"""

from __future__ import annotations
from decimal import Decimal
from typing import Any, Dict, Optional
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, TaskResult,
)
from healthcare_platform.shared.domain.value_objects import Money

class CalculateChargesWorker(BaseExternalTaskWorker):
    """Calculate charges for procedures. Thin worker - all rules delegated to DMN."""

    TOPIC = "billing.calculate_charges"
    OPERATION_NAME = "Calcular valores de cobrança"
    DMN_CATEGORY = "billing"
    DMN_COMPANION_KEY = "charge_calculation_validation"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def execute(self, context: TaskContext) -> TaskResult:
        try:
            variables = context.variables
            procedures = variables.get("procedures")
            modifiers = variables.get("modifiers", [])

            # Validate required inputs - basic checks only, DMN will route empty/invalid data
            if procedures is None:
                return TaskResult.bpmn_error(
                    error_code="ERR_MISSING_PROCEDURES",
                    error_message="procedures is required",
                )

            if not isinstance(procedures, list):
                return TaskResult.bpmn_error(
                    error_code="ERR_INVALID_PROCEDURES",
                    error_message="procedures must be a list",
                )

            # Validate each procedure (only if procedures exist)
            for idx, proc in enumerate(procedures):
                if "code" not in proc or not proc["code"]:
                    return TaskResult.bpmn_error(
                        error_code="ERR_MISSING_PROCEDURE_CODE",
                        error_message=f"Procedure {idx}: code is required",
                    )
                if "unit_price" not in proc:
                    return TaskResult.bpmn_error(
                        error_code="ERR_MISSING_UNIT_PRICE",
                        error_message=f"Procedure {idx}: unit_price is required",
                    )
                try:
                    Decimal(str(proc["unit_price"]))
                except (ValueError, TypeError):
                    return TaskResult.bpmn_error(
                        error_code="ERR_INVALID_UNIT_PRICE",
                        error_message=f"Procedure {idx}: invalid unit_price",
                    )

            # Call DMN first - it will decide how to handle empty procedures
            dmn_result = self.evaluate_dmn(
                context,
                decision_key=self.DMN_COMPANION_KEY,
                variables={"procedureCount": len(procedures), "modifierCount": len(modifiers)},
                category=self.DMN_CATEGORY,
            )

            resultado = dmn_result.get("resultado", "REVISAR")
            acao = dmn_result.get("acao") or f"{dmn_result.get('observacao', '')} {dmn_result.get('acaoRecomendada', '')}".strip()
            risco = dmn_result.get("risco") or dmn_result.get("riscoDenial", "MEDIO")

            if resultado == "BLOQUEAR":
                return TaskResult.bpmn_error(error_code="ERR_CHARGE_CALCULATION", error_message=acao, variables={"risco": risco})
            elif resultado == "REVISAR":
                return TaskResult.success({"requiresReview": True, "action": acao, "risco": risco})
            else:
                line_items = self._calculate_items(procedures, modifiers)
                total_amt, total_adj = self._calculate_totals(line_items)
                return TaskResult.success({"line_items": line_items, "total_amount": str(total_amt.amount), "modifier_adjustments": str(total_adj.amount)})

        except Exception as e:
            self.logger.error(f"Charge calculation failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(error_code="ERR_CHARGE_PROCESSING", error_message=str(e))

    def _calculate_items(self, procedures, modifiers):
        items = []
        for idx, proc in enumerate(procedures):
            unit_price = Money.brl(Decimal(str(proc.get("unit_price", 0))))
            quantity = int(proc.get("quantity", 1))
            base_amt = unit_price * Decimal(str(quantity))
            adjustment = Money.zero()
            applied_modifiers = []

            # Apply modifiers
            for mod in modifiers:
                # Check if modifier applies to this procedure
                applies_to = mod.get("applies_to")
                proc_code = proc.get("code")

                if applies_to is not None:
                    # Handle wildcard patterns (e.g., "101*" matches "10101012", "10101013")
                    if "*" in applies_to:
                        pattern = applies_to.replace("*", "")
                        if not proc_code.startswith(pattern):
                            continue
                    elif applies_to != proc_code:
                        continue

                mod_type = mod.get("type", "percentage")

                # Get modifier value with defaults for standard types
                if "value" in mod:
                    mod_value = Decimal(str(mod.get("value")))
                else:
                    # Default values for standard modifier types
                    default_values = {
                        "multiple_procedure": Decimal("-50"),  # -50%
                        "assistant_surgeon": Decimal("-30"),   # -30%
                        "bilateral": Decimal("50"),             # +50%
                        "repeat_procedure": Decimal("-25"),     # -25%
                    }
                    mod_value = default_values.get(mod_type, Decimal("0"))

                if mod_type == "percentage" or mod_type in ["multiple_procedure", "assistant_surgeon", "bilateral", "repeat_procedure"]:
                    mod_amt = base_amt * (mod_value / Decimal("100"))
                elif mod_type == "fixed":
                    mod_amt = Money.brl(mod_value)
                else:
                    mod_amt = Money.zero()

                adjustment += mod_amt
                applied_modifiers.append({
                    "code": mod.get("code"),
                    "type": mod_type,
                    "value": str(mod_value),
                    "amount": str(mod_amt.amount),
                })

            total = base_amt + adjustment
            # Ensure total never goes below zero
            if total.amount < Decimal("0"):
                total = Money.zero()

            items.append({
                "sequence": idx + 1,
                "code": proc.get("code"),
                "quantity": quantity,
                "unit_price": str(unit_price.amount),
                "base_amount": str(base_amt.amount),
                "adjustments": str(adjustment.amount),
                "total_price": str(total.amount),
                "applied_modifiers": applied_modifiers,
            })
        return items

    def _calculate_totals(self, items):
        total_amt = Money.zero()
        total_adj = Money.zero()
        for item in items:
            total_amt += Money.brl(Decimal(item["total_price"]))
            total_adj += Money.brl(Decimal(item["adjustments"]))
        return total_amt, total_adj
