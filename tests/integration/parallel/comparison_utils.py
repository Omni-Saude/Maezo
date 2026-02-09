"""
Result Comparison Utilities for Java vs Python Parallel Testing
===============================================================

This module provides utilities for comparing outputs from Java and Python
implementations to ensure behavioral compatibility.

Features:
- Exact match detection
- Semantic match detection (normalized values, naming conventions)
- Detailed diff reporting for mismatches
- Field mapping for camelCase to snake_case conversion
- Value normalization for enums and monetary values

Author: Revenue Cycle Development Team
Version: 1.0.0
Date: 2026-02-04
"""

import json
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union


class MatchType(Enum):
    """Type of match between Java and Python outputs."""
    EXACT_MATCH = "exact_match"
    SEMANTIC_MATCH = "semantic_match"
    MISMATCH = "mismatch"


@dataclass
class FieldDifference:
    """Represents a difference in a single field."""
    field_name: str
    java_value: Any
    python_value: Any
    normalized_java: Any = None
    normalized_python: Any = None
    is_semantic_match: bool = False
    description: str = ""

    def __str__(self) -> str:
        if self.is_semantic_match:
            return (
                f"Field '{self.field_name}': Java='{self.java_value}' -> "
                f"Python='{self.python_value}' (semantic match after normalization)"
            )
        return (
            f"Field '{self.field_name}': Java='{self.java_value}' vs "
            f"Python='{self.python_value}'"
        )


@dataclass
class ComparisonResult:
    """Result of comparing Java and Python outputs."""
    match_type: MatchType
    java_output: Dict[str, Any]
    python_output: Dict[str, Any]
    differences: List[FieldDifference] = field(default_factory=list)
    normalized_java: Optional[Dict[str, Any]] = None
    normalized_python: Optional[Dict[str, Any]] = None
    input_hash: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def is_match(self) -> bool:
        """Check if outputs match (exact or semantic)."""
        return self.match_type in (MatchType.EXACT_MATCH, MatchType.SEMANTIC_MATCH)

    @property
    def is_exact_match(self) -> bool:
        """Check if outputs are exactly equal."""
        return self.match_type == MatchType.EXACT_MATCH

    @property
    def is_semantic_match(self) -> bool:
        """Check if outputs match after normalization."""
        return self.match_type == MatchType.SEMANTIC_MATCH

    @property
    def is_mismatch(self) -> bool:
        """Check if outputs do not match."""
        return self.match_type == MatchType.MISMATCH

    def get_diff_report(self) -> str:
        """Generate a human-readable diff report."""
        lines = [
            f"Match Type: {self.match_type.value}",
            f"Timestamp: {self.timestamp}",
            "",
        ]

        if self.differences:
            lines.append("Differences:")
            for diff in self.differences:
                lines.append(f"  - {diff}")

        if self.is_mismatch:
            lines.extend([
                "",
                "Java Output:",
                json.dumps(self.java_output, indent=2, default=str),
                "",
                "Python Output:",
                json.dumps(self.python_output, indent=2, default=str),
            ])

        return "\n".join(lines)


