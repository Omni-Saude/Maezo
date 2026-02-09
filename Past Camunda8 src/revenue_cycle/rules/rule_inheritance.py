"""
RuleInheritance mechanism for Hospital Revenue Cycle multi-tenant SaaS system.

This module implements a hierarchical rule inheritance system that allows:
- Immutable platform-wide (GLOBAL) rules
- Tenant-level (COMPANY) rule defaults
- Business unit-level (BUSINESS_UNIT) customizable rules with bounds

Rule Categories:
- REGULATORY: Immutable rules for compliance (TISS, ANS deadlines)
- SECURITY: Immutable security rules (MFA, encryption)
- BUSINESS: Configurable business rules within defined bounds

The inheritance hierarchy ensures that:
1. Global rules override all else
2. Company defaults can be overridden by business units
3. All overrides respect min/max bounds and allowed_options constraints
4. Rules are tagged with their source (SYSTEM, TENANT, BUSINESS_UNIT, CUSTOM)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class RuleLevel(Enum):
    """
    Rule hierarchy levels in the multi-tenant system.

    GLOBAL rules are immutable platform-wide defaults.
    COMPANY rules are tenant-level defaults, may be customizable.
    BUSINESS_UNIT rules are customizable per business unit within bounds.
    """

    GLOBAL = 1
    COMPANY = 2
    BUSINESS_UNIT = 3


class RuleCategory(Enum):
    """
    Rule categories defining mutability and scope.

    REGULATORY: Immutable compliance rules (TISS, ANS, legal requirements)
    SECURITY: Immutable security rules (MFA, encryption, authentication)
    BUSINESS: Configurable business rules within min/max bounds
    """

    REGULATORY = "REGULATORY"
    SECURITY = "SECURITY"
    BUSINESS = "BUSINESS"


@dataclass
class RuleDefinition:
    """
    Definition of a business rule with validation bounds and inheritance metadata.

    Attributes:
        key: Unique rule identifier (e.g., "glosa.auto_appeal_threshold")
        value: Current rule value
        level: Hierarchy level (GLOBAL, COMPANY, BUSINESS_UNIT)
        source: Where rule came from (SYSTEM, TENANT, BUSINESS_UNIT, CUSTOM)
        overridable: Whether this rule can be overridden at lower levels
        min_value: Minimum allowed value (for numeric rules)
        max_value: Maximum allowed value (for numeric rules)
        allowed_options: Whitelist of allowed values (for enum-like rules)
        description: Human-readable rule description
        category: Rule category affecting mutability
    """

    key: str
    value: Any
    level: RuleLevel
    source: str
    overridable: bool = True
    category: RuleCategory = RuleCategory.BUSINESS
    min_value: Optional[Any] = None
    max_value: Optional[Any] = None
    allowed_options: Optional[list[Any]] = None
    description: str = ""
    created_at: str = field(default_factory=lambda: None)
    updated_at: str = field(default_factory=lambda: None)

    def __post_init__(self) -> None:
        """Validate rule definition after initialization."""
        self._validate_rule()

    def _validate_rule(self) -> None:
        """Validate rule constraints and bounds."""
        # Regulatory and Security rules are always immutable
        if self.category in (RuleCategory.REGULATORY, RuleCategory.SECURITY):
            if self.overridable and self.level == RuleLevel.GLOBAL:
                logger.warning(
                    "Immutable rule marked as overridable",
                    rule_key=self.key,
                    category=self.category.value,
                )
                self.overridable = False

        # Validate value is within bounds if bounds exist
        if self.min_value is not None and self.value < self.min_value:
            raise ValueError(
                f"Rule '{self.key}' value {self.value} is below minimum {self.min_value}"
            )

        if self.max_value is not None and self.value > self.max_value:
            raise ValueError(
                f"Rule '{self.key}' value {self.value} exceeds maximum {self.max_value}"
            )

        # Validate value is in allowed options if specified
        if (
            self.allowed_options is not None
            and self.value not in self.allowed_options
        ):
            raise ValueError(
                f"Rule '{self.key}' value {self.value} not in allowed options: {self.allowed_options}"
            )

    def validate_override(self, new_value: Any, new_level: RuleLevel) -> bool:
        """
        Validate whether a rule can be overridden at a lower level.

        Args:
            new_value: Proposed new value
            new_level: Level attempting to override (should be > self.level)

        Returns:
            True if override is valid

        Raises:
            ValueError: If override is invalid
        """
        # Check immutability
        if not self.overridable:
            raise ValueError(
                f"Rule '{self.key}' is not overridable (category: {self.category.value})"
            )

        # Check level hierarchy (can only override downward)
        if new_level.value <= self.level.value:
            raise ValueError(
                f"Cannot override rule at same or higher level. Current: {self.level.name}, Attempted: {new_level.name}"
            )

        # Validate bounds
        if self.min_value is not None and new_value < self.min_value:
            raise ValueError(
                f"Override value {new_value} is below minimum {self.min_value}"
            )

        if self.max_value is not None and new_value > self.max_value:
            raise ValueError(
                f"Override value {new_value} exceeds maximum {self.max_value}"
            )

        # Validate allowed options
        if (
            self.allowed_options is not None
            and new_value not in self.allowed_options
        ):
            raise ValueError(
                f"Override value {new_value} not in allowed options: {self.allowed_options}"
            )

        return True

    def to_dict(self) -> dict[str, Any]:
        """Convert rule definition to dictionary."""
        return {
            "key": self.key,
            "value": self.value,
            "level": self.level.name,
            "source": self.source,
            "overridable": self.overridable,
            "category": self.category.value,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "allowed_options": self.allowed_options,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class RuleRegistry:
    """
    Registry of all business rules with inheritance hierarchy support.

    Manages:
    - Global (platform-wide) rules
    - Company (tenant) level rules
    - Business unit level rules
    - Rule validation and override constraints
    """

    # Global immutable rules (PLATFORM-WIDE)
    GLOSA_AUTO_APPEAL_ENABLED = RuleDefinition(
        key="glosa.auto_appeal_enabled",
        value=True,
        level=RuleLevel.GLOBAL,
        source="SYSTEM",
        overridable=False,
        category=RuleCategory.REGULATORY,
        description="Enable automatic appeals for regulatory compliance",
    )

    GLOSA_TISS_DEADLINE_DAYS = RuleDefinition(
        key="glosa.tiss_deadline_days",
        value=30,
        level=RuleLevel.GLOBAL,
        source="SYSTEM",
        overridable=False,
        category=RuleCategory.REGULATORY,
        description="TISS regulatory deadline for glosa appeals in days",
    )

    SECURITY_MFA_REQUIRED = RuleDefinition(
        key="security.mfa_required",
        value=True,
        level=RuleLevel.GLOBAL,
        source="SYSTEM",
        overridable=False,
        category=RuleCategory.SECURITY,
        description="Require multi-factor authentication for all users",
    )

    SECURITY_ENCRYPTION_ENABLED = RuleDefinition(
        key="security.encryption_enabled",
        value=True,
        level=RuleLevel.GLOBAL,
        source="SYSTEM",
        overridable=False,
        category=RuleCategory.SECURITY,
        description="Require encryption for sensitive data at rest",
    )

    # Company-level configurable rules (TENANT DEFAULTS)
    GLOSA_AUTO_APPEAL_THRESHOLD = RuleDefinition(
        key="glosa.auto_appeal_threshold",
        value=5000,
        level=RuleLevel.COMPANY,
        source="SYSTEM",
        overridable=True,
        category=RuleCategory.BUSINESS,
        min_value=1000,
        max_value=50000,
        description="Amount threshold for automatic glosa appeals (in cents)",
    )

    COLLECTION_DAYS_BEFORE_REMINDER = RuleDefinition(
        key="collection.days_before_reminder",
        value=30,
        level=RuleLevel.COMPANY,
        source="SYSTEM",
        overridable=True,
        category=RuleCategory.BUSINESS,
        min_value=7,
        max_value=60,
        description="Days before sending first collection reminder",
    )

    COLLECTION_DAYS_BEFORE_AGENCY_REFERRAL = RuleDefinition(
        key="collection.days_before_agency_referral",
        value=90,
        level=RuleLevel.COMPANY,
        source="SYSTEM",
        overridable=True,
        category=RuleCategory.BUSINESS,
        min_value=30,
        max_value=180,
        description="Days before referring debt to external collection agency",
    )

    CODING_AUTO_CORRECT_ENABLED = RuleDefinition(
        key="coding.auto_correct_enabled",
        value=True,
        level=RuleLevel.COMPANY,
        source="SYSTEM",
        overridable=True,
        category=RuleCategory.BUSINESS,
        allowed_options=[True, False],
        description="Enable automatic medical code correction",
    )

    BILLING_PAYMENT_TERMS_DAYS = RuleDefinition(
        key="billing.payment_terms_days",
        value=30,
        level=RuleLevel.COMPANY,
        source="SYSTEM",
        overridable=True,
        category=RuleCategory.BUSINESS,
        min_value=7,
        max_value=90,
        description="Payment terms in days for invoices",
    )

    # Business unit customizable rules (BUSINESS_UNIT LEVEL)
    GLOSA_APPEAL_STRATEGY = RuleDefinition(
        key="glosa.appeal_strategy",
        value="AGGRESSIVE",
        level=RuleLevel.BUSINESS_UNIT,
        source="SYSTEM",
        overridable=True,
        category=RuleCategory.BUSINESS,
        allowed_options=["AGGRESSIVE", "MODERATE", "CONSERVATIVE"],
        description="Strategy for appealing glosas (AGGRESSIVE/MODERATE/CONSERVATIVE)",
    )

    def __init__(self) -> None:
        """Initialize rule registry with default rules."""
        self._rules: dict[str, RuleDefinition] = {}
        self._company_overrides: dict[str, RuleDefinition] = {}
        self._business_unit_overrides: dict[str, dict[str, RuleDefinition]] = {}

        # Register default rules
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register all default rules from class constants."""
        for attr_name in dir(self.__class__):
            attr = getattr(self.__class__, attr_name)
            if isinstance(attr, RuleDefinition):
                self._rules[attr.key] = attr
                logger.debug("Registered default rule", rule_key=attr.key)

    def get_rule(
        self,
        key: str,
        company_id: Optional[str] = None,
        business_unit_id: Optional[str] = None,
    ) -> RuleDefinition:
        """
        Get effective rule value considering inheritance hierarchy.

        Hierarchy (highest priority first):
        1. Business unit override (if business_unit_id provided)
        2. Company override (if company_id provided)
        3. Global default

        Args:
            key: Rule key
            company_id: Company/tenant ID for overrides
            business_unit_id: Business unit ID for overrides

        Returns:
            Effective RuleDefinition

        Raises:
            KeyError: If rule not found
        """
        if key not in self._rules:
            raise KeyError(f"Rule '{key}' not found")

        # Check business unit override
        if (
            business_unit_id
            and business_unit_id in self._business_unit_overrides
            and key in self._business_unit_overrides[business_unit_id]
        ):
            return self._business_unit_overrides[business_unit_id][key]

        # Check company override
        if company_id:
            override_key = f"{company_id}:{key}"
            if override_key in self._company_overrides:
                return self._company_overrides[override_key]

        # Return global default
        return self._rules[key]

    def set_company_override(
        self,
        key: str,
        value: Any,
        company_id: str,
    ) -> RuleDefinition:
        """
        Override a rule at company level.

        Args:
            key: Rule key
            value: New value
            company_id: Company/tenant ID

        Returns:
            Updated RuleDefinition

        Raises:
            KeyError: If rule not found
            ValueError: If override violates constraints
        """
        if key not in self._rules:
            raise KeyError(f"Rule '{key}' not found")

        global_rule = self._rules[key]

        # Check immutability - cannot override immutable rules
        if not global_rule.overridable:
            raise ValueError(
                f"Rule '{key}' is not overridable (category: {global_rule.category.value})"
            )

        # Validate bounds and options
        if global_rule.min_value is not None and value < global_rule.min_value:
            raise ValueError(
                f"Override value {value} is below minimum {global_rule.min_value}"
            )

        if global_rule.max_value is not None and value > global_rule.max_value:
            raise ValueError(
                f"Override value {value} exceeds maximum {global_rule.max_value}"
            )

        if (
            global_rule.allowed_options is not None
            and value not in global_rule.allowed_options
        ):
            raise ValueError(
                f"Override value {value} not in allowed options: {global_rule.allowed_options}"
            )

        override_key = f"{company_id}:{key}"
        override = RuleDefinition(
            key=key,
            value=value,
            level=RuleLevel.COMPANY,
            source=f"TENANT:{company_id}",
            overridable=global_rule.overridable,
            category=global_rule.category,
            min_value=global_rule.min_value,
            max_value=global_rule.max_value,
            allowed_options=global_rule.allowed_options,
            description=global_rule.description,
        )

        self._company_overrides[override_key] = override
        logger.info(
            "Company rule override set",
            rule_key=key,
            company_id=company_id,
            value=value,
        )

        return override

    def set_business_unit_override(
        self,
        key: str,
        value: Any,
        company_id: str,
        business_unit_id: str,
    ) -> RuleDefinition:
        """
        Override a rule at business unit level.

        Args:
            key: Rule key
            value: New value
            company_id: Company/tenant ID
            business_unit_id: Business unit ID

        Returns:
            Updated RuleDefinition

        Raises:
            KeyError: If rule not found
            ValueError: If override violates constraints
        """
        if key not in self._rules:
            raise KeyError(f"Rule '{key}' not found")

        # Get company-level rule (may be overridden)
        company_rule = self.get_rule(key, company_id=company_id)

        # Validate override is allowed
        company_rule.validate_override(value, RuleLevel.BUSINESS_UNIT)

        if business_unit_id not in self._business_unit_overrides:
            self._business_unit_overrides[business_unit_id] = {}

        override = RuleDefinition(
            key=key,
            value=value,
            level=RuleLevel.BUSINESS_UNIT,
            source=f"BUSINESS_UNIT:{business_unit_id}",
            overridable=company_rule.overridable,
            category=company_rule.category,
            min_value=company_rule.min_value,
            max_value=company_rule.max_value,
            allowed_options=company_rule.allowed_options,
            description=company_rule.description,
        )

        self._business_unit_overrides[business_unit_id][key] = override
        logger.info(
            "Business unit rule override set",
            rule_key=key,
            company_id=company_id,
            business_unit_id=business_unit_id,
            value=value,
        )

        return override

    def list_rules(
        self,
        category: Optional[RuleCategory] = None,
        level: Optional[RuleLevel] = None,
    ) -> list[RuleDefinition]:
        """
        List all registered rules with optional filtering.

        Args:
            category: Filter by rule category
            level: Filter by rule level

        Returns:
            List of RuleDefinition objects
        """
        rules = list(self._rules.values())

        if category:
            rules = [r for r in rules if r.category == category]

        if level:
            rules = [r for r in rules if r.level == level]

        return sorted(rules, key=lambda r: r.key)

    def get_rule_info(self, key: str) -> dict[str, Any]:
        """
        Get comprehensive info about a rule including constraints.

        Args:
            key: Rule key

        Returns:
            Dictionary with rule information
        """
        if key not in self._rules:
            raise KeyError(f"Rule '{key}' not found")

        rule = self._rules[key]
        return rule.to_dict()


# Global registry instance
_registry: Optional[RuleRegistry] = None


def get_rule_registry() -> RuleRegistry:
    """Get or create the global rule registry."""
    global _registry
    if _registry is None:
        _registry = RuleRegistry()
    return _registry


def reset_rule_registry() -> None:
    """Reset the global rule registry (for testing)."""
    global _registry
    _registry = None
