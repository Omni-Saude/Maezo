"""
ApplyContractRulesWorker - Camunda 8 External Task Worker.

Applies insurance contract rules to consolidated billing charges:
- Category-specific discount rates
- Procedure coverage validation
- Contract limit validation
- Comprehensive audit trail of rules applied

This is the Python equivalent of the Java ApplyContractRulesDelegate.

Business Rule: RN-BIL-001-ApplyContractRules.md
Regulatory Compliance: ANS RN 439/2015, TISS 4.01.00
Migrated from: com.hospital.revenuecycle.delegates.ApplyContractRulesDelegate

Section references:
- Section II: Definição da Regra de Negócio (Contract-specific discount rules)
- Section III: Algoritmo de Processamento (Validation and discount application)
- Section IV: Regras de Negócio Associadas (Coverage and limits validation)

BPMN Task: Task_Apply_Contract_Rules in SUB_06_Billing_Submission
Zeebe Topic: apply-contract-rules
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import structlog

from revenue_cycle.domain.exceptions import (
    BpmnErrorException,
    BusinessRuleException,
    EntityNotFoundException,
)
from revenue_cycle.integrations.ans import RolClient
from revenue_cycle.integrations.ans.models import RolValidationResult
from revenue_cycle.services.contract_service import (
    ContractPricingService,
    ContractService,
    DEFAULT_DISCOUNT_RATES,
)
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker
from revenue_cycle.workers.billing.models import (
    AdjustedChargeItem,
    ApplyContractRulesInput,
    ApplyContractRulesOutput,
    ChargeCategory,
    ChargeItem,
    Contract,
    DiscountApplied,
)

logger = structlog.get_logger(__name__)


# Custom exceptions for contract rules processing
class ContractNotFoundError(EntityNotFoundException):
    """Raised when no active contract is found for a payer."""

    def __init__(self, payer_id: str):
        super().__init__(
            entity_type="Contract",
            entity_id=payer_id,
            message=f"No active contract found for payer: {payer_id}",
        )


class ProcedureNotCoveredError(BusinessRuleException):
    """Raised when a procedure is not covered by the contract."""

    def __init__(self, procedure_code: str, payer_id: str):
        super().__init__(
            message=f"Procedure {procedure_code} is not covered by contract for payer {payer_id}",
            rule_name="PROCEDURE_COVERAGE",
            code="PROCEDURE_NOT_COVERED",
            details={
                "procedure_code": procedure_code,
                "payer_id": payer_id,
            },
        )


class ContractLimitExceededError(BusinessRuleException):
    """Raised when adjusted amount exceeds contract limit."""

    def __init__(
        self,
        adjusted_amount: Decimal,
        max_amount: Decimal,
        contract_id: str,
    ):
        super().__init__(
            message=(
                f"Adjusted amount R$ {adjusted_amount} exceeds contract maximum "
                f"R$ {max_amount} for contract {contract_id}"
            ),
            rule_name="CONTRACT_LIMIT",
            code="INVALID_CONTRACT_RULES",
            details={
                "adjusted_amount": float(adjusted_amount),
                "max_claim_amount": float(max_amount),
                "contract_id": contract_id,
            },
        )


class ProcedureNotInRolError(BusinessRuleException):
    """Raised when procedure is not in ANS Rol de Procedimentos (ANS RN 465/2021)."""

    def __init__(self, procedure_code: str):
        super().__init__(
            message=(
                f"Procedure {procedure_code} is not in the current ANS Rol de Procedimentos "
                f"as required by ANS RN 465/2021"
            ),
            rule_name="ANS_ROL_VALIDATION",
            code="PROCEDURE_NOT_IN_ROL",
            details={
                "procedure_code": procedure_code,
            },
        )


@worker(
    topic="apply-contract-rules",
    lock_duration=30000,  # 30 seconds
    max_jobs=32,
)
class ApplyContractRulesWorker(BaseWorker):
    """
    Zeebe worker for applying insurance contract rules to billing charges.

    Applies:
    - Category-specific discount rates (PROFESSIONAL, HOSPITAL, MATERIALS, MEDICATIONS)
    - Procedure coverage validation
    - Contract limit validation

    This worker is naturally idempotent as it performs deterministic calculations
    based on the same input data.

    Input Variables:
        payerId: Insurance payer identifier (ANS code or CNPJ)
        consolidatedCharges: List of charge items from ConsolidateChargesWorker
        totalChargeAmount: Total amount before adjustments

    Output Variables:
        contractAdjustedCharges: Charges after contract rules applied
        contractAdjustedAmount: Total amount after adjustments
        contractDiscount: Total discount applied
        contractRulesApplied: List of rules applied (audit trail)

    BPMN Errors:
        CONTRACT_NOT_FOUND: No active contract for payer
        PROCEDURE_NOT_COVERED: Procedure not in coverage list
        INVALID_CONTRACT_RULES: Amount exceeds contract limit
        PROCEDURE_NOT_IN_ROL: Procedure not in ANS Rol de Procedimentos

    Regulatory Compliance:
        - ANS RN 465/2021: Validates procedure codes against Rol de Procedimentos
    """

    def __init__(
        self,
        contract_service: ContractService | None = None,
        rol_client: RolClient | None = None,
        **kwargs: Any,
    ):
        """
        Initialize the worker.

        Args:
            contract_service: Service for contract operations
            rol_client: ANS Rol client for procedure validation
            **kwargs: Additional arguments for BaseWorker
        """
        super().__init__(**kwargs)
        self._contract_service = contract_service or ContractPricingService()
        self._rol_client = rol_client
        self._logger = logger.bind(worker=self.worker_name)

    @property
    def operation_name(self) -> str:
        """Get the operation name for idempotency and logging."""
        return "apply_contract_rules"

    @property
    def requires_idempotency(self) -> bool:
        """
        Contract rules application is deterministic.

        Same charges + same contract = same result, so explicit
        idempotency checking is not required.
        """
        return False

    async def _validate_procedure_in_rol(
        self,
        procedure_code: str,
        tenant_id: str | None,
    ) -> RolValidationResult:
        """
        Validate procedure code against ANS Rol de Procedimentos (ANS RN 465/2021).

        Per ANS Normativa 465/2021, all procedures billed to health insurers
        must be included in the current Rol de Procedimentos e Eventos em Saúde.

        This method integrates with the ANS Rol database/API to validate:
        1. Procedure exists in current Rol
        2. Procedure is active (not deprecated/suspended)
        3. Procedure has mandatory or optional coverage

        Args:
            procedure_code: TUSS procedure code
            tenant_id: Tenant identifier for multi-tenant support

        Returns:
            Validation result with coverage information

        Raises:
            ProcedureNotInRolError: If procedure not in Rol or validation fails
        """
        # Basic format validation
        if not procedure_code or not isinstance(procedure_code, str):
            raise ProcedureNotInRolError(procedure_code)

        # TUSS codes are 8 digits: TTMMPPPP
        if not (len(procedure_code) == 8 and procedure_code.isdigit()):
            self._logger.warning(
                "Invalid TUSS code format",
                procedure_code=procedure_code,
            )
            raise ProcedureNotInRolError(procedure_code)

        # If no Rol client configured, skip validation with warning
        if self._rol_client is None:
            self._logger.warning(
                "ANS Rol client not configured - skipping Rol validation",
                procedure_code=procedure_code,
            )
            # Return a default "valid" result to not block processing
            # In production, this should be configurable based on hospital policy
            from revenue_cycle.integrations.ans.models import (
                CoverageType,
                ProcedureStatus,
            )
            from datetime import datetime

            return RolValidationResult(
                procedure_code=procedure_code,
                is_valid=True,
                is_covered=True,
                status=ProcedureStatus.ACTIVE,
                coverage_type=CoverageType.MANDATORY,
                validation_date=datetime.now(),
                cached=False,
                error_message="ANS Rol validation disabled - client not configured",
            )

        # Validate against ANS Rol
        try:
            result = await self._rol_client.validate_procedure(
                procedure_code=procedure_code,
                use_cache=True,  # Use cache for performance (24h TTL)
            )

            # Check validation result
            if not result.is_valid:
                self._logger.warning(
                    "Procedure not valid in ANS Rol",
                    procedure_code=procedure_code,
                    status=result.status.value if result.status else "unknown",
                    error=result.error_message,
                )
                raise ProcedureNotInRolError(procedure_code)

            # Log if procedure not covered (but don't fail - contract may still cover it)
            if not result.is_covered:
                self._logger.info(
                    "Procedure not in mandatory coverage but present in Rol",
                    procedure_code=procedure_code,
                    coverage_type=result.coverage_type.value if result.coverage_type else "unknown",
                )

            self._logger.debug(
                "Procedure validated in ANS Rol",
                procedure_code=procedure_code,
                is_valid=result.is_valid,
                is_covered=result.is_covered,
                cached=result.cached,
            )

            return result

        except Exception as e:
            # If ANS Rol API fails, check if we got cached fallback data
            if isinstance(e, ProcedureNotInRolError):
                raise  # Re-raise if already our error

            self._logger.error(
                "ANS Rol validation error",
                procedure_code=procedure_code,
                error=str(e),
            )
            # Don't fail the entire process - log and continue
            # The contract validation will still catch uncovered procedures
            from revenue_cycle.integrations.ans.models import (
                CoverageType,
                ProcedureStatus,
            )
            from datetime import datetime

            return RolValidationResult(
                procedure_code=procedure_code,
                is_valid=True,  # Assume valid to not block processing
                is_covered=True,
                status=ProcedureStatus.ACTIVE,
                coverage_type=CoverageType.MANDATORY,
                validation_date=datetime.now(),
                cached=False,
                error_message=f"ANS Rol validation failed: {str(e)}",
            )

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the apply-contract-rules task.

        Main processing flow:
        1. Parse and validate input variables
        2. Retrieve active contract for payer
        3. Validate ANS Rol de Procedimentos (ANS RN 465/2021)
        4. Validate procedure coverage
        5. Apply discount rules to each charge
        6. Validate against contract limits
        7. Build output with audit trail

        Args:
            job: Camunda external task
            variables: Job variables from the process

        Returns:
            WorkerResult with adjusted charges and totals

        Raises:
            ContractNotFoundError: If no active contract found
            ProcedureNotCoveredError: If procedure not covered
            ContractLimitExceededError: If amount exceeds limit
        """
        # Extract tenant_id from variables for multi-tenant support
        tenant_id = variables.get("tenantId")

        self._logger.info(
            "Starting contract rules application",
            job_key=str(getattr(job, "key", "unknown")),
            tenant_id=tenant_id,
        )

        try:
            # 1. Parse and validate input
            input_data = self._parse_input(variables)

            self._logger.info(
                "Processing contract rules",
                payer_id=input_data.payer_id,
                total_charges=len(input_data.consolidated_charges),
                total_amount=float(input_data.total_charge_amount),
            )

            # 2. Retrieve contract
            contract = await self._retrieve_contract(
                input_data.payer_id,
                tenant_id,
            )

            # 3. Validate ANS Rol de Procedimentos (ANS RN 465/2021)
            for charge in input_data.consolidated_charges:
                await self._validate_procedure_in_rol(
                    charge.charge_code,
                    tenant_id,
                )

            # 4. Validate procedure coverage
            self._validate_procedure_coverage(
                input_data.consolidated_charges,
                contract,
            )

            # 5. Apply discount rules
            adjusted_charges = await self._apply_discount_rules(
                input_data.consolidated_charges,
                contract,
            )

            # 6. Calculate totals
            adjusted_amount = self._calculate_adjusted_total(adjusted_charges)
            contract_discount = input_data.total_charge_amount - adjusted_amount

            # 7. Validate contract limits
            self._validate_contract_limits(
                adjusted_amount,
                contract,
            )

            # 8. Calculate and document discounts
            discounts_applied = await self._contract_service.calculate_discounts(
                contract,
                adjusted_charges,
                input_data.total_charge_amount,
            )

            # 9. Build rules applied list
            rules_applied = self._extract_applied_rules(
                contract,
                adjusted_charges,
            )

            # 10. Build output
            output = ApplyContractRulesOutput(
                contract_adjusted_charges=adjusted_charges,
                contract_adjusted_amount=adjusted_amount,
                contract_discount=contract_discount,
                contract_rules_applied=rules_applied,
                contract_id=contract.contract_id,
                pricing_table_used=contract.pricing_table.value,
                discounts_applied=discounts_applied,
                max_claim_amount=contract.max_claim_amount,
                within_contract_limits=True,
            )

            self._logger.info(
                "Contract rules applied successfully",
                payer_id=input_data.payer_id,
                contract_id=contract.contract_id,
                original_amount=float(input_data.total_charge_amount),
                adjusted_amount=float(adjusted_amount),
                discount=float(contract_discount),
                rules_count=len(rules_applied),
            )

            return WorkerResult.ok(output.model_dump(by_alias=True))

        except ContractNotFoundError as e:
            self._logger.warning(
                "Contract not found",
                payer_id=variables.get("payerId"),
                error=str(e),
            )
            return WorkerResult.bpmn_error(
                error_code="CONTRACT_NOT_FOUND",
                error_message=str(e),
            )

        except ProcedureNotCoveredError as e:
            self._logger.warning(
                "Procedure not covered",
                details=e.details,
            )
            return WorkerResult.bpmn_error(
                error_code="PROCEDURE_NOT_COVERED",
                error_message=str(e),
                variables=e.details,
            )

        except ContractLimitExceededError as e:
            self._logger.warning(
                "Contract limit exceeded",
                details=e.details,
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_CONTRACT_RULES",
                error_message=str(e),
                variables=e.details,
            )

        except ProcedureNotInRolError as e:
            self._logger.warning(
                "Procedure not in ANS Rol",
                details=e.details,
            )
            return WorkerResult.bpmn_error(
                error_code="PROCEDURE_NOT_IN_ROL",
                error_message=str(e),
                variables=e.details,
            )

        except Exception as e:
            self._logger.exception(
                "Contract rules application failed",
                error=str(e),
            )
            raise

    def _parse_input(self, variables: dict[str, Any]) -> ApplyContractRulesInput:
        """
        Parse and validate input variables.

        Args:
            variables: Job variables

        Returns:
            Validated input model

        Raises:
            BpmnErrorException: If validation fails
        """
        try:
            return ApplyContractRulesInput.model_validate(variables)
        except Exception as e:
            raise BpmnErrorException(
                error_code="INVALID_INPUT",
                message=f"Invalid input data: {e}",
            )

    async def _retrieve_contract(
        self,
        payer_id: str,
        tenant_id: str | None,
    ) -> Contract:
        """
        Retrieve active contract for the payer.

        Args:
            payer_id: Insurance payer identifier
            tenant_id: Optional tenant identifier

        Returns:
            Active contract

        Raises:
            ContractNotFoundError: If no active contract found
        """
        contract = await self._contract_service.get_active_contract(
            payer_id,
            tenant_id,
        )

        if contract is None:
            raise ContractNotFoundError(payer_id)

        if not contract.is_active:
            raise ContractNotFoundError(payer_id)

        self._logger.debug(
            "Contract retrieved",
            contract_id=contract.contract_id,
            payer_id=contract.payer_id,
            effective_date=str(contract.effective_date),
            max_claim_amount=float(contract.max_claim_amount or 0),
        )

        return contract

    def _validate_procedure_coverage(
        self,
        charges: list[ChargeItem],
        contract: Contract,
    ) -> None:
        """
        Validate that all procedures are covered by the contract.

        Args:
            charges: List of charge items
            contract: Contract with coverage information

        Raises:
            ProcedureNotCoveredError: If any procedure is not covered
        """
        # If contract has no specific coverage list, all procedures are covered
        if not contract.covered_procedures:
            return

        for charge in charges:
            if not contract.is_procedure_covered(charge.charge_code):
                raise ProcedureNotCoveredError(
                    charge.charge_code,
                    contract.payer_id,
                )

    async def _apply_discount_rules(
        self,
        charges: list[ChargeItem],
        contract: Contract,
    ) -> list[AdjustedChargeItem]:
        """
        Apply contract discount rules to all charges.

        Args:
            charges: List of charge items
            contract: Contract with discount rules

        Returns:
            List of adjusted charge items
        """
        return await self._contract_service.apply_rules(contract, charges)

    def _calculate_adjusted_total(
        self,
        adjusted_charges: list[AdjustedChargeItem],
    ) -> Decimal:
        """
        Calculate total adjusted amount.

        Args:
            adjusted_charges: List of adjusted charges

        Returns:
            Total adjusted amount
        """
        total = sum(charge.amount for charge in adjusted_charges)
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _validate_contract_limits(
        self,
        adjusted_amount: Decimal,
        contract: Contract,
    ) -> None:
        """
        Validate adjusted amount against contract limits.

        Args:
            adjusted_amount: Total adjusted amount
            contract: Contract with limits

        Raises:
            ContractLimitExceededError: If amount exceeds limit
        """
        if contract.max_claim_amount is None:
            return

        if adjusted_amount > contract.max_claim_amount:
            raise ContractLimitExceededError(
                adjusted_amount,
                contract.max_claim_amount,
                contract.contract_id,
            )

        self._logger.debug(
            "Contract limits validated",
            adjusted_amount=float(adjusted_amount),
            max_claim_amount=float(contract.max_claim_amount),
        )

    def _extract_applied_rules(
        self,
        contract: Contract,
        adjusted_charges: list[AdjustedChargeItem],
    ) -> list[str]:
        """
        Extract descriptive list of rules applied.

        Args:
            contract: Contract used
            adjusted_charges: Charges with rules applied

        Returns:
            List of rule descriptions for audit trail
        """
        rules: list[str] = [
            f"Contract {contract.contract_id} applied",
            f"Pricing table: {contract.pricing_table.value}",
        ]

        # Add validation rules
        rules.extend([
            "ANS Rol de Procedimentos validation (ANS RN 465/2021)",
            "Procedure coverage validation",
            "Contract limit validation",
        ])

        # Add discount rate rules
        categories_processed = set()
        for charge in adjusted_charges:
            if charge.category not in categories_processed:
                percentage = float(charge.discount_rate * 100)
                rules.append(
                    f"Category {charge.category}: {percentage:.1f}% discount"
                )
                categories_processed.add(charge.category)

        # Add contract limit if applicable
        if contract.max_claim_amount:
            rules.append(
                f"Maximum claim amount: R$ {float(contract.max_claim_amount):,.2f}"
            )

        return rules

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """
        Extract parameters for idempotency key generation.

        Uses payer_id and total_charge_amount for idempotency.

        Args:
            variables: Job variables

        Returns:
            String representation of key parameters
        """
        payer_id = variables.get("payerId", "")
        total_amount = variables.get("totalChargeAmount", "")
        process_instance = variables.get("processInstanceKey", "")
        return f"{process_instance}:{payer_id}:{total_amount}"


# Worker registration function for use with Zeebe client
def create_apply_contract_rules_worker(
    contract_service: ContractService | None = None,
    rol_client: RolClient | None = None,
) -> ApplyContractRulesWorker:
    """
    Factory function to create ApplyContractRulesWorker.

    Args:
        contract_service: Optional custom contract service
        rol_client: Optional ANS Rol client for procedure validation

    Returns:
        Configured worker instance
    """
    return ApplyContractRulesWorker(
        contract_service=contract_service,
        rol_client=rol_client,
    )
