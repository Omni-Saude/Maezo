"""Integration clients for external systems.

ADR-004: CDC only, NO direct ERP queries.
ADR-005: FHIR R4 canonical store.
ADR-006: REST bridge only, NO Kafka consumption.

Each client provides: Protocol (ABC) + Production + Stub implementations.
"""
from __future__ import annotations

from platform.shared.integrations.base import (
    BaseIntegrationClient,
    CircuitBreaker,
    CircuitState,
    IntegrationSettings,
)

__all__ = [
    "BaseIntegrationClient",
    "CircuitBreaker",
    "CircuitState",
    "IntegrationSettings",
]
