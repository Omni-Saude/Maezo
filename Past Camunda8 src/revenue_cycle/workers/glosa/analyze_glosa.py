"""
AnalyzeGlosaWorker - Analyzes claim denials and determines appeal strategy.

This is the Python equivalent of the Java AnalyzeGlosaDelegate.

Migrated from: com.hospital.revenuecycle.delegates.glosa.AnalyzeGlosaDelegate
Zeebe Topic: analyze-glosa
Business Rule: RN-GLOSA-001-AnalyzeGlosa.md
Regulatory Compliance: ANS RN 424/2017 (30-day appeal deadline), ANS RN 395/2016 (60-day submission)

Input Variables:
    glosaType (str): Type of glosa (FULL_DENIAL, PARTIAL_DENIAL, UNDERPAYMENT,
                     OVERPAYMENT, NO_GLOSA) or domain types (CLINICAL, ADMINISTRATIVE, etc.)
    glosaReason (str, optional): Textual reason for denial
    glosaAmount (Decimal): Monetary value of the glosa (>= 0)
    glosaSource (str, optional): Origin of glosa (AUDIT, INSURANCE, INTERNAL, REGULATORY, ANS)
    hasDocumentation (bool, optional): Whether supporting documentation is available
    daysSinceOccurrence (int, optional): Days since glosa was identified

Output Variables:
    appealStrategy (str): Recommended appeal strategy
    priority (str): Appeal priority (HIGH, MEDIUM, LOW)
    assignedTo (str): Team/person assigned to handle appeal
    recoveryProbability (int, optional): Probability of recovery (0-100%)
    deadlineDays (int, optional): Days until appeal deadline
    requiresLegal (bool, optional): Whether legal action is required

BPMN Errors:
    INVALID_GLOSA_DATA: Glosa data is invalid or incomplete
    ANALYSIS_FAILED: Glosa analysis failed
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Optional, Protocol

import structlog
from pydantic import BaseModel, Field, field_validator

from revenue_cycle.domain import (
    AppealStrategy,
    GlosaType,
    Priority,
    Money,
)
from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)

# Thresholds for priority classification (in BRL)
HIGH_PRIORITY_THRESHOLD = Decimal("5000.00")
MEDIUM_PRIORITY_THRESHOLD = Decimal("1000.00")

# DMN evaluation thresholds
DMN_CRITICAL_AMOUNT_THRESHOLD = Decimal("10000.00")
DMN_LOW_AMOUNT_THRESHOLD = Decimal("500.00")


# =============================================================================
# Input/Output Pydantic Models (Migration Spec Compliance)
# =============================================================================


class BpmnGlosaType(str, Enum):
    """
    BPMN process glosa types from Java delegate.

    These are the original types from the Camunda process and need to be
    mapped to the domain GlosaType for processing.
    """
    FULL_DENIAL = "FULL_DENIAL"
    PARTIAL_DENIAL = "PARTIAL_DENIAL"
    UNDERPAYMENT = "UNDERPAYMENT"
    OVERPAYMENT = "OVERPAYMENT"
    NO_GLOSA = "NO_GLOSA"


class GlosaSource(str, Enum):
    """Source/origin of the glosa identification."""
    AUDIT = "AUDIT"
    INSURANCE = "INSURANCE"
    INTERNAL = "INTERNAL"
    REGULATORY = "REGULATORY"
    ANS = "ANS"


class AssignedTeam(str, Enum):
    """Teams that can be assigned to handle glosa appeals."""
    SENIOR_APPEALS_TEAM = "SENIOR_APPEALS_TEAM"
    AUTHORIZATION_TEAM = "AUTHORIZATION_TEAM"
    ELIGIBILITY_TEAM = "ELIGIBILITY_TEAM"
    CODING_TEAM = "CODING_TEAM"
    CLINICAL_APPEALS_TEAM = "CLINICAL_APPEALS_TEAM"
    COMPLIANCE_TEAM = "COMPLIANCE_TEAM"
    BILLING_TEAM = "BILLING_TEAM"
    GENERAL_APPEALS_TEAM = "GENERAL_APPEALS_TEAM"
    ACCOUNTING_TEAM = "ACCOUNTING_TEAM"
    NONE = "NONE"


class AnalyzeGlosaInput(BaseModel):
    """
    Input model for glosa analysis.

    Validates and normalizes input from BPMN process variables.
    Supports both camelCase (from Java/BPMN) and snake_case naming.
    """
    glosa_type: str = Field(..., alias="glosaType", description="Type of glosa")
    glosa_amount: Decimal = Field(
        ...,
        alias="glosaAmount",
        ge=0,
        description="Monetary value of the glosa"
    )
    glosa_reason: Optional[str] = Field(
        None,
        alias="glosaReason",
        description="Textual reason for denial"
    )
    glosa_source: GlosaSource = Field(
        GlosaSource.INSURANCE,
        alias="glosaSource",
        description="Origin of glosa identification"
    )
    has_documentation: bool = Field(
        True,
        alias="hasDocumentation",
        description="Whether supporting documentation is available"
    )
    days_since_occurrence: int = Field(
        0,
        alias="daysSinceOccurrence",
        ge=0,
        description="Days since glosa was identified"
    )

    model_config = {
        "populate_by_name": True,
        "str_strip_whitespace": True,
    }

    @field_validator('glosa_amount', mode='before')
    @classmethod
    def parse_amount(cls, v):
        """Parse amount from various formats."""
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            # Handle Brazilian number format (comma as decimal separator)
            return Decimal(v.replace(",", "."))
        return v


class AnalyzeGlosaOutput(BaseModel):
    """
    Output model for glosa analysis results.

    Contains the appeal strategy, priority, team assignment, and optional
    DMN-derived fields.
    """
    appeal_strategy: str = Field(..., alias="appealStrategy")
    priority: str = Field(...)
    assigned_to: str = Field(..., alias="assignedTo")
    recovery_probability: Optional[int] = Field(
        None,
        alias="recoveryProbability",
        ge=0,
        le=100,
        description="Probability of recovery (0-100%)"
    )
    deadline_days: Optional[int] = Field(
        None,
        alias="deadlineDays",
        ge=0,
        description="Days until appeal deadline"
    )
    requires_legal: Optional[bool] = Field(
        None,
        alias="requiresLegal",
        description="Whether legal action is required"
    )
    glosa_analyzed: bool = Field(True, alias="glosaAnalyzed")

    model_config = {
        "populate_by_name": True,
        "use_enum_values": True,
    }


class DMNServiceProtocol(Protocol):
    """Protocol for DMN service integration."""
    async def evaluate(
        self,
        decision_key: str,
        variables: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Evaluate a DMN decision table."""
        ...


