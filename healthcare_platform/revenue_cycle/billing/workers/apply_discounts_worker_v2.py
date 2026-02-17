"""
Apply Discounts Worker (Refactored)
Purpose: Apply contractual discounts to billing line items

TOPIC: billing.apply_discounts

Refactored using Keep & Augment DMN strategy:
- Business rules extracted to DMN: discount_rules_validation.dmn
- Worker focuses on: DMN evaluation + discount calculations
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

class ApplyDiscountsWorker(BaseExternalTaskWorker):
    """Apply discounts to line items. Thin worker - all rules delegated to DMN."""

    TOPIC = "billing.apply_discounts"
    OPERATION_NAME = "Aplicar descontos contratuais"
    DMN_CATEGORY = "billing"
    DMN_COMPANION_KEY = "discount_rules_validation"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def execute(self, context: TaskContext) -> TaskResult:
        try:
            variables = context.variables
            line_items = variables.get("line_items")
            discount_rules = variables.get("discount_rules", [])

            # Validate required inputs
            if line_items is None:
                return TaskResult.bpmn_error(
                    error_code="ERR_MISSING_LINE_ITEMS",
                    error_message="line_items is required",
                )

            if not isinstance(line_items, list):
                return TaskResult.bpmn_error(
                    error_code="ERR_INVALID_LINE_ITEMS",
                    error_message="line_items must be a list",
                )

            # Validate each line item has required fields
            for idx, item in enumerate(line_items):
                if "total_price" not in item:
                    return TaskResult.bpmn_error(
                        error_code="ERR_MISSING_TOTAL_PRICE",
                        error_message=f"Item {idx} missing total_price",
                    )
                try:
                    Decimal(str(item["total_price"]))
                except (ValueError, TypeError):
                    return TaskResult.bpmn_error(
                        error_code="ERR_INVALID_TOTAL_PRICE",
                        error_message=f"Item {idx} has invalid total_price",
                    )

            # Validate discount rules
            for rule in discount_rules:
                pct = Decimal(str(rule.get("percentage", 0)))
                if pct > Decimal("100"):
                    return TaskResult.bpmn_error(
                        error_code="ERR_INVALID_DISCOUNT",
                        error_message=f"Discount percentage cannot exceed 100%",
                    )

            dmn_result = self.evaluate_dmn(
                context,
                decision_key=self.DMN_COMPANION_KEY,
                variables={
                    "discountRules": discount_rules,
                    "itemCount": len(line_items),
                },
                category=self.DMN_CATEGORY,
            )

            resultado = dmn_result.get("resultado", "REVISAR")
            acao = dmn_result.get("acao") or f"{dmn_result.get('observacao', '')} {dmn_result.get('acaoRecomendada', '')}".strip()
            risco = dmn_result.get("risco") or dmn_result.get("riscoDenial", "MEDIO")

            if resultado == "BLOQUEAR":
                return TaskResult.bpmn_error(
                    error_code="ERR_DISCOUNT_VIOLATION",
                    error_message=acao,
                    variables={"risco": risco},
                )
            elif resultado == "REVISAR":
                return TaskResult.success({
                    "requiresReview": True,
                    "action": acao,
                    "risco": risco,
                })
            else:
                discounted_items = self._apply_discounts(line_items, discount_rules)
                total_discount, final_amount, original_amount = self._calculate_totals(discounted_items)

                # Calculate discount percentage
                discount_pct = Decimal("0")
                if original_amount.amount > Decimal("0"):
                    discount_pct = (total_discount.amount / original_amount.amount) * Decimal("100")

                return TaskResult.success({
                    "discounted_items": discounted_items,
                    "total_discount": str(total_discount.amount),
                    "final_amount": str(final_amount.amount),
                    "original_amount": str(original_amount.amount),
                    "discount_percentage": str(discount_pct),
                })

        except Exception as e:
            self.logger.error(f"Discount application failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="ERR_DISCOUNT_PROCESSING",
                error_message=str(e),
            )

    def _apply_discounts(self, items, rules):
        discounted = []
        for item in items:
            total_price = Money.brl(Decimal(str(item.get("total_price", 0))))
            discount_amt = Money.zero()
            applied_discounts = []

            # Apply each rule and track details
            for rule in rules:
                # Check rule conditions
                if not self._rule_applies(item, rule):
                    continue

                pct = Decimal(str(rule.get("percentage", 0)))
                rule_discount = total_price * (pct / Decimal("100"))

                # Apply volume-based bonus for volume discounts
                if rule.get("type") == "volume":
                    quantity = item.get("quantity", 1)
                    bonus = self._calculate_volume_bonus(quantity)
                    rule_discount = rule_discount * (Decimal("1") + bonus)

                discount_amt += rule_discount
                applied_discounts.append({
                    "type": rule.get("type", "unknown"),
                    "percentage": str(pct),
                    "amount": str(rule_discount.amount),
                })

            final = total_price - discount_amt
            if final.amount < Decimal("0"):
                final = Money.zero()

            discounted.append({
                **item,
                "original_price": str(total_price.amount),
                "discount_amount": str(discount_amt.amount),
                "final_price": str(final.amount),
                "applied_discounts": applied_discounts,
            })
        return discounted

    def _rule_applies(self, item, rule):
        """Check if a discount rule applies to an item."""
        conditions = rule.get("conditions", {})

        # Check procedure code condition
        if "procedure_code" in conditions:
            required_code = conditions["procedure_code"]
            item_code = item.get("code", "")

            # Support wildcard matching
            if "*" in required_code:
                prefix = required_code.replace("*", "")
                if not item_code.startswith(prefix):
                    return False
            elif item_code != required_code:
                return False

        # Check minimum quantity condition
        if "min_quantity" in conditions:
            min_qty = int(conditions["min_quantity"])
            item_qty = item.get("quantity", 1)
            if item_qty < min_qty:
                return False

        return True

    def _calculate_volume_bonus(self, quantity):
        """Calculate volume-based discount bonus."""
        if quantity >= 100:
            return Decimal("0.50")  # 50% bonus
        elif quantity >= 50:
            return Decimal("0.30")  # 30% bonus
        elif quantity >= 20:
            return Decimal("0.15")  # 15% bonus
        return Decimal("0")  # No bonus

    def _calculate_totals(self, items):
        total_discount = Money.zero()
        final_amount = Money.zero()
        original_amount = Money.zero()
        for item in items:
            total_discount += Money.brl(Decimal(item["discount_amount"]))
            final_amount += Money.brl(Decimal(item["final_price"]))
            original_amount += Money.brl(Decimal(item["original_price"]))
        return total_discount, final_amount, original_amount
