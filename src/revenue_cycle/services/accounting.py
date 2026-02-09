"""
Accounting service for CPC 25 compliant provision accounting.

Handles:
- Journal entry creation
- Accounting period management
- ERP integration queueing
- Audit trail logging
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import uuid4

import structlog

from revenue_cycle.config import Settings, get_settings
from revenue_cycle.domain.value_objects.provision import (
    AccountCode,
    AccountingEntry,
    CPC25Category,
    ProvisionType,
)

logger = structlog.get_logger(__name__)


class AccountingService:
    """
    Service for accounting operations related to provisions.

    Implements CPC 25 (NBC TG 25) compliant accounting for:
    - Provision recognition
    - Journal entry creation
    - ERP integration

    Example:
        accounting = AccountingService()

        # Create provision journal entries
        entries = accounting.create_provision_entries(
            provision_id="PROV-001",
            glosa_id="GL-001",
            amount=Decimal("5000.00"),
            period="2026-01",
            provision_type=ProvisionType.GLOSA_FULL,
        )
    """

    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize accounting service.

        Args:
            settings: Application settings
        """
        self._settings = settings or get_settings()
        self._logger = logger.bind(service="accounting")

    def create_provision_entries(
        self,
        provision_id: str,
        glosa_id: str,
        amount: Decimal,
        period: str,
        provision_type: ProvisionType = ProvisionType.GLOSA_FULL,
    ) -> tuple[AccountingEntry, AccountingEntry]:
        """
        Create double-entry journal entries for a provision.

        CPC 25 requires recognition of provisions when:
        1. There is a present obligation from a past event
        2. It is probable that outflow will be required
        3. The amount can be reliably estimated

        Args:
            provision_id: Unique provision identifier
            glosa_id: Related glosa identifier
            amount: Provision amount
            period: Accounting period (YYYY-MM)
            provision_type: Type of provision

        Returns:
            Tuple of (debit_entry, credit_entry)

        Raises:
            ValueError: If amount is invalid
        """
        if amount <= 0 and provision_type != ProvisionType.REVERSAL:
            raise ValueError(f"Provision amount must be positive: {amount}")

        # Get account codes based on provision type
        debit_code, debit_desc = AccountCode.get_debit_account(provision_type)
        credit_code, credit_desc = AccountCode.get_credit_account(provision_type)

        # Generate entry IDs
        entry_id_debit = f"JE-{provision_id}-D"
        entry_id_credit = f"JE-{provision_id}-C"

        # Create debit entry (expense for new provisions, liability for reversals)
        debit_entry = AccountingEntry(
            entry_id=entry_id_debit,
            account_code=debit_code,
            account_name=debit_desc,
            debit=amount,
            credit=Decimal("0"),
            period=period,
            reference=provision_id,
            description=f"Provisao para Glosa {glosa_id} - {provision_type.value}",
        )

        # Create credit entry (liability for new provisions, revenue for reversals)
        credit_entry = AccountingEntry(
            entry_id=entry_id_credit,
            account_code=credit_code,
            account_name=credit_desc,
            debit=Decimal("0"),
            credit=amount,
            period=period,
            reference=provision_id,
            description=f"Provisao para Glosa {glosa_id} - {provision_type.value}",
        )

        self._logger.info(
            "Created provision journal entries",
            provision_id=provision_id,
            glosa_id=glosa_id,
            amount=str(amount),
            period=period,
            debit_account=debit_code,
            credit_account=credit_code,
        )

        return debit_entry, credit_entry

    def determine_cpc25_category(
        self,
        recovery_probability: int,
        provision_type: ProvisionType,
    ) -> CPC25Category:
        """
        Determine CPC 25 classification for a provision.

        Based on NBC TG 25 guidance:
        - Probable (> 75%): Recognize provision
        - Possible (25-75%): Disclose as contingent liability
        - Remote (< 25%): No disclosure required

        Args:
            recovery_probability: Probability of recovery (0-100)
            provision_type: Type of provision

        Returns:
            CPC 25 category
        """
        # For provisions, we look at loss probability (inverse of recovery)
        loss_probability = 100 - recovery_probability

        return CPC25Category.from_probability(loss_probability)

    def calculate_provision_amount(
        self,
        glosa_amount: Decimal,
        provision_type: ProvisionType,
        provision_percentage: Optional[Decimal] = None,
        recovery_probability: Optional[int] = None,
    ) -> Decimal:
        """
        Calculate the provision amount based on type and probability.

        Args:
            glosa_amount: Original glosa amount
            provision_type: Type of provision
            provision_percentage: Optional explicit percentage
            recovery_probability: Optional recovery probability for partial provisions

        Returns:
            Calculated provision amount
        """
        if provision_percentage is not None:
            percentage = provision_percentage
        elif provision_type == ProvisionType.GLOSA_PARTIAL and recovery_probability is not None:
            # For partial provisions, use inverse of recovery probability
            percentage = Decimal(100 - recovery_probability)
        else:
            percentage = provision_type.default_percentage

        amount = (glosa_amount * percentage) / Decimal("100")

        self._logger.debug(
            "Calculated provision amount",
            glosa_amount=str(glosa_amount),
            percentage=str(percentage),
            provision_amount=str(amount),
            provision_type=provision_type.value,
        )

        return amount.quantize(Decimal("0.01"))

    def get_current_accounting_period(self) -> str:
        """
        Get the current accounting period in YYYY-MM format.

        Returns:
            Current period string
        """
        now = datetime.utcnow()
        return f"{now.year}-{now.month:02d}"

    def validate_accounting_period(self, period: str) -> bool:
        """
        Validate an accounting period format.

        Args:
            period: Period string to validate

        Returns:
            True if valid, False otherwise
        """
        import re

        if not re.match(r"^\d{4}-\d{2}$", period):
            return False

        try:
            year = int(period[:4])
            month = int(period[5:7])
            return 1900 <= year <= 2100 and 1 <= month <= 12
        except ValueError:
            return False

    def generate_accounting_entry_id(self, provision_id: str) -> str:
        """
        Generate a unique accounting entry ID.

        Args:
            provision_id: Related provision ID

        Returns:
            Unique entry ID
        """
        return f"AE-{provision_id}-{uuid4().hex[:8].upper()}"
