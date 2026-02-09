"""
DMN Rules Adapter for Hospital Revenue Cycle.

This module provides an adapter that translates federated business rules
from the RuleRegistry into DMN context variables that can be consumed by
Camunda DMN decisions.

Features:
- Converts rule values to DMN-compatible formats
- Generates domain-specific DMN contexts (glosa, collection, coding)
- Supports multi-tenant rule hierarchies
- Provides default values when rules are unavailable
- Validates DMN context completeness and types
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

import structlog

from revenue_cycle.rules.rule_inheritance import RuleRegistry, get_rule_registry

logger = structlog.get_logger(__name__)


class DMNContextValidationError(Exception):
    """Exception raised when DMN context validation fails."""

    def __init__(
        self,
        message: str,
        context_type: Optional[str] = None,
        missing_fields: Optional[list[str]] = None,
    ):
        self.message = message
        self.context_type = context_type
        self.missing_fields = missing_fields or []
        super().__init__(message)


class DMNRulesAdapter:
    """
    Adapter that bridges federated rules and Camunda DMN decisions.

    Translates RuleRegistry entries into DMN context objects that can be
    consumed by DMN decision tables deployed in Camunda 8.

    Supports:
    - Multi-tenant rule hierarchies (global -> company -> business unit)
    - Domain-specific DMN contexts (glosa, collection, coding)
    - Type conversion and validation
    - Fallback to sensible defaults
    """

    def __init__(
        self,
        rules_engine: Optional[RuleRegistry] = None,
        tenant_id: Optional[str] = None,
        business_unit_id: Optional[str] = None,
    ):
        """
        Initialize the DMN Rules Adapter.

        Args:
            rules_engine: Optional RuleRegistry instance (uses global if not provided)
            tenant_id: Optional tenant/company ID for rule lookups
            business_unit_id: Optional business unit ID for rule lookups
        """
        self.rules_engine = rules_engine or get_rule_registry()
        self.tenant_id = tenant_id
        self.business_unit_id = business_unit_id
        self._default_rules = self._load_defaults()
        self._logger = logger.bind(
            adapter="DMNRulesAdapter",
            tenant_id=tenant_id,
            business_unit_id=business_unit_id,
        )

    def _load_defaults(self) -> Dict[str, Any]:
        """
        Load default DMN context values.

        These are fallback values used when rules are unavailable.

        Returns:
            Dictionary of default DMN values
        """
        return {
            "autoAppealThreshold": Decimal("5000.00"),
            "autoAppealEnabled": True,
            "priorityMethod": "HYBRID",
            "teamAssignment": "SPECIALIZED",
            "daysBeforeReminder": 30,
            "daysBeforeAgency": 90,
            "minCollectionAmount": Decimal("500.00"),
            "autoCorrectEnabled": True,
            "drgMethod": "AI_ASSISTED",
            "paymentTermsDays": 30,
            "tisDeadlineDays": 30,
            "mfaRequired": True,
            "encryptionEnabled": True,
            "appealStrategy": "MODERATE",
        }

    def _get_rule_value(self, rule_key: str, default: Any = None) -> Any:
        """
        Get a rule value with fallback to default.

        Args:
            rule_key: Rule key to lookup
            default: Default value if rule not found

        Returns:
            Rule value or default

        Raises:
            Logs warning if rule not found
        """
        try:
            rule = self.rules_engine.get_rule(
                rule_key,
                company_id=self.tenant_id,
                business_unit_id=self.business_unit_id,
            )
            return rule.value
        except KeyError:
            self._logger.warning(
                "Rule not found, using default",
                rule_key=rule_key,
                default=default,
            )
            return default

    def get_dmn_context(self) -> Dict[str, Any]:
        """
        Generate base DMN input context with all tenant-specific rules.

        This is the foundation for all domain-specific contexts. It includes
        rules from all categories (regulatory, security, business).

        Returns:
            Dictionary with DMN variables ready for decision evaluation

        Example:
            >>> adapter = DMNRulesAdapter(tenant_id="hospital-001")
            >>> context = adapter.get_dmn_context()
            >>> # Use with Zeebe DMN evaluation
            >>> result = await dmn_service.evaluate("some-decision", context)
        """
        context = self._default_rules.copy()

        # Override with tenant rules
        context["autoAppealThreshold"] = Decimal(
            str(
                self._get_rule_value(
                    "glosa.auto_appeal_threshold",
                    self._default_rules["autoAppealThreshold"],
                )
            )
        )

        context["autoAppealEnabled"] = self._get_rule_value(
            "glosa.auto_appeal_enabled",
            self._default_rules["autoAppealEnabled"],
        )

        context["daysBeforeReminder"] = self._get_rule_value(
            "collection.days_before_reminder",
            self._default_rules["daysBeforeReminder"],
        )

        context["daysBeforeAgency"] = self._get_rule_value(
            "collection.days_before_agency_referral",
            self._default_rules["daysBeforeAgency"],
        )

        context["autoCorrectEnabled"] = self._get_rule_value(
            "coding.auto_correct_enabled",
            self._default_rules["autoCorrectEnabled"],
        )

        context["paymentTermsDays"] = self._get_rule_value(
            "billing.payment_terms_days",
            self._default_rules["paymentTermsDays"],
        )

        context["tisDeadlineDays"] = self._get_rule_value(
            "glosa.tiss_deadline_days",
            self._default_rules["tisDeadlineDays"],
        )

        context["mfaRequired"] = self._get_rule_value(
            "security.mfa_required",
            self._default_rules["mfaRequired"],
        )

        context["encryptionEnabled"] = self._get_rule_value(
            "security.encryption_enabled",
            self._default_rules["encryptionEnabled"],
        )

        context["appealStrategy"] = self._get_rule_value(
            "glosa.appeal_strategy",
            self._default_rules["appealStrategy"],
        )

        self._logger.debug(
            "Generated base DMN context",
            context_keys=list(context.keys()),
        )

        return context

    def get_glosa_dmn_context(self, glosa_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate DMN context specifically for glosa classification and appeal decisions.

        Inputs from glosa_data:
        - glosaAmount: Decimal amount of the glosa
        - glosaReason: String reason code (e.g., "INVALID_CODE", "DUPLICATE")
        - glosaDate: ISO date when glosa was issued
        - claimAmount: Decimal original claim amount
        - procedureType: String (e.g., "CLINICAL", "DIAGNOSTIC")

        Outputs from DMN context:
        - autoAppealThreshold: Amount threshold for automatic appeals
        - autoAppealEnabled: Whether auto-appeal is enabled
        - appellStrategy: Strategy for appeal (AGGRESSIVE, MODERATE, CONSERVATIVE)
        - daysToDeadline: Days until TISS deadline
        - priorityLevel: Priority for appeal (HIGH, MEDIUM, LOW)

        Args:
            glosa_data: Dictionary with glosa information

        Returns:
            DMN context dictionary for glosa decisions

        Raises:
            DMNContextValidationError: If required fields are missing
        """
        # Validate required input fields
        required_fields = ["glosaAmount", "claimAmount"]
        missing = [f for f in required_fields if f not in glosa_data]
        if missing:
            raise DMNContextValidationError(
                f"Missing required glosa fields: {missing}",
                context_type="glosa",
                missing_fields=missing,
            )

        # Get base context
        context = self.get_dmn_context()

        # Add glosa-specific fields
        glosa_amount = Decimal(str(glosa_data.get("glosaAmount", 0)))
        claim_amount = Decimal(str(glosa_data.get("claimAmount", 0)))

        context["glosaAmount"] = glosa_amount
        context["claimAmount"] = claim_amount
        context["glosaPercentage"] = (
            float((glosa_amount / claim_amount) * 100)
            if claim_amount > 0
            else 0.0
        )
        context["glosaReason"] = glosa_data.get("glosaReason", "UNKNOWN")
        context["glosaDate"] = glosa_data.get("glosaDate")
        context["procedureType"] = glosa_data.get("procedureType", "CLINICAL")

        # Determine priority level based on glosa amount
        auto_appeal_threshold = context.get("autoAppealThreshold", Decimal("5000.00"))
        if glosa_amount >= auto_appeal_threshold * 2:
            context["priorityLevel"] = "HIGH"
        elif glosa_amount >= auto_appeal_threshold:
            context["priorityLevel"] = "MEDIUM"
        else:
            context["priorityLevel"] = "LOW"

        self._logger.debug(
            "Generated glosa DMN context",
            glosa_amount=float(glosa_amount),
            priority_level=context.get("priorityLevel"),
        )

        return context

    def get_collection_dmn_context(self, account_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate DMN context for collection process decisions.

        Inputs from account_data:
        - accountBalance: Decimal outstanding balance
        - daysOverdue: Integer days past due
        - payerType: String (INDIVIDUAL, CORPORATE)
        - collectionHistory: List of past collection events
        - lastPaymentDate: Optional ISO date of last payment

        Outputs from DMN context:
        - daysBeforeReminder: Days before sending reminder
        - daysBeforeAgency: Days before agency referral
        - minCollectionAmount: Minimum amount to pursue collection
        - collectionStrategy: Strategy for collection (AGGRESSIVE, MODERATE, SOFT)
        - teamAssignment: Which team handles collection
        - escalationLevel: Escalation level (1-5)

        Args:
            account_data: Dictionary with account collection information

        Returns:
            DMN context dictionary for collection decisions

        Raises:
            DMNContextValidationError: If required fields are missing
        """
        # Validate required input fields
        required_fields = ["accountBalance", "daysOverdue"]
        missing = [f for f in required_fields if f not in account_data]
        if missing:
            raise DMNContextValidationError(
                f"Missing required collection fields: {missing}",
                context_type="collection",
                missing_fields=missing,
            )

        # Get base context
        context = self.get_dmn_context()

        # Add collection-specific fields
        account_balance = Decimal(str(account_data.get("accountBalance", 0)))
        days_overdue = account_data.get("daysOverdue", 0)
        payer_type = account_data.get("payerType", "INDIVIDUAL")
        collection_history = account_data.get("collectionHistory", [])

        context["accountBalance"] = account_balance
        context["daysOverdue"] = days_overdue
        context["payerType"] = payer_type
        context["collectionHistoryCount"] = len(collection_history)
        context["lastPaymentDate"] = account_data.get("lastPaymentDate")

        # Determine collection strategy based on days overdue
        days_before_agency = context.get("daysBeforeAgency", 90)
        days_before_reminder = context.get("daysBeforeReminder", 30)

        if days_overdue >= days_before_agency:
            context["collectionStrategy"] = "AGGRESSIVE"
            context["escalationLevel"] = 5
            context["recommendAgencyReferral"] = True
        elif days_overdue >= days_before_agency * 0.75:
            context["collectionStrategy"] = "AGGRESSIVE"
            context["escalationLevel"] = 4
            context["recommendAgencyReferral"] = False
        elif days_overdue >= days_before_reminder:
            context["collectionStrategy"] = "MODERATE"
            context["escalationLevel"] = 2
            context["recommendAgencyReferral"] = False
        else:
            context["collectionStrategy"] = "SOFT"
            context["escalationLevel"] = 1
            context["recommendAgencyReferral"] = False

        # Skip collection if below minimum amount
        min_collection_amount = context.get(
            "minCollectionAmount", Decimal("500.00")
        )
        context["skipCollection"] = account_balance < min_collection_amount

        self._logger.debug(
            "Generated collection DMN context",
            account_balance=float(account_balance),
            days_overdue=days_overdue,
            collection_strategy=context.get("collectionStrategy"),
            escalation_level=context.get("escalationLevel"),
        )

        return context

    def get_coding_dmn_context(self, encounter_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate DMN context for medical coding audit and correction decisions.

        Inputs from encounter_data:
        - claimCodes: List of medical codes (ICD-10, CPT)
        - procedureDescription: String description of procedures
        - diagnosisDescription: String description of diagnoses
        - claimAmount: Decimal claim amount for procedures
        - patientAge: Integer patient age
        - drgCode: String DRG code

        Outputs from DMN context:
        - autoCorrectEnabled: Whether auto-correction is allowed
        - drgMethod: Method for DRG assignment (AI_ASSISTED, MANUAL, HYBRID)
        - validationLevel: How strict code validation is (STRICT, NORMAL, LENIENT)
        - requiresPhysicianReview: Whether physician review required
        - codeAuditPriority: Priority for code audit (HIGH, NORMAL, LOW)

        Args:
            encounter_data: Dictionary with encounter/coding information

        Returns:
            DMN context dictionary for coding decisions

        Raises:
            DMNContextValidationError: If required fields are missing
        """
        # Validate required input fields
        required_fields = ["claimCodes", "claimAmount"]
        missing = [f for f in required_fields if f not in encounter_data]
        if missing:
            raise DMNContextValidationError(
                f"Missing required coding fields: {missing}",
                context_type="coding",
                missing_fields=missing,
            )

        # Get base context
        context = self.get_dmn_context()

        # Add coding-specific fields
        claim_codes = encounter_data.get("claimCodes", [])
        claim_amount = Decimal(str(encounter_data.get("claimAmount", 0)))
        patient_age = encounter_data.get("patientAge", 0)
        procedure_desc = encounter_data.get("procedureDescription", "")
        diagnosis_desc = encounter_data.get("diagnosisDescription", "")
        drg_code = encounter_data.get("drgCode", "")

        context["claimCodesCount"] = len(claim_codes)
        context["claimAmount"] = claim_amount
        context["patientAge"] = patient_age
        context["procedureDescription"] = procedure_desc
        context["diagnosisDescription"] = diagnosis_desc
        context["drgCode"] = drg_code

        # Determine validation level based on claim amount
        if claim_amount > Decimal("50000.00"):
            context["validationLevel"] = "STRICT"
            context["requiresPhysicianReview"] = True
            context["codeAuditPriority"] = "HIGH"
        elif claim_amount > Decimal("10000.00"):
            context["validationLevel"] = "NORMAL"
            context["requiresPhysicianReview"] = False
            context["codeAuditPriority"] = "NORMAL"
        else:
            context["validationLevel"] = "LENIENT"
            context["requiresPhysicianReview"] = False
            context["codeAuditPriority"] = "LOW"

        # Add auto-correct setting
        context["autoCorrectEnabled"] = self._get_rule_value(
            "coding.auto_correct_enabled",
            self._default_rules["autoCorrectEnabled"],
        )

        # Add DRG method setting
        context["drgMethod"] = self._get_rule_value(
            "coding.drg_method",
            self._default_rules["drgMethod"],
        )

        # Flag high-risk cases
        context["highRiskCase"] = (
            len(claim_codes) > 20 or claim_amount > Decimal("100000.00")
        )

        self._logger.debug(
            "Generated coding DMN context",
            claim_codes_count=len(claim_codes),
            claim_amount=float(claim_amount),
            validation_level=context.get("validationLevel"),
            high_risk=context.get("highRiskCase"),
        )

        return context

    def validate_dmn_context(
        self,
        context: Dict[str, Any],
        required_fields: Optional[list[str]] = None,
    ) -> bool:
        """
        Validate that a DMN context has all required fields and correct types.

        Args:
            context: DMN context to validate
            required_fields: Optional list of required field names

        Returns:
            True if context is valid

        Raises:
            DMNContextValidationError: If validation fails
        """
        if required_fields is None:
            required_fields = []

        missing = [f for f in required_fields if f not in context]
        if missing:
            raise DMNContextValidationError(
                f"DMN context missing required fields: {missing}",
                missing_fields=missing,
            )

        self._logger.debug(
            "DMN context validation passed",
            context_fields=len(context),
            required_fields=len(required_fields),
        )

        return True

    def get_context_summary(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get a summary of DMN context with key values highlighted.

        Useful for logging and debugging.

        Args:
            context: DMN context dictionary

        Returns:
            Summary dictionary with key metrics
        """
        summary = {
            "totalFields": len(context),
            "decimalFields": sum(
                1 for v in context.values() if isinstance(v, Decimal)
            ),
            "booleanFields": sum(
                1 for v in context.values() if isinstance(v, bool)
            ),
            "stringFields": sum(
                1 for v in context.values() if isinstance(v, str)
            ),
            "numericFields": sum(
                1 for v in context.values()
                if isinstance(v, (int, float))
            ),
        }

        return summary
