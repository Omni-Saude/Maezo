"""Domain exceptions for Hospital Revenue Cycle."""

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
