"""
Payment workers for the Hospital Revenue Cycle.

This module contains Camunda 8 workers for payment processing operations:

Workers:
    - ProcessPaymentWorker: Processes payments through payment gateways
    - RecordPaymentWorker: Records payments with accounting integration
    - AllocatePaymentWorker: Allocates payments across multiple claims
    - AutoMatchingWorker: Automated remittance-to-claim matching
    - SubmitClaimWorker: Submits claims to insurance carriers

The payment workers handle:
- Payment processing via gateways (credit card, PIX, boleto, bank transfer)
- Payment recording with idempotency
- Payment allocation strategies (FIFO, LIFO, PROPORTIONAL, MANUAL)
- Multi-payer support (insurance, patient, collection agency)
- Payment method tracking (PIX, boleto, credit card, etc.)
- CPC 25 compliant accounting integration
- Multi-tenant database isolation
- SAGA compensation support
- PCI-DSS compliant card processing (tokenized data only)
- Automated remittance matching with fuzzy logic
- Confidence scoring for matches
- Claim submission to insurance carriers

Example:
    from revenue_cycle.workers.payment import (
        ProcessPaymentWorker,
        RecordPaymentWorker,
        AllocatePaymentWorker,
        AutoMatchingWorker,
        SubmitClaimWorker,
    )

    # Workers are automatically registered via @worker decorator
    process_worker = ProcessPaymentWorker()
    record_worker = RecordPaymentWorker()
    allocate_worker = AllocatePaymentWorker()
    matching_worker = AutoMatchingWorker()
    submit_worker = SubmitClaimWorker()
"""

from revenue_cycle.workers.payment.allocate_payment_worker import AllocatePaymentWorker
from revenue_cycle.workers.payment.auto_matching_worker import AutoMatchingWorker
from revenue_cycle.workers.payment.process_payment_worker import ProcessPaymentWorker
from revenue_cycle.workers.payment.record_payment_worker import RecordPaymentWorker
from revenue_cycle.workers.payment.submit_claim_worker import (
    SubmitClaimWorker,
    SubmissionValidationError,
    SubmissionError,
)

__all__ = [
    "AllocatePaymentWorker",
    "AutoMatchingWorker",
    "ProcessPaymentWorker",
    "RecordPaymentWorker",
    "SubmitClaimWorker",
    "SubmissionValidationError",
    "SubmissionError",
]
