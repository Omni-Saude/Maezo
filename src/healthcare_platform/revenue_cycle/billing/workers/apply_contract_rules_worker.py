"""
Apply Contract Rules Worker (Refactored)
Purpose: Apply payer-specific contract rules to billing claims

TOPIC: billing.apply_contract_rules

Refactored using Keep & Augment DMN strategy:
- Business rules extracted to DMN: contract_rules_validation.dmn
- Worker focuses on: DMN evaluation + contract adjustments
- No inline business rules

Author: Claude Flow V3 (Phase 3 Billing Refactoring 2026-02-14)
"""

from __future__ import annotations
from decimal import Decimal
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, TaskResult,
)
from healthcare_platform.shared.domain.value_objects import Money

class ApplyContractRulesWorker(BaseExternalTaskWorker):
    """Apply contract rules to claims. Thin worker - all rules delegated to DMN."""

    TOPIC = "billing.apply_contract_rules"
    OPERATION_NAME = "Aplicar regras contratuais"
    DMN_CATEGORY = "billing"
    DMN_COMPANION_KEY = "contract_rules_validation"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def execute(self, context: TaskContext) -> TaskResult:
        try:
            variables = context.variables
            charges = variables.get("charges")
            payer = variables.get("payer")
            contract = variables.get("contract")
            # TODO: modifier_rules sera aplicado na logica de modificadores de cobranca
            # modifier_rules = variables.get("modifierRules", [])
            # TODO: bundling_rules sera aplicado na logica de agrupamento de procedimentos
            # bundling_rules = variables.get("bundlingRules", [])
            procedures = variables.get("procedures", [])
            claim_id = charges
            # TODO: payer_id sera usado na consulta de regras contratuais da operadora
            # payer_id = payer
            contract_rules = contract if isinstance(contract, dict) else {}

            # Evaluate companion DMN (ADMIN_ADJUDICATION 3-output)
            dmn_result = self.evaluate_dmn(
                context,
                decision_key=self.DMN_COMPANION_KEY,
                variables={
                    "payerId": payer,
                    "contractRules": contract,
                    "procedureCount": len(procedures or []),
                },
                category=self.DMN_CATEGORY,
            )

            # Normalize DMN response (handle both 3-output and legacy 5-output)
            resultado = dmn_result.get("resultado", "REVISAR")
            acao = dmn_result.get("acao") or f"{dmn_result.get('observacao', '')} {dmn_result.get('acaoRecomendada', '')}".strip()
            risco = dmn_result.get("risco") or dmn_result.get("riscoDenial", "MEDIO")

            # Route based on resultado
            if resultado == "BLOQUEAR":
                return TaskResult.bpmn_error(
                    error_code="ERR_CONTRACT_VIOLATION",
                    error_message=acao,
                    variables={"risco": risco, "claimId": claim_id},
                )
            elif resultado == "REVISAR":
                return TaskResult.success({
                    "requiresReview": True,
                    "action": acao,
                    "risco": risco,
                    "claimId": claim_id,
                })
            else:  # PROSSEGUIR
                # Apply contract adjustments
                adjusted_items = self._apply_rules(procedures, contract_rules)
                total_patient, total_payer = self._calculate_responsibilities(adjusted_items)
                total_charges = total_patient + total_payer

                return TaskResult.success({
                    "adjusted_items": adjusted_items,
                    "adjustedCharges": adjusted_items,
                    "total_patient_responsibility": str(total_patient.amount),
                    "total_payer_responsibility": str(total_payer.amount),
                    "total_charges": str(total_charges.amount),
                    "applied_rules": contract_rules,
                    "claimId": claim_id,
                })

        except Exception as e:
            self.logger.error(f"Contract rules application failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="ERR_CONTRACT_PROCESSING",
                error_message=str(e),
            )

    def _apply_rules(self, procedures, rules):
        """Apply contract rules to procedures."""
        copay_pct = Decimal(str(rules.get("copay_pct", 0)))
        deductible = Money.brl(Decimal(str(rules.get("deductible", 0))))
        coverage_limit = Money.brl(Decimal(str(rules.get("coverage_limit", 0)))) if rules.get("coverage_limit") else None
        procedure_limits = rules.get("procedure_limits", {})
        remaining_deductible = deductible
        remaining_coverage = coverage_limit if coverage_limit else None
        adjusted = []

        for idx, proc in enumerate(procedures):
            unit_price = Money.brl(Decimal(str(proc.get("unit_price", 0))))
            quantity = int(proc.get("quantity", 1))
            base_line_total = unit_price * Decimal(str(quantity))

            # Apply procedure-specific limit if exists
            proc_code = proc.get("code")
            if proc_code and proc_code in procedure_limits:
                proc_limit = Money.brl(Decimal(str(procedure_limits[proc_code])))
                line_total = min(base_line_total, proc_limit)
            else:
                line_total = base_line_total

            copay = line_total * (copay_pct / Decimal("100"))
            deduct_applied = Money.zero()
            if remaining_deductible > Money.zero():
                deduct_applied = min(line_total, remaining_deductible)
                remaining_deductible -= deduct_applied

            # Calculate payer/patient before coverage limit
            payer_amt = line_total - copay - deduct_applied
            patient_amt = copay + deduct_applied

            # Apply coverage limit
            if remaining_coverage is not None:
                if payer_amt > remaining_coverage:
                    excess = payer_amt - remaining_coverage
                    payer_amt = remaining_coverage
                    patient_amt += excess
                remaining_coverage = max(Money.zero(), remaining_coverage - payer_amt)

            adjusted.append({
                "sequence": idx + 1,
                "code": proc_code,
                "line_total": str(line_total.amount),
                "copay_amount": str(copay.amount),
                "deductible_applied": str(deduct_applied.amount),
                "payer_responsibility": str(payer_amt.amount),
                "patient_responsibility": str(patient_amt.amount),
            })

        return adjusted

    def _calculate_responsibilities(self, items):
        """Calculate total patient and payer responsibilities."""
        total_patient = Money.zero()
        total_payer = Money.zero()

        for item in items:
            total_patient += Money.brl(Decimal(item["patient_responsibility"]))
            total_payer += Money.brl(Decimal(item["payer_responsibility"]))

        return total_patient, total_payer
