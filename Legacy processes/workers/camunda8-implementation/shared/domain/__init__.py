"""
Domain layer for Hospital Revenue Cycle.

Contains:
- Value Objects: Immutable domain primitives (Money, GlosaType, Priority)
- Entities: Domain entities with identity
- Events: Domain events for event-driven architecture
- Exceptions: Domain-specific exceptions
"""

from revenue_cycle.domain.value_objects.enums import GlosaType, Priority, GlosaStatus, AppealStrategy
from revenue_cycle.domain.value_objects.money import Money
from revenue_cycle.domain.value_objects.provision import (
    ProvisionType,
    ProvisionStatus,
    ERPSyncStatus,
    CPC25Category,
    AccountingEntry,
    AccountCode,
)
from revenue_cycle.domain.exceptions.base import (
    DomainException,
    ValidationException,
    BusinessRuleException,
    EntityNotFoundException,
    ConcurrencyException,
    IntegrationException,
    BpmnErrorException,
    ExternalServiceException,
    CalculationError,
    PricingError,
    PaymentAllocationException,
)

__all__ = [
    # Enums
    "GlosaType",
    "Priority",
    "GlosaStatus",
    "AppealStrategy",
    # Provision Enums
    "ProvisionType",
    "ProvisionStatus",
    "ERPSyncStatus",
    "CPC25Category",
    # Value Objects
    "Money",
    "AccountingEntry",
    "AccountCode",
    # Exceptions
    "DomainException",
    "ValidationException",
    "BusinessRuleException",
    "EntityNotFoundException",
    "ConcurrencyException",
    "IntegrationException",
    "BpmnErrorException",
    "ExternalServiceException",
    "CalculationError",
    "PricingError",
    "PaymentAllocationException",
]
