"""
DMN Federation Service - ADR-007
Merges base DMN decision tables with tenant-specific overrides.
Multi-tenant decision management for CIB7 Healthcare Orchestrator.

Author: CIB7 Platform Team
Version: 1.0.0
License: Proprietary
"""

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# DMN namespace constants
DMN_NAMESPACE = "https://www.omg.org/spec/DMN/20191111/MODEL/"
CAMUNDA_NAMESPACE = "http://camunda.org/schema/1.0/dmn"

# Path constants
DMN_BASE_PATH = Path(__file__).parent
DMN_OVERRIDE_PATH = DMN_BASE_PATH / "tenant_overrides"

# Domain-driven DMN paths (ADR-009)
DOMAIN_DMN_PATHS = {
    'authorization': Path('../../revenue_cycle/dmn'),
    'clinical_safety': Path('../../clinical_operations/dmn'),
    'billing': Path('../../revenue_cycle/dmn'),
    'coding_audit': Path('../../revenue_cycle/dmn'),
    'glosa_prevention': Path('../../revenue_cycle/dmn'),
    'revenue_recovery': Path('../../revenue_cycle/dmn'),
    'pricing': Path('../../revenue_cycle/dmn'),
    'cash_operations': Path('../../revenue_cycle/dmn'),
    'compliance': Path('../../platform_services/dmn'),
    'credentialing': Path('../../platform_services/dmn'),
    'access_control': Path('../../platform_services/dmn'),
    'infrastructure': Path('../../platform_services/dmn'),
}

# Supported categories (all domain categories)
CATEGORIES = list(DOMAIN_DMN_PATHS.keys())

# Supported hit policies
HIT_POLICIES = ["FIRST", "COLLECT", "UNIQUE", "ANY"]


@dataclass
class CacheEntry:
    """Cache entry for parsed DMN tables."""
    data: Dict[str, Any]
    expires_at: datetime


