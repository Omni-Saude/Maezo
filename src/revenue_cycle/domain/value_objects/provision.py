"""
Provision-related value objects and enums.

CPC 25 (Provisions, Contingent Liabilities and Contingent Assets) compliant
structures for financial provisions in the Brazilian healthcare system.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional


class ProvisionType(str, Enum):
    """
    Types of financial provisions based on CPC 25 standards.

    Attributes:
        GLOSA_FULL: Full provision for entire glosa amount (100%)
        GLOSA_PARTIAL: Partial provision based on recovery probability
        ESTIMATED_LOSS: Provision for estimated loss on appeal
        CONTINGENT_LIABILITY: Contingent liability provision
        REVERSAL: Provision reversal (negative provision)
    """

    GLOSA_FULL = "GLOSA_FULL"
    GLOSA_PARTIAL = "GLOSA_PARTIAL"
    ESTIMATED_LOSS = "ESTIMATED_LOSS"
    CONTINGENT_LIABILITY = "CONTINGENT_LIABILITY"
    REVERSAL = "REVERSAL"

    @property
    def is_full_provision(self) -> bool:
        """Check if this is a full (100%) provision."""
        return self == ProvisionType.GLOSA_FULL

    @property
    def default_percentage(self) -> Decimal:
        """Get the default provision percentage for this type."""
        percentages = {
            ProvisionType.GLOSA_FULL: Decimal("100.00"),
            ProvisionType.GLOSA_PARTIAL: Decimal("50.00"),
            ProvisionType.ESTIMATED_LOSS: Decimal("100.00"),
            ProvisionType.CONTINGENT_LIABILITY: Decimal("50.00"),
            ProvisionType.REVERSAL: Decimal("0.00"),
        }
        return percentages.get(self, Decimal("100.00"))


class ProvisionStatus(str, Enum):
    """
    Status of a provision in its lifecycle.

    Attributes:
        ACTIVE: Provision is active and affects financial statements
        REVERSED: Provision was reversed (e.g., glosa recovered)
        UTILIZED: Provision was utilized (e.g., write-off)
        CANCELLED: Provision was cancelled
    """

    ACTIVE = "ACTIVE"
    REVERSED = "REVERSED"
    UTILIZED = "UTILIZED"
    CANCELLED = "CANCELLED"


class ERPSyncStatus(str, Enum):
    """
    ERP synchronization status for provisions.

    Attributes:
        PENDING: Not yet sent to ERP
        SENT: Sent to ERP, awaiting confirmation
        SYNCED: Successfully synchronized with ERP
        FAILED: Synchronization failed
        NOT_APPLICABLE: ERP sync not applicable
    """

    PENDING = "PENDING"
    SENT = "SENT"
    SYNCED = "SYNCED"
    FAILED = "FAILED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CPC25Category(str, Enum):
    """
    CPC 25 provision categories for financial reporting.

    Based on NBC TG 25 (Provisoes, Passivos Contingentes e Ativos Contingentes).

    Attributes:
        PROVISION_PROBABLE: Provision for probable loss (recognized)
        CONTINGENT_POSSIBLE: Contingent liability for possible loss (disclosed)
        CONTINGENT_REMOTE: Contingent liability for remote loss (not disclosed)
        ASSET_VIRTUAL_CERTAIN: Contingent asset virtually certain (recognized)
        ASSET_PROBABLE: Contingent asset probable (disclosed)
    """

    PROVISION_PROBABLE = "PROVISION_PROBABLE"
    CONTINGENT_POSSIBLE = "CONTINGENT_POSSIBLE"
    CONTINGENT_REMOTE = "CONTINGENT_REMOTE"
    ASSET_VIRTUAL_CERTAIN = "ASSET_VIRTUAL_CERTAIN"
    ASSET_PROBABLE = "ASSET_PROBABLE"

    @classmethod
    def from_probability(cls, probability: int) -> "CPC25Category":
        """
        Determine CPC 25 category based on probability percentage.

        Args:
            probability: Probability of loss/recovery (0-100)

        Returns:
            Appropriate CPC 25 category
        """
        if probability >= 75:
            return cls.PROVISION_PROBABLE
        elif probability >= 25:
            return cls.CONTINGENT_POSSIBLE
        else:
            return cls.CONTINGENT_REMOTE


@dataclass(frozen=True)
class AccountingEntry:
    """
    Immutable representation of a journal entry for accounting.

    Attributes:
        entry_id: Unique entry identifier
        account_code: Chart of accounts code
        account_name: Account description
        debit: Debit amount (0 if credit)
        credit: Credit amount (0 if debit)
        period: Accounting period (YYYY-MM)
        reference: Reference document (e.g., provision_id)
        description: Entry description
    """

    entry_id: str
    account_code: str
    account_name: str
    debit: Decimal
    credit: Decimal
    period: str
    reference: str
    description: str

    def __post_init__(self):
        """Validate entry after initialization."""
        if self.debit < 0 or self.credit < 0:
            raise ValueError("Debit and credit must be non-negative")
        if self.debit > 0 and self.credit > 0:
            raise ValueError("Entry cannot have both debit and credit")

    @property
    def is_debit(self) -> bool:
        """Check if this is a debit entry."""
        return self.debit > 0

    @property
    def is_credit(self) -> bool:
        """Check if this is a credit entry."""
        return self.credit > 0

    @property
    def amount(self) -> Decimal:
        """Get the entry amount."""
        return self.debit if self.is_debit else self.credit


# CPC 25 compliant chart of accounts codes
class AccountCode:
    """Standard account codes for provision accounting (Brazilian PCASP-inspired)."""

    # Expense accounts (Despesas - Grupo 6)
    PROVISION_EXPENSE = "6301"  # Despesa com Provisao para Glosas
    PROVISION_EXPENSE_DESC = "Despesa de Provisao para Glosas"

    # Liability accounts (Passivo Circulante - Grupo 2)
    PROVISION_LIABILITY = "2101"  # Provisao para Glosas (Passivo)
    PROVISION_LIABILITY_DESC = "Provisao para Glosas"

    # Revenue accounts (Receitas - Grupo 4) - for reversals
    PROVISION_REVERSAL_REVENUE = "4901"
    PROVISION_REVERSAL_REVENUE_DESC = "Reversao de Provisao para Glosas"

    @classmethod
    def get_debit_account(cls, provision_type: ProvisionType) -> tuple[str, str]:
        """Get the debit account code and name for a provision type."""
        if provision_type == ProvisionType.REVERSAL:
            return cls.PROVISION_LIABILITY, cls.PROVISION_LIABILITY_DESC
        return cls.PROVISION_EXPENSE, cls.PROVISION_EXPENSE_DESC

    @classmethod
    def get_credit_account(cls, provision_type: ProvisionType) -> tuple[str, str]:
        """Get the credit account code and name for a provision type."""
        if provision_type == ProvisionType.REVERSAL:
            return cls.PROVISION_REVERSAL_REVENUE, cls.PROVISION_REVERSAL_REVENUE_DESC
        return cls.PROVISION_LIABILITY, cls.PROVISION_LIABILITY_DESC
