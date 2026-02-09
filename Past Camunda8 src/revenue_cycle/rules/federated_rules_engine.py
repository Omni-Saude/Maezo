"""
FederatedRulesEngine for Hospital Revenue Cycle multi-tenant SaaS system.

This module implements a federated rules engine that manages:
- Immutable global platform rules (TISS, ANS, security)
- Tenant-level rule defaults (company configuration)
- Business unit-level rule customizations with bounds validation

The engine supports a hierarchical override system where:
1. Global rules are immutable platform-wide defaults
2. Company rules may override some globals (if overridable)
3. Business unit rules may override company rules (if within bounds)

Rule Categories:
- REGULATORY: ANS, TISS compliance rules (immutable)
- SECURITY: Authentication, encryption rules (immutable)
- BUSINESS: Configurable operational rules with min/max bounds

Default Global Rules Implemented:
- tiss.version = "4.01.00" (immutable)
- tiss.submission_deadline_days = 60 (ANS RN 395)
- appeal_deadline_days = 30 (ANS RN 424)
- data_retention_years = 20 (LGPD healthcare)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

import structlog

from revenue_cycle.rules.rule_inheritance import (
    RuleCategory,
    RuleDefinition,
    RuleLevel,
    get_rule_registry,
)

logger = structlog.get_logger(__name__)


class FederatedRulesEngine:
    """
    Federated rules engine managing multi-tenant rule inheritance and overrides.

    The engine provides a single interface to retrieve rules considering the
    full inheritance hierarchy: Business Unit > Company > Global.

    Attributes:
        tenant_id: Unique tenant/company identifier
        rules_cache: In-memory cache of rule resolution results
        _global_rules: Platform-wide immutable rules
        _company_rules: Tenant-level customizable rules
        _business_unit_rules: Business unit-level overrides with bounds

    Example:
        engine = FederatedRulesEngine(tenant_id="tenant-123")
        engine.load_global_rules()
        engine.load_tenant_rules(config)

        # Get rule with inheritance: BU -> Company -> Global
        rule_value = engine.get_rule("glosa.auto_appeal_threshold")

        # Set BU-level override with validation
        success = engine.set_rule(
            "glosa.auto_appeal_threshold",
            7500,
            validate=True
        )

        # Get all rules with source information
        all_rules = engine.get_effective_rules()
    """

    def __init__(self, tenant_id: str, config_source: Optional[Any] = None):
        """
        Initialize the federated rules engine.

        Args:
            tenant_id: Unique identifier for the tenant/company
            config_source: Optional configuration source (dict, config file, etc.)

        Raises:
            ValueError: If tenant_id is empty or invalid
        """
        if not tenant_id or not isinstance(tenant_id, str):
            raise ValueError("tenant_id must be a non-empty string")

        self.tenant_id = tenant_id
        self.config_source = config_source
        self.rules_cache: Dict[str, Any] = {}
        self._global_rules: Dict[str, RuleDefinition] = {}
        self._company_rules: Dict[str, RuleDefinition] = {}
        self._business_unit_rules: Dict[str, Dict[str, RuleDefinition]] = {}
        self._registry = get_rule_registry()

        logger.info("FederatedRulesEngine initialized", tenant_id=tenant_id)

    def get_rule(self, key: str, business_unit_id: Optional[str] = None) -> Any:
        """
        Get rule value with inheritance: Business Unit > Company > Global.

        The method implements the override hierarchy:
        1. If business_unit_id provided and has override: return BU override value
        2. If company has override: return company override value
        3. Otherwise: return global rule value

        Args:
            key: Rule identifier (e.g., "glosa.auto_appeal_threshold")
            business_unit_id: Optional business unit ID for BU-level overrides

        Returns:
            Effective rule value

        Raises:
            KeyError: If rule key not found in any level
            ValueError: If rule retrieval fails

        Example:
            value = engine.get_rule("tiss.submission_deadline_days")
            value = engine.get_rule("glosa.auto_appeal_threshold", "bu-123")
        """
        # Check cache first
        cache_key = f"{business_unit_id or 'global'}:{key}"
        if cache_key in self.rules_cache:
            return self.rules_cache[cache_key]

        try:
            rule_def = self._resolve_rule_hierarchy(key, business_unit_id)
            if rule_def is None:
                raise KeyError(f"Rule '{key}' not found in any hierarchy level")

            value = rule_def.value
            self.rules_cache[cache_key] = value
            return value

        except KeyError as e:
            logger.warning(
                "Rule not found",
                rule_key=key,
                business_unit_id=business_unit_id,
                error=str(e),
            )
            raise

    def set_rule(
        self,
        key: str,
        value: Any,
        business_unit_id: Optional[str] = None,
        validate: bool = True,
    ) -> bool:
        """
        Set business unit rule with validation against bounds.

        Sets a rule at the business unit level with optional validation.
        If validate=True, the override is checked against:
        - Immutability constraints (REGULATORY/SECURITY rules)
        - Min/max value bounds
        - Allowed options whitelist

        Args:
            key: Rule identifier
            value: New rule value
            business_unit_id: Business unit ID (defaults to company-level if None)
            validate: Whether to validate override constraints

        Returns:
            True if rule set successfully, False if validation failed

        Raises:
            KeyError: If rule not found
            ValueError: If validation fails and validate=True

        Example:
            success = engine.set_rule(
                "glosa.auto_appeal_threshold",
                7500,
                business_unit_id="bu-123",
                validate=True
            )
        """
        try:
            if not validate:
                # Set without validation (use with caution)
                if business_unit_id:
                    if business_unit_id not in self._business_unit_rules:
                        self._business_unit_rules[business_unit_id] = {}
                    self._business_unit_rules[business_unit_id][key] = value
                else:
                    self._company_rules[key] = value

                # Clear cache for this rule
                cache_key = f"{business_unit_id or 'global'}:{key}"
                self.rules_cache.pop(cache_key, None)
                return True

            # Validate the override
            if not self._validate_rule_override(key, value, business_unit_id):
                logger.warning(
                    "Rule validation failed",
                    rule_key=key,
                    value=value,
                    business_unit_id=business_unit_id,
                )
                return False

            # Set the rule after validation passes
            if business_unit_id:
                if business_unit_id not in self._business_unit_rules:
                    self._business_unit_rules[business_unit_id] = {}
                self._business_unit_rules[business_unit_id][key] = value
            else:
                self._company_rules[key] = value

            # Clear cache for this rule
            cache_key = f"{business_unit_id or 'global'}:{key}"
            self.rules_cache.pop(cache_key, None)

            logger.info(
                "Rule set successfully",
                rule_key=key,
                value=value,
                business_unit_id=business_unit_id,
                tenant_id=self.tenant_id,
            )
            return True

        except Exception as e:
            logger.error(
                "Error setting rule",
                rule_key=key,
                value=value,
                business_unit_id=business_unit_id,
                error=str(e),
            )
            if validate:
                raise
            return False

    def _validate_rule_override(
        self, key: str, value: Any, business_unit_id: Optional[str] = None
    ) -> bool:
        """
        Validate override against min/max/options constraints.

        Checks:
        1. Rule exists
        2. Rule is overridable (not REGULATORY/SECURITY at GLOBAL level)
        3. Value is within min/max bounds
        4. Value is in allowed_options (if specified)

        Args:
            key: Rule key
            value: Proposed value
            business_unit_id: Business unit ID (or None for company-level)

        Returns:
            True if validation passes, False otherwise

        Raises:
            ValueError: If validation fails with details
        """
        try:
            # Check local global rules first
            if key in self._global_rules:
                rule_def = self._global_rules[key]
            else:
                # Fall back to registry
                rule_def = self._registry.get_rule(key, company_id=self.tenant_id)

            if rule_def is None:
                logger.error(
                    "Rule definition not found",
                    rule_key=key,
                    tenant_id=self.tenant_id,
                )
                return False

            # Check immutability
            if not rule_def.overridable:
                logger.warning(
                    "Rule is not overridable",
                    rule_key=key,
                    category=rule_def.category.value,
                )
                raise ValueError(
                    f"Rule '{key}' is immutable (category: {rule_def.category.value})"
                )

            # Check min/max bounds for numeric values
            if rule_def.min_value is not None and value < rule_def.min_value:
                logger.warning(
                    "Value below minimum",
                    rule_key=key,
                    value=value,
                    min_value=rule_def.min_value,
                )
                raise ValueError(
                    f"Value {value} is below minimum {rule_def.min_value}"
                )

            if rule_def.max_value is not None and value > rule_def.max_value:
                logger.warning(
                    "Value exceeds maximum",
                    rule_key=key,
                    value=value,
                    max_value=rule_def.max_value,
                )
                raise ValueError(
                    f"Value {value} exceeds maximum {rule_def.max_value}"
                )

            # Check allowed options whitelist
            if (
                rule_def.allowed_options is not None
                and value not in rule_def.allowed_options
            ):
                logger.warning(
                    "Value not in allowed options",
                    rule_key=key,
                    value=value,
                    allowed_options=rule_def.allowed_options,
                )
                raise ValueError(
                    f"Value {value} not in allowed options: {rule_def.allowed_options}"
                )

            return True

        except ValueError:
            raise
        except Exception as e:
            logger.error(
                "Validation error",
                rule_key=key,
                value=value,
                error=str(e),
            )
            return False

    def _resolve_rule_hierarchy(
        self, key: str, business_unit_id: Optional[str] = None
    ) -> Optional[RuleDefinition]:
        """
        Resolve rule considering full inheritance hierarchy.

        Implements the override hierarchy:
        1. Business unit override (if business_unit_id provided)
        2. Company override
        3. Global default

        Args:
            key: Rule key
            business_unit_id: Optional business unit ID

        Returns:
            Resolved RuleDefinition or None if not found
        """
        # Check business unit override
        if (
            business_unit_id
            and business_unit_id in self._business_unit_rules
            and key in self._business_unit_rules[business_unit_id]
        ):
            rule_value = self._business_unit_rules[business_unit_id][key]
            return RuleDefinition(
                key=key,
                value=rule_value,
                level=RuleLevel.BUSINESS_UNIT,
                source=f"BUSINESS_UNIT:{business_unit_id}",
                category=RuleCategory.BUSINESS,
                description=f"Business unit override for {key}",
            )

        # Check company override
        if key in self._company_rules:
            rule_value = self._company_rules[key]
            return RuleDefinition(
                key=key,
                value=rule_value,
                level=RuleLevel.COMPANY,
                source=f"TENANT:{self.tenant_id}",
                category=RuleCategory.BUSINESS,
                description=f"Company override for {key}",
            )

        # Check global rules
        if key in self._global_rules:
            return self._global_rules[key]

        # Fall back to registry
        try:
            return self._registry.get_rule(
                key, company_id=self.tenant_id, business_unit_id=business_unit_id
            )
        except KeyError:
            return None

    def get_effective_rules(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all effective rules with source information.

        Returns a dictionary of all rules at each level showing:
        - The effective value (considering inheritance)
        - The source (GLOBAL, COMPANY, BUSINESS_UNIT)
        - The category (REGULATORY, SECURITY, BUSINESS)

        Returns:
            Dictionary with keys: "global_rules", "company_rules", "business_unit_rules"
            Each containing: {rule_key: {value, source, category}}

        Example:
            rules = engine.get_effective_rules()
            print(rules["global_rules"]["tiss.version"])
            # {"value": "4.01.00", "source": "SYSTEM", "category": "REGULATORY"}
        """
        effective_rules = {
            "global_rules": {},
            "company_rules": {},
            "business_unit_rules": {},
        }

        # Global rules
        for key, rule_def in self._global_rules.items():
            effective_rules["global_rules"][key] = {
                "value": rule_def.value,
                "source": rule_def.source,
                "category": rule_def.category.value,
                "overridable": rule_def.overridable,
                "description": rule_def.description,
            }

        # Company rules
        for key, rule_def in self._company_rules.items():
            effective_rules["company_rules"][key] = {
                "value": rule_def,
                "source": f"TENANT:{self.tenant_id}",
                "category": "BUSINESS",
            }

        # Business unit rules
        for bu_id, rules in self._business_unit_rules.items():
            if bu_id not in effective_rules["business_unit_rules"]:
                effective_rules["business_unit_rules"][bu_id] = {}
            for key, value in rules.items():
                effective_rules["business_unit_rules"][bu_id][key] = {
                    "value": value,
                    "source": f"BUSINESS_UNIT:{bu_id}",
                    "category": "BUSINESS",
                }

        return effective_rules

    def load_global_rules(self) -> None:
        """
        Load immutable global rules (TISS, ANS, security, LGPD).

        Initializes the engine with platform-wide default rules:
        - tiss.version = "4.01.00" (immutable)
        - tiss.submission_deadline_days = 60 (ANS RN 395)
        - appeal_deadline_days = 30 (ANS RN 424)
        - data_retention_years = 20 (LGPD healthcare)

        These rules are immutable and cannot be overridden by tenants.

        Raises:
            ValueError: If rule validation fails
        """
        global_rules = [
            RuleDefinition(
                key="tiss.version",
                value="4.01.00",
                level=RuleLevel.GLOBAL,
                source="SYSTEM",
                overridable=False,
                category=RuleCategory.REGULATORY,
                description="TISS version (immutable regulatory requirement)",
            ),
            RuleDefinition(
                key="tiss.submission_deadline_days",
                value=60,
                level=RuleLevel.GLOBAL,
                source="SYSTEM",
                overridable=False,
                category=RuleCategory.REGULATORY,
                min_value=1,
                max_value=365,
                description="ANS RN 395: Days allowed for TISS submission",
            ),
            RuleDefinition(
                key="appeal_deadline_days",
                value=30,
                level=RuleLevel.GLOBAL,
                source="SYSTEM",
                overridable=False,
                category=RuleCategory.REGULATORY,
                min_value=1,
                max_value=365,
                description="ANS RN 424: Days allowed for appeal submission",
            ),
            RuleDefinition(
                key="data_retention_years",
                value=20,
                level=RuleLevel.GLOBAL,
                source="SYSTEM",
                overridable=False,
                category=RuleCategory.REGULATORY,
                min_value=1,
                max_value=50,
                description="LGPD healthcare requirement: Years to retain patient data",
            ),
        ]

        for rule_def in global_rules:
            self._global_rules[rule_def.key] = rule_def
            logger.debug(
                "Global rule loaded",
                rule_key=rule_def.key,
                value=rule_def.value,
                category=rule_def.category.value,
            )

        logger.info(
            "Global rules loaded",
            count=len(global_rules),
            tenant_id=self.tenant_id,
        )

    def load_tenant_rules(self, tenant_config: Dict[str, Any]) -> None:
        """
        Load tenant-specific rule overrides from configuration.

        Loads company-level rule overrides from a configuration dictionary.
        Each override is validated against the global rule definition bounds.

        Configuration format:
        {
            "rules": {
                "glosa.auto_appeal_threshold": 7500,
                "collection.days_before_reminder": 14,
                ...
            }
        }

        Args:
            tenant_config: Dictionary with "rules" key containing overrides

        Raises:
            ValueError: If rule override violates constraints
            KeyError: If referenced rule not found in global rules

        Example:
            config = {
                "rules": {
                    "glosa.auto_appeal_threshold": 5000,
                    "collection.days_before_reminder": 30
                }
            }
            engine.load_tenant_rules(config)
        """
        if not tenant_config or "rules" not in tenant_config:
            logger.warning(
                "No tenant rules provided",
                tenant_id=self.tenant_id,
            )
            return

        rules_config = tenant_config["rules"]
        loaded_count = 0

        for key, value in rules_config.items():
            try:
                # Validate against global rule
                global_rule = self._registry.get_rule(key, company_id=self.tenant_id)

                # Check immutability
                if not global_rule.overridable:
                    logger.warning(
                        "Cannot override immutable rule",
                        rule_key=key,
                        category=global_rule.category.value,
                    )
                    continue

                # Validate bounds
                if global_rule.min_value is not None and value < global_rule.min_value:
                    raise ValueError(
                        f"Rule '{key}' value {value} below minimum {global_rule.min_value}"
                    )

                if global_rule.max_value is not None and value > global_rule.max_value:
                    raise ValueError(
                        f"Rule '{key}' value {value} exceeds maximum {global_rule.max_value}"
                    )

                # Validate allowed options
                if (
                    global_rule.allowed_options is not None
                    and value not in global_rule.allowed_options
                ):
                    raise ValueError(
                        f"Rule '{key}' value {value} not in allowed options: {global_rule.allowed_options}"
                    )

                self._company_rules[key] = value
                loaded_count += 1
                logger.debug(
                    "Tenant rule loaded",
                    rule_key=key,
                    value=value,
                    tenant_id=self.tenant_id,
                )

            except (KeyError, ValueError) as e:
                logger.warning(
                    "Failed to load tenant rule",
                    rule_key=key,
                    error=str(e),
                    tenant_id=self.tenant_id,
                )

        logger.info(
            "Tenant rules loaded",
            count=loaded_count,
            total_provided=len(rules_config),
            tenant_id=self.tenant_id,
        )

    def clear_cache(self) -> None:
        """
        Clear the rule resolution cache.

        Should be called after updating rules to ensure fresh resolution.
        Useful for testing and dynamic rule updates.
        """
        self.rules_cache.clear()
        logger.debug("Rules cache cleared", tenant_id=self.tenant_id)

    def get_rule_info(self, key: str) -> Dict[str, Any]:
        """
        Get comprehensive information about a rule.

        Returns metadata about a rule including:
        - Current value
        - Level (GLOBAL, COMPANY, BUSINESS_UNIT)
        - Overridability
        - Constraints (min/max/options)
        - Category (REGULATORY, SECURITY, BUSINESS)

        Args:
            key: Rule key

        Returns:
            Dictionary with rule metadata

        Raises:
            KeyError: If rule not found

        Example:
            info = engine.get_rule_info("glosa.auto_appeal_threshold")
            print(info["min_value"], info["max_value"])
        """
        try:
            # Check local global rules first
            if key in self._global_rules:
                rule_def = self._global_rules[key]
            else:
                rule_def = self._registry.get_rule(key, company_id=self.tenant_id)
            return rule_def.to_dict()
        except KeyError:
            logger.warning(
                "Rule info not found",
                rule_key=key,
                tenant_id=self.tenant_id,
            )
            raise
