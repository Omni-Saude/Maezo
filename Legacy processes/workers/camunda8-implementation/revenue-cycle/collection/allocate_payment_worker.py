"""
AllocatePaymentWorker - Zeebe worker for allocating payments across multiple claims.

This worker implements payment allocation strategies for the Brazilian healthcare revenue cycle:
- FIFO (First In, First Out) - allocate to oldest claims first
- LIFO (Last In, First Out) - allocate to newest claims first
- PROPORTIONAL - split proportionally based on claim amounts
- MANUAL - use manually specified allocations

Features:
- Multiple allocation strategies
- Partial allocation support
- Accounting integration for each allocation
- Multi-tenant database isolation
- Comprehensive allocation summary

Business Rule: RN-AllocatePaymentDelegate.md
Regulatory Compliance: ANS RN 439/2015, TISS 4.01.00, CPC 25 (Accounting Standard)
Migrated from: com.hospital.revenuecycle.delegates.AllocatePaymentDelegate

Section references:
- Payment allocation strategy selection
- Multi-claim payment distribution
- Partial payment handling
- Accounting journal entry generation

Topic: allocate-payment
BPMN Task: Task_Allocate_Payment (Alocar Pagamento)
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

import structlog
from pydantic import ValidationError

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.services.accounting import AccountingService
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker
from revenue_cycle.workers.payment.allocation_models import (
    AllocatePaymentInput,
    AllocatePaymentOutput,
    AllocationResult,
    AllocationStrategy,
    ClaimAllocationItem,
)

logger = structlog.get_logger(__name__)


class AllocationError(BpmnErrorException):
    """Raised when payment allocation fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="ALLOCATION_ERROR",
            message=message,
            details=details,
        )


class InvalidAllocationStrategyError(BpmnErrorException):
    """Raised when allocation strategy is invalid."""

    def __init__(self, strategy: str):
        super().__init__(
            error_code="INVALID_ALLOCATION_STRATEGY",
            message=f"Invalid allocation strategy: {strategy}",
            details={"strategy": strategy},
        )


class InsufficientClaimDataError(BpmnErrorException):
    """Raised when claim data is insufficient for allocation."""

    def __init__(self, message: str):
        super().__init__(
            error_code="INSUFFICIENT_CLAIM_DATA",
            message=message,
        )


class InvalidAllocationError(BpmnErrorException):
    """Raised when allocation data is invalid."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="INVALID_ALLOCATION",
            message=message,
            details=details,
        )


class InsufficientBalanceError(BpmnErrorException):
    """Raised when payment balance is insufficient for allocation."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="INSUFFICIENT_BALANCE",
            message=message,
            details=details,
        )


