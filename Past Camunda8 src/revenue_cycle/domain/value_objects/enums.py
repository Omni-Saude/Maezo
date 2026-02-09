"""
Domain enumerations for Hospital Revenue Cycle.

These enums represent domain concepts that have a fixed set of values.
They provide type safety and documentation for domain logic.
"""

from enum import Enum, auto


class GlosaType(str, Enum):
    """
    Types of glosa (claim denial) in the Brazilian healthcare system.

    Based on TISS (Troca de Informacoes em Saude Suplementar) standards.

    Attributes:
        ADMINISTRATIVE: Administrative denial (missing documentation, late submission)
        CLINICAL: Clinical denial (medical necessity, inappropriate treatment)
        TECHNICAL: Technical denial (coding errors, wrong procedure codes)
        COVERAGE: Coverage denial (not covered by plan, exclusions)
        DOCUMENTATION: Documentation denial (incomplete medical records)
        DUPLICATE: Duplicate claim submission
        AUTHORIZATION: Missing or invalid prior authorization
        ELIGIBILITY: Patient eligibility issues
        BUNDLING: Unbundling/bundling coding issues
        MODIFIER: Incorrect modifier usage
    """

    ADMINISTRATIVE = "ADMINISTRATIVE"
    CLINICAL = "CLINICAL"
    TECHNICAL = "TECHNICAL"
    COVERAGE = "COVERAGE"
    DOCUMENTATION = "DOCUMENTATION"
    DUPLICATE = "DUPLICATE"
    AUTHORIZATION = "AUTHORIZATION"
    ELIGIBILITY = "ELIGIBILITY"
    BUNDLING = "BUNDLING"
    MODIFIER = "MODIFIER"

    @classmethod
    def from_tiss_code(cls, code: str) -> "GlosaType":
        """
        Map TISS glosa codes to GlosaType.

        Args:
            code: TISS glosa code (e.g., "A001", "C002")

        Returns:
            Corresponding GlosaType

        Raises:
            ValueError: If code is not recognized
        """
        code_mapping = {
            # Administrative codes (A series)
            "A001": cls.ADMINISTRATIVE,
            "A002": cls.DOCUMENTATION,
            "A003": cls.AUTHORIZATION,
            # Clinical codes (C series)
            "C001": cls.CLINICAL,
            "C002": cls.CLINICAL,
            # Technical codes (T series)
            "T001": cls.TECHNICAL,
            "T002": cls.BUNDLING,
            "T003": cls.MODIFIER,
            # Coverage codes (V series)
            "V001": cls.COVERAGE,
            "V002": cls.ELIGIBILITY,
            # Duplicate (D series)
            "D001": cls.DUPLICATE,
        }

        if code in code_mapping:
            return code_mapping[code]

        # Default mapping by first letter
        prefix = code[0].upper() if code else ""
        prefix_mapping = {
            "A": cls.ADMINISTRATIVE,
            "C": cls.CLINICAL,
            "T": cls.TECHNICAL,
            "V": cls.COVERAGE,
            "D": cls.DUPLICATE,
        }

        return prefix_mapping.get(prefix, cls.ADMINISTRATIVE)


class GlosaStatus(str, Enum):
    """
    Status of a glosa (claim denial) in the appeal process.

    Attributes:
        PENDING: Glosa identified, not yet analyzed
        IN_ANALYSIS: Being analyzed by appeals team
        IN_APPEAL: Appeal submitted to payer
        ACCEPTED: Glosa accepted (no appeal possible or appeal denied)
        REVERSED: Glosa reversed (appeal successful)
        PARTIAL_REVERSED: Partially reversed
        WRITE_OFF: Written off as uncollectable
    """

    PENDING = "PENDING"
    IN_ANALYSIS = "IN_ANALYSIS"
    IN_APPEAL = "IN_APPEAL"
    ACCEPTED = "ACCEPTED"
    REVERSED = "REVERSED"
    PARTIAL_REVERSED = "PARTIAL_REVERSED"
    WRITE_OFF = "WRITE_OFF"


class Priority(str, Enum):
    """
    Priority levels for task processing.

    Used to determine processing order and SLA requirements.

    Attributes:
        CRITICAL: Immediate attention required (regulatory deadlines)
        HIGH: High priority (large amounts, aging claims)
        MEDIUM: Standard priority
        LOW: Low priority (small amounts, routine items)
    """

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

    @property
    def sla_hours(self) -> int:
        """Get the SLA in hours for this priority level."""
        sla_mapping = {
            Priority.CRITICAL: 4,
            Priority.HIGH: 24,
            Priority.MEDIUM: 72,
            Priority.LOW: 168,  # 7 days
        }
        return sla_mapping[self]

    @classmethod
    def from_amount(cls, amount_value: float) -> "Priority":
        """
        Determine priority based on monetary amount.

        Args:
            amount_value: Amount in BRL

        Returns:
            Appropriate priority level
        """
        if amount_value >= 10000.0:
            return cls.CRITICAL
        elif amount_value >= 5000.0:
            return cls.HIGH
        elif amount_value >= 1000.0:
            return cls.MEDIUM
        else:
            return cls.LOW