class FederatedDMNService:
    """
    DMN Federation Service that merges base decision tables with tenant overrides.

    Supports multi-tenant decision management with caching and multiple hit policies.
    """

    def __init__(self, cache_ttl_seconds: int = 300):
        """
        Initialize the DMN Federation Service.

        Args:
            cache_ttl_seconds: Time-to-live for cached parsed tables (default: 300s)
        """
        self.cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._cache: Dict[str, CacheEntry] = {}

        # Ensure override directory exists
        DMN_OVERRIDE_PATH.mkdir(parents=True, exist_ok=True)

        logger.info(
            "DMN Federation Service initialized with cache TTL: %ds",
            cache_ttl_seconds
        )

    def load_base_table(self, category: str, table_name: str) -> Dict[str, Any]:
        """
        Load base DMN decision table from XML file.

        Args:
            category: DMN category (billing, clinical, etc.)
            table_name: Name of the DMN table file (without extension)

        Returns:
            Parsed DMN table as dictionary

        Raises:
            FileNotFoundError: If DMN file not found
            ValueError: If category is invalid or parsing fails
        """
        if category not in CATEGORIES:
            raise ValueError(f"Invalid category: {category}. Must be one of {CATEGORIES}")

        cache_key = f"base:{category}:{table_name}"

        # Check cache
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if datetime.now() < entry.expires_at:
                logger.debug("Cache hit for base table: %s/%s", category, table_name)
                return entry.data
            else:
                # Expired cache entry
                del self._cache[cache_key]

        # Try domain-specific path first (ADR-009)
        file_path = None
        if category in DOMAIN_DMN_PATHS:
            domain_base = (DMN_BASE_PATH / DOMAIN_DMN_PATHS[category]).resolve()
            domain_path = domain_base / category / f"{table_name}.dmn"
            if domain_path.exists():
                file_path = domain_path

        # Fallback to shared path for backward compatibility
        if file_path is None:
            file_path = DMN_BASE_PATH / category / f"{table_name}.dmn"

        if not file_path.exists():
            raise FileNotFoundError(f"DMN file not found: {file_path}")

        logger.info("Loading base DMN table: %s", file_path)

        try:
            parsed_table = self._parse_dmn_xml(file_path)

            # Cache the result
            self._cache[cache_key] = CacheEntry(
                data=parsed_table,
                expires_at=datetime.now() + self.cache_ttl
            )

            return parsed_table

        except ET.ParseError as e:
            raise ValueError(f"Failed to parse DMN XML: {e}") from e

    def load_tenant_override(
        self,
        tenant_id: str,
        category: str,
        table_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Load tenant-specific DMN override table.

        Args:
            tenant_id: Unique tenant identifier
            category: DMN category
            table_name: Name of the DMN table

        Returns:
            Parsed DMN override table, or None if no override exists
        """
        cache_key = f"override:{tenant_id}:{category}:{table_name}"

        # Check cache
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if datetime.now() < entry.expires_at:
                logger.debug(
                    "Cache hit for tenant override: %s/%s/%s",
                    tenant_id, category, table_name
                )
                return entry.data
            else:
                del self._cache[cache_key]

        # Load from file
        file_path = DMN_OVERRIDE_PATH / tenant_id / category / f"{table_name}.dmn"

        if not file_path.exists():
            logger.debug("No tenant override found: %s", file_path)
            return None

        logger.info("Loading tenant override DMN table: %s", file_path)

        try:
            parsed_table = self._parse_dmn_xml(file_path)

            # Cache the result
            self._cache[cache_key] = CacheEntry(
                data=parsed_table,
                expires_at=datetime.now() + self.cache_ttl
            )

            return parsed_table

        except Exception as e:
            logger.error("Failed to parse tenant override DMN: %s", e)
            return None

    def evaluate(
        self,
        tenant_id: str,
        category: str,
        table_name: str,
        inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Evaluate DMN decision table with tenant-specific overrides.

        Args:
            tenant_id: Unique tenant identifier
            category: DMN category
            table_name: Name of the DMN table
            inputs: Input variables for decision evaluation

        Returns:
            Decision output as dictionary

        Raises:
            ValueError: If evaluation fails or no matching rules found
        """
        logger.info(
            "Evaluating DMN: tenant=%s, category=%s, table=%s",
            tenant_id, category, table_name
        )

        # Load base table
        base_table = self.load_base_table(category, table_name)

        # Load tenant override (if exists)
        override_table = self.load_tenant_override(tenant_id, category, table_name)

        # Merge rules
        if override_table:
            merged_rules = self.merge_rules(
                base_table["rules"],
                override_table["rules"]
            )
            hit_policy = override_table.get("hitPolicy", base_table["hitPolicy"])
        else:
            merged_rules = base_table["rules"]
            hit_policy = base_table["hitPolicy"]

        # Evaluate rules against inputs
        matched_rules = self._match_rules(merged_rules, inputs)

        if not matched_rules:
            logger.warning("No matching rules found for inputs: %s", inputs)
            raise ValueError("No matching DMN rules found")

        # Apply hit policy
        result = self._apply_hit_policy(hit_policy, matched_rules)

        # Log evaluation
        logger.info(
            "DMN evaluation complete: matched_rules=%d, hit_policy=%s",
            len(matched_rules), hit_policy
        )

        return result

    def merge_rules(
        self,
        base_rules: List[Dict[str, Any]],
        override_rules: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Merge base rules with tenant-specific overrides.

        Override rules take priority over base rules. Rules are matched by ID,
        and tenant overrides replace or extend base rules.

        Args:
            base_rules: List of base decision rules
            override_rules: List of tenant override rules

        Returns:
            Merged list of rules with overrides applied
        """
        # Create a dictionary of base rules by ID
        merged: Dict[str, Dict[str, Any]] = {
            rule["id"]: rule.copy() for rule in base_rules
        }

        # Apply overrides
        for override_rule in override_rules:
            rule_id = override_rule["id"]

            if rule_id in merged:
                # Override existing rule
                logger.debug("Overriding rule: %s", rule_id)
                merged[rule_id] = override_rule.copy()
            else:
                # Add new tenant-specific rule
                logger.debug("Adding new tenant rule: %s", rule_id)
                merged[rule_id] = override_rule.copy()

        # Convert back to list, maintaining order (overrides first)
        result = []

        # Add override rules first (higher priority)
        for override_rule in override_rules:
            result.append(merged[override_rule["id"]])

        # Add remaining base rules
        for base_rule in base_rules:
            if base_rule["id"] not in [r["id"] for r in override_rules]:
                result.append(merged[base_rule["id"]])

        logger.debug(
            "Merged rules: base=%d, override=%d, total=%d",
            len(base_rules), len(override_rules), len(result)
        )

        return result

    def _apply_hit_policy(
        self,
        hit_policy: str,
        matched_rules: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Apply DMN hit policy to matched rules.

        Args:
            hit_policy: Hit policy (FIRST, COLLECT, UNIQUE, ANY)
            matched_rules: List of matched rules

        Returns:
            Decision output based on hit policy

        Raises:
            ValueError: If hit policy is unsupported or rules are inconsistent
        """
        if hit_policy not in HIT_POLICIES:
            raise ValueError(f"Unsupported hit policy: {hit_policy}")

        if hit_policy == "FIRST":
            # Return first matched rule
            return matched_rules[0]["output"]

        elif hit_policy == "UNIQUE":
            # Ensure only one rule matched
            if len(matched_rules) > 1:
                raise ValueError("UNIQUE hit policy violated: multiple rules matched")
            return matched_rules[0]["output"]

        elif hit_policy == "ANY":
            # All matched rules must produce same output
            first_output = matched_rules[0]["output"]
            for rule in matched_rules[1:]:
                if rule["output"] != first_output:
                    raise ValueError("ANY hit policy violated: outputs differ")
            return first_output

        elif hit_policy == "COLLECT":
            # Return all matched rule outputs as a list
            return {
                "results": [rule["output"] for rule in matched_rules],
                "count": len(matched_rules)
            }

        return {}

    def _match_rules(
        self,
        rules: List[Dict[str, Any]],
        inputs: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Match decision rules against input values.

        Args:
            rules: List of decision rules
            inputs: Input variables

        Returns:
            List of matched rules
        """
        matched = []

        for rule in rules:
            if self._rule_matches(rule, inputs):
                matched.append(rule)

        return matched

    def _rule_matches(
        self,
        rule: Dict[str, Any],
        inputs: Dict[str, Any]
    ) -> bool:
        """
        Check if a rule matches given inputs.

        Args:
            rule: Decision rule
            inputs: Input variables

        Returns:
            True if rule matches, False otherwise
        """
        for input_key, input_conditions in rule.get("inputs", {}).items():
            if input_key not in inputs:
                return False

            input_value = inputs[input_key]

            # Empty condition means any value matches
            if not input_conditions:
                continue

            # Check if input value matches any condition
            if not self._value_matches_condition(input_value, input_conditions):
                return False

        return True

    def _value_matches_condition(
        self,
        value: Any,
        conditions: Union[str, List[str]]
    ) -> bool:
        """
        Check if value matches DMN input condition(s).

        Args:
            value: Input value to check
            conditions: DMN condition expression(s)

        Returns:
            True if value matches condition
        """
        # Normalize conditions to list
        if isinstance(conditions, str):
            conditions = [conditions]

        for condition in conditions:
            # Remove quotes and check equality or list membership
            condition_clean = condition.strip('"\'')

            # Check for comma-separated values (OR logic)
            if "," in condition_clean:
                allowed_values = [v.strip().strip('"\'') for v in condition_clean.split(",")]
                if str(value) in allowed_values:
                    return True
            elif str(value) == condition_clean:
                return True

        return False

    def _parse_dmn_xml(self, file_path: Path) -> Dict[str, Any]:
        """
        Parse DMN XML file into structured dictionary.

        Args:
            file_path: Path to DMN XML file

        Returns:
            Parsed DMN table structure

        Raises:
            ET.ParseError: If XML parsing fails
        """
        tree = ET.parse(file_path)
        root = tree.getroot()

        # Register namespaces
        namespaces = {
            "dmn": DMN_NAMESPACE,
            "camunda": CAMUNDA_NAMESPACE
        }

        # Find decision table
        decision = root.find(".//dmn:decision", namespaces)
        if decision is None:
            raise ValueError("No decision element found in DMN")

        decision_table = decision.find(".//dmn:decisionTable", namespaces)
        if decision_table is None:
            raise ValueError("No decisionTable element found in DMN")

        # Extract hit policy
        hit_policy = decision_table.get("hitPolicy", "UNIQUE")

        # Parse inputs
        inputs = []
        for input_elem in decision_table.findall(".//dmn:input", namespaces):
            input_id = input_elem.get("id")
            label = input_elem.get("label", "")
            inputs.append({"id": input_id, "label": label})

        # Parse outputs
        outputs = []
        for output_elem in decision_table.findall(".//dmn:output", namespaces):
            output_id = output_elem.get("id")
            output_name = output_elem.get("name", "")
            outputs.append({"id": output_id, "name": output_name})

        # Parse rules
        rules = []
        for rule_elem in decision_table.findall(".//dmn:rule", namespaces):
            rule_id = rule_elem.get("id")

            rule_inputs = {}
            for i, input_entry in enumerate(rule_elem.findall(".//dmn:inputEntry", namespaces)):
                text_elem = input_entry.find(".//dmn:text", namespaces)
                if text_elem is not None and text_elem.text:
                    input_key = inputs[i]["label"] if i < len(inputs) else f"input_{i}"
                    rule_inputs[input_key] = text_elem.text.strip()

            rule_outputs = {}
            for i, output_entry in enumerate(rule_elem.findall(".//dmn:outputEntry", namespaces)):
                text_elem = output_entry.find(".//dmn:text", namespaces)
                if text_elem is not None and text_elem.text:
                    output_key = outputs[i]["name"] if i < len(outputs) else f"output_{i}"
                    output_value = text_elem.text.strip()

                    # Convert boolean strings
                    if output_value.lower() in ("true", "false"):
                        output_value = output_value.lower() == "true"
                    # Convert numeric strings
                    elif output_value.isdigit():
                        output_value = int(output_value)
                    # Remove quotes from strings
                    elif output_value.startswith('"') and output_value.endswith('"'):
                        output_value = output_value[1:-1]

                    rule_outputs[output_key] = output_value

            rules.append({
                "id": rule_id,
                "inputs": rule_inputs,
                "output": rule_outputs
            })

        return {
            "hitPolicy": hit_policy,
            "inputs": inputs,
            "outputs": outputs,
            "rules": rules
        }

    def clear_cache(self) -> None:
        """Clear all cached DMN tables."""
        self._cache.clear()
        logger.info("DMN cache cleared")

    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache size and expired entries count
        """
        now = datetime.now()
        expired_count = sum(1 for entry in self._cache.values() if entry.expires_at < now)

        return {
            "total_entries": len(self._cache),
            "expired_entries": expired_count,
            "active_entries": len(self._cache) - expired_count
        }


# Global service instance
_service_instance: Optional[FederatedDMNService] = None


def get_dmn_service(cache_ttl_seconds: int = 300) -> FederatedDMNService:
    """
    Get or create global DMN Federation Service instance.

    Args:
        cache_ttl_seconds: Cache TTL for new instance (default: 300s)

    Returns:
        Global FederatedDMNService instance
    """
    global _service_instance

    if _service_instance is None:
        _service_instance = FederatedDMNService(cache_ttl_seconds)

    return _service_instance
