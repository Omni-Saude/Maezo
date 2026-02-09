"""
Collection workers for payment collection and AR management.

This module contains Camunda 8 workers for debt collection operations:

Workers:
    - InitiateCollectionWorker: Initiates debt collection with multi-tier strategy
    - CollectExternalWorker: Processes external collection agency payments
    - SendPaymentReminderWorker: Sends payment reminders to patients
    - WriteOffWorker: Records financial write-offs of uncollectible claims
    - AnalyzeDifferenceWorker: Analyzes payment discrepancies
    - LegalReferralWorker: Refers cases to legal department

The collection workers handle:
- Multi-tier collection strategy (internal/agency/legal)
- Tenant-specific threshold configuration
- Collection agency API integration
- Communication plan generation
- CDC (Código de Defesa do Consumidor) compliance
- History tracking of collection attempts
- Write-off and legal referral processing

Example:
    from revenue_cycle.workers.collection import InitiateCollectionWorker

    # Worker is automatically registered via @worker decorator
    worker = InitiateCollectionWorker()
"""

from revenue_cycle.workers.collection.initiate_collection_worker import (
    InitiateCollectionWorker,
)
from revenue_cycle.workers.collection.collect_external_worker import (
    CollectExternalWorker,
)
from revenue_cycle.workers.collection.send_payment_reminder_worker import (
    SendPaymentReminderWorker,
)
from revenue_cycle.workers.collection.write_off_worker import WriteOffWorker
from revenue_cycle.workers.collection.analyze_difference_worker import (
    AnalyzeDifferenceWorker,
)
from revenue_cycle.workers.collection.legal_referral_worker import LegalReferralWorker

__all__ = [
    "InitiateCollectionWorker",
    "CollectExternalWorker",
    "SendPaymentReminderWorker",
    "WriteOffWorker",
    "AnalyzeDifferenceWorker",
    "LegalReferralWorker",
]