class AppealStrategy(str, Enum):
    """
    Strategies for appealing claim denials.

    Based on denial type and historical success rates.

    Attributes:
        COMPREHENSIVE_APPEAL: Full appeal with all documentation
        AUTHORIZATION_APPEAL: Focus on authorization issues
        ELIGIBILITY_VERIFICATION_APPEAL: Focus on eligibility verification
        CODING_REVIEW_APPEAL: Focus on coding corrections
        MEDICAL_NECESSITY_APPEAL: Clinical appeal with peer-to-peer
        TIMELY_FILING_APPEAL: Focus on timely filing exceptions
        DUPLICATE_CLAIM_RESOLUTION: Resolve duplicate claim issues
        MODIFIER_CORRECTION_APPEAL: Focus on modifier corrections
        QUICK_REVIEW_AND_RESUBMIT: Simple resubmission
        STANDARD_APPEAL: Standard appeal process
        REFUND_PROCESSING: Process overpayment refund
        NO_ACTION_REQUIRED: No appeal needed
    """

    COMPREHENSIVE_APPEAL = "COMPREHENSIVE_APPEAL"
    AUTHORIZATION_APPEAL = "AUTHORIZATION_APPEAL"
    ELIGIBILITY_VERIFICATION_APPEAL = "ELIGIBILITY_VERIFICATION_APPEAL"
    CODING_REVIEW_APPEAL = "CODING_REVIEW_APPEAL"
    MEDICAL_NECESSITY_APPEAL = "MEDICAL_NECESSITY_APPEAL"
    TIMELY_FILING_APPEAL = "TIMELY_FILING_APPEAL"
    DUPLICATE_CLAIM_RESOLUTION = "DUPLICATE_CLAIM_RESOLUTION"
    MODIFIER_CORRECTION_APPEAL = "MODIFIER_CORRECTION_APPEAL"
    QUICK_REVIEW_AND_RESUBMIT = "QUICK_REVIEW_AND_RESUBMIT"
    STANDARD_APPEAL = "STANDARD_APPEAL"
    REFUND_PROCESSING = "REFUND_PROCESSING"
    NO_ACTION_REQUIRED = "NO_ACTION_REQUIRED"

    @property
    def requires_clinical_review(self) -> bool:
        """Check if this strategy requires clinical team review."""
        return self in {
            AppealStrategy.MEDICAL_NECESSITY_APPEAL,
            AppealStrategy.COMPREHENSIVE_APPEAL,
        }

    @property
    def assigned_team(self) -> str:
        """Get the team assigned to handle this appeal strategy."""
        team_mapping = {
            AppealStrategy.AUTHORIZATION_APPEAL: "AUTHORIZATION_TEAM",
            AppealStrategy.ELIGIBILITY_VERIFICATION_APPEAL: "ELIGIBILITY_TEAM",
            AppealStrategy.CODING_REVIEW_APPEAL: "CODING_TEAM",
            AppealStrategy.MODIFIER_CORRECTION_APPEAL: "CODING_TEAM",
            AppealStrategy.MEDICAL_NECESSITY_APPEAL: "CLINICAL_APPEALS_TEAM",
            AppealStrategy.TIMELY_FILING_APPEAL: "COMPLIANCE_TEAM",
            AppealStrategy.QUICK_REVIEW_AND_RESUBMIT: "BILLING_TEAM",
            AppealStrategy.REFUND_PROCESSING: "ACCOUNTING_TEAM",
            AppealStrategy.NO_ACTION_REQUIRED: "NONE",
        }
        return team_mapping.get(self, "GENERAL_APPEALS_TEAM")


class ClaimStatus(str, Enum):
    """
    Status of a claim in the revenue cycle.

    Attributes:
        DRAFT: Claim being prepared
        PENDING_SUBMISSION: Ready for submission
        SUBMITTED: Submitted to payer
        ACKNOWLEDGED: Acknowledged by payer
        IN_REVIEW: Under payer review
        PENDING_INFO: Payer requesting additional information
        ADJUDICATED: Payer made decision
        PAID: Claim paid
        PARTIAL_PAID: Partially paid
        DENIED: Claim denied
        IN_APPEAL: Appeal in progress
        CLOSED: Claim closed
    """

    DRAFT = "DRAFT"
    PENDING_SUBMISSION = "PENDING_SUBMISSION"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    IN_REVIEW = "IN_REVIEW"
    PENDING_INFO = "PENDING_INFO"
    ADJUDICATED = "ADJUDICATED"
    PAID = "PAID"
    PARTIAL_PAID = "PARTIAL_PAID"
    DENIED = "DENIED"
    IN_APPEAL = "IN_APPEAL"
    CLOSED = "CLOSED"


class PaymentStatus(str, Enum):
    """
    Status of a payment in the revenue cycle.

    Attributes:
        PENDING: Payment expected
        RECEIVED: Payment received
        POSTED: Payment posted to account
        RECONCILED: Payment reconciled
        DISPUTED: Payment disputed
        REFUNDED: Payment refunded
    """

    PENDING = "PENDING"
    RECEIVED = "RECEIVED"
    POSTED = "POSTED"
    RECONCILED = "RECONCILED"
    DISPUTED = "DISPUTED"
    REFUNDED = "REFUNDED"
