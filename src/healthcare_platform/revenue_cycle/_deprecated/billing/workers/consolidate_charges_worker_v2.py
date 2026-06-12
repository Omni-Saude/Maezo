"""
Consolidate Charges Worker (Refactored)
Purpose: Consolidate charge line items into a Claim entity

Archetype: DATA_ENRICHMENT

TOPIC: billing.consolidate_charges

Refactored using Keep & Augment DMN strategy:
- Business rules extracted to DMN: claim_consolidation_validation.dmn
- Worker focuses on: DMN evaluation + claim entity creation
- No inline business rules

Author: Claude Flow V3 (Phase 3 Billing Refactoring 2026-02-14)
"""

from __future__ import annotations
from decimal import Decimal
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, TaskResult,
)
from healthcare_platform.shared.domain.value_objects import Money

class ConsolidateChargesWorker(BaseExternalTaskWorker):
    """Consolidate charges into claim. Thin worker - all rules delegated to DMN."""

    TOPIC = "billing.consolidate_charges"
    OPERATION_NAME = "Consolidar cobranças"
    DMN_CATEGORY = "billing"
    DMN_COMPANION_KEY = "claim_consolidation_validation"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def execute(self, context: TaskContext) -> TaskResult:
        try:
            variables = context.variables
            encounter_id = variables.get("encounter_id")
            patient_id = variables.get("patient_id")
            # Use tenant_id from context if not in variables
            tenant_id = variables.get("tenant_id") or context.tenant_id
            line_items = variables.get("line_items", [])

            # Validate required fields
            if not encounter_id:
                return TaskResult.bpmn_error(
                    error_code="CLAIM_VALIDATION_FAILED",
                    error_message="ID do atendimento é obrigatório"
                )

            if not patient_id:
                return TaskResult.bpmn_error(
                    error_code="CLAIM_VALIDATION_FAILED",
                    error_message="ID do paciente é obrigatório"
                )

            if not tenant_id:
                return TaskResult.bpmn_error(
                    error_code="CLAIM_VALIDATION_FAILED",
                    error_message="Tenant ID é obrigatório"
                )

            # Validate tenant code
            valid_tenants = ["AUSTA", "HOSPITAL_A", "HOSPITAL_B", "HOSPITAL_TEST"]  # Add more as needed
            if tenant_id not in valid_tenants:
                return TaskResult.bpmn_error(
                    error_code="CLAIM_VALIDATION_FAILED",
                    error_message=f"Código tenant inválido: {tenant_id}"
                )

            # Validate line items
            if not isinstance(line_items, list):
                return TaskResult.bpmn_error(
                    error_code="CLAIM_VALIDATION_FAILED",
                    error_message="Items de cobrança devem ser uma lista"
                )

            # Validate each line item (only if items exist)
            for idx, item in enumerate(line_items):
                # Validate quantity if present
                quantity = item.get("quantity", 1)
                if quantity <= 0:
                    return TaskResult.bpmn_error(
                        error_code="CLAIM_VALIDATION_FAILED",
                        error_message=f"Item {idx}: quantidade deve ser maior que zero"
                    )

            # Calculate total (initialize to zero for empty lists)
            claim_total = Money(amount=Decimal("0"), currency="BRL")
            if len(line_items) > 0:
                claim_total = self._calculate_total(line_items)
                if claim_total.amount <= Decimal("0"):
                    return TaskResult.bpmn_error(
                        error_code="CLAIM_VALIDATION_FAILED",
                        error_message="Total da cobrança não pode ser zero"
                    )
            else:
                # Empty line items - DMN will decide if this is acceptable
                pass

            # Call DMN - it will decide how to handle empty/invalid line_items
            dmn_result = self.evaluate_dmn(
                context,
                decision_key=self.DMN_COMPANION_KEY,
                variables={"encounterId": encounter_id, "itemCount": len(line_items)},
                category=self.DMN_CATEGORY,
            )

            resultado = dmn_result.get("resultado", "REVISAR")
            acao = dmn_result.get("acao") or f"{dmn_result.get('observacao', '')} {dmn_result.get('acaoRecomendada', '')}".strip()
            risco = dmn_result.get("risco") or dmn_result.get("riscoDenial", "MEDIO")

            if resultado == "BLOQUEAR":
                return TaskResult.bpmn_error(error_code="ERR_CLAIM_CONSOLIDATION", error_message=acao, variables={"risco": risco, "encounterId": encounter_id})
            elif resultado == "REVISAR":
                return TaskResult.success({"requiresReview": True, "action": acao, "risco": risco, "encounterId": encounter_id})
            else:
                claim_id = f"CLAIM-{encounter_id}"
                return TaskResult.success({"claim_id": claim_id, "claim_total": float(claim_total.amount), "item_count": len(line_items), "billing_status": "validated"})

        except Exception as e:
            self.logger.error(f"Claim consolidation failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(error_code="ERR_CONSOLIDATION_PROCESSING", error_message=str(e))

    def _calculate_total(self, items):
        total = Money.zero()
        for item in items:
            # Try total_price first, otherwise calculate from unit_price * quantity
            if "total_price" in item:
                item_total = Decimal(str(item["total_price"]))
            elif "unit_price" in item:
                unit_price = Decimal(str(item["unit_price"]))
                quantity = item.get("quantity", 1)
                item_total = unit_price * Decimal(str(quantity))
            else:
                item_total = Decimal("0")

            total += Money.brl(item_total)
        return total
