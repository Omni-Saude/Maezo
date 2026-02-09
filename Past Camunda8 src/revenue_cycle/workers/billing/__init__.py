"""
Billing workers for claim and invoice processing.

This module contains workers for:
- Contract rules application
- Copay and coinsurance calculation
- Claim generation
- TISS XML generation
- Billing submission
- Pre-validation
- Charge consolidation
- Grouping by guide
- Idempotency checking
- Correction application
"""

from revenue_cycle.workers.billing.apply_contract_rules_worker import (
    ApplyContractRulesWorker,
    ContractLimitExceededError,
    ContractNotFoundError,
    ProcedureNotCoveredError,
    create_apply_contract_rules_worker,
)
from revenue_cycle.workers.billing.calculate_copay_worker import (
    CalculateCopayWorker,
    CopayCalculationError,
    CoverageNotFoundError,
    create_calculate_copay_worker,
)
from revenue_cycle.workers.billing.consolidate_charges_worker import (
    ConsolidateChargesWorker,
    ConsolidationValidationError,
)
from revenue_cycle.workers.billing.pre_validation_worker import (
    PreValidationWorker,
    PreValidationError,
)
from revenue_cycle.workers.billing.group_by_guide_worker import (
    GroupByGuideWorker,
    GroupingValidationError,
)
from revenue_cycle.workers.billing.check_idempotency_worker import (
    CheckIdempotencyWorker,
    IdempotencyValidationError,
    DuplicateOperationError,
)
from revenue_cycle.workers.billing.apply_corrections_worker import (
    ApplyCorrectionsWorker,
    CorrectionsValidationError,
)
from revenue_cycle.workers.billing.copay_models import (
    CalculateCopayInput,
    CalculateCopayOutput,
    ContractCopayRule,
    CoverageStatus,
    CopayType,
    ProcedureCopayDetail,
)
from revenue_cycle.workers.billing.models import (
    AdjustedChargeItem,
    ApplyContractRulesInput,
    ApplyContractRulesOutput,
    ChargeCategory,
    ChargeItem,
    Contract,
    ContractDiscountRate,
    ContractProcedure,
    ContractRuleType,
    DiscountApplied,
    EncounterType,
    PricingTableType,
)

__all__ = [
    # ApplyContractRulesWorker
    "ApplyContractRulesWorker",
    "create_apply_contract_rules_worker",
    # CalculateCopayWorker
    "CalculateCopayWorker",
    "create_calculate_copay_worker",
    # P4.1 Critical Path Workers
    "ConsolidateChargesWorker",
    "PreValidationWorker",
    "GroupByGuideWorker",
    "CheckIdempotencyWorker",
    "ApplyCorrectionsWorker",
    # Exceptions
    "ContractNotFoundError",
    "ProcedureNotCoveredError",
    "ContractLimitExceededError",
    "CopayCalculationError",
    "CoverageNotFoundError",
    "ConsolidationValidationError",
    "PreValidationError",
    "GroupingValidationError",
    "IdempotencyValidationError",
    "DuplicateOperationError",
    "CorrectionsValidationError",
    # Input/Output models - ApplyContractRules
    "ApplyContractRulesInput",
    "ApplyContractRulesOutput",
    "AdjustedChargeItem",
    "DiscountApplied",
    # Input/Output models - CalculateCopay
    "CalculateCopayInput",
    "CalculateCopayOutput",
    "ProcedureCopayDetail",
    "ContractCopayRule",
    # Enums
    "ChargeCategory",
    "ChargeItem",
    "CopayType",
    "CoverageStatus",
    # Domain models
    "Contract",
    "ContractDiscountRate",
    "ContractProcedure",
    "ContractRuleType",
    "EncounterType",
    "PricingTableType",
]
