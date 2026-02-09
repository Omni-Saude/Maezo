"""
DMN Test Suite for Hospital Administrative Rules
=================================================

This package contains comprehensive tests for 125+ DMN decision tables
organized by tier priority:

- TIER1 (Critical): COMP-LGPD, BILL-OPME, BILL-MED, RECV-PARTIAL, RECV-WRITEOFF
- TIER2 (High): AUTH-EXTENSION, DENY-PAYER, RECV-NEGO, DENY-APPEAL
- TIER3 (Medium): COMP-ACCRED, COMP-COUNCIL, BILL-BUNDLE-EXT
- TIER4 (Low): COMP-INTL, BILL-SPECIALTY

Total: 300+ test cases across all tiers.
"""

from tests.dmn.conftest import (
    ResultadoEnum,
    PrazoStatusEnum,
    RiskLevelEnum,
    DMNResult,
    MockDMNEvaluator,
)

__all__ = [
    "ResultadoEnum",
    "PrazoStatusEnum",
    "RiskLevelEnum",
    "DMNResult",
    "MockDMNEvaluator",
]
