"""Worker for applying contract rules to claims."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from healthcare_platform.revenue_cycle.billing.workers.base import BaseWorker, WorkerResult, worker
from healthcare_platform.shared.domain.exceptions import ContractRuleViolation
from healthcare_platform.shared.domain.value_objects import Money
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


@worker(topic="billing.apply_contract_rules", max_jobs=1, lock_duration=300000)
class ApplyContractRulesWorker(BaseWorker):
    """Applies contract rules to billing claims.

    This worker applies payer-specific contract rules including co-payments,
    deductibles, and coverage limits to determine patient and payer responsibilities.

    Input Variables:
        claim_id: str - Unique identifier for the claim
        payer_id: str - Health insurance payer identifier
        procedures: List[Dict] - List of procedures with pricing
        contract_rules: Dict - Contract rules with:
            - copay_pct: Decimal - Co-payment percentage (0-100)
            - deductible: Decimal - Deductible amount in BRL
            - coverage_limit: Optional[Decimal] - Maximum coverage in BRL
            - procedure_limits: Optional[Dict] - Per-procedure limits

    Output Variables:
        adjusted_items: List[Dict] - Procedures with adjustments applied
        total_patient_responsibility: Decimal - Amount patient must pay
        total_payer_responsibility: Decimal - Amount payer must pay
        applied_rules: Dict - Summary of rules applied
    """

    def __init__(self) -> None:
        super().__init__()
        self.dmn_service = FederatedDMNService()

    @property
    def operation_name(self) -> str:
        """Get operation name."""
        return _("Aplicar regras contratuais")

    def _evaluate_billing_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate billing DMN decision table via federation service."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=getattr(self, '_tenant_id', 'default'),
                category='billing',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    async def process_task(self, job: Any, variables: dict[str, Any]) -> WorkerResult:
        """Process contract rules application.

        Args:
            job: Job object from workflow engine
            variables: Process variables

        Returns:
            WorkerResult with adjusted items and responsibilities

        Raises:
            ContractRuleViolation: If contract rules are invalid or violated
        """
        # Validate required input variables
        claim_id = variables.get("claim_id")
        if not claim_id:
            raise ContractRuleViolation(
                message=_("ID da guia é obrigatório"),
                bpmn_error_code="MISSING_CLAIM_ID",
                retryable=False,
                details={"variables": list(variables.keys())}
            )

        payer_id = variables.get("payer_id")
        if not payer_id:
            raise ContractRuleViolation(
                message=_("ID da operadora é obrigatório"),
                bpmn_error_code="MISSING_PAYER_ID",
                retryable=False,
                details={"claim_id": claim_id}
            )

        procedures = variables.get("procedures")
        if not procedures or not isinstance(procedures, list):
            raise ContractRuleViolation(
                message=_("Lista de procedimentos é obrigatória"),
                bpmn_error_code="MISSING_PROCEDURES",
                retryable=False,
                details={"claim_id": claim_id}
            )

        contract_rules = variables.get("contract_rules")
        if not contract_rules or not isinstance(contract_rules, dict):
            raise ContractRuleViolation(
                message=_("Regras contratuais são obrigatórias"),
                bpmn_error_code="MISSING_CONTRACT_RULES",
                retryable=False,
                details={"claim_id": claim_id, "payer_id": payer_id}
            )

        self._logger.info(
            "Applying contract rules",
            claim_id=claim_id,
            payer_id=payer_id,
            procedure_count=len(procedures)
        )

        try:
            # Validate contract rules
            validated_rules = await self._validate_contract_rules(contract_rules)

            # Apply rules to procedures
            result = await self._apply_rules(
                procedures,
                validated_rules,
                claim_id,
                payer_id
            )

            self._logger.info(
                "Contract rules applied successfully",
                claim_id=claim_id,
                patient_responsibility=str(result["total_patient_responsibility"]),
                payer_responsibility=str(result["total_payer_responsibility"])
            )

            return WorkerResult.ok(result)

        except Exception as e:
            self._logger.error(
                "Error applying contract rules",
                claim_id=claim_id,
                error=str(e),
                exc_info=True
            )
            raise

    async def _validate_contract_rules(
        self,
        rules: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate contract rules structure and values.

        Args:
            rules: Contract rules dictionary

        Returns:
            Validated rules dictionary

        Raises:
            ContractRuleViolation: If rules are invalid
        """
        validated = {}

        # Validate co-payment percentage
        copay_pct = rules.get("copay_pct")
        if copay_pct is not None:
            try:
                copay_decimal = Decimal(str(copay_pct))
                if copay_decimal < Decimal("0") or copay_decimal > Decimal("100"):
                    raise ContractRuleViolation(
                        message=_("Percentual de co-pagamento deve estar entre 0 e 100"),
                        bpmn_error_code="INVALID_COPAY_PERCENTAGE",
                        retryable=False,
                        details={"copay_pct": copay_pct}
                    )
                validated["copay_pct"] = copay_decimal
            except (ValueError, TypeError) as e:
                raise ContractRuleViolation(
                    message=_("Percentual de co-pagamento inválido"),
                    bpmn_error_code="INVALID_COPAY_PERCENTAGE",
                    retryable=False,
                    details={"copay_pct": copay_pct, "error": str(e)}
                )
        else:
            validated["copay_pct"] = Decimal("0")

        # Validate deductible
        deductible = rules.get("deductible")
        if deductible is not None:
            try:
                deductible_decimal = Decimal(str(deductible))
                if deductible_decimal < Decimal("0"):
                    raise ContractRuleViolation(
                        message=_("Franquia não pode ser negativa"),
                        bpmn_error_code="INVALID_DEDUCTIBLE",
                        retryable=False,
                        details={"deductible": deductible}
                    )
                validated["deductible"] = Money.brl(deductible_decimal)
            except (ValueError, TypeError) as e:
                raise ContractRuleViolation(
                    message=_("Franquia inválida"),
                    bpmn_error_code="INVALID_DEDUCTIBLE",
                    retryable=False,
                    details={"deductible": deductible, "error": str(e)}
                )
        else:
            validated["deductible"] = Money.zero()

        # Validate coverage limit
        coverage_limit = rules.get("coverage_limit")
        if coverage_limit is not None:
            try:
                limit_decimal = Decimal(str(coverage_limit))
                if limit_decimal < Decimal("0"):
                    raise ContractRuleViolation(
                        message=_("Limite de cobertura não pode ser negativo"),
                        bpmn_error_code="INVALID_COVERAGE_LIMIT",
                        retryable=False,
                        details={"coverage_limit": coverage_limit}
                    )
                validated["coverage_limit"] = Money.brl(limit_decimal)
            except (ValueError, TypeError) as e:
                raise ContractRuleViolation(
                    message=_("Limite de cobertura inválido"),
                    bpmn_error_code="INVALID_COVERAGE_LIMIT",
                    retryable=False,
                    details={"coverage_limit": coverage_limit, "error": str(e)}
                )
        else:
            validated["coverage_limit"] = None

        # Validate procedure limits
        procedure_limits = rules.get("procedure_limits", {})
        if not isinstance(procedure_limits, dict):
            raise ContractRuleViolation(
                message=_("Limites por procedimento devem ser um dicionário"),
                bpmn_error_code="INVALID_PROCEDURE_LIMITS",
                retryable=False,
                details={"type": type(procedure_limits).__name__}
            )
        validated["procedure_limits"] = procedure_limits

        return validated

    async def _apply_rules(
        self,
        procedures: List[Dict[str, Any]],
        rules: Dict[str, Any],
        claim_id: str,
        payer_id: str
    ) -> Dict[str, Any]:
        """Apply contract rules to procedures.

        Args:
            procedures: List of procedures to adjust
            rules: Validated contract rules
            claim_id: Claim identifier
            payer_id: Payer identifier

        Returns:
            Dictionary with adjusted items and totals
        """
        adjusted_items = []
        total_charges = Money.zero()
        total_copay = Money.zero()
        deductible_remaining = rules["deductible"]

        # Process each procedure
        for idx, proc in enumerate(procedures):
            # Extract procedure data
            code = proc.get("code", "")
            quantity = int(proc.get("quantity", 1))
            unit_price_raw = proc.get("unit_price", 0)

            try:
                unit_price = Money.brl(Decimal(str(unit_price_raw)))
            except (ValueError, TypeError):
                raise ContractRuleViolation(
                    message=_("Preço unitário inválido para procedimento"),
                    bpmn_error_code="INVALID_UNIT_PRICE",
                    retryable=False,
                    details={"index": idx, "code": code, "unit_price": unit_price_raw}
                )

            # Calculate base amount
            line_total = unit_price * Decimal(str(quantity))
            total_charges += line_total

            # Check procedure-specific limits
            proc_limit = rules["procedure_limits"].get(code)
            if proc_limit is not None:
                try:
                    limit_money = Money.brl(Decimal(str(proc_limit)))
                    if line_total > limit_money:
                        self._logger.warning(
                            "Procedure exceeds limit",
                            code=code,
                            amount=str(line_total),
                            limit=str(limit_money)
                        )
                        line_total = limit_money
                except (ValueError, TypeError):
                    pass  # Ignore invalid limit

            # Apply co-payment
            copay_amount = line_total * (rules["copay_pct"] / Decimal("100"))
            total_copay += copay_amount

            # Apply deductible
            deductible_applied = Money.zero()
            if deductible_remaining > Money.zero():
                if line_total >= deductible_remaining:
                    deductible_applied = deductible_remaining
                    deductible_remaining = Money.zero()
                else:
                    deductible_applied = line_total
                    deductible_remaining -= line_total

            # Calculate payer and patient responsibility
            payer_amount = line_total - copay_amount - deductible_applied
            patient_amount = copay_amount + deductible_applied

            # Ensure non-negative amounts
            if payer_amount.amount < Decimal("0"):
                patient_amount += payer_amount
                payer_amount = Money.zero()

            adjusted_items.append({
                "sequence": idx + 1,
                "code": code,
                "quantity": quantity,
                "unit_price": str(unit_price.amount),
                "line_total": str(line_total.amount),
                "copay_amount": str(copay_amount.amount),
                "deductible_applied": str(deductible_applied.amount),
                "payer_responsibility": str(payer_amount.amount),
                "patient_responsibility": str(patient_amount.amount),
                **{k: v for k, v in proc.items() if k not in ["unit_price", "quantity"]}
            })

        # Calculate total responsibilities
        total_patient = total_copay + (rules["deductible"] - deductible_remaining)
        total_payer = total_charges - total_patient

        # Apply coverage limit if specified
        if rules["coverage_limit"] is not None:
            if total_payer > rules["coverage_limit"]:
                excess = total_payer - rules["coverage_limit"]
                total_payer = rules["coverage_limit"]
                total_patient += excess

                self._logger.warning(
                    "Coverage limit exceeded",
                    claim_id=claim_id,
                    total_charges=str(total_charges),
                    limit=str(rules["coverage_limit"]),
                    excess=str(excess)
                )

        return {
            "adjusted_items": adjusted_items,
            "total_patient_responsibility": str(total_patient.amount),
            "total_payer_responsibility": str(total_payer.amount),
            "total_charges": str(total_charges.amount),
            "applied_rules": {
                "copay_pct": str(rules["copay_pct"]),
                "deductible": str(rules["deductible"].amount),
                "deductible_applied": str((rules["deductible"] - deductible_remaining).amount),
                "coverage_limit": str(rules["coverage_limit"].amount) if rules["coverage_limit"] else None
            },
            "claim_id": claim_id,
            "payer_id": payer_id
        }