class OutputComparator:
    """
    Compares Java and Python outputs for behavioral compatibility.

    Handles:
    - Exact matching
    - Semantic matching with normalization
    - Field name mapping (camelCase <-> snake_case)
    - Value normalization (enums, decimals)
    - Detailed diff generation
    """

    # Field name mappings (Java camelCase -> Python snake_case)
    FIELD_MAPPINGS: Dict[str, str] = {
        "appealStrategy": "appeal_strategy",
        "assignedTo": "assigned_to",
        "glosaType": "glosa_type",
        "glosaAmount": "glosa_amount",
        "glosaReason": "glosa_reason",
        "recoveryProbability": "recovery_probability",
        "deadlineDays": "deadline_days",
        "requiresLegal": "requires_legal",
        "glosaAnalyzed": "glosa_analyzed",
        "provisionId": "provision_id",
        "provisionAmount": "provision_amount",
        "provisionCreated": "provision_created",
        "provisionDate": "provision_date",
        "accountingPeriod": "accounting_period",
        "accountingEntryId": "accounting_entry_id",
        "cpc25Category": "cpc25_category",
        "contractAdjustedCharges": "contract_adjusted_charges",
        "contractAdjustedAmount": "contract_adjusted_amount",
        "contractDiscount": "contract_discount",
        "contractRulesApplied": "contract_rules_applied",
        "contractId": "contract_id",
        "pricingTableUsed": "pricing_table_used",
        "discountsApplied": "discounts_applied",
        "maxClaimAmount": "max_claim_amount",
        "withinContractLimits": "within_contract_limits",
        "claimId": "claim_id",
        "claimStatus": "claim_status",
        "claimAmount": "claim_amount",
        "tissXml": "tiss_xml",
        "payerId": "payer_id",
        "patientId": "patient_id",
        "totalChargeAmount": "total_charge_amount",
    }

    # Value mappings (Java -> Python equivalents)
    VALUE_MAPPINGS: Dict[str, str] = {
        "SENIOR_APPEALS_TEAM": "senior_appeals_team",
        "AUTHORIZATION_TEAM": "authorization_team",
        "ELIGIBILITY_TEAM": "eligibility_team",
        "CODING_TEAM": "coding_team",
        "CLINICAL_APPEALS_TEAM": "clinical_appeals_team",
        "COMPLIANCE_TEAM": "compliance_team",
        "BILLING_TEAM": "billing_team",
        "GENERAL_APPEALS_TEAM": "general_appeals_team",
        "ACCOUNTING_TEAM": "accounting_team",
        "NONE": "none",
        "HIGH": "high",
        "MEDIUM": "medium",
        "LOW": "low",
        "AUTHORIZATION_APPEAL": "authorization_appeal",
        "ELIGIBILITY_VERIFICATION_APPEAL": "eligibility_verification_appeal",
        "CODING_REVIEW_APPEAL": "coding_review_appeal",
        "MEDICAL_NECESSITY_APPEAL": "medical_necessity_appeal",
        "COMPREHENSIVE_APPEAL": "comprehensive_appeal",
        "STANDARD_APPEAL": "standard_appeal",
        "QUICK_REVIEW_AND_RESUBMIT": "quick_review_and_resubmit",
        "REFUND_PROCESSING": "refund_processing",
        "NO_ACTION_REQUIRED": "no_action_required",
        "DUPLICATE_CLAIM_RESOLUTION": "duplicate_claim_resolution",
        "MODIFIER_CORRECTION_APPEAL": "modifier_correction_appeal",
        "TIMELY_FILING_APPEAL": "timely_filing_appeal",
    }

    # Fields that contain monetary values (need decimal comparison)
    MONETARY_FIELDS: set = {
        "glosa_amount", "glosaAmount",
        "provision_amount", "provisionAmount",
        "contract_adjusted_amount", "contractAdjustedAmount",
        "contract_discount", "contractDiscount",
        "max_claim_amount", "maxClaimAmount",
        "claim_amount", "claimAmount",
        "total_charge_amount", "totalChargeAmount",
        "amount",
    }

    # Fields that should be ignored in comparison (timestamps, generated IDs)
    IGNORED_FIELDS: set = {
        "timestamp", "created_at", "updated_at",
        "process_instance_key", "processInstanceKey",
    }

    def __init__(
        self,
        decimal_tolerance: Decimal = Decimal("0.01"),
        ignore_case: bool = True,
        strict_mode: bool = False,
    ):
        """
        Initialize the comparator.

        Args:
            decimal_tolerance: Tolerance for decimal comparisons
            ignore_case: Whether to ignore case in string comparisons
            strict_mode: If True, only exact matches are considered valid
        """
        self.decimal_tolerance = decimal_tolerance
        self.ignore_case = ignore_case
        self.strict_mode = strict_mode

        # Build reverse field mapping
        self._reverse_field_mapping = {v: k for k, v in self.FIELD_MAPPINGS.items()}

    def compare(
        self,
        java_output: Dict[str, Any],
        python_output: Dict[str, Any],
        input_data: Optional[Dict[str, Any]] = None,
    ) -> ComparisonResult:
        """
        Compare Java and Python outputs.

        Args:
            java_output: Output from Java implementation
            python_output: Output from Python implementation
            input_data: Optional input data for hash generation

        Returns:
            ComparisonResult with match type and differences
        """
        # Generate input hash for tracking
        input_hash = ""
        if input_data:
            input_hash = hashlib.md5(
                json.dumps(input_data, sort_keys=True, default=str).encode()
            ).hexdigest()[:8]

        # Handle None cases
        if java_output is None and python_output is None:
            return ComparisonResult(
                match_type=MatchType.EXACT_MATCH,
                java_output={},
                python_output={},
                input_hash=input_hash,
            )

        if java_output is None or python_output is None:
            return ComparisonResult(
                match_type=MatchType.MISMATCH,
                java_output=java_output or {},
                python_output=python_output or {},
                differences=[
                    FieldDifference(
                        field_name="output",
                        java_value=java_output,
                        python_value=python_output,
                        description="One output is None",
                    )
                ],
                input_hash=input_hash,
            )

        # Check for exact match first
        if self._deep_equals(java_output, python_output):
            return ComparisonResult(
                match_type=MatchType.EXACT_MATCH,
                java_output=java_output,
                python_output=python_output,
                input_hash=input_hash,
            )

        # Normalize and check for semantic match
        normalized_java = self._normalize_output(java_output)
        normalized_python = self._normalize_output(python_output)

        if self._deep_equals(normalized_java, normalized_python):
            # Find which fields differ before normalization
            differences = self._find_differences(
                java_output, python_output, normalized_java, normalized_python
            )
            return ComparisonResult(
                match_type=MatchType.SEMANTIC_MATCH,
                java_output=java_output,
                python_output=python_output,
                differences=differences,
                normalized_java=normalized_java,
                normalized_python=normalized_python,
                input_hash=input_hash,
            )

        # Not a match - find all differences
        differences = self._find_differences(
            java_output, python_output, normalized_java, normalized_python
        )
        return ComparisonResult(
            match_type=MatchType.MISMATCH,
            java_output=java_output,
            python_output=python_output,
            differences=differences,
            normalized_java=normalized_java,
            normalized_python=normalized_python,
            input_hash=input_hash,
        )

    def _deep_equals(self, obj1: Any, obj2: Any) -> bool:
        """Deep equality check with type coercion for compatible types."""
        if obj1 == obj2:
            return True

        if type(obj1) != type(obj2):
            # Handle numeric type differences
            if isinstance(obj1, (int, float, Decimal)) and isinstance(obj2, (int, float, Decimal)):
                return self._compare_decimals(obj1, obj2)
            return False

        if isinstance(obj1, dict):
            if set(obj1.keys()) != set(obj2.keys()):
                return False
            return all(self._deep_equals(obj1[k], obj2[k]) for k in obj1.keys())

        if isinstance(obj1, list):
            if len(obj1) != len(obj2):
                return False
            return all(self._deep_equals(a, b) for a, b in zip(obj1, obj2))

        return False

    def _compare_decimals(self, val1: Any, val2: Any) -> bool:
        """Compare two numeric values within tolerance."""
        try:
            d1 = Decimal(str(val1))
            d2 = Decimal(str(val2))
            return abs(d1 - d2) <= self.decimal_tolerance
        except (InvalidOperation, ValueError):
            return False

    def _normalize_output(self, output: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize output for semantic comparison.

        - Convert field names to snake_case
        - Normalize string values (lowercase, strip)
        - Map enum values
        - Normalize decimal values
        """
        normalized = {}

        for key, value in output.items():
            if key in self.IGNORED_FIELDS:
                continue

            # Normalize key to snake_case
            norm_key = self._normalize_field_name(key)

            # Normalize value
            norm_value = self._normalize_value(value, norm_key)

            normalized[norm_key] = norm_value

        return normalized

    def _normalize_field_name(self, name: str) -> str:
        """Convert field name to snake_case."""
        if name in self.FIELD_MAPPINGS:
            return self.FIELD_MAPPINGS[name]

        # Convert camelCase to snake_case
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

    def _normalize_value(self, value: Any, field_name: str = "") -> Any:
        """Normalize a value for comparison."""
        if value is None:
            return None

        if isinstance(value, dict):
            return self._normalize_output(value)

        if isinstance(value, list):
            return [self._normalize_value(v, field_name) for v in value]

        if isinstance(value, str):
            # Check for known value mapping
            if value in self.VALUE_MAPPINGS:
                return self.VALUE_MAPPINGS[value].lower()

            # Normalize string
            normalized = value.strip()
            if self.ignore_case:
                normalized = normalized.lower()

            # Replace underscores with spaces for comparison
            normalized = normalized.replace("_", " ")
            return normalized

        if isinstance(value, (int, float, Decimal)):
            # Normalize to Decimal with 2 decimal places for monetary fields
            if field_name in self.MONETARY_FIELDS:
                try:
                    return float(Decimal(str(value)).quantize(Decimal("0.01")))
                except InvalidOperation:
                    return float(value)
            return float(value) if isinstance(value, Decimal) else value

        if isinstance(value, bool):
            return value

        return str(value)

    def _find_differences(
        self,
        java_output: Dict[str, Any],
        python_output: Dict[str, Any],
        normalized_java: Dict[str, Any],
        normalized_python: Dict[str, Any],
    ) -> List[FieldDifference]:
        """Find all differences between outputs."""
        differences = []

        # Collect all keys (normalized)
        all_keys = set(normalized_java.keys()) | set(normalized_python.keys())

        for key in all_keys:
            java_val = normalized_java.get(key)
            python_val = normalized_python.get(key)

            if not self._deep_equals(java_val, python_val):
                # Find original values
                orig_java_key = self._find_original_key(key, java_output)
                orig_python_key = self._find_original_key(key, python_output)

                orig_java_val = java_output.get(orig_java_key) if orig_java_key else None
                orig_python_val = python_output.get(orig_python_key) if orig_python_key else None

                differences.append(
                    FieldDifference(
                        field_name=key,
                        java_value=orig_java_val,
                        python_value=orig_python_val,
                        normalized_java=java_val,
                        normalized_python=python_val,
                        is_semantic_match=False,
                    )
                )

        return differences

    def _find_original_key(self, normalized_key: str, output: Dict[str, Any]) -> Optional[str]:
        """Find the original key in output for a normalized key."""
        # Check if key exists directly
        if normalized_key in output:
            return normalized_key

        # Check reverse mapping
        if normalized_key in self._reverse_field_mapping:
            camel_key = self._reverse_field_mapping[normalized_key]
            if camel_key in output:
                return camel_key

        # Check forward mapping
        for orig_key in output.keys():
            if self._normalize_field_name(orig_key) == normalized_key:
                return orig_key

        return None


def compare_outputs(
    java_output: Dict[str, Any],
    python_output: Dict[str, Any],
    input_data: Optional[Dict[str, Any]] = None,
) -> ComparisonResult:
    """
    Convenience function to compare Java and Python outputs.

    Args:
        java_output: Output from Java implementation
        python_output: Output from Python implementation
        input_data: Optional input data for hash generation

    Returns:
        ComparisonResult with match type and differences
    """
    comparator = OutputComparator()
    return comparator.compare(java_output, python_output, input_data)


def generate_mismatch_report(
    results: List[ComparisonResult],
    include_matches: bool = False,
) -> str:
    """
    Generate a detailed mismatch report.

    Args:
        results: List of comparison results
        include_matches: Whether to include matched results

    Returns:
        Formatted report string
    """
    lines = [
        "=" * 60,
        "PARALLEL VALIDATION MISMATCH REPORT",
        f"Generated: {datetime.now().isoformat()}",
        "=" * 60,
        "",
    ]

    # Summary
    total = len(results)
    exact_matches = sum(1 for r in results if r.is_exact_match)
    semantic_matches = sum(1 for r in results if r.is_semantic_match)
    mismatches = sum(1 for r in results if r.is_mismatch)

    lines.extend([
        "SUMMARY:",
        f"  Total Tests: {total}",
        f"  Exact Matches: {exact_matches} ({100*exact_matches/max(1,total):.1f}%)",
        f"  Semantic Matches: {semantic_matches} ({100*semantic_matches/max(1,total):.1f}%)",
        f"  Mismatches: {mismatches} ({100*mismatches/max(1,total):.1f}%)",
        "",
    ])

    # Mismatches detail
    mismatch_results = [r for r in results if r.is_mismatch]
    if mismatch_results:
        lines.extend([
            "MISMATCH DETAILS:",
            "-" * 40,
            "",
        ])

        for i, result in enumerate(mismatch_results, 1):
            lines.extend([
                f"Mismatch #{i}:",
                f"  Input Hash: {result.input_hash}",
                f"  Differences: {len(result.differences)}",
            ])

            for diff in result.differences:
                lines.append(f"    - {diff}")

            lines.append("")

    # Include matches if requested
    if include_matches:
        match_results = [r for r in results if r.is_match]
        if match_results:
            lines.extend([
                "MATCHED RESULTS:",
                "-" * 40,
            ])
            for result in match_results:
                lines.append(f"  {result.match_type.value}: {result.input_hash}")
            lines.append("")

    return "\n".join(lines)
