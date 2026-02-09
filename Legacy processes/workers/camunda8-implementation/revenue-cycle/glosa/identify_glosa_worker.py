"""
IdentifyGlosaWorker - Analyzes claim denials to identify root causes.

This worker performs deep analysis of glosa (claim denial) patterns to identify
root causes, suggest corrective actions, and recommend prevention strategies.

Migrated from Java IdentifyGlosaDelegate.
Topic: identify-glosa
BPMN Task: Task_Identify_Glosa_RootCauses
Business Rule: RN-GLOSA-005-IdentifyGlosa.md
Regulatory Compliance: ANS RN 424/2017 (appeal documentation)

Input Variables:
    claimId (str): Claim identifier (required)
    denialCode (str): Denial code from insurance/audit (required)
    denialDescription (str, optional): Human-readable denial reason
    clinicalData (dict, optional): Clinical context data
    chargeCode (str, optional): Specific charge code denied
    patientDiagnosis (str, optional): Patient diagnosis codes
    procedureCode (str, optional): CPT/medical procedure codes
    tenantId (str, optional): Multi-tenant identifier

Output Variables:
    rootCauses (list[str]): Identified root causes for the denial
    rootCauseCategories (list[str]): Categorized root cause types
    suggestedActions (list[dict]): List of suggested corrective actions
    preventionRecommendations (list[str]): Future prevention strategies
    denialAnalysisId (str): Unique identifier for this analysis
    confidenceScore (float): Confidence in root cause identification (0-1)
    requiresReview (bool): Whether manual review is recommended
    analysisDate (str): ISO format timestamp of analysis
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

import structlog
from pydantic import BaseModel, Field, ConfigDict, field_validator

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


# ============================================================================
# Root Cause Categories and Denial Code Mappings
# ============================================================================

class RootCauseCategory(str, Enum):
    """Categories of root causes for claim denials."""
    CLINICAL = "CLINICAL"
    ADMINISTRATIVE = "ADMINISTRATIVE"
    CODING = "CODING"
    ELIGIBILITY = "ELIGIBILITY"
    AUTHORIZATION = "AUTHORIZATION"
    DOCUMENTATION = "DOCUMENTATION"
    BILLING = "BILLING"
    REGULATORY = "REGULATORY"
    BUNDLING = "BUNDLING"
    DUPLICATE = "DUPLICATE"


class SuggestedActionType(str, Enum):
    """Types of suggested corrective actions."""
    RESUBMIT = "RESUBMIT"
    AMEND_CLAIM = "AMEND_CLAIM"
    REQUEST_MEDICAL_RECORDS = "REQUEST_MEDICAL_RECORDS"
    APPEAL = "APPEAL"
    TRAINING = "TRAINING"
    PROCESS_IMPROVEMENT = "PROCESS_IMPROVEMENT"
    SYSTEM_CORRECTION = "SYSTEM_CORRECTION"
    PATIENT_CONTACT = "PATIENT_CONTACT"
    INSURANCE_CLARIFICATION = "INSURANCE_CLARIFICATION"
    MANAGEMENT_REVIEW = "MANAGEMENT_REVIEW"


# Mapping of denial codes to root causes
DENIAL_CODE_ROOT_CAUSES = {
    # Eligibility denials
    "INELIGIBLE_PATIENT": [RootCauseCategory.ELIGIBILITY],
    "COVERAGE_TERMINATED": [RootCauseCategory.ELIGIBILITY, RootCauseCategory.ADMINISTRATIVE],
    "PRE_AUTH_REQUIRED": [RootCauseCategory.AUTHORIZATION],
    "PRE_AUTH_EXPIRED": [RootCauseCategory.AUTHORIZATION],
    "PRE_AUTH_NOT_PROVIDED": [RootCauseCategory.AUTHORIZATION],
    # Medical necessity denials
    "NOT_MEDICALLY_NECESSARY": [RootCauseCategory.CLINICAL],
    "EXPERIMENTAL_TREATMENT": [RootCauseCategory.CLINICAL],
    "TREATMENT_PLAN_EXCEEDED": [RootCauseCategory.CLINICAL],
    # Coding denials
    "INVALID_PROCEDURE_CODE": [RootCauseCategory.CODING],
    "INVALID_DIAGNOSIS_CODE": [RootCauseCategory.CODING],
    "INVALID_MODIFIER": [RootCauseCategory.CODING],
    "UNLISTED_PROCEDURE": [RootCauseCategory.CODING],
    # Bundling/Unbundling denials
    "BUNDLED_CHARGES": [RootCauseCategory.BUNDLING],
    "UNBUNDLING_NOT_ALLOWED": [RootCauseCategory.BUNDLING],
    "UNBUNDLED_PROCEDURE": [RootCauseCategory.BUNDLING],
    # Duplicate denials
    "DUPLICATE_CLAIM": [RootCauseCategory.DUPLICATE],
    "DUPLICATE_SERVICE": [RootCauseCategory.DUPLICATE],
    "CLAIM_ALREADY_PAID": [RootCauseCategory.DUPLICATE],
    # Documentation denials
    "INSUFFICIENT_DOCUMENTATION": [RootCauseCategory.DOCUMENTATION],
    "MISSING_MEDICAL_RECORDS": [RootCauseCategory.DOCUMENTATION],
    "MISSING_SIGNATURE": [RootCauseCategory.DOCUMENTATION],
    # Administrative denials
    "TIMELY_FILING_EXCEEDED": [RootCauseCategory.ADMINISTRATIVE],
    "MISSING_REQUIRED_FIELD": [RootCauseCategory.ADMINISTRATIVE],
    "INVALID_PROVIDER_ID": [RootCauseCategory.ADMINISTRATIVE],
    "INVALID_SUBSCRIBER_ID": [RootCauseCategory.ADMINISTRATIVE],
    # Billing denials
    "CHARGE_EXCEEDS_LIMIT": [RootCauseCategory.BILLING],
    "PAYMENT_RULE_VIOLATION": [RootCauseCategory.BILLING],
    "EXCEEDS_ANNUAL_BENEFIT": [RootCauseCategory.BILLING],
}


# Prevention recommendations by category
PREVENTION_STRATEGIES = {
    RootCauseCategory.ELIGIBILITY: [
        "Verify patient eligibility before service delivery",
        "Implement real-time eligibility check system",
        "Train front-desk staff on coverage verification",
        "Maintain current insurance plan database",
        "Implement automatic coverage confirmation workflow",
    ],
    RootCauseCategory.AUTHORIZATION: [
        "Implement pre-authorization workflow for all required services",
        "Train staff on pre-authorization requirements",
        "Use automated pre-auth decision engine",
        "Monitor pre-auth expiration dates",
        "Implement escalation for pre-auth denials",
    ],
    RootCauseCategory.CLINICAL: [
        "Ensure clinical documentation supports medical necessity",
        "Implement evidence-based clinical guidelines",
        "Regular provider training on clinical requirements",
        "Peer review of high-risk clinical decisions",
        "Maintain updated clinical guidelines",
    ],
    RootCauseCategory.CODING: [
        "Implement quarterly coding audits",
        "Provide regular coding staff training",
        "Use automated coding validation tools",
        "Maintain current CPT/ICD code references",
        "Implement coding quality assurance program",
    ],
    RootCauseCategory.DOCUMENTATION: [
        "Implement electronic health record (EHR) templates",
        "Require complete documentation before claim submission",
        "Train staff on documentation standards",
        "Implement document completeness validation",
        "Regular audits of medical record documentation",
    ],
    RootCauseCategory.ADMINISTRATIVE: [
        "Implement claim form completeness check",
        "Use automated claim validation rules",
        "Train billing staff on claim requirements",
        "Implement timely filing deadline tracking",
        "Regular audits of administrative processes",
    ],
    RootCauseCategory.BUNDLING: [
        "Implement bundling rule engine",
        "Regular training on bundling rules",
        "Use coding software that identifies bundling",
        "Maintain updated bundling reference materials",
        "Implement bundling validation before submission",
    ],
    RootCauseCategory.DUPLICATE: [
        "Implement duplicate claim detection system",
        "Regular audits for duplicate submissions",
        "Use claim transaction database for lookups",
        "Implement automated duplicate checking",
        "Staff training on duplicate prevention",
    ],
}


# ============================================================================
# Pydantic Models
# ============================================================================


class SuggestedAction(BaseModel):
    """Model for a suggested corrective action."""
    model_config = ConfigDict(populate_by_name=True)

    action_type: SuggestedActionType = Field(..., alias="actionType")
    description: str
    priority: str = Field(default="MEDIUM")  # HIGH, MEDIUM, LOW
    estimated_cost: Optional[Decimal] = Field(None, alias="estimatedCost")
    implementation_steps: list[str] = Field(
        default_factory=list,
        alias="implementationSteps"
    )
    owner: Optional[str] = None


class IdentifyGlosaInput(BaseModel):
    """Input model for glosa root cause analysis."""
    model_config = ConfigDict(populate_by_name=True)

    claim_id: str = Field(..., alias="claimId")
    denial_code: str = Field(..., alias="denialCode")
    denial_description: Optional[str] = Field(
        None,
        alias="denialDescription",
        description="Human-readable denial reason"
    )
    clinical_data: Optional[dict[str, Any]] = Field(
        None,
        alias="clinicalData",
        description="Clinical context data"
    )
    charge_code: Optional[str] = Field(None, alias="chargeCode")
    patient_diagnosis: Optional[str] = Field(None, alias="patientDiagnosis")
    procedure_code: Optional[str] = Field(None, alias="procedureCode")
    tenant_id: Optional[str] = Field(None, alias="tenantId")

    @field_validator('denial_code', mode='before')
    @classmethod
    def normalize_denial_code(cls, v):
        """Normalize denial code to uppercase."""
        if isinstance(v, str):
            return v.upper().strip()
        return v


class IdentifyGlosaOutput(BaseModel):
    """Output model for glosa root cause analysis."""
    model_config = ConfigDict(populate_by_name=True)

    denial_analysis_id: str = Field(..., alias="denialAnalysisId")
    claim_id: str = Field(..., alias="claimId")
    root_causes: list[str] = Field(..., alias="rootCauses")
    root_cause_categories: list[str] = Field(..., alias="rootCauseCategories")
    suggested_actions: list[dict[str, Any]] = Field(..., alias="suggestedActions")
    prevention_recommendations: list[str] = Field(
        ...,
        alias="preventionRecommendations"
    )
    confidence_score: float = Field(
        ...,
        alias="confidenceScore",
        ge=0.0,
        le=1.0
    )
    requires_review: bool = Field(..., alias="requiresReview")
    analysis_date: str = Field(..., alias="analysisDate")


# ============================================================================
# Worker Implementation
# ============================================================================


@worker(
    topic="identify-glosa",
    max_jobs=10,
    lock_duration=60000,  # 1 minute
)
class IdentifyGlosaWorker(BaseWorker):
    """
    Worker for identifying glosa root causes and recommending corrective actions.

    Responsibilities:
    - Analyze denial code to identify root cause categories
    - Review clinical data for medical necessity issues
    - Check for coding/documentation problems
    - Generate suggested corrective actions
    - Identify prevention strategies
    - Calculate confidence score for analysis

    Business Logic:
    1. VALIDATE input data
    2. LOOK UP root causes for denial code
    3. ANALYZE clinical data if available
    4. GENERATE suggested actions based on root causes
    5. COMPILE prevention recommendations
    6. CALCULATE confidence score
    7. DETERMINE if manual review needed
    8. RETURN analysis results
    """

    def __init__(self, settings=None, **kwargs):
        """
        Initialize the worker.

        Args:
            settings: Application settings
            **kwargs: Additional arguments for BaseWorker
        """
        super().__init__(settings=settings)

    @property
    def operation_name(self) -> str:
        return "identify_glosa_root_causes"

    @property
    def requires_idempotency(self) -> bool:
        # Analysis is deterministic - same inputs produce same outputs
        return False

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Execute the glosa root cause identification.

        Args:
            job: Camunda external task
            variables: Job variables

        Returns:
            WorkerResult with root causes and recommendations
        """
        self._logger.info(
            "Starting glosa root cause analysis",
            business_key=variables.get("businessKey"),
            claim_id=variables.get("claimId"),
        )

        # 1. Extract and validate input
        claim_id = self.get_required_variable(variables, "claimId", str)
        denial_code = self.get_required_variable(variables, "denialCode", str)
        denial_description = self.get_variable(
            variables, "denialDescription", str
        )
        clinical_data = self.get_variable(
            variables, "clinicalData", dict, {}
        )
        charge_code = self.get_variable(variables, "chargeCode", str)
        patient_diagnosis = self.get_variable(variables, "patientDiagnosis", str)
        procedure_code = self.get_variable(variables, "procedureCode", str)

        # Normalize denial code
        denial_code_upper = denial_code.upper().strip()

        # 2. Look up root causes for denial code
        root_cause_categories = self._get_root_causes_for_code(denial_code_upper)

        # 3. Analyze clinical data for additional context
        clinical_issues = self._analyze_clinical_data(
            clinical_data,
            patient_diagnosis,
            procedure_code,
        )
        if clinical_issues:
            root_cause_categories.extend(clinical_issues)

        # Remove duplicates while preserving order
        root_cause_categories = list(dict.fromkeys(root_cause_categories))

        # 4. Generate root cause descriptions
        root_causes = self._generate_root_cause_descriptions(
            root_cause_categories,
            denial_code_upper,
            denial_description,
        )

        # 5. Generate suggested actions
        suggested_actions = self._generate_suggested_actions(
            root_cause_categories,
            denial_code_upper,
            claim_id,
        )

        # 6. Compile prevention recommendations
        prevention_recommendations = self._compile_prevention_strategies(
            root_cause_categories
        )

        # 7. Calculate confidence score
        confidence_score = self._calculate_confidence_score(
            denial_code_upper,
            clinical_data,
            root_cause_categories,
        )

        # 8. Determine if review needed
        requires_review = confidence_score < 0.7 or len(root_cause_categories) > 2

        # 9. Generate analysis ID
        analysis_id = f"DEN-ANALYSIS-{claim_id}-{datetime.utcnow().timestamp():.0f}"

        # 10. Build output
        output = IdentifyGlosaOutput(
            denial_analysis_id=analysis_id,
            claim_id=claim_id,
            root_causes=root_causes,
            root_cause_categories=root_cause_categories,
            suggested_actions=[
                action.model_dump(by_alias=True, exclude_none=True)
                for action in suggested_actions
            ],
            prevention_recommendations=prevention_recommendations,
            confidence_score=confidence_score,
            requires_review=requires_review,
            analysis_date=datetime.utcnow().isoformat(),
        )

        self._logger.info(
            "Glosa analysis complete",
            claim_id=claim_id,
            root_causes=root_causes,
            confidence_score=confidence_score,
            requires_review=requires_review,
        )

        return WorkerResult.ok(output.model_dump(by_alias=True, exclude_none=True))

    def _get_root_causes_for_code(
        self,
        denial_code: str,
    ) -> list[str]:
        """
        Look up root cause categories for a denial code.

        Args:
            denial_code: Denial code from insurance/audit

        Returns:
            List of root cause category strings
        """
        # Direct mapping
        if denial_code in DENIAL_CODE_ROOT_CAUSES:
            categories = DENIAL_CODE_ROOT_CAUSES[denial_code]
            return [cat.value for cat in categories]

        # Fallback: check if code contains keywords
        code_upper = denial_code.upper()

        if "ELIGIBILITY" in code_upper or "COVERAGE" in code_upper:
            return [RootCauseCategory.ELIGIBILITY.value]
        elif "AUTH" in code_upper or "PREAUTH" in code_upper:
            return [RootCauseCategory.AUTHORIZATION.value]
        elif "MEDICAL" in code_upper or "NECESSARY" in code_upper:
            return [RootCauseCategory.CLINICAL.value]
        elif "CODE" in code_upper or "CPT" in code_upper or "ICD" in code_upper:
            return [RootCauseCategory.CODING.value]
        elif "BUNDLE" in code_upper or "UNBUNDLE" in code_upper:
            return [RootCauseCategory.BUNDLING.value]
        elif "DUPLICATE" in code_upper:
            return [RootCauseCategory.DUPLICATE.value]
        elif "DOCUMENTATION" in code_upper or "RECORDS" in code_upper:
            return [RootCauseCategory.DOCUMENTATION.value]
        else:
            # Default to administrative
            return [RootCauseCategory.ADMINISTRATIVE.value]

    def _analyze_clinical_data(
        self,
        clinical_data: dict[str, Any],
        patient_diagnosis: Optional[str],
        procedure_code: Optional[str],
    ) -> list[str]:
        """
        Analyze clinical data for additional root cause indicators.

        Args:
            clinical_data: Clinical context data
            patient_diagnosis: Patient diagnosis codes
            procedure_code: Procedure codes

        Returns:
            Additional root cause categories identified
        """
        additional_causes: list[str] = []

        if not clinical_data:
            return additional_causes

        # Check for missing clinical documentation
        if clinical_data.get("missing_documentation", False):
            additional_causes.append(RootCauseCategory.DOCUMENTATION.value)

        # Check for medical necessity issues
        if clinical_data.get("justification_missing", False):
            additional_causes.append(RootCauseCategory.CLINICAL.value)

        # Check for clinical guideline violations
        if clinical_data.get("guideline_violation", False):
            additional_causes.append(RootCauseCategory.CLINICAL.value)

        # Check for experimental treatment
        if clinical_data.get("experimental_treatment", False):
            additional_causes.append(RootCauseCategory.CLINICAL.value)

        return additional_causes

    def _generate_root_cause_descriptions(
        self,
        root_cause_categories: list[str],
        denial_code: str,
        denial_description: Optional[str],
    ) -> list[str]:
        """
        Generate human-readable root cause descriptions.

        Args:
            root_cause_categories: List of root cause category strings
            denial_code: Original denial code
            denial_description: Optional human-readable description

        Returns:
            List of root cause descriptions
        """
        descriptions: list[str] = []

        category_descriptions = {
            RootCauseCategory.ELIGIBILITY.value: "Patient eligibility issue",
            RootCauseCategory.AUTHORIZATION.value: "Pre-authorization requirement not met",
            RootCauseCategory.CLINICAL.value: "Clinical justification or medical necessity issue",
            RootCauseCategory.CODING.value: "Coding error or invalid codes",
            RootCauseCategory.BUNDLING.value: "Bundling or unbundling issue",
            RootCauseCategory.DUPLICATE.value: "Duplicate claim or service",
            RootCauseCategory.DOCUMENTATION.value: "Missing or insufficient documentation",
            RootCauseCategory.ADMINISTRATIVE.value: "Administrative or billing issue",
            RootCauseCategory.BILLING.value: "Billing rule violation",
            RootCauseCategory.REGULATORY.value: "Regulatory compliance issue",
        }

        for category in root_cause_categories:
            if category in category_descriptions:
                descriptions.append(category_descriptions[category])

        # Add denial description if provided
        if denial_description:
            descriptions.append(f"Denial reason: {denial_description}")

        return descriptions if descriptions else [f"Denial code: {denial_code}"]

    def _generate_suggested_actions(
        self,
        root_cause_categories: list[str],
        denial_code: str,
        claim_id: str,
    ) -> list[SuggestedAction]:
        """
        Generate suggested corrective actions based on root causes.

        Args:
            root_cause_categories: Root cause categories
            denial_code: Original denial code
            claim_id: Claim identifier

        Returns:
            List of suggested actions
        """
        actions: list[SuggestedAction] = []

        # Eligibility issues
        if RootCauseCategory.ELIGIBILITY.value in root_cause_categories:
            actions.append(SuggestedAction(
                action_type=SuggestedActionType.REQUEST_MEDICAL_RECORDS,
                description="Verify patient eligibility status with insurance",
                priority="HIGH",
                implementation_steps=[
                    "Contact insurance carrier",
                    "Verify current plan coverage",
                    "Confirm patient enrollment status",
                ],
            ))

        # Authorization issues
        if RootCauseCategory.AUTHORIZATION.value in root_cause_categories:
            actions.append(SuggestedAction(
                action_type=SuggestedActionType.INSURANCE_CLARIFICATION,
                description="Obtain required pre-authorization",
                priority="HIGH",
                implementation_steps=[
                    "Submit pre-authorization request",
                    "Monitor approval status",
                    "Resubmit claim after approval",
                ],
            ))

        # Coding issues
        if RootCauseCategory.CODING.value in root_cause_categories:
            actions.append(SuggestedAction(
                action_type=SuggestedActionType.AMEND_CLAIM,
                description="Correct coding errors and resubmit",
                priority="HIGH",
                implementation_steps=[
                    "Review claim codes",
                    "Correct invalid codes",
                    "Resubmit amended claim",
                ],
            ))

        # Documentation issues
        if RootCauseCategory.DOCUMENTATION.value in root_cause_categories:
            actions.append(SuggestedAction(
                action_type=SuggestedActionType.REQUEST_MEDICAL_RECORDS,
                description="Gather and submit supporting documentation",
                priority="MEDIUM",
                implementation_steps=[
                    "Request medical records from provider",
                    "Attach to appeal",
                    "Resubmit claim",
                ],
            ))

        # Clinical issues
        if RootCauseCategory.CLINICAL.value in root_cause_categories:
            actions.append(SuggestedAction(
                action_type=SuggestedActionType.APPEAL,
                description="File medical necessity appeal",
                priority="MEDIUM",
                implementation_steps=[
                    "Prepare clinical justification",
                    "Submit appeal with evidence",
                    "Follow up on appeal status",
                ],
            ))

        # If no specific actions, suggest appeal
        if not actions:
            actions.append(SuggestedAction(
                action_type=SuggestedActionType.APPEAL,
                description="File general appeal of denial",
                priority="MEDIUM",
                implementation_steps=[
                    "Prepare appeal documentation",
                    "Submit within deadline",
                    "Track appeal status",
                ],
            ))

        return actions

    def _compile_prevention_strategies(
        self,
        root_cause_categories: list[str],
    ) -> list[str]:
        """
        Compile prevention recommendations based on root causes.

        Args:
            root_cause_categories: Root cause categories

        Returns:
            List of prevention strategy recommendations
        """
        recommendations: set[str] = set()

        for category in root_cause_categories:
            if category in PREVENTION_STRATEGIES:
                strategies = PREVENTION_STRATEGIES[category]
                recommendations.update(strategies)

        return sorted(list(recommendations))

    def _calculate_confidence_score(
        self,
        denial_code: str,
        clinical_data: dict[str, Any],
        root_cause_categories: list[str],
    ) -> float:
        """
        Calculate confidence score for root cause analysis.

        Args:
            denial_code: Original denial code
            clinical_data: Clinical context data
            root_cause_categories: Identified root cause categories

        Returns:
            Confidence score (0-1)
        """
        score = 0.5  # Base score

        # Boost for known denial codes
        if denial_code in DENIAL_CODE_ROOT_CAUSES:
            score += 0.3

        # Boost for multiple data sources
        if clinical_data:
            score += 0.1

        # Slight reduction for multiple root causes (harder to pinpoint)
        if len(root_cause_categories) > 2:
            score -= 0.05

        # Cap score at 0.95 (to avoid false certainty)
        return min(0.95, max(0.0, score))

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """
        Extract parameters for idempotency key generation.

        Args:
            variables: Job variables

        Returns:
            String representation of key parameters
        """
        claim_id = variables.get("claimId", "")
        denial_code = variables.get("denialCode", "")
        process_instance = variables.get("processInstanceKey", "")
        return f"{process_instance}:{claim_id}:{denial_code}"
