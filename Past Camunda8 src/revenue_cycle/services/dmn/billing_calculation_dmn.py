"""
Python implementation of billing-calculation.dmn decision table.

This module provides a Python fallback for the DMN billing calculation
rules when the Zeebe DMN service is unavailable.

Decision Key: billing-calculation
Hit Policy: FIRST (first matching rule applies)

Rules are based on the original Java DMN implementation.
"""

from typing import Any, Dict

import structlog

logger = structlog.get_logger(__name__)


class BillingCalculationDMN:
    """
    Python implementation of billing-calculation.dmn rules.

    Implements 8 decision rules for billing calculation:
    1. SURGICAL + SUS: Base value, no discount
    2. AMB table: 20% increase
    3. CBHPM table: 40% increase
    4. Partial glosa (<=30%): Apply glosa, needs audit
    5. High glosa (>30%): Apply glosa, needs audit
    6. HOSPITALIZATION: Base value
    7. DIAGNOSTIC + BRASINDICE: 10% increase
    8. Default: Standard calculation

    Inputs:
    - procedureType: SURGICAL, CLINICAL, DIAGNOSTIC, THERAPEUTIC, HOSPITALIZATION
    - insuranceTable: SUS, AMB, CBHPM, BRASINDICE, SIMPRO, CUSTOM
    - baseValue: Total amount to calculate
    - hasGlosa: Whether there is a denial
    - glosaPercentage: Denial percentage (0-100)

    Outputs:
    - billableAmount: Amount that can be billed
    - discountApplied: Discount/glosa amount
    - finalAmount: Final calculated amount
    - calculationRule: Name of rule applied
    - needsAudit: Whether audit is required
    """

    def __init__(self):
        """Initialize billing calculation DMN."""
        self._logger = logger.bind(dmn="billing-calculation")

    def evaluate(
        self,
        procedure_type: str,
        insurance_table: str,
        base_value: float,
        has_glosa: bool,
        glosa_percentage: float,
    ) -> Dict[str, Any]:
        """
        Evaluate billing calculation rules.

        Uses FIRST hit policy - returns result from first matching rule.

        Args:
            procedure_type: Type of procedure (SURGICAL, CLINICAL, etc.)
            insurance_table: Pricing table (SUS, AMB, CBHPM, etc.)
            base_value: Base amount to calculate
            has_glosa: Whether there is a glosa/denial
            glosa_percentage: Glosa percentage (0-100)

        Returns:
            Dictionary with billing calculation outputs
        """
        self._logger.debug(
            "Evaluating billing-calculation DMN",
            procedure_type=procedure_type,
            insurance_table=insurance_table,
            base_value=base_value,
            has_glosa=has_glosa,
            glosa_percentage=glosa_percentage,
        )

        # Rule 1: SURGICAL + SUS (no increase, no discount)
        if procedure_type == "SURGICAL" and insurance_table == "SUS" and not has_glosa:
            result = self._result(
                base_value, 0, base_value, "SUS_SURGICAL_BASE", False
            )
            self._log_result(result, 1)
            return result

        # Rule 2: AMB table (20% increase)
        if insurance_table == "AMB" and not has_glosa:
            amount = base_value * 1.20
            result = self._result(amount, 0, amount, "AMB_TABLE_120", False)
            self._log_result(result, 2)
            return result

        # Rule 3: CBHPM table (40% increase)
        if insurance_table == "CBHPM" and not has_glosa:
            amount = base_value * 1.40
            result = self._result(amount, 0, amount, "CBHPM_TABLE_140", False)
            self._log_result(result, 3)
            return result

        # Rule 4: Partial glosa (up to 30%)
        if has_glosa and 0 < glosa_percentage <= 30:
            discount = base_value * (glosa_percentage / 100)
            final = base_value - discount
            result = self._result(base_value, discount, final, "PARTIAL_GLOSA", True)
            self._log_result(result, 4)
            return result

        # Rule 5: High glosa (over 30%)
        if has_glosa and glosa_percentage > 30:
            discount = base_value * (glosa_percentage / 100)
            final = base_value - discount
            result = self._result(
                base_value, discount, final, "HIGH_GLOSA_AUDIT_REQUIRED", True
            )
            self._log_result(result, 5)
            return result

        # Rule 6: HOSPITALIZATION (no increase)
        if procedure_type == "HOSPITALIZATION" and not has_glosa:
            result = self._result(
                base_value, 0, base_value, "HOSPITALIZATION_DAILY", False
            )
            self._log_result(result, 6)
            return result

        # Rule 7: DIAGNOSTIC + BRASINDICE (10% increase)
        if (
            procedure_type == "DIAGNOSTIC"
            and insurance_table == "BRASINDICE"
            and not has_glosa
        ):
            amount = base_value * 1.10
            result = self._result(amount, 0, amount, "BRASINDICE_DIAGNOSTIC_110", False)
            self._log_result(result, 7)
            return result

        # Rule 8: Default calculation (no modification)
        result = self._result(base_value, 0, base_value, "STANDARD_CALCULATION", False)
        self._log_result(result, 8)
        return result

    def _result(
        self,
        billable: float,
        discount: float,
        final: float,
        rule: str,
        audit: bool,
    ) -> Dict[str, Any]:
        """
        Build result dictionary.

        Args:
            billable: Billable amount
            discount: Discount applied
            final: Final amount
            rule: Rule name applied
            audit: Whether audit is needed

        Returns:
            Dictionary matching DMN output structure
        """
        return {
            "billableAmount": round(billable, 2),
            "discountApplied": round(discount, 2),
            "finalAmount": round(final, 2),
            "calculationRule": rule,
            "needsAudit": audit,
        }

    def _log_result(self, result: Dict[str, Any], rule_number: int) -> None:
        """Log the evaluation result."""
        self._logger.debug(
            "DMN rule matched",
            rule_number=rule_number,
            calculation_rule=result["calculationRule"],
            final_amount=result["finalAmount"],
            needs_audit=result["needsAudit"],
        )
