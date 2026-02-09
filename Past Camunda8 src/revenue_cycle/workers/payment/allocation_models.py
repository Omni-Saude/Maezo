"""
Pydantic models for payment allocation workers input/output validation.

These models provide type-safe validation for allocating payments across
multiple claims with various allocation strategies.

Allocation Strategies:
- FIFO: First In, First Out (allocate to oldest claims first)
- LIFO: Last In, First Out (allocate to newest claims first)
- PROPORTIONAL: Split proportionally based on claim amounts
- MANUAL: Use provided manual allocations
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class AllocationStrategy(str, Enum):
    """
    Strategies for allocating payments across multiple claims.

    Attributes:
        FIFO: First In, First Out - allocate to oldest claims first
        LIFO: Last In, First Out - allocate to newest claims first
        PROPORTIONAL: Split proportionally based on claim amounts
        MANUAL: Use manually specified allocations
    """

    FIFO = "FIFO"
    LIFO = "LIFO"
    PROPORTIONAL = "PROPORTIONAL"
    MANUAL = "MANUAL"


class ClaimAllocationItem(BaseModel):
    """
    A single claim allocation item.

    Represents allocation of payment to one specific claim.
    """

    claim_id: str = Field(
        ...,
        alias="claimId",
        description="Claim identifier",
    )
    claim_amount: Decimal = Field(
        ...,
        alias="claimAmount",
        gt=0,
        description="Total claim amount",
    )
    claim_balance: Decimal = Field(
        ...,
        alias="claimBalance",
        ge=0,
        description="Remaining balance on claim",
    )
    claim_date: Optional[datetime] = Field(
        None,
        alias="claimDate",
        description="Claim creation date (for FIFO/LIFO)",
    )
    allocated_amount: Decimal = Field(
        Decimal("0"),
        alias="allocatedAmount",
        ge=0,
        description="Amount allocated to this claim",
    )

    @field_validator("claim_amount", "claim_balance", "allocated_amount", mode="before")
    @classmethod
    def parse_decimal(cls, v: Any) -> Decimal:
        """Parse various numeric types to Decimal."""
        if v is None:
            return Decimal("0")
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v.replace(",", "."))
        raise ValueError(f"Cannot convert {type(v).__name__} to Decimal")

    @field_validator("claim_date", mode="before")
    @classmethod
    def parse_datetime(cls, v: Any) -> Optional[datetime]:
        """Parse datetime from various formats."""
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                from dateutil import parser
                return parser.parse(v)
        raise ValueError(f"Cannot convert {type(v).__name__} to datetime")

    model_config = {
        "populate_by_name": True,
    }


class ManualAllocation(BaseModel):
    """
    Manual allocation specification.

    Used when allocation_strategy is MANUAL.
    """

    claim_id: str = Field(
        ...,
        alias="claimId",
        description="Claim identifier",
    )
    amount: Decimal = Field(
        ...,
        gt=0,
        description="Amount to allocate to this claim",
    )

    @field_validator("amount", mode="before")
    @classmethod
    def parse_decimal(cls, v: Any) -> Decimal:
        """Parse various numeric types to Decimal."""
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v.replace(",", "."))
        raise ValueError(f"Cannot convert {type(v).__name__} to Decimal")

    model_config = {
        "populate_by_name": True,
    }


class AllocatePaymentInput(BaseModel):
    """
    Input model for AllocatePaymentWorker.

    Validates all required fields for allocating payments across claims.
    """

    payment_id: str = Field(
        ...,
        alias="paymentId",
        min_length=1,
        description="Unique payment identifier",
    )
    payment_amount: Decimal = Field(
        ...,
        alias="paymentAmount",
        gt=0,
        description="Total payment amount to allocate",
    )
    claim_ids: list[str] = Field(
        ...,
        alias="claimIds",
        min_length=1,
        description="List of claim IDs to allocate against",
    )
    allocation_strategy: AllocationStrategy = Field(
        ...,
        alias="allocationStrategy",
        description="Strategy to use for allocation",
    )

    # Optional fields
    manual_allocations: Optional[list[ManualAllocation]] = Field(
        None,
        alias="manualAllocations",
        description="Manual allocation amounts (required if strategy is MANUAL)",
    )
    claims_data: Optional[list[ClaimAllocationItem]] = Field(
        None,
        alias="claimsData",
        description="Claim details for allocation calculations",
    )

    # Multi-tenant support
    tenant_id: Optional[str] = Field(
        None,
        alias="tenantId",
        description="Tenant identifier",
    )

    @field_validator("payment_amount", mode="before")
    @classmethod
    def parse_decimal(cls, v: Any) -> Decimal:
        """Parse various numeric types to Decimal."""
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v.replace(",", "."))
        raise ValueError(f"Cannot convert {type(v).__name__} to Decimal")

    @model_validator(mode="after")
    def validate_manual_allocations(self) -> "AllocatePaymentInput":
        """Validate manual allocations if strategy is MANUAL."""
        if self.allocation_strategy == AllocationStrategy.MANUAL:
            if not self.manual_allocations:
                raise ValueError("manual_allocations required when strategy is MANUAL")

            # Validate manual allocations match claim IDs
            manual_claim_ids = {alloc.claim_id for alloc in self.manual_allocations}
            if manual_claim_ids != set(self.claim_ids):
                raise ValueError(
                    "manual_allocations must include all claim_ids and no others"
                )

            # Validate total manual allocations don't exceed payment amount
            total_manual = sum(alloc.amount for alloc in self.manual_allocations)
            if total_manual > self.payment_amount:
                raise ValueError(
                    f"Total manual allocations ({total_manual}) exceeds payment amount ({self.payment_amount})"
                )

        return self

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "paymentId": "PAY-2026-001234",
                    "paymentAmount": "10000.00",
                    "claimIds": ["CLM-2026-001", "CLM-2026-002", "CLM-2026-003"],
                    "allocationStrategy": "FIFO",
                }
            ]
        },
    }


class AllocationResult(BaseModel):
    """
    Result of allocating payment to a single claim.

    Contains the claim ID and allocated amount.
    """

    claim_id: str = Field(
        ...,
        alias="claimId",
        description="Claim identifier",
    )
    allocated_amount: Decimal = Field(
        ...,
        alias="allocatedAmount",
        ge=0,
        description="Amount allocated to this claim",
    )
    claim_balance_before: Decimal = Field(
        ...,
        alias="claimBalanceBefore",
        description="Claim balance before allocation",
    )
    claim_balance_after: Decimal = Field(
        ...,
        alias="claimBalanceAfter",
        ge=0,
        description="Claim balance after allocation",
    )
    fully_paid: bool = Field(
        ...,
        alias="fullyPaid",
        description="Whether claim is fully paid after allocation",
    )

    @field_validator("allocated_amount", "claim_balance_before", "claim_balance_after", mode="before")
    @classmethod
    def parse_decimal(cls, v: Any) -> Decimal:
        """Parse various numeric types to Decimal."""
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v.replace(",", "."))
        raise ValueError(f"Cannot convert {type(v).__name__} to Decimal")

    model_config = {
        "populate_by_name": True,
    }


class AllocatePaymentOutput(BaseModel):
    """
    Output model for AllocatePaymentWorker.

    Contains allocation results and summary.
    """

    allocation_complete: bool = Field(
        ...,
        alias="allocationComplete",
        description="Whether allocation completed successfully",
    )
    allocations: list[AllocationResult] = Field(
        ...,
        description="List of allocations per claim",
    )
    unallocated_amount: Decimal = Field(
        ...,
        alias="unallocatedAmount",
        ge=0,
        description="Remaining unallocated amount",
    )
    allocation_summary: dict[str, Any] = Field(
        ...,
        alias="allocationSummary",
        description="Summary of allocation results",
    )

    # Accounting references
    accounting_references: list[str] = Field(
        default_factory=list,
        alias="accountingReferences",
        description="Accounting entry references for each allocation",
    )
    allocation_date: datetime = Field(
        default_factory=datetime.utcnow,
        alias="allocationDate",
        description="Timestamp of allocation",
    )

    @field_validator("unallocated_amount", mode="before")
    @classmethod
    def parse_decimal(cls, v: Any) -> Decimal:
        """Parse various numeric types to Decimal."""
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v.replace(",", "."))
        raise ValueError(f"Cannot convert {type(v).__name__} to Decimal")

    model_config = {
        "populate_by_name": True,
        "json_encoders": {
            Decimal: lambda v: float(round(v, 2)),
            datetime: lambda v: v.isoformat(),
        },
        "json_schema_extra": {
            "examples": [
                {
                    "allocationComplete": True,
                    "allocations": [
                        {
                            "claimId": "CLM-2026-001",
                            "allocatedAmount": "5000.00",
                            "claimBalanceBefore": "5000.00",
                            "claimBalanceAfter": "0.00",
                            "fullyPaid": True,
                        },
                        {
                            "claimId": "CLM-2026-002",
                            "allocatedAmount": "5000.00",
                            "claimBalanceBefore": "8000.00",
                            "claimBalanceAfter": "3000.00",
                            "fullyPaid": False,
                        },
                    ],
                    "unallocatedAmount": "0.00",
                    "allocationSummary": {
                        "totalAllocated": "10000.00",
                        "claimsPaidInFull": 1,
                        "claimsPartiallyPaid": 1,
                        "strategy": "FIFO",
                    },
                }
            ]
        },
    }