@worker(
    topic="analyze-glosa",
    max_jobs=10,
    lock_duration=60000,  # 1 minute
)
class AnalyzeGlosaWorker(BaseWorker):
    """
    Worker for analyzing glosa (claim denials) and determining appeal strategy.

    Migrated from: com.hospital.revenuecycle.delegates.glosa.AnalyzeGlosaDelegate

    Responsibilities:
    - Analyze glosa type and reason
    - Determine appeal strategy based on glosa characteristics
    - Assign priority level for appeal processing
    - Assign responsible team/person for appeal
    - Optionally evaluate DMN decision tables for enhanced classification

    Business Logic Summary:
    1. VALIDATE input data (glosaType, glosaAmount)
    2. DETERMINE appeal strategy based on:
       - Glosa type (FULL_DENIAL, PARTIAL_DENIAL, etc.)
       - Glosa reason (AUTHORIZATION, ELIGIBILITY, CODING, etc.)
       - Glosa amount (thresholds: HIGH=$5000, MEDIUM=$1000)
    3. CLASSIFY priority based on:
       - Full denials always >= MEDIUM
       - Amount-based for other types
    4. ASSIGN responsible team based on:
       - Amount (high value -> senior team)
       - Appeal strategy (specialized teams)
    5. INVOKE DMN decision table if available
    6. OVERRIDE with DMN results if present
    7. SET output variables

    This worker mirrors the Java AnalyzeGlosaDelegate logic.
    """

    def __init__(
        self,
        dmn_service: Optional[DMNServiceProtocol] = None,
        **kwargs
    ):
        """
        Initialize the worker.

        Args:
            dmn_service: Optional DMN service for decision table evaluation
            **kwargs: Additional arguments for BaseWorker
        """
        super().__init__(**kwargs)
        self._dmn_service = dmn_service

    @property
    def operation_name(self) -> str:
        return "analyze_glosa"

    @property
    def requires_idempotency(self) -> bool:
        # Analysis is deterministic and naturally idempotent
        # Same inputs always produce same outputs
        return False

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Execute the glosa analysis business logic.

        Args:
            job: Camunda external task
            variables: Job variables

        Returns:
            WorkerResult with appeal strategy, priority, and assignment
        """
        self._logger.info(
            "Starting glosa analysis",
            business_key=variables.get("businessKey"),
        )

        # 1. Retrieve and validate input variables
        glosa_type_str = self.get_required_variable(variables, "glosaType", str)
        glosa_reason = self.get_variable(variables, "glosaReason", str)
        glosa_amount = self.get_required_amount_variable(variables, "glosaAmount")
        glosa_source_str = self.get_variable(
            variables, "glosaSource", str, GlosaSource.INSURANCE.value
        )
        has_documentation = self.get_variable(variables, "hasDocumentation", bool, True)
        days_since_occurrence = self.get_variable(
            variables, "daysSinceOccurrence", int, 0
        )

        # 2. Validate glosa data
        self._validate_glosa_data(glosa_type_str, glosa_amount)

        # 3. Parse glosa source (with fallback)
        try:
            glosa_source = GlosaSource(glosa_source_str)
        except ValueError:
            glosa_source = GlosaSource.INSURANCE

        # 4. Determine if this is a BPMN type or domain type and convert
        bpmn_type: Optional[BpmnGlosaType] = None
        try:
            bpmn_type = BpmnGlosaType(glosa_type_str)
            # Map BPMN type to domain type
            glosa_type = self._map_bpmn_to_domain_type(bpmn_type)
        except ValueError:
            # Try domain type directly
            try:
                glosa_type = GlosaType(glosa_type_str)
            except ValueError:
                # Fallback mapping
                glosa_type = self._map_glosa_type(glosa_type_str)

        # 5. Determine appeal strategy
        appeal_strategy = self._determine_appeal_strategy(
            glosa_type, glosa_reason, glosa_amount, bpmn_type
        )
        self._logger.info(
            "Determined appeal strategy",
            glosa_type=glosa_type.value,
            bpmn_type=bpmn_type.value if bpmn_type else None,
            strategy=appeal_strategy.value,
        )

        # 6. Assign priority based on amount and type
        priority = self._determine_priority(glosa_type, glosa_amount, bpmn_type)
        self._logger.info(
            "Assigned priority",
            glosa_amount=str(glosa_amount),
            priority=priority.value,
        )

        # 7. Assign responsible team/person
        assigned_to = self._assign_responsible(
            glosa_type, glosa_amount, appeal_strategy
        )
        self._logger.info("Assigned glosa to team", assigned_to=assigned_to)

        # 8. Calculate recovery probability (simple heuristic)
        recovery_probability = self._calculate_recovery_probability(
            glosa_type, appeal_strategy, glosa_amount
        )

        # 9. Calculate deadline days based on source and amount
        deadline_days = self._calculate_deadline_days(
            glosa_source, glosa_amount, days_since_occurrence
        )

        # 10. Determine if legal action is required
        requires_legal = self._requires_legal_action(
            glosa_source, glosa_amount, days_since_occurrence
        )

        # 11. Build base output
        output = AnalyzeGlosaOutput(
            appeal_strategy=appeal_strategy.value,
            priority=priority.value,
            assigned_to=assigned_to,
            recovery_probability=recovery_probability,
            deadline_days=deadline_days,
            requires_legal=requires_legal,
            glosa_analyzed=True,
        )

        # 12. Invoke DMN if service is available
        if self._dmn_service:
            dmn_result = await self._invoke_dmn(
                glosa_type=glosa_type,
                glosa_source=glosa_source,
                glosa_amount=glosa_amount,
                has_documentation=has_documentation,
                days_since_occurrence=days_since_occurrence,
            )
            if dmn_result:
                output = self._merge_dmn_results(output, dmn_result)
                self._logger.info(
                    "DMN results merged",
                    dmn_strategy=dmn_result.get("appealStrategy"),
                    dmn_priority=dmn_result.get("appealPriority"),
                )

        # 13. Return result as dictionary
        return WorkerResult.ok(output.model_dump(by_alias=True, exclude_none=True))

    def _validate_glosa_data(
        self,
        glosa_type: str,
        glosa_amount: Decimal,
    ) -> None:
        """
        Validate glosa input data.

        Args:
            glosa_type: Glosa type string
            glosa_amount: Glosa amount

        Raises:
            BpmnErrorException: If data is invalid
        """
        if not glosa_type or not glosa_type.strip():
            raise BpmnErrorException.invalid_glosa_data("Glosa type is required")

        if glosa_amount < 0:
            raise BpmnErrorException.invalid_glosa_data(
                f"Glosa amount must be non-negative: {glosa_amount}"
            )

    def _map_bpmn_to_domain_type(self, bpmn_type: BpmnGlosaType) -> GlosaType:
        """
        Map BPMN process glosa type to domain GlosaType.

        This mapping is defined in the migration spec section 9 (DMN Decision Tables).

        Args:
            bpmn_type: BPMN process glosa type

        Returns:
            Domain GlosaType
        """
        mapping = {
            BpmnGlosaType.FULL_DENIAL: GlosaType.CLINICAL,
            BpmnGlosaType.PARTIAL_DENIAL: GlosaType.CLINICAL,
            BpmnGlosaType.UNDERPAYMENT: GlosaType.ADMINISTRATIVE,
            BpmnGlosaType.OVERPAYMENT: GlosaType.ADMINISTRATIVE,
            BpmnGlosaType.NO_GLOSA: GlosaType.DOCUMENTATION,
        }
        return mapping.get(bpmn_type, GlosaType.ADMINISTRATIVE)

    def _map_glosa_type(self, glosa_type_str: str) -> GlosaType:
        """
        Map alternative glosa type names to GlosaType enum.

        Args:
            glosa_type_str: Glosa type string

        Returns:
            Mapped GlosaType
        """
        type_mapping = {
            "FULL_DENIAL": GlosaType.CLINICAL,
            "PARTIAL_DENIAL": GlosaType.CLINICAL,
            "UNDERPAYMENT": GlosaType.ADMINISTRATIVE,
            "OVERPAYMENT": GlosaType.ADMINISTRATIVE,
            "NO_GLOSA": GlosaType.DOCUMENTATION,
        }

        return type_mapping.get(glosa_type_str.upper(), GlosaType.ADMINISTRATIVE)

    def _determine_appeal_strategy(
        self,
        glosa_type: GlosaType,
        glosa_reason: Optional[str],
        glosa_amount: Decimal,
        bpmn_type: Optional[BpmnGlosaType] = None,
    ) -> AppealStrategy:
        """
        Determine the appeal strategy based on glosa characteristics.

        Strategy determination follows the migration spec:
        - FULL_DENIAL: Map reasons to strategies (AUTHORIZATION, ELIGIBILITY, CODING, MEDICAL_NECESSITY)
        - PARTIAL_DENIAL: Calculate based on amount thresholds
        - UNDERPAYMENT: Standard appeal
        - OVERPAYMENT: Accept glosa (refund processing)
        - NO_GLOSA: No action required

        Args:
            glosa_type: Type of glosa (domain type)
            glosa_reason: Reason for denial
            glosa_amount: Amount denied
            bpmn_type: Optional BPMN process type for enhanced strategy

        Returns:
            Recommended appeal strategy
        """
        # Handle BPMN types specifically if available
        if bpmn_type:
            return self._determine_bpmn_type_strategy(
                bpmn_type, glosa_reason, glosa_amount
            )

        # High value claims get comprehensive review
        if glosa_amount >= HIGH_PRIORITY_THRESHOLD:
            return AppealStrategy.COMPREHENSIVE_APPEAL

        # Strategy based on domain glosa type
        type_strategies = {
            GlosaType.AUTHORIZATION: AppealStrategy.AUTHORIZATION_APPEAL,
            GlosaType.ELIGIBILITY: AppealStrategy.ELIGIBILITY_VERIFICATION_APPEAL,
            GlosaType.TECHNICAL: AppealStrategy.CODING_REVIEW_APPEAL,
            GlosaType.BUNDLING: AppealStrategy.CODING_REVIEW_APPEAL,
            GlosaType.MODIFIER: AppealStrategy.MODIFIER_CORRECTION_APPEAL,
            GlosaType.DUPLICATE: AppealStrategy.DUPLICATE_CLAIM_RESOLUTION,
            GlosaType.DOCUMENTATION: AppealStrategy.COMPREHENSIVE_APPEAL,
        }

        if glosa_type in type_strategies:
            return type_strategies[glosa_type]

        # Check reason for more specific strategy
        if glosa_reason:
            strategy = self._determine_strategy_from_reason(glosa_reason)
            if strategy:
                return strategy

        # Default to standard appeal
        return AppealStrategy.STANDARD_APPEAL

    def _determine_bpmn_type_strategy(
        self,
        bpmn_type: BpmnGlosaType,
        glosa_reason: Optional[str],
        glosa_amount: Decimal,
    ) -> AppealStrategy:
        """
        Determine strategy for BPMN process glosa types.

        Implements the strategy mapping from migration spec section 8:
        - FULL_DENIAL: Map reasons to specific strategies
        - PARTIAL_DENIAL: Amount-based or reason-based
        - UNDERPAYMENT: Quick review and resubmit
        - OVERPAYMENT: Refund processing
        - NO_GLOSA: No action required

        Args:
            bpmn_type: BPMN process glosa type
            glosa_reason: Reason for denial
            glosa_amount: Amount denied

        Returns:
            Recommended appeal strategy
        """
        if bpmn_type == BpmnGlosaType.FULL_DENIAL:
            return self._determine_full_denial_strategy(glosa_reason, glosa_amount)

        elif bpmn_type == BpmnGlosaType.PARTIAL_DENIAL:
            return self._determine_partial_denial_strategy(glosa_reason, glosa_amount)

        elif bpmn_type == BpmnGlosaType.UNDERPAYMENT:
            return AppealStrategy.QUICK_REVIEW_AND_RESUBMIT

        elif bpmn_type == BpmnGlosaType.OVERPAYMENT:
            return AppealStrategy.REFUND_PROCESSING

        elif bpmn_type == BpmnGlosaType.NO_GLOSA:
            return AppealStrategy.NO_ACTION_REQUIRED

        return AppealStrategy.STANDARD_APPEAL

    def _determine_full_denial_strategy(
        self,
        glosa_reason: Optional[str],
        glosa_amount: Decimal,
    ) -> AppealStrategy:
        """
        Determine strategy for full denial glosas.

        Strategy mapping from migration spec:
        - AUTHORIZATION reason -> AUTHORIZATION_APPEAL
        - ELIGIBILITY reason -> ELIGIBILITY_VERIFICATION_APPEAL
        - CODING reason -> CODING_REVIEW_APPEAL
        - MEDICAL NECESSITY reason -> MEDICAL_NECESSITY_APPEAL
        - Default -> COMPREHENSIVE_APPEAL

        Args:
            glosa_reason: Reason for denial
            glosa_amount: Amount denied

        Returns:
            Appeal strategy
        """
        # High value full denials always get comprehensive appeal
        if glosa_amount >= HIGH_PRIORITY_THRESHOLD:
            return AppealStrategy.COMPREHENSIVE_APPEAL

        if not glosa_reason:
            return AppealStrategy.COMPREHENSIVE_APPEAL

        strategy = self._determine_strategy_from_reason(glosa_reason)
        return strategy if strategy else AppealStrategy.COMPREHENSIVE_APPEAL

    def _determine_partial_denial_strategy(
        self,
        glosa_reason: Optional[str],
        glosa_amount: Decimal,
    ) -> AppealStrategy:
        """
        Determine strategy for partial denial glosas.

        Strategy mapping from migration spec:
        - Amount >= 5000 -> COMPREHENSIVE_APPEAL
        - DUPLICATE reason -> DUPLICATE_CLAIM_RESOLUTION (mapped to STANDARD_APPEAL)
        - BUNDLING/UNBUNDLING reason -> CODING_REVIEW_APPEAL
        - MODIFIER reason -> CODING_REVIEW_APPEAL
        - Default -> STANDARD_APPEAL

        Args:
            glosa_reason: Reason for denial
            glosa_amount: Amount denied

        Returns:
            Appeal strategy
        """
        if glosa_amount >= HIGH_PRIORITY_THRESHOLD:
            return AppealStrategy.COMPREHENSIVE_APPEAL

        if not glosa_reason:
            return AppealStrategy.STANDARD_APPEAL

        reason_upper = glosa_reason.upper()

        if "DUPLICATE" in reason_upper:
            return AppealStrategy.DUPLICATE_CLAIM_RESOLUTION
        elif "BUNDLING" in reason_upper or "UNBUNDLING" in reason_upper:
            return AppealStrategy.CODING_REVIEW_APPEAL
        elif "MODIFIER" in reason_upper:
            return AppealStrategy.MODIFIER_CORRECTION_APPEAL

        return AppealStrategy.STANDARD_APPEAL

    def _determine_strategy_from_reason(
        self,
        glosa_reason: str,
    ) -> Optional[AppealStrategy]:
        """
        Determine strategy from reason text.

        Args:
            glosa_reason: Reason text

        Returns:
            Appeal strategy or None if no match
        """
        reason_upper = glosa_reason.upper()

        if "AUTHORIZATION" in reason_upper or "PRE-AUTH" in reason_upper:
            return AppealStrategy.AUTHORIZATION_APPEAL
        elif "ELIGIBILITY" in reason_upper or "COVERAGE" in reason_upper:
            return AppealStrategy.ELIGIBILITY_VERIFICATION_APPEAL
        elif "CODING" in reason_upper or "PROCEDURE" in reason_upper:
            return AppealStrategy.CODING_REVIEW_APPEAL
        elif "MEDICAL NECESSITY" in reason_upper:
            return AppealStrategy.MEDICAL_NECESSITY_APPEAL
        elif "TIMELY" in reason_upper or "DEADLINE" in reason_upper:
            return AppealStrategy.TIMELY_FILING_APPEAL
        elif "DUPLICATE" in reason_upper:
            return AppealStrategy.DUPLICATE_CLAIM_RESOLUTION
        elif "BUNDLING" in reason_upper or "UNBUNDLING" in reason_upper:
            return AppealStrategy.CODING_REVIEW_APPEAL
        elif "MODIFIER" in reason_upper:
            return AppealStrategy.MODIFIER_CORRECTION_APPEAL

        return None

    def _determine_priority(
        self,
        glosa_type: GlosaType,
        glosa_amount: Decimal,
        bpmn_type: Optional[BpmnGlosaType] = None,
    ) -> Priority:
        """
        Determine priority level based on glosa characteristics.

        Priority rules from migration spec:
        - HIGH: Amount >= R$5000
        - MEDIUM: Amount >= R$1000 and < R$5000
        - LOW: Amount < R$1000
        - FULL_DENIAL: Always >= HIGH if >= R$1000, MEDIUM if < R$1000

        Args:
            glosa_type: Type of glosa
            glosa_amount: Amount denied
            bpmn_type: Optional BPMN process type

        Returns:
            Priority level
        """
        # FULL_DENIAL gets HIGH if >= R$1000, otherwise MEDIUM
        if bpmn_type == BpmnGlosaType.FULL_DENIAL:
            if glosa_amount >= MEDIUM_PRIORITY_THRESHOLD:
                return Priority.HIGH
            return Priority.MEDIUM

        # NO_GLOSA and OVERPAYMENT are typically low priority
        if bpmn_type in (BpmnGlosaType.NO_GLOSA, BpmnGlosaType.OVERPAYMENT):
            if glosa_amount >= HIGH_PRIORITY_THRESHOLD:
                return Priority.HIGH
            return Priority.LOW

        # Amount-based priority for other types (PARTIAL_DENIAL, UNDERPAYMENT, etc.)
        if glosa_amount >= HIGH_PRIORITY_THRESHOLD:
            return Priority.HIGH
        elif glosa_amount >= MEDIUM_PRIORITY_THRESHOLD:
            return Priority.MEDIUM
        else:
            return Priority.LOW

    def _assign_responsible(
        self,
        glosa_type: GlosaType,
        glosa_amount: Decimal,
        appeal_strategy: AppealStrategy,
    ) -> str:
        """
        Assign responsible team/person based on glosa characteristics.

        Team assignment rules from migration spec:
        - High value (>= R$5000) -> SENIOR_APPEALS_TEAM
        - Otherwise, specialized team based on strategy

        Args:
            glosa_type: Type of glosa
            glosa_amount: Amount denied
            appeal_strategy: Determined appeal strategy

        Returns:
            Assigned team name
        """
        # High value claims go to senior team
        if glosa_amount >= HIGH_PRIORITY_THRESHOLD:
            return AssignedTeam.SENIOR_APPEALS_TEAM.value

        # Map strategy to team
        strategy_team_map = {
            AppealStrategy.AUTHORIZATION_APPEAL: AssignedTeam.AUTHORIZATION_TEAM,
            AppealStrategy.ELIGIBILITY_VERIFICATION_APPEAL: AssignedTeam.ELIGIBILITY_TEAM,
            AppealStrategy.CODING_REVIEW_APPEAL: AssignedTeam.CODING_TEAM,
            AppealStrategy.MODIFIER_CORRECTION_APPEAL: AssignedTeam.CODING_TEAM,
            AppealStrategy.MEDICAL_NECESSITY_APPEAL: AssignedTeam.CLINICAL_APPEALS_TEAM,
            AppealStrategy.TIMELY_FILING_APPEAL: AssignedTeam.COMPLIANCE_TEAM,
            AppealStrategy.QUICK_REVIEW_AND_RESUBMIT: AssignedTeam.BILLING_TEAM,
            AppealStrategy.REFUND_PROCESSING: AssignedTeam.ACCOUNTING_TEAM,
            AppealStrategy.NO_ACTION_REQUIRED: AssignedTeam.NONE,
            AppealStrategy.DUPLICATE_CLAIM_RESOLUTION: AssignedTeam.BILLING_TEAM,
            AppealStrategy.COMPREHENSIVE_APPEAL: AssignedTeam.GENERAL_APPEALS_TEAM,
            AppealStrategy.STANDARD_APPEAL: AssignedTeam.GENERAL_APPEALS_TEAM,
        }

        team = strategy_team_map.get(appeal_strategy, AssignedTeam.GENERAL_APPEALS_TEAM)
        return team.value

    def _calculate_recovery_probability(
        self,
        glosa_type: GlosaType,
        appeal_strategy: AppealStrategy,
        glosa_amount: Decimal,
    ) -> int:
        """
        Calculate the probability of recovering the denied amount.

        This is a simplified heuristic. In production, this would
        use ML models trained on historical appeal outcomes.

        Args:
            glosa_type: Type of glosa
            appeal_strategy: Appeal strategy
            glosa_amount: Amount denied

        Returns:
            Recovery probability as percentage (0-100)
        """
        # Base probabilities by glosa type
        type_probabilities = {
            GlosaType.ADMINISTRATIVE: 70,
            GlosaType.DOCUMENTATION: 65,
            GlosaType.TECHNICAL: 60,
            GlosaType.BUNDLING: 55,
            GlosaType.MODIFIER: 60,
            GlosaType.DUPLICATE: 40,
            GlosaType.AUTHORIZATION: 45,
            GlosaType.ELIGIBILITY: 35,
            GlosaType.CLINICAL: 50,
            GlosaType.COVERAGE: 30,
        }

        base_probability = type_probabilities.get(glosa_type, 50)

        # Adjust for amount (higher amounts are harder to recover)
        if glosa_amount > DMN_CRITICAL_AMOUNT_THRESHOLD:
            base_probability -= 10
        elif glosa_amount < DMN_LOW_AMOUNT_THRESHOLD:
            base_probability += 5

        # Adjust for strategy (specialized strategies have better outcomes)
        strategy_adjustments = {
            AppealStrategy.COMPREHENSIVE_APPEAL: 10,
            AppealStrategy.MEDICAL_NECESSITY_APPEAL: 5,
            AppealStrategy.AUTHORIZATION_APPEAL: 5,
            AppealStrategy.NO_ACTION_REQUIRED: -base_probability,  # 0%
            AppealStrategy.REFUND_PROCESSING: -base_probability,  # 0%
        }
        base_probability += strategy_adjustments.get(appeal_strategy, 0)

        # Clamp to valid range
        return max(0, min(100, base_probability))

    def _calculate_deadline_days(
        self,
        glosa_source: GlosaSource,
        glosa_amount: Decimal,
        days_since_occurrence: int,
    ) -> int:
        """
        Calculate the number of days until appeal deadline.

        Deadline rules based on Brazilian healthcare regulations:
        - ANS/REGULATORY: 30 days from identification
        - INSURANCE: 60 days from identification
        - AUDIT: 90 days from identification
        - High value claims may have extended deadlines

        Args:
            glosa_source: Source of glosa identification
            glosa_amount: Amount of glosa
            days_since_occurrence: Days since glosa was identified

        Returns:
            Days remaining until deadline
        """
        # Base deadline by source
        source_deadlines = {
            GlosaSource.ANS: 30,
            GlosaSource.REGULATORY: 30,
            GlosaSource.INSURANCE: 60,
            GlosaSource.AUDIT: 90,
            GlosaSource.INTERNAL: 90,
        }

        base_deadline = source_deadlines.get(glosa_source, 60)

        # High value claims may have extended deadline
        if glosa_amount >= DMN_CRITICAL_AMOUNT_THRESHOLD:
            base_deadline += 30

        # Calculate remaining days
        remaining_days = max(0, base_deadline - days_since_occurrence)

        return remaining_days

    def _requires_legal_action(
        self,
        glosa_source: GlosaSource,
        glosa_amount: Decimal,
        days_since_occurrence: int,
    ) -> bool:
        """
        Determine if legal action is required.

        Legal action rules from migration spec:
        - ANS/REGULATORY source with amount > R$5000 and days > 90 -> Legal required
        - Amount > R$10000 and days > 60 -> Consider legal

        Args:
            glosa_source: Source of glosa identification
            glosa_amount: Amount of glosa
            days_since_occurrence: Days since identification

        Returns:
            True if legal action is required
        """
        # Regulatory sources with high value and long duration
        if glosa_source in (GlosaSource.ANS, GlosaSource.REGULATORY):
            if glosa_amount > HIGH_PRIORITY_THRESHOLD and days_since_occurrence > 90:
                return True

        # Critical amount with extended duration
        if glosa_amount > DMN_CRITICAL_AMOUNT_THRESHOLD and days_since_occurrence > 60:
            return True

        return False

    async def _invoke_dmn(
        self,
        glosa_type: GlosaType,
        glosa_source: GlosaSource,
        glosa_amount: Decimal,
        has_documentation: bool,
        days_since_occurrence: int,
    ) -> Optional[dict[str, Any]]:
        """
        Invoke DMN decision table for enhanced classification.

        Uses the glosa-classification.dmn decision table with inputs:
        - glosaType (mapped to DMN format)
        - glosaSource
        - glosaAmount
        - hasDocumentation
        - daysSinceOccurrence

        Args:
            glosa_type: Domain glosa type
            glosa_source: Glosa source
            glosa_amount: Amount
            has_documentation: Documentation availability
            days_since_occurrence: Days since occurrence

        Returns:
            DMN evaluation result or None if evaluation fails
        """
        if not self._dmn_service:
            return None

        try:
            # Map domain type to DMN expected format
            dmn_type = self._map_domain_type_to_dmn(glosa_type)

            variables = {
                "glosaType": dmn_type,
                "glosaSource": glosa_source.value,
                "glosaAmount": float(glosa_amount),
                "hasDocumentation": has_documentation,
                "daysSinceOccurrence": days_since_occurrence,
            }

            self._logger.debug(
                "Invoking DMN decision table",
                decision_key="glosa-classification",
                variables=variables,
            )

            result = await self._dmn_service.evaluate("glosa-classification", variables)
            return result

        except Exception as e:
            self._logger.warning(
                "DMN evaluation failed, using programmatic classification",
                error=str(e),
            )
            return None

    def _map_domain_type_to_dmn(self, glosa_type: GlosaType) -> str:
        """
        Map domain GlosaType to DMN expected values.

        DMN expects: ADMINISTRATIVE, CLINICAL, TECHNICAL, COVERAGE, DOCUMENTATION

        Args:
            glosa_type: Domain glosa type

        Returns:
            DMN-compatible type string
        """
        # Most domain types map directly to DMN types
        direct_mapping = {
            GlosaType.ADMINISTRATIVE: "ADMINISTRATIVE",
            GlosaType.CLINICAL: "CLINICAL",
            GlosaType.TECHNICAL: "TECHNICAL",
            GlosaType.COVERAGE: "COVERAGE",
            GlosaType.DOCUMENTATION: "DOCUMENTATION",
        }

        if glosa_type in direct_mapping:
            return direct_mapping[glosa_type]

        # Map other types to closest DMN equivalent
        technical_types = {GlosaType.BUNDLING, GlosaType.MODIFIER, GlosaType.DUPLICATE}
        if glosa_type in technical_types:
            return "TECHNICAL"

        authorization_types = {GlosaType.AUTHORIZATION, GlosaType.ELIGIBILITY}
        if glosa_type in authorization_types:
            return "COVERAGE"

        return "ADMINISTRATIVE"

    def _merge_dmn_results(
        self,
        output: AnalyzeGlosaOutput,
        dmn_result: dict[str, Any],
    ) -> AnalyzeGlosaOutput:
        """
        Merge DMN results into output, overriding programmatic values.

        DMN outputs:
        - appealPriority: CRITICAL, HIGH, MEDIUM, LOW, DO_NOT_APPEAL
        - appealStrategy: IMMEDIATE_DOCUMENTATION, CLINICAL_REVIEW, etc.
        - recoveryProbability: 0-100
        - deadlineDays: integer
        - requiresLegal: boolean

        Args:
            output: Current output model
            dmn_result: DMN evaluation result

        Returns:
            Updated output model
        """
        output_dict = output.model_dump(by_alias=True)

        # Map DMN strategy if present
        if dmn_strategy := dmn_result.get("appealStrategy"):
            try:
                # Try to map DMN strategy to our AppealStrategy enum
                strategy = AppealStrategy(dmn_strategy)
                output_dict["appealStrategy"] = strategy.value
            except ValueError:
                # Map DMN-specific strategies
                dmn_strategy_map = {
                    "IMMEDIATE_DOCUMENTATION": AppealStrategy.COMPREHENSIVE_APPEAL.value,
                    "CLINICAL_REVIEW": AppealStrategy.MEDICAL_NECESSITY_APPEAL.value,
                    "LEGAL_APPEAL": AppealStrategy.COMPREHENSIVE_APPEAL.value,
                    "NEGOTIATION": AppealStrategy.STANDARD_APPEAL.value,
                    "ACCEPT_GLOSA": AppealStrategy.NO_ACTION_REQUIRED.value,
                }
                output_dict["appealStrategy"] = dmn_strategy_map.get(
                    dmn_strategy, output_dict["appealStrategy"]
                )

        # Map DMN priority if present
        if dmn_priority := dmn_result.get("appealPriority"):
            priority_map = {
                "CRITICAL": Priority.HIGH.value,
                "HIGH": Priority.HIGH.value,
                "MEDIUM": Priority.MEDIUM.value,
                "LOW": Priority.LOW.value,
                "DO_NOT_APPEAL": Priority.LOW.value,
            }
            output_dict["priority"] = priority_map.get(
                dmn_priority, output_dict["priority"]
            )

        # Merge numeric/boolean fields
        if "recoveryProbability" in dmn_result:
            output_dict["recoveryProbability"] = dmn_result["recoveryProbability"]
        if "deadlineDays" in dmn_result:
            output_dict["deadlineDays"] = dmn_result["deadlineDays"]
        if "requiresLegal" in dmn_result:
            output_dict["requiresLegal"] = dmn_result["requiresLegal"]

        return AnalyzeGlosaOutput(**output_dict)

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """
        Extract parameters for idempotency key generation.

        For glosa analysis, use glosaType, glosaAmount, and process instance.

        Args:
            variables: Job variables

        Returns:
            String representation of key parameters
        """
        glosa_type = variables.get("glosaType", "")
        glosa_amount = variables.get("glosaAmount", "0")
        process_instance = variables.get("processInstanceKey", "")
        return f"{process_instance}:{glosa_type}:{glosa_amount}"
