"""
Contract pricing service for hospital revenue cycle.

Provides contract lookup, pricing rules application, and discount calculations
based on Brazilian healthcare insurance contracts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional, Protocol

import structlog

if TYPE_CHECKING:
    from revenue_cycle.workers.billing.models import (
        AdjustedChargeItem,
        ChargeItem,
        Contract,
        DiscountApplied,
        PricingTableType,
    )

logger = structlog.get_logger(__name__)


# Define ChargeCategory locally to avoid circular imports
# This mirrors the enum in workers/billing/models.py
class ChargeCategory(str, Enum):
    """
    Categories of charges in the billing system.

    Based on ANS (Agencia Nacional de Saude Suplementar) standards.
    """

    PROFESSIONAL = "PROFESSIONAL"
    HOSPITAL = "HOSPITAL"
    MATERIALS = "MATERIALS"
    MEDICATIONS = "MEDICATIONS"
    SERVICES = "SERVICES"
    PACKAGES = "PACKAGES"


# Default discount rates by category (ANS standard)
DEFAULT_DISCOUNT_RATES: dict[ChargeCategory, Decimal] = {
    ChargeCategory.PROFESSIONAL: Decimal("0.10"),  # 10% AMB/CBHPM procedures
    ChargeCategory.HOSPITAL: Decimal("0.15"),  # 15% hospital fees
    ChargeCategory.MATERIALS: Decimal("0.05"),  # 5% OPME materials
    ChargeCategory.MEDICATIONS: Decimal("0.08"),  # 8% medications
    ChargeCategory.SERVICES: Decimal("0.10"),  # 10% general services
    ChargeCategory.PACKAGES: Decimal("0.12"),  # 12% package rates
}


class DatabaseServiceProtocol(Protocol):
    """Protocol for database service operations."""

    async def fetch_one(self, query: str, params: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Fetch a single row from the database."""
        ...

    async def fetch_all(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Fetch all rows matching the query."""
        ...


class ContractService(ABC):
    """
    Abstract contract service interface.

    Defines the contract for retrieving and applying contract rules.
    """

    @abstractmethod
    async def get_active_contract(
        self,
        payer_id: str,
        tenant_id: Optional[str] = None,
    ) -> Optional[Contract]:
        """
        Get active contract for a payer.

        Args:
            payer_id: Insurance payer identifier (ANS code or CNPJ)
            tenant_id: Optional tenant identifier for multi-tenant support

        Returns:
            Contract object if found, None otherwise
        """
        ...

    @abstractmethod
    async def apply_rules(
        self,
        contract: Contract,
        charges: list[ChargeItem],
    ) -> list[AdjustedChargeItem]:
        """
        Apply contract pricing rules to charge items.

        Args:
            contract: Contract with rules to apply
            charges: List of charge items to process

        Returns:
            List of adjusted charge items with discounts applied
        """
        ...

    @abstractmethod
    async def calculate_discounts(
        self,
        contract: Contract,
        adjusted_charges: list[AdjustedChargeItem],
        subtotal: Decimal,
    ) -> list[DiscountApplied]:
        """
        Calculate and document all discounts applied.

        Args:
            contract: Contract rules
            adjusted_charges: Charges after rule application
            subtotal: Original subtotal before discounts

        Returns:
            List of discount information
        """
        ...


class ContractPricingService(ContractService):
    """
    Contract pricing service implementation.

    Provides full contract rules application with:
    - Category-specific discount rates
    - Procedure coverage validation
    - Contract limit validation
    - Discount documentation
    """

    def __init__(self, db_service: Optional[DatabaseServiceProtocol] = None):
        """
        Initialize the contract pricing service.

        Args:
            db_service: Optional database service for contract lookup
        """
        self.db = db_service
        self._logger = logger.bind(service="ContractPricingService")

    async def get_active_contract(
        self,
        payer_id: str,
        tenant_id: Optional[str] = None,
    ) -> Optional[Contract]:
        """
        Get active contract for a payer.

        Queries the database for an active contract matching the payer.
        Falls back to default rates if no database service is configured.

        Args:
            payer_id: Insurance payer identifier
            tenant_id: Optional tenant identifier

        Returns:
            Contract object if found, None otherwise
        """
        self._logger.info(
            "Looking up contract",
            payer_id=payer_id,
            tenant_id=tenant_id,
        )

        if self.db is not None:
            return await self._get_contract_from_db(payer_id, tenant_id)

        # Fallback: return mock contract with default rates
        self._logger.warning(
            "No database configured, using default contract rates",
            payer_id=payer_id,
        )
        return self._create_default_contract(payer_id, tenant_id)

    async def _get_contract_from_db(
        self,
        payer_id: str,
        tenant_id: Optional[str] = None,
    ) -> Optional["Contract"]:
        """
        Get contract from database.

        Args:
            payer_id: Insurance payer identifier
            tenant_id: Optional tenant identifier

        Returns:
            Contract object if found, None otherwise
        """
        # Lazy import to avoid circular dependency
        from revenue_cycle.workers.billing.models import Contract, PricingTableType

        # Build query with optional tenant filter
        query = """
            SELECT c.contract_id, c.payer_id, c.payer_name, c.max_claim_amount,
                   c.effective_date, c.expiration_date, c.status, c.pricing_table
            FROM contracts c
            WHERE c.payer_id = :payer_id
              AND c.status = 'ACTIVE'
              AND c.effective_date <= CURRENT_DATE
              AND (c.expiration_date IS NULL OR c.expiration_date >= CURRENT_DATE)
        """
        params: dict[str, Any] = {"payer_id": payer_id}

        if tenant_id:
            query += " AND c.tenant_id = :tenant_id"
            params["tenant_id"] = tenant_id

        query += " LIMIT 1"

        contract_row = await self.db.fetch_one(query, params)

        if not contract_row:
            self._logger.warning("No active contract found", payer_id=payer_id)
            return None

        # Fetch discount rates
        rates = await self.db.fetch_all(
            "SELECT category, discount_rate FROM contract_discount_rates "
            "WHERE contract_id = :contract_id",
            {"contract_id": contract_row["contract_id"]},
        )

        # Fetch covered procedures
        procedures = await self.db.fetch_all(
            "SELECT procedure_code FROM contract_procedures "
            "WHERE contract_id = :contract_id AND coverage_status = 'COVERED'",
            {"contract_id": contract_row["contract_id"]},
        )

        # Build contract object
        discount_rates = {
            r["category"]: Decimal(str(r["discount_rate"])) for r in rates
        }

        contract = Contract(
            contract_id=contract_row["contract_id"],
            payer_id=contract_row["payer_id"],
            payer_name=contract_row.get("payer_name"),
            max_claim_amount=(
                Decimal(str(contract_row["max_claim_amount"]))
                if contract_row.get("max_claim_amount")
                else None
            ),
            effective_date=contract_row["effective_date"],
            expiration_date=contract_row.get("expiration_date"),
            status=contract_row["status"],
            pricing_table=PricingTableType(
                contract_row.get("pricing_table", "TUSS")
            ),
            discount_rates=discount_rates,
            covered_procedures=[p["procedure_code"] for p in procedures],
            tenant_id=tenant_id,
        )

        self._logger.info(
            "Contract retrieved",
            contract_id=contract.contract_id,
            payer_id=contract.payer_id,
            categories_with_rates=len(discount_rates),
            covered_procedures=len(contract.covered_procedures),
        )

        return contract

    def _create_default_contract(
        self,
        payer_id: str,
        tenant_id: Optional[str] = None,
    ) -> "Contract":
        """
        Create a default contract with standard rates.

        Used when no database is configured or as a fallback.

        Args:
            payer_id: Insurance payer identifier
            tenant_id: Optional tenant identifier

        Returns:
            Contract with default rates
        """
        # Lazy import to avoid circular dependency
        from revenue_cycle.workers.billing.models import Contract, PricingTableType

        return Contract(
            contract_id=f"DEFAULT-{payer_id}",
            payer_id=payer_id,
            payer_name=f"Default Contract for {payer_id}",
            effective_date=date.today(),
            pricing_table=PricingTableType.TUSS,
            discount_rates={
                cat.value: rate for cat, rate in DEFAULT_DISCOUNT_RATES.items()
            },
            covered_procedures=[],  # Empty = all covered
            tenant_id=tenant_id,
        )

    async def apply_rules(
        self,
        contract: "Contract",
        charges: "list[ChargeItem]",
    ) -> "list[AdjustedChargeItem]":
        """
        Apply contract pricing rules to charge items.

        For each charge:
        1. Look up discount rate for the category
        2. Calculate discount amount
        3. Apply rounding (HALF_UP to 2 decimal places)
        4. Create adjusted charge with all metadata

        Args:
            contract: Contract with rules to apply
            charges: List of charge items to process

        Returns:
            List of adjusted charge items with discounts applied
        """
        # Lazy import to avoid circular dependency
        from revenue_cycle.workers.billing.models import AdjustedChargeItem

        adjusted_charges: list[AdjustedChargeItem] = []

        for charge in charges:
            # Get discount rate for category
            discount_rate = self._get_discount_rate(contract, charge.category)

            # Calculate discount and adjusted amount
            total_amount = charge.total_amount
            discount = (total_amount * discount_rate).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            adjusted_amount = (total_amount - discount).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

            # Build rule description
            rule_description = self._build_rule_description(
                charge.category, discount_rate, contract.pricing_table
            )

            # Create adjusted charge
            adjusted = AdjustedChargeItem(
                charge_code=charge.charge_code,
                description=charge.description,
                category=charge.category.value,
                quantity=charge.quantity,
                original_amount=total_amount,
                contract_discount=discount,
                amount=adjusted_amount,
                discount_rate=discount_rate,
                rule_applied=rule_description,
                pricing_table=contract.pricing_table.value,
            )

            adjusted_charges.append(adjusted)

            self._logger.debug(
                "Applied rule to charge",
                charge_code=charge.charge_code,
                category=charge.category.value,
                original=float(total_amount),
                discount=float(discount),
                adjusted=float(adjusted_amount),
                rate=float(discount_rate),
            )

        return adjusted_charges

    def _get_discount_rate(
        self,
        contract: "Contract",
        category: Any,
    ) -> Decimal:
        """
        Get discount rate for a category from contract or defaults.

        Args:
            contract: Contract with rates
            category: Charge category

        Returns:
            Discount rate as Decimal (0.0 to 1.0)
        """
        # First try contract-specific rate
        rate = contract.get_discount_rate(category)

        # If no contract rate, use default
        if rate == Decimal("0"):
            rate = DEFAULT_DISCOUNT_RATES.get(category, Decimal("0"))

        return rate

    def _build_rule_description(
        self,
        category: Any,
        discount_rate: Decimal,
        pricing_table: Any,
    ) -> str:
        """
        Build a human-readable rule description.

        Args:
            category: Charge category
            discount_rate: Applied discount rate
            pricing_table: Pricing table used

        Returns:
            Rule description string
        """
        percentage = float(discount_rate * 100)
        return (
            f"Category {category.value}: {percentage:.1f}% discount "
            f"per {pricing_table.value} table"
        )

    async def calculate_discounts(
        self,
        contract: "Contract",
        adjusted_charges: "list[AdjustedChargeItem]",
        subtotal: Decimal,
    ) -> "list[DiscountApplied]":
        """
        Calculate and document all discounts applied.

        Groups discounts by category and calculates totals.

        Args:
            contract: Contract rules
            adjusted_charges: Charges after rule application
            subtotal: Original subtotal before discounts

        Returns:
            List of discount information
        """
        # Lazy import to avoid circular dependency
        from revenue_cycle.workers.billing.models import DiscountApplied

        discounts: list[DiscountApplied] = []

        # Group discounts by category
        category_discounts: dict[str, Decimal] = {}
        category_rates: dict[str, Decimal] = {}

        for charge in adjusted_charges:
            category = charge.category
            if category not in category_discounts:
                category_discounts[category] = Decimal("0")
                category_rates[category] = charge.discount_rate

            category_discounts[category] += charge.contract_discount

        # Create discount entries
        for category, amount in category_discounts.items():
            if amount > 0:
                rate = category_rates[category]
                percentage = float(rate * 100)

                discount = DiscountApplied(
                    discount_type="CATEGORY",
                    category=category,
                    rate=rate,
                    amount=amount,
                    description=f"{category} discount: {percentage:.1f}% = R$ {float(amount):.2f}",
                )
                discounts.append(discount)

        # Add total contract discount
        total_discount = sum(d.amount for d in discounts)
        if total_discount > 0:
            overall_rate = (
                total_discount / subtotal if subtotal > 0 else Decimal("0")
            ).quantize(Decimal("0.0001"))

            discounts.append(
                DiscountApplied(
                    discount_type="CONTRACT",
                    category=None,
                    rate=overall_rate,
                    amount=total_discount,
                    description=f"Total contract discount: {float(overall_rate * 100):.2f}% = R$ {float(total_discount):.2f}",
                )
            )

        return discounts


# Lazy import helper for runtime imports to avoid circular dependencies
def _get_billing_models():
    """Lazy import billing models to avoid circular imports."""
    from revenue_cycle.workers.billing.models import (
        AdjustedChargeItem,
        ChargeItem,
        Contract,
        DiscountApplied,
        PricingTableType,
    )
    return AdjustedChargeItem, ChargeItem, Contract, DiscountApplied, PricingTableType


class MockContractService(ContractService):
    """
    Mock contract service for testing.

    Provides configurable contract rules without database dependency.
    """

    def __init__(
        self,
        contracts: Optional[dict[str, Any]] = None,
        default_rates: Optional[dict[ChargeCategory, Decimal]] = None,
    ):
        """
        Initialize mock service.

        Args:
            contracts: Pre-configured contracts by payer_id
            default_rates: Default discount rates
        """
        self._contracts = contracts or {}
        self._default_rates = default_rates or DEFAULT_DISCOUNT_RATES
        self._logger = logger.bind(service="MockContractService")

    async def get_active_contract(
        self,
        payer_id: str,
        tenant_id: Optional[str] = None,
    ) -> Optional["Contract"]:
        """Get contract from mock data."""
        # Lazy import to avoid circular dependency
        from revenue_cycle.workers.billing.models import Contract, PricingTableType

        if payer_id in self._contracts:
            return self._contracts[payer_id]

        # Create default contract
        return Contract(
            contract_id=f"MOCK-{payer_id}",
            payer_id=payer_id,
            payer_name=f"Mock Contract for {payer_id}",
            effective_date=date.today(),
            pricing_table=PricingTableType.TUSS,
            discount_rates={
                cat.value: rate for cat, rate in self._default_rates.items()
            },
            covered_procedures=[],
            tenant_id=tenant_id,
        )

    async def apply_rules(
        self,
        contract: "Contract",
        charges: "list[ChargeItem]",
    ) -> "list[AdjustedChargeItem]":
        """Apply rules using same logic as main service."""
        service = ContractPricingService()
        return await service.apply_rules(contract, charges)

    async def calculate_discounts(
        self,
        contract: "Contract",
        adjusted_charges: "list[AdjustedChargeItem]",
        subtotal: Decimal,
    ) -> "list[DiscountApplied]":
        """Calculate discounts using same logic as main service."""
        service = ContractPricingService()
        return await service.calculate_discounts(
            contract, adjusted_charges, subtotal
        )

    def add_contract(self, contract: "Contract") -> None:
        """Add a contract to the mock data."""
        self._contracts[contract.payer_id] = contract

    def set_rates(
        self,
        payer_id: str,
        rates: dict[ChargeCategory, Decimal],
    ) -> None:
        """Set custom rates for a payer."""
        if payer_id in self._contracts:
            self._contracts[payer_id].discount_rates = {
                cat.value: rate for cat, rate in rates.items()
            }
