"""
DMN (Decision Model and Notation) Platform Module
CIB7 Healthcare Orchestrator

This module provides DMN decision table federation and evaluation for multi-tenant
healthcare revenue cycle management.

Exports:
    - FederatedDMNService: Main DMN federation service
    - get_dmn_service: Factory function for service instance
    - CATEGORIES: Supported DMN categories
    - HIT_POLICIES: Supported DMN hit policies
"""

from .federation_service import (
    CATEGORIES,
    HIT_POLICIES,
    CacheEntry,
    FederatedDMNService,
    get_dmn_service,
)

__all__ = [
    "FederatedDMNService",
    "get_dmn_service",
    "CacheEntry",
    "CATEGORIES",
    "HIT_POLICIES",
]

__version__ = "1.0.0"
__author__ = "CIB7 Platform Team"