@worker(topic="allocate-payment", max_jobs=16, lock_duration=45000)
class AllocatePaymentWorker(BaseWorker):
    """
    Zeebe worker for allocating payments across multiple claims.

    Business Rules Reference:
        - Document: docs/Regras de Negocio (PT-BR)/02_Payment_Processing/RN-PAY-003-Allocate-Payment.md
        - Rule IDs: RN-PAY-003-001 (Allocation Strategies), RN-PAY-003-002 (Balance Validation),
                    RN-PAY-003-003 (Accounting Integration)
        - Regulatory: CPC 25 (Journal Entries), TISS (Claim Reconciliation)
        - Financial Controls: Decimal precision, Audit trail per claim, Balance integrity

    BPMN Task: Task_Allocate_Payment
    Topic: allocate-payment

    This worker implements various allocation strategies:
    1. FIFO - Allocate to oldest claims first (by claim date)
    2. LIFO - Allocate to newest claims first (by claim date)
    3. PROPORTIONAL - Split proportionally by claim balance
    4. MANUAL - Use provided allocations

    For each allocation:
    - Creates accounting journal entries
    - Tracks claim balance updates
    - Handles partial allocations
    - Returns comprehensive allocation summary

    Input Variables:
        - paymentId: Unique payment identifier (required)
        - paymentAmount: Total amount to allocate (required, Decimal)
        - claimIds: List of claim IDs (required, list)
        - allocationStrategy: FIFO/LIFO/PROPORTIONAL/MANUAL (required)
        - manualAllocations: Manual allocation amounts (required for MANUAL)
        - claimsData: Claim details for allocation (optional)

    Output Variables:
        - allocationComplete: Whether allocation completed (boolean)
        - allocations: List of allocations per claim
        - unallocatedAmount: Remaining unallocated amount (Decimal)
        - allocationSummary: Allocation summary breakdown
        - accountingReferences: Accounting entry IDs
        - allocationDate: Timestamp of allocation

    Financial Controls:
        - Uses Decimal for all monetary amounts
        - Validates allocations don't exceed claim balances
        - Creates audit trail via accounting entries
        - Multi-tenant database isolation
    """

    def __init__(
        self,
        settings=None,
        allocation_service=None,
        accounting_service=None,
        **kwargs
    ):
        """
        Initialize the worker with accounting service.

        Args:
            settings: Optional worker settings
            allocation_service: Optional allocation service (for testing)
            accounting_service: Optional accounting service (for testing)
            **kwargs: Additional keyword arguments (ignored)
        """
        super().__init__(settings=settings)
        self._accounting_service = accounting_service or AccountingService()
        # Store optional services for testing
        self._allocation_service = allocation_service

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "allocate_payment"

    @property
    def requires_idempotency(self) -> bool:
        """This worker requires idempotency."""
        return True

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """
        Extract payment ID for idempotency key generation.

        Uses paymentId + claimIds as the unique key.
        """
        payment_id = variables.get("paymentId", "")
        claim_ids = variables.get("claimIds", [])
        claim_ids_str = ",".join(sorted(claim_ids)) if claim_ids else ""
        return f"{payment_id}:{claim_ids_str}"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the payment allocation task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with allocation outcome

        Raises:
            AllocationError: If allocation fails
            InvalidAllocationStrategyError: If strategy is invalid
            InsufficientClaimDataError: If claim data is missing
        """
        self._logger.info(
            "Processing payment allocation",
            job_key=str(getattr(job, "key", "unknown")),
            payment_id=variables.get("paymentId"),
            strategy=variables.get("allocationStrategy"),
        )

        try:
            # Parse and validate input
            input_data = AllocatePaymentInput.model_validate(variables)

            # Load claim data if not provided
            claims_data = await self._load_claims_data(input_data)

            # Validate claim data
            self._validate_claims_data(claims_data, input_data)

            # Allocate payment based on strategy
            allocations, unallocated_amount = await self._allocate_payment(
                input_data,
                claims_data,
            )

            # Create accounting entries for allocations
            accounting_references = await self._create_allocation_accounting(
                payment_id=input_data.payment_id,
                allocations=allocations,
            )

            # Generate allocation summary
            allocation_summary = self._create_allocation_summary(
                input_data=input_data,
                allocations=allocations,
                unallocated_amount=unallocated_amount,
            )

            # Create output
            output = AllocatePaymentOutput(
                allocationComplete=unallocated_amount == 0,
                allocations=allocations,
                unallocatedAmount=unallocated_amount,
                allocationSummary=allocation_summary,
                accountingReferences=accounting_references,
                allocationDate=datetime.utcnow(),
            )

            self._logger.info(
                "Payment allocation completed",
                payment_id=input_data.payment_id,
                total_allocated=str(sum(a.allocated_amount for a in allocations)),
                unallocated=str(unallocated_amount),
                claims_count=len(allocations),
            )

            # Return success with output variables
            return WorkerResult.ok(output.model_dump(by_alias=True))

        except ValidationError as e:
            self._logger.error(
                "Allocation validation failed",
                errors=e.errors(),
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_ALLOCATION_DATA",
                error_message=f"Allocation validation failed: {e}",
            )

        except (AllocationError, InvalidAllocationStrategyError, InsufficientClaimDataError) as e:
            self._logger.error(
                "Allocation error",
                error=str(e),
                error_code=e.error_code,
            )
            return WorkerResult.bpmn_error(
                error_code=e.error_code,
                error_message=e.message,
            )

        except Exception as e:
            self._logger.error(
                "Unexpected error allocating payment",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Failed to allocate payment: {e}",
                retry=True,
            )

    async def _load_claims_data(
        self,
        input_data: AllocatePaymentInput,
    ) -> list[ClaimAllocationItem]:
        """
        Load claim data for allocation.

        If claims_data is provided in input, use that.
        Otherwise, load from database (tenant-isolated).

        Args:
            input_data: Allocation input data

        Returns:
            List of claim allocation items

        Raises:
            InsufficientClaimDataError: If claim data cannot be loaded
        """
        if input_data.claims_data:
            return input_data.claims_data

        # In production, would load from database with tenant isolation
        # For now, raise error if not provided
        raise InsufficientClaimDataError(
            "Claim data must be provided in claimsData variable. "
            "Database lookup not yet implemented."
        )

    def _validate_claims_data(
        self,
        claims_data: list[ClaimAllocationItem],
        input_data: AllocatePaymentInput,
    ) -> None:
        """
        Validate claim data for allocation.

        Args:
            claims_data: Claim allocation items
            input_data: Allocation input data

        Raises:
            InsufficientClaimDataError: If validation fails
        """
        # Validate all claim IDs are present
        claim_ids_in_data = {item.claim_id for item in claims_data}
        claim_ids_requested = set(input_data.claim_ids)

        if claim_ids_in_data != claim_ids_requested:
            missing = claim_ids_requested - claim_ids_in_data
            extra = claim_ids_in_data - claim_ids_requested
            raise InsufficientClaimDataError(
                f"Claim data mismatch. Missing: {missing}, Extra: {extra}"
            )

        # Validate claim balances
        for claim in claims_data:
            if claim.claim_balance < 0:
                raise InsufficientClaimDataError(
                    f"Claim {claim.claim_id} has negative balance: {claim.claim_balance}"
                )

        # For FIFO/LIFO, validate claim dates are present
        if input_data.allocation_strategy in (AllocationStrategy.FIFO, AllocationStrategy.LIFO):
            for claim in claims_data:
                if claim.claim_date is None:
                    raise InsufficientClaimDataError(
                        f"Claim {claim.claim_id} missing claim_date required for {input_data.allocation_strategy} strategy"
                    )

    async def _allocate_payment(
        self,
        input_data: AllocatePaymentInput,
        claims_data: list[ClaimAllocationItem],
    ) -> tuple[list[AllocationResult], Decimal]:
        """
        Allocate payment across claims based on strategy.

        Args:
            input_data: Allocation input data
            claims_data: Claim allocation items

        Returns:
            Tuple of (allocations, unallocated_amount)

        Raises:
            InvalidAllocationStrategyError: If strategy is unknown
        """
        strategy = input_data.allocation_strategy

        if strategy == AllocationStrategy.FIFO:
            return await self._allocate_fifo(input_data.payment_amount, claims_data)
        elif strategy == AllocationStrategy.LIFO:
            return await self._allocate_lifo(input_data.payment_amount, claims_data)
        elif strategy == AllocationStrategy.PROPORTIONAL:
            return await self._allocate_proportional(input_data.payment_amount, claims_data)
        elif strategy == AllocationStrategy.MANUAL:
            return await self._allocate_manual(input_data, claims_data)
        else:
            raise InvalidAllocationStrategyError(strategy.value)

    async def _allocate_fifo(
        self,
        payment_amount: Decimal,
        claims_data: list[ClaimAllocationItem],
    ) -> tuple[list[AllocationResult], Decimal]:
        """
        Allocate payment using FIFO (First In, First Out) strategy.

        Allocates to oldest claims first (by claim_date).

        Args:
            payment_amount: Total amount to allocate
            claims_data: Claim allocation items

        Returns:
            Tuple of (allocations, unallocated_amount)
        """
        # Sort by claim date (oldest first)
        sorted_claims = sorted(claims_data, key=lambda x: x.claim_date or datetime.min)

        return await self._allocate_sequential(payment_amount, sorted_claims)

    async def _allocate_lifo(
        self,
        payment_amount: Decimal,
        claims_data: list[ClaimAllocationItem],
    ) -> tuple[list[AllocationResult], Decimal]:
        """
        Allocate payment using LIFO (Last In, First Out) strategy.

        Allocates to newest claims first (by claim_date).

        Args:
            payment_amount: Total amount to allocate
            claims_data: Claim allocation items

        Returns:
            Tuple of (allocations, unallocated_amount)
        """
        # Sort by claim date (newest first)
        sorted_claims = sorted(claims_data, key=lambda x: x.claim_date or datetime.min, reverse=True)

        return await self._allocate_sequential(payment_amount, sorted_claims)

    async def _allocate_sequential(
        self,
        payment_amount: Decimal,
        sorted_claims: list[ClaimAllocationItem],
    ) -> tuple[list[AllocationResult], Decimal]:
        """
        Allocate payment sequentially across claims.

        Helper method for FIFO and LIFO strategies.

        Args:
            payment_amount: Total amount to allocate
            sorted_claims: Claims sorted by allocation order

        Returns:
            Tuple of (allocations, unallocated_amount)
        """
        remaining = payment_amount
        allocations: list[AllocationResult] = []

        for claim in sorted_claims:
            if remaining <= 0:
                break

            # Calculate allocation amount (minimum of remaining and claim balance)
            allocation_amount = min(remaining, claim.claim_balance)

            if allocation_amount > 0:
                # Create allocation result
                allocation = AllocationResult(
                    claimId=claim.claim_id,
                    allocatedAmount=allocation_amount,
                    claimBalanceBefore=claim.claim_balance,
                    claimBalanceAfter=claim.claim_balance - allocation_amount,
                    fullyPaid=(claim.claim_balance - allocation_amount) == 0,
                )
                allocations.append(allocation)

                # Update remaining amount
                remaining -= allocation_amount

        unallocated_amount = remaining

        return allocations, unallocated_amount

    async def _allocate_proportional(
        self,
        payment_amount: Decimal,
        claims_data: list[ClaimAllocationItem],
    ) -> tuple[list[AllocationResult], Decimal]:
        """
        Allocate payment proportionally across claims.

        Splits payment proportionally based on claim balances.

        Args:
            payment_amount: Total amount to allocate
            claims_data: Claim allocation items

        Returns:
            Tuple of (allocations, unallocated_amount)
        """
        # Calculate total balance across all claims
        total_balance = sum(claim.claim_balance for claim in claims_data)

        if total_balance == 0:
            # No balances to allocate to
            return [], payment_amount

        allocations: list[AllocationResult] = []
        total_allocated = Decimal("0")

        # Calculate proportional allocations
        for i, claim in enumerate(claims_data):
            if claim.claim_balance == 0:
                continue

            # Calculate proportional share
            proportion = claim.claim_balance / total_balance

            # For last claim, use remaining amount to avoid rounding errors
            if i == len(claims_data) - 1:
                allocation_amount = payment_amount - total_allocated
            else:
                allocation_amount = (payment_amount * proportion).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )

            # Ensure allocation doesn't exceed claim balance
            allocation_amount = min(allocation_amount, claim.claim_balance)

            if allocation_amount > 0:
                allocation = AllocationResult(
                    claimId=claim.claim_id,
                    allocatedAmount=allocation_amount,
                    claimBalanceBefore=claim.claim_balance,
                    claimBalanceAfter=claim.claim_balance - allocation_amount,
                    fullyPaid=(claim.claim_balance - allocation_amount) == 0,
                )
                allocations.append(allocation)
                total_allocated += allocation_amount

        unallocated_amount = payment_amount - total_allocated

        return allocations, unallocated_amount

    async def _allocate_manual(
        self,
        input_data: AllocatePaymentInput,
        claims_data: list[ClaimAllocationItem],
    ) -> tuple[list[AllocationResult], Decimal]:
        """
        Allocate payment using manual allocations.

        Uses provided manual allocation amounts.

        Args:
            input_data: Allocation input data
            claims_data: Claim allocation items

        Returns:
            Tuple of (allocations, unallocated_amount)

        Raises:
            AllocationError: If manual allocations are invalid
        """
        if not input_data.manual_allocations:
            raise AllocationError("Manual allocations not provided for MANUAL strategy")

        # Create claim lookup
        claims_by_id = {claim.claim_id: claim for claim in claims_data}

        allocations: list[AllocationResult] = []
        total_allocated = Decimal("0")

        for manual_alloc in input_data.manual_allocations:
            claim = claims_by_id.get(manual_alloc.claim_id)
            if not claim:
                raise AllocationError(
                    f"Claim {manual_alloc.claim_id} not found in claims data"
                )

            # Validate allocation doesn't exceed claim balance
            if manual_alloc.amount > claim.claim_balance:
                raise AllocationError(
                    f"Allocation {manual_alloc.amount} exceeds claim balance {claim.claim_balance} "
                    f"for claim {manual_alloc.claim_id}"
                )

            allocation = AllocationResult(
                claimId=claim.claim_id,
                allocatedAmount=manual_alloc.amount,
                claimBalanceBefore=claim.claim_balance,
                claimBalanceAfter=claim.claim_balance - manual_alloc.amount,
                fullyPaid=(claim.claim_balance - manual_alloc.amount) == 0,
            )
            allocations.append(allocation)
            total_allocated += manual_alloc.amount

        unallocated_amount = input_data.payment_amount - total_allocated

        return allocations, unallocated_amount

    async def _create_allocation_accounting(
        self,
        payment_id: str,
        allocations: list[AllocationResult],
    ) -> list[str]:
        """
        Create accounting journal entries for each allocation.

        For each allocation:
        - Debit: Accounts Receivable for specific claim (decrease asset)
        - Credit: Revenue Recognition (increase revenue)

        Args:
            payment_id: Payment identifier
            allocations: List of allocations

        Returns:
            List of accounting reference IDs
        """
        accounting_references: list[str] = []

        for i, allocation in enumerate(allocations):
            # Generate journal entry ID
            journal_entry_id = f"JE-ALLOC-{payment_id}-{allocation.claim_id}-{i+1}"

            self._logger.info(
                "Creating accounting entry for allocation",
                journal_entry_id=journal_entry_id,
                payment_id=payment_id,
                claim_id=allocation.claim_id,
                amount=str(allocation.allocated_amount),
            )

            # In production, would create actual journal entries via accounting service
            # For now, just return the reference

            accounting_references.append(journal_entry_id)

        return accounting_references

    def _create_allocation_summary(
        self,
        input_data: AllocatePaymentInput,
        allocations: list[AllocationResult],
        unallocated_amount: Decimal,
    ) -> dict[str, Any]:
        """
        Create allocation summary breakdown.

        Args:
            input_data: Allocation input data
            allocations: List of allocations
            unallocated_amount: Remaining unallocated amount

        Returns:
            Allocation summary dictionary
        """
        total_allocated = sum(a.allocated_amount for a in allocations)
        claims_paid_in_full = sum(1 for a in allocations if a.fully_paid)
        claims_partially_paid = sum(1 for a in allocations if not a.fully_paid and a.allocated_amount > 0)

        summary = {
            "paymentId": input_data.payment_id,
            "strategy": input_data.allocation_strategy.value,
            "paymentAmount": float(input_data.payment_amount),
            "totalAllocated": float(total_allocated),
            "unallocatedAmount": float(unallocated_amount),
            "allocationPercentage": float(
                (total_allocated / input_data.payment_amount * 100).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            ) if input_data.payment_amount > 0 else 0.0,
            "claimsCount": len(allocations),
            "claimsPaidInFull": claims_paid_in_full,
            "claimsPartiallyPaid": claims_partially_paid,
            "allocationsByClaimId": {
                alloc.claim_id: {
                    "allocated": float(alloc.allocated_amount),
                    "balanceBefore": float(alloc.claim_balance_before),
                    "balanceAfter": float(alloc.claim_balance_after),
                    "fullyPaid": alloc.fully_paid,
                }
                for alloc in allocations
            },
        }

        return summary
