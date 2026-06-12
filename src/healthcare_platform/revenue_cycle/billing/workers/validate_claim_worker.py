"""
Validate Claim Worker (Refactored)
Purpose: Pre-submission validation of claim data

TOPIC: billing.validate_claim

Refactored using Keep & Augment DMN strategy:
- Business rules extracted to DMN: claim_validation.dmn
- Worker focuses on: DMN evaluation + validation orchestration
- No inline business rules

Author: Claude Flow V3 (Phase 3 Billing Refactoring 2026-02-14)
"""

from __future__ import annotations
from typing import Dict, List
from decimal import Decimal
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, TaskResult,
)

class ValidateClaimWorker(BaseExternalTaskWorker):
    """Valida dados da conta antes da submissão. Thin worker - regras delegadas ao DMN."""

    TOPIC = "billing.validate_claim"
    OPERATION_NAME = "Validar reivindicação"
    DMN_CATEGORY = "billing"
    DMN_COMPANION_KEY = "claim_validation"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def execute(self, context: TaskContext) -> TaskResult:
        try:
            variables = context.variables
            encounter = variables.get("encounter", "")
            patient = variables.get("patient", "")
            procedure_list = variables.get("procedureList", [])
            claim_id = encounter
            claim_data = {
                "patient_id": patient,
                "payer_id": variables.get("payer", ""),
                "items": procedure_list,
                "total": {"amount": 0},
            }

            if not claim_id:
                return TaskResult.bpmn_error(
                    error_code="CLAIM_VALIDATION_FAILED",
                    error_message="ID do encontro não fornecido",
                )

            if not patient and not procedure_list:
                return TaskResult.bpmn_error(
                    error_code="CLAIM_VALIDATION_FAILED",
                    error_message="Dados do encontro não fornecidos",
                )

            # Collect validation errors
            errors: List[str] = []
            self._validate_required_fields(claim_data, errors)
            self._validate_guide_type(claim_data, errors)
            self._validate_items(claim_data, errors)
            self._validate_price_consistency(claim_data, errors)
            self._validate_total(claim_data, errors)
            self._validate_duplicates(claim_data, errors)
            self._validate_authorization(claim_data, errors)

            # Evaluate companion DMN (ADMIN_ADJUDICATION 3-output)
            dmn_result = self.evaluate_dmn(
                context,
                decision_key=self.DMN_COMPANION_KEY,
                variables={
                    "claimId": claim_id,
                    "itemCount": len(claim_data.get("items", [])),
                    "totalAmount": float(claim_data.get("total", {}).get("amount", 0)),
                    "validationErrors": errors,
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
                    error_code="ERR_VALIDATION_FAILED",
                    error_message=acao,
                    variables={
                        "risco": risco,
                        "validation_errors": errors,
                        "validation_passed": False,
                        "claim_ready_for_submission": False,
                    },
                )
            elif resultado == "REVISAR":
                return TaskResult.success({
                    "requiresReview": True,
                    "action": acao,
                    "risco": risco,
                    "validation_passed": False,
                    "validation_errors": errors,
                    "claim_ready_for_submission": False,
                })
            else:  # PROSSEGUIR
                validation_passed = len(errors) == 0
                return TaskResult.success({
                    "validation_passed": validation_passed,
                    "validation_errors": errors,
                    "claim_ready_for_submission": validation_passed,
                    "validationResult": validation_passed,
                    "validationErrors": errors,
                })

        except Exception as e:
            self.logger.error(f"Validation failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="ERR_VALIDATION_EXCEPTION",
                error_message=str(e),
            )

    def _validate_required_fields(self, claim: Dict, errors: List[str]) -> None:
        """Validate required fields presence."""
        required_fields = ["patient_id", "payer_id", "items", "total"]
        for field in required_fields:
            if not claim.get(field):
                errors.append(f"Campo obrigatório ausente: {field}")

    def _validate_guide_type(self, claim: Dict, errors: List[str]) -> None:
        """Validate TISS guide type."""
        valid_types = ["sp_sadt", "admission", "hospitalization", "emergency"]
        guide_type = claim.get("tiss_guide_type")
        if guide_type and guide_type not in valid_types:
            errors.append(f"Tipo de guia TISS inválido: {guide_type}")

    def _validate_items(self, claim: Dict, errors: List[str]) -> None:
        """Validate claim items structure."""
        items = claim.get("items", [])
        if not isinstance(items, list):
            errors.append("Items deve ser uma lista")
            return
        if len(items) == 0:
            errors.append("Pelo menos um item é obrigatório")
            return

        for idx, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                errors.append(f"Item {idx} deve ser um dicionário")
                continue

            # sequence is optional - can be auto-generated during submission
            if "procedure_code" not in item:
                errors.append(f"Item {idx}: código do procedimento ausente")
            if "quantity" not in item or not isinstance(item.get("quantity"), int) or item.get("quantity", 0) < 1:
                errors.append(f"Item {idx}: quantidade inválida")

    def _validate_price_consistency(self, claim: Dict, errors: List[str]) -> None:
        """Validate price consistency for items."""
        items = claim.get("items", [])
        for idx, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            unit_price = item.get("unit_price")
            quantity = item.get("quantity")
            total_price = item.get("total_price")

            if unit_price is not None and quantity is not None and total_price is not None:
                expected_total = Decimal(str(unit_price)) * Decimal(str(quantity))
                actual_total = Decimal(str(total_price))
                if abs(expected_total - actual_total) > Decimal("0.01"):
                    errors.append(f"Item {idx}: preço total inconsistente (esperado: {expected_total}, atual: {actual_total})")

    def _validate_total(self, claim: Dict, errors: List[str]) -> None:
        """Validate claim total matches sum of items."""
        items = claim.get("items", [])
        total_amount = claim.get("total", {}).get("amount")

        if total_amount is not None and items:
            # Only validate if items have total_price
            items_with_price = [item for item in items if isinstance(item, dict) and "total_price" in item]
            if items_with_price:
                items_sum = sum(Decimal(str(item.get("total_price", 0))) for item in items_with_price)
                claim_total = Decimal(str(total_amount))
                if abs(items_sum - claim_total) > Decimal("0.01"):
                    errors.append(f"Total da fatura não corresponde à soma dos itens (soma: {items_sum}, total: {claim_total})")

    def _validate_duplicates(self, claim: Dict, errors: List[str]) -> None:
        """Validate no duplicate items."""
        items = claim.get("items", [])
        seen_procedures = {}
        for idx, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            proc_code = item.get("procedure_code", {})
            if isinstance(proc_code, dict):
                code = proc_code.get("code")
            else:
                code = str(proc_code)

            if code:
                if code in seen_procedures:
                    errors.append(f"Item duplicado: procedimento {code} aparece nos itens {seen_procedures[code]} e {idx}")
                else:
                    seen_procedures[code] = idx

    def _validate_authorization(self, claim: Dict, errors: List[str]) -> None:
        """Validate authorization for admission/hospitalization."""
        guide_type = claim.get("tiss_guide_type")
        if guide_type in ["admission", "hospitalization"]:
            items = claim.get("items", [])
            for idx, item in enumerate(items, start=1):
                if not isinstance(item, dict):
                    continue
                if "authorization_reference" not in item:
                    errors.append(f"Item {idx}: autorização obrigatória para guias de internação")
