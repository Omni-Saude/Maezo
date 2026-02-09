"""
SAGA Compensation Workers for Hospital Revenue Cycle.

This package contains compensation workers that implement the SAGA pattern
for distributed transaction management. Each worker reverses a specific
business operation to maintain consistency when transactions fail.

Workers:
    - ReversePaymentWorker: Reverses payment transactions
    - CancelClaimWorker: Cancels submitted claims
    - RollbackAllocationWorker: Rolls back payment allocations
    - UndoBillingWorker: Undoes billing entries
    - RevertEligibilityWorker: Reverts eligibility verification
    - CancelNotificationWorker: Cancels pending notifications
    - AbortCollectionWorker: Aborts collection processes

All workers:
    - Follow BaseWorker pattern
    - Support idempotency for safe retry
    - Create audit trail entries
    - Handle multi-tenant isolation
    - Return CompensationStatus (SUCCESS/FAILED/SKIPPED/PARTIAL)
"""

from revenue_cycle.workers.compensation.abort_collection_worker import (
    AbortCollectionWorker,
)
from revenue_cycle.workers.compensation.cancel_claim_worker import CancelClaimWorker
from revenue_cycle.workers.compensation.cancel_notification_worker import (
    CancelNotificationWorker,
)
from revenue_cycle.workers.compensation.compensate_appeal_worker import (
    CompensateAppealWorker,
)
from revenue_cycle.workers.compensation.compensate_calculate_worker import (
    CompensateCalculateWorker,
)
from revenue_cycle.workers.compensation.compensate_provision_worker import (
    CompensateProvisionWorker,
)
from revenue_cycle.workers.compensation.compensate_recovery_worker import (
    CompensateRecoveryWorker,
)
from revenue_cycle.workers.compensation.compensate_submit_worker import (
    CompensateSubmitWorker,
)
from revenue_cycle.workers.compensation.compensation_handler_worker import (
    CompensationHandlerWorker,
)
from revenue_cycle.workers.compensation.models import (
    AbortCollectionInput,
    AbortCollectionOutput,
    CancelClaimInput,
    CancelClaimOutput,
    CancelNotificationInput,
    CancelNotificationOutput,
    CompensationReason,
    CompensationStatus,
    RevertEligibilityInput,
    RevertEligibilityOutput,
    ReversePaymentInput,
    ReversePaymentOutput,
    RollbackAllocationInput,
    RollbackAllocationOutput,
    UndoBillingInput,
    UndoBillingOutput,
)
from revenue_cycle.workers.compensation.revert_eligibility_worker import (
    RevertEligibilityWorker,
)
from revenue_cycle.workers.compensation.reverse_payment_worker import (
    ReversePaymentWorker,
)
from revenue_cycle.workers.compensation.rollback_allocation_worker import (
    RollbackAllocationWorker,
)
from revenue_cycle.workers.compensation.undo_billing_worker import UndoBillingWorker

__all__ = [
    # Original Workers
    "ReversePaymentWorker",
    "CancelClaimWorker",
    "RollbackAllocationWorker",
    "UndoBillingWorker",
    "RevertEligibilityWorker",
    "CancelNotificationWorker",
    "AbortCollectionWorker",
    # New SAGA Compensation Workers
    "CompensateAppealWorker",
    "CompensateProvisionWorker",
    "CompensateRecoveryWorker",
    "CompensateSubmitWorker",
    "CompensateCalculateWorker",
    "CompensationHandlerWorker",
    # Original Models - Input
    "ReversePaymentInput",
    "CancelClaimInput",
    "RollbackAllocationInput",
    "UndoBillingInput",
    "RevertEligibilityInput",
    "CancelNotificationInput",
    "AbortCollectionInput",
    # Original Models - Output
    "ReversePaymentOutput",
    "CancelClaimOutput",
    "RollbackAllocationOutput",
    "UndoBillingOutput",
    "RevertEligibilityOutput",
    "CancelNotificationOutput",
    "AbortCollectionOutput",
    # Enums
    "CompensationStatus",
    "CompensationReason",
]
