"""
CalculateCopayWorker - Camunda 8 External Task Worker.

Calculates patient copay, coinsurance, and deductible amounts based on:
- Contract coverage details
- Insurance copay rules (fixed or percentage-based)
- Annual deductible tracking
- Procedure-specific coverage exceptions

This is the Python equivalent of the Java CalculateCopayDelegate.

Business Rule: Benchmark - Brazilian healthcare copay standards (ANS RN 439/2015)
Regulatory Compliance: ANS RN 439/2015, TISS 4.01.00, CFM Resolução 2.127/2015
Migrated from: com.hospital.revenuecycle.delegates.CalculateCopayDelegate

Section references:
- Patient coinsurance and cost-sharing calculations
- Deductible application and tracking
- Procedure-specific coverage exception handling

BPMN Task: Task_Calculate_Copay in SUB_06_Billing_Submission
Zeebe Topic: calculate-copay
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

import structlog

from revenue_cycle.domain.exceptions import BpmnErrorException, BusinessRuleException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker
from revenue_cycle.workers.billing.copay_models import (
    CalculateCopayInput,
    CalculateCopayOutput,
    CoverageStatus,
    CopayType,
    ContractCopayRule,
    ProcedureCopayDetail,
)
from revenue_cycle.workers.billing.models import ChargeCategory

logger = structlog.get_logger(__name__)


# Custom exceptions for copay processing
class CopayCalculationError(BusinessRuleException):
    """Raised when copay calculation fails due to missing or invalid rules."""

    def __init__(
        self,
        message: str,
        procedure_code: Optional[str] = None,
        contract_id: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            rule_name="COPAY_CALCULATION",
            code="COPAY_CALCULATION_ERROR",
            details={
                "procedure_code": procedure_code,
                "contract_id": contract_id,
            },
        )


class CoverageNotFoundError(BusinessRuleException):
    """Raised when coverage details are incomplete or missing."""

    def __init__(self, contract_id: str, missing_field: str):
        super().__init__(
            message=f"Coverage details missing required field '{missing_field}' for contract {contract_id}",
            rule_name="COVERAGE_VALIDATION",
            code="COVERAGE_NOT_FOUND",
            details={
                "contract_id": contract_id,
                "missing_field": missing_field,
            },
        )


# Alias for test compatibility - tests expect CalculationError
CalculationError = CopayCalculationError

# Maximum out-of-pocket constant (R$100,000 annual limit per contract)
MAX_OUT_OF_POCKET = Decimal("100000.00")


@worker(
    topic="calculate-copay",
    lock_duration=30000,  # 30 seconds
    max_jobs=32,
)
class CalculateCopayWorker(BaseWorker):
    """
    Zeebe worker for calculating patient copay and coinsurance.

    Business Rules Reference:
        - Document: docs/Regras de Negocio (PT-BR)/06_Billing/RN-BIL-001-Calculate-Copay.md
        - Rule IDs: RN-BIL-001-001 (Fixed Copay), RN-BIL-001-002 (Coinsurance),
                    RN-BIL-001-003 (Deductible Application), RN-BIL-001-004 (Coverage Limits)
        - Regulatory: ANS TISS (Coverage Rules), Resolution 2965 (Insurance Plans),
                      CPC 25 (Accounting)
        - Calculations: Deterministic, Decimal precision, Audit trail

    BPMN Task: Task_Calculate_Copay
    Topic: calculate-copay

    Calculates:
    - Fixed copay amounts per procedure
    - Percentage-based coinsurance (20%, 30%, etc.)
    - Annual deductible application
    - Insurance coverage amounts
    - Patient total responsibility

    This worker is naturally idempotent as it performs deterministic calculations
    based on the same coverage rules and procedure amounts.

    Input Variables:
        procedureCodes: List of TUSS codes for procedures
        coverageDetails: Coverage information from eligibility check
        contractId: Insurance contract identifier
        totalAmount: Pre-calculated total amount for all procedures
        patientId: (Optional) Patient ID for deductible tracking
        payerId: (Optional) Insurance payer identifier
        deductibleUsedYear: (Optional) Deductible already used in current year
        encounterDate: (Optional) Encounter date for deductible calculation

    Output Variables:
        copayAmount: Total fixed copay amount
        coinsuranceAmount: Total percentage-based coinsurance
        deductibleRemaining: Remaining annual deductible
        deductibleApplied: Deductible applied to this encounter
        coverageAmount: Total insurance pays
        patientResponsibility: Total patient must pay
        breakdownByProcedure: Detailed calculation per procedure
        copayTypeApplied: Type of copay mechanism used
        calculationRulesApplied: List of rules applied (audit trail)

    BPMN Errors:
        COVERAGE_NOT_FOUND: Missing required coverage information
        COPAY_CALCULATION_ERROR: Failed to calculate copay
    """

    def __init__(
        self,
        settings=None,
        benefit_service=None,
        **kwargs
    ):
        """
        Initialize the worker.

        Args:
            settings: Optional worker settings
            benefit_service: Optional benefit service (for testing)
            **kwargs: Additional keyword arguments (ignored)
        """
        super().__init__(settings=settings)
        self._benefit_service = benefit_service
        self._logger = logger.bind(worker=self.worker_name)

    @property
    def operation_name(self) -> str:
        """Get the operation name for idempotency and logging."""
        return "calculate_copay"

    @property
    def requires_idempotency(self) -> bool:
        """
        Copay calculation is deterministic.

        Same coverage rules + same procedures = same result, so explicit
        idempotency checking is not required.
        """
        return False

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the calculate-copay task.

        Main processing flow:
        1. Parse and validate input variables
        2. Extract and validate coverage rules from coverage details
        3. Calculate copay for each procedure
        4. Apply deductible if applicable
        5. Calculate insurance coverage and patient responsibility
        6. Build output with audit trail

        Args:
            job: Camunda external task
            variables: Job variables from the process

        Returns:
            WorkerResult with copay breakdown and totals

        Raises:
            CoverageNotFoundError: If coverage details are incomplete
            CopayCalculationError: If copay calculation fails
        """
        # Extract tenant_id from variables for multi-tenant support
        tenant_id = variables.get("tenantId")

        self._logger.info(
            "Starting copay calculation",
            job_key=str(getattr(job, "key", "unknown")),
            tenant_id=tenant_id,
        )

        try:
            # 1. Parse and validate input
            input_data = self._parse_input(variables)

            self._logger.info(
                "Processing copay calculation",
                contract_id=input_data.contract_id,
                procedures_count=len(input_data.procedure_codes),
                total_amount=float(input_data.total_amount),
            )

            # 2. Extract copay rules from coverage details
            copay_rules = self._extract_copay_rules(input_data.coverage_details, input_data.contract_id)

            # 3. Calculate copay per procedure
            procedure_details = await self._calculate_procedure_copay(
                input_data.procedure_codes,
                input_data.total_amount,
                copay_rules,
                input_data.contract_id,
            )

            # 4. Calculate totals before deductible
            total_copay = sum(p.copay_amount for p in procedure_details)
            total_coinsurance = sum(p.coinsurance_amount for p in procedure_details)

            # 5. Apply deductible
            deductible_remaining, deductible_applied = self._apply_deductible(
                input_data.deductible_used_year or Decimal("0"),
                total_copay,
                total_coinsurance,
                copay_rules,
            )

            # 6. Update procedure details with deductible
            self._distribute_deductible(procedure_details, deductible_applied)

            # 7. Calculate coverage amounts
            coverage_amount = sum(p.insurance_covers for p in procedure_details)
            patient_responsibility = sum(p.patient_responsibility for p in procedure_details)

            # 8. Determine copay type
            copay_type_applied = self._determine_copay_type(copay_rules)

            # 9. Build rules applied list
            rules_applied = self._extract_applied_rules(copay_rules, procedure_details)

            # 10. Build output
            output = CalculateCopayOutput(
                copay_amount=total_copay,
                coinsurance_amount=total_coinsurance,
                deductible_remaining=deductible_remaining,
                deductible_applied=deductible_applied,
                coverage_amount=coverage_amount,
                patient_responsibility=patient_responsibility,
                breakdown_by_procedure=procedure_details,
                copay_type_applied=copay_type_applied,
                calculation_rules_applied=rules_applied,
                contract_id=input_data.contract_id,
            )

            self._logger.info(
                "Copay calculation completed successfully",
                contract_id=input_data.contract_id,
                total_amount=float(input_data.total_amount),
                copay_amount=float(total_copay),
                coinsurance_amount=float(total_coinsurance),
                patient_responsibility=float(patient_responsibility),
                coverage_amount=float(coverage_amount),
                deductible_applied=float(deductible_applied),
            )

            return WorkerResult.ok(output.model_dump(by_alias=True))

        except CoverageNotFoundError as e:
            self._logger.warning(
                "Coverage details incomplete",
                contract_id=variables.get("contractId"),
                error=str(e),
            )
            return WorkerResult.bpmn_error(
                error_code="COVERAGE_NOT_FOUND",
                error_message=str(e),
                variables=e.details,
            )

        except CopayCalculationError as e:
            self._logger.warning(
                "Copay calculation error",
                details=e.details,
                error=str(e),
            )
            return WorkerResult.bpmn_error(
                error_code="COPAY_CALCULATION_ERROR",
                error_message=str(e),
                variables=e.details,
            )

        except Exception as e:
            self._logger.exception(
                "Copay calculation failed",
                error=str(e),
            )
            raise

    def _parse_input(self, variables: dict[str, Any]) -> CalculateCopayInput:
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
            return CalculateCopayInput.model_validate(variables)
        except Exception as e:
            raise BpmnErrorException(
                error_code="INVALID_INPUT",
                message=f"Invalid input data: {e}",
            )

    def _extract_copay_rules(
        self,
        coverage_details: dict[str, Any],
        contract_id: str,
    ) -> ContractCopayRule:
        """
        Extract copay rules from coverage details.

        Expected coverage_details structure:
        {
            "copayType": "COPAY" | "COINSURANCE" | "MIXED",
            "copayAmount": "50.00",  # For fixed copay
            "coinsuranceRate": "0.20",  # For percentage-based
            "deductibleAmount": "500.00",  # Annual deductible
            "appliesToCategories": ["PROFESSIONAL", "HOSPITAL"],  # Optional
        }

        Args:
            coverage_details: Coverage details from input
            contract_id: Contract identifier for error messages

        Returns:
            Parsed copay rules

        Raises:
            CoverageNotFoundError: If required fields are missing
        """
        # Validate required fields
        copay_type_str = coverage_details.get("copayType")
        if not copay_type_str:
            raise CoverageNotFoundError(contract_id, "copayType")

        try:
            copay_type = CopayType(copay_type_str)
        except ValueError:
            raise CoverageNotFoundError(contract_id, "copayType (invalid value)")

        # Parse amounts
        copay_amount = self._parse_decimal(coverage_details.get("copayAmount"), "0")
        coinsurance_rate = self._parse_decimal(coverage_details.get("coinsuranceRate"), "0")
        deductible_amount = self._parse_decimal(coverage_details.get("deductibleAmount"), "0")

        # Validate based on copay type
        if copay_type == CopayType.COPAY and copay_amount == Decimal("0"):
            raise CoverageNotFoundError(contract_id, "copayAmount (required for COPAY type)")

        if copay_type in (CopayType.COINSURANCE, CopayType.MIXED):
            if coinsurance_rate == Decimal("0"):
                raise CoverageNotFoundError(contract_id, "coinsuranceRate (required for COINSURANCE/MIXED type)")

            if coinsurance_rate < Decimal("0") or coinsurance_rate > Decimal("1"):
                raise CoverageNotFoundError(contract_id, "coinsuranceRate (must be between 0 and 1)")

        # Build rule
        return ContractCopayRule(
            rule_id=contract_id,
            copay_type=copay_type,
            copay_amount=copay_amount if copay_type in (CopayType.COPAY, CopayType.MIXED) else None,
            coinsurance_rate=coinsurance_rate if copay_type in (CopayType.COINSURANCE, CopayType.MIXED) else None,
            deductible_amount=deductible_amount,
            applies_to_categories=coverage_details.get("appliesToCategories"),
            applies_to_procedures=coverage_details.get("appliesToProcedures"),
        )

    async def _calculate_procedure_copay(
        self,
        procedure_codes: list[str],
        total_amount: Decimal,
        copay_rules: ContractCopayRule,
        contract_id: str,
    ) -> list[ProcedureCopayDetail]:
        """
        Calculate copay for each procedure.

        Distributes total amount proportionally across procedures and applies copay rules.

        Args:
            procedure_codes: List of TUSS codes
            total_amount: Total amount to distribute
            copay_rules: Copay rules to apply
            contract_id: Contract identifier

        Returns:
            List of procedure copay details
        """
        if not procedure_codes:
            raise CopayCalculationError(
                "No procedure codes provided",
                contract_id=contract_id,
            )

        # Distribute amount equally among procedures (simplified)
        # In production, would use actual procedure amounts
        amount_per_procedure = (total_amount / len(procedure_codes)).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        details: list[ProcedureCopayDetail] = []

        for idx, code in enumerate(procedure_codes):
            # Last procedure gets remainder to avoid rounding errors
            if idx == len(procedure_codes) - 1:
                procedure_amount = total_amount - (amount_per_procedure * idx)
            else:
                procedure_amount = amount_per_procedure

            # Calculate copay and coinsurance
            copay = Decimal("0")
            coinsurance = Decimal("0")

            if copay_rules.copay_type in (CopayType.COPAY, CopayType.MIXED):
                copay = copay_rules.copay_amount or Decimal("0")

            if copay_rules.copay_type in (CopayType.COINSURANCE, CopayType.MIXED):
                rate = copay_rules.coinsurance_rate or Decimal("0")
                coinsurance = (procedure_amount * rate).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )

            # Calculate insurance coverage
            insurance_covers = procedure_amount - copay - coinsurance

            # Create detail
            detail = ProcedureCopayDetail(
                procedure_code=code,
                total_amount=procedure_amount,
                coverage_status=CoverageStatus.COVERED,
                copay_amount=copay,
                coinsurance_amount=coinsurance,
                coinsurance_rate=copay_rules.coinsurance_rate or Decimal("0"),
                deductible_applied=Decimal("0"),  # Will be updated later
                insurance_covers=insurance_covers,
                patient_responsibility=copay + coinsurance,
            )

            details.append(detail)

        return details

    def _apply_deductible(
        self,
        deductible_used_year: Decimal,
        total_copay: Decimal,
        total_coinsurance: Decimal,
        copay_rules: ContractCopayRule,
    ) -> tuple[Decimal, Decimal]:
        """
        Apply annual deductible to the encounter.

        Deductible is applied before coinsurance but after fixed copay.

        Args:
            deductible_used_year: Deductible already used in current year
            total_copay: Total copay amount
            total_coinsurance: Total coinsurance amount
            copay_rules: Copay rules with deductible amount

        Returns:
            Tuple of (remaining_deductible, deductible_applied)
        """
        deductible_limit = copay_rules.deductible_amount or Decimal("0")

        # No deductible configured
        if deductible_limit == Decimal("0"):
            return Decimal("0"), Decimal("0")

        # Calculate remaining deductible
        remaining = deductible_limit - deductible_used_year
        if remaining <= Decimal("0"):
            return Decimal("0"), Decimal("0")

        # Apply to coinsurance first, then to remaining copay
        # (This is a typical insurance behavior)
        deductible_applied = min(remaining, total_coinsurance)

        remaining_after = remaining - deductible_applied

        self._logger.debug(
            "Deductible applied",
            deductible_limit=float(deductible_limit),
            deductible_used=float(deductible_used_year),
            deductible_applied=float(deductible_applied),
            remaining=float(remaining_after),
        )

        return remaining_after, deductible_applied

    def _distribute_deductible(
        self,
        procedure_details: list[ProcedureCopayDetail],
        deductible_applied: Decimal,
    ) -> None:
        """
        Distribute deductible amount across procedures.

        Updates deductible_applied in each procedure detail proportionally.

        Args:
            procedure_details: List of procedure details to update
            deductible_applied: Total deductible amount to distribute
        """
        if deductible_applied == Decimal("0") or not procedure_details:
            return

        # Distribute proportionally to coinsurance amounts
        total_coinsurance = sum(p.coinsurance_amount for p in procedure_details)

        if total_coinsurance == Decimal("0"):
            # If no coinsurance, distribute equally
            per_procedure = (deductible_applied / len(procedure_details)).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            for idx, detail in enumerate(procedure_details):
                if idx == len(procedure_details) - 1:
                    detail.deductible_applied = deductible_applied - (per_procedure * idx)
                else:
                    detail.deductible_applied = per_procedure
        else:
            # Distribute proportionally
            for idx, detail in enumerate(procedure_details):
                if detail.coinsurance_amount > Decimal("0"):
                    proportion = detail.coinsurance_amount / total_coinsurance
                    deductible_share = (deductible_applied * proportion).quantize(
                        Decimal("0.01"),
                        rounding=ROUND_HALF_UP,
                    )
                    detail.deductible_applied = deductible_share

        # Update patient responsibility and insurance covers
        for detail in procedure_details:
            detail.insurance_covers = (
                detail.total_amount - detail.copay_amount - detail.coinsurance_amount + detail.deductible_applied
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            detail.patient_responsibility = (
                detail.copay_amount + detail.coinsurance_amount - detail.deductible_applied
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _determine_copay_type(self, copay_rules: ContractCopayRule) -> CopayType:
        """
        Determine the copay type applied.

        Args:
            copay_rules: Copay rules

        Returns:
            CopayType that was applied
        """
        return copay_rules.copay_type

    def _extract_applied_rules(
        self,
        copay_rules: ContractCopayRule,
        procedure_details: list[ProcedureCopayDetail],
    ) -> list[str]:
        """
        Extract descriptive list of rules applied.

        Args:
            copay_rules: Copay rules used
            procedure_details: Procedures processed

        Returns:
            List of rule descriptions for audit trail
        """
        rules: list[str] = [
            f"Copay type: {copay_rules.copay_type.value}",
        ]

        # Add fixed copay rule
        if copay_rules.copay_amount:
            rules.append(f"Fixed copay: R$ {float(copay_rules.copay_amount):,.2f}")

        # Add coinsurance rule
        if copay_rules.coinsurance_rate:
            percentage = float(copay_rules.coinsurance_rate * 100)
            rules.append(f"Coinsurance: {percentage:.1f}%")

        # Add deductible rule
        if copay_rules.deductible_amount:
            rules.append(f"Annual deductible: R$ {float(copay_rules.deductible_amount):,.2f}")

        # Add category filtering if applicable
        if copay_rules.applies_to_categories:
            categories = ", ".join(copay_rules.applies_to_categories)
            rules.append(f"Applies to categories: {categories}")

        # Add procedure count
        rules.append(f"Procedures processed: {len(procedure_details)}")

        return rules

    def _parse_decimal(self, value: Any, default: str = "0") -> Decimal:
        """
        Parse various types to Decimal.

        Args:
            value: Value to parse
            default: Default value if None

        Returns:
            Parsed Decimal value
        """
        if value is None:
            return Decimal(default)

        if isinstance(value, Decimal):
            return value

        if isinstance(value, (int, float)):
            return Decimal(str(value))

        if isinstance(value, str):
            return Decimal(value.replace(",", "."))

        return Decimal(default)

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """
        Extract parameters for idempotency key generation.

        Uses contract_id and total_amount for idempotency.

        Args:
            variables: Job variables

        Returns:
            String representation of key parameters
        """
        contract_id = variables.get("contractId", "")
        total_amount = variables.get("totalAmount", "")
        process_instance = variables.get("processInstanceKey", "")
        return f"{process_instance}:{contract_id}:{total_amount}"


# Worker registration function for use with Zeebe client
def create_calculate_copay_worker() -> CalculateCopayWorker:
    """
    Factory function to create CalculateCopayWorker.

    Returns:
        Configured worker instance
    """
    return CalculateCopayWorker()
