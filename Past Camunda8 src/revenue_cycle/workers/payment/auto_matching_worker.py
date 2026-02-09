"""
AutoMatchingWorker - Zeebe worker for automated remittance-to-claim matching.

This worker implements intelligent matching of insurance remittance items with claims:
- Exact matching on claim number + amount
- Fuzzy matching on patient name + service date + amount (within tolerance)
- Partial match suggestions for manual review
- Confidence scoring for each match
- Handling of remittance adjustments (glosas)
- Queue unmatched items for manual reconciliation

Business Rule: RN-AutoMatchingDelegate.md
Regulatory Compliance: ANS RN 439/2015, TISS 4.01.00
Migrated from: com.hospital.revenuecycle.delegates.AutoMatchingDelegate

Section references:
- Remittance-to-claim matching algorithms
- Confidence score calculation
- Partial match handling
- Unmatched item reconciliation queue

Topic: auto-matching
BPMN Task: Task_Auto_Matching (Conciliação Automática)
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from difflib import SequenceMatcher
from typing import Any, Optional

import structlog
from pydantic import ValidationError

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker
from revenue_cycle.workers.payment.matching_models import (
    AutoMatchingInput,
    AutoMatchingOutput,
    MatchedItem,
    MatchingSummary,
    MatchType,
    RemittanceItem,
    UnmatchedClaim,
)

logger = structlog.get_logger(__name__)


class MatchingValidationError(BpmnErrorException):
    """Raised when matching validation fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="MATCHING_VALIDATION_ERROR",
            message=message,
            details=details,
        )


class AmbiguousMatchError(BpmnErrorException):
    """Raised when multiple potential matches are found with similar confidence."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="AMBIGUOUS_MATCH_ERROR",
            message=message,
            details=details,
        )


class NoMatchFoundError(BpmnErrorException):
    """Raised when no matching claim is found for a remittance item."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="NO_MATCH_FOUND_ERROR",
            message=message,
            details=details,
        )


class InvalidRemittanceError(BpmnErrorException):
    """Raised when remittance data is invalid or malformed."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            error_code="INVALID_REMITTANCE_ERROR",
            message=message,
            details=details,
        )


@worker(topic="auto-matching", max_jobs=8, lock_duration=60000)
class AutoMatchingWorker(BaseWorker):
    """
    Zeebe worker for automated remittance-to-claim matching.

    Business Rules Reference:
        - Document: docs/Regras de Negocio (PT-BR)/03_Reconciliation/RN-REC-001-Auto-Matching.md
        - Rule IDs: RN-REC-001-001 (Exact Match), RN-REC-001-002 (Fuzzy Match),
                    RN-REC-001-003 (Confidence Scoring)
        - Regulatory: ANS TISS (Remittance Standards), CDC (Consumer Protection)
        - Matching: Exact (claim#+ amount), Fuzzy (patient+date+amount), Partial (review)

    BPMN Task: Task_Auto_Matching
    Topic: auto-matching

    This worker:
    1. Validates input remittance and claims data
    2. Performs exact matching on claim number + amount
    3. Performs fuzzy matching on patient name + date + amount
    4. Calculates confidence scores for each match
    5. Identifies partial matches requiring manual review
    6. Generates matching summary statistics
    7. Returns matched and unmatched items

    Input Variables:
        - remittanceFile: Remittance file identifier (required)
        - remittanceItems: List of remittance items (required)
        - unmatchedClaims: List of claims awaiting payment (required)
        - matchingTolerance: Amount variance tolerance (optional, default R$0.01)
        - fuzzyThreshold: Minimum confidence for fuzzy matches (optional, default 0.80)

    Output Variables:
        - matchingComplete: Whether matching completed successfully (boolean)
        - matchedItems: List of successfully matched items
        - unmatchedRemittances: Remittance items without matches
        - unmatchedClaims: Claims without matches
        - matchingSummary: Summary statistics
        - confidenceScores: Confidence scores by item ID (dict)
        - requiresManualReview: Whether manual review needed (boolean)
        - manualReviewCount: Number of items for manual review

    Matching Strategy:
        1. EXACT: Claim number matches + amount within tolerance = confidence 1.0
        2. FUZZY: Patient name similarity + date match + amount within tolerance
        3. PARTIAL: Potential match but low confidence (<threshold) = manual review

    Confidence Calculation:
        - Claim number match: 0.4 weight
        - Patient name similarity: 0.3 weight
        - Date match: 0.2 weight
        - Amount match (within tolerance): 0.1 weight
    """

    def __init__(
        self,
        settings=None,
        matching_service=None,
        remittance_parser=None,
        **kwargs
    ):
        """
        Initialize the worker.

        Args:
            settings: Optional worker settings
            matching_service: Optional matching service (for testing)
            remittance_parser: Optional remittance parser (for testing)
        """
        super().__init__(settings=settings)
        # Store optional services for testing
        self._matching_service = matching_service
        self._remittance_parser = remittance_parser

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "auto_matching"

    @property
    def requires_idempotency(self) -> bool:
        """This worker benefits from idempotency."""
        return True

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """
        Extract remittance file ID for idempotency key generation.
        """
        remittance_file = variables.get("remittanceFile", "")
        return f"{remittance_file}"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the auto-matching task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with matching results

        Raises:
            MatchingValidationError: If validation fails
        """
        self._logger.info(
            "Processing auto-matching",
            job_key=str(getattr(job, "key", "unknown")),
            remittance_file=variables.get("remittanceFile"),
        )

        try:
            # Parse and validate input
            input_data = AutoMatchingInput.model_validate(variables)

            # Validate input data
            await self._validate_input(input_data)

            # Perform matching
            matched_items, unmatched_remittances, unmatched_claims = await self._perform_matching(
                input_data
            )

            # Calculate summary statistics
            matching_summary = self._calculate_summary(
                input_data,
                matched_items,
                unmatched_remittances,
                unmatched_claims,
            )

            # Extract confidence scores
            confidence_scores = {
                item.remittance_item.item_id: float(item.confidence_score)
                for item in matched_items
            }

            # Determine if manual review is required
            partial_matches = [
                item for item in matched_items if item.match_type == MatchType.PARTIAL
            ]
            requires_manual_review = (
                len(partial_matches) > 0
                or len(unmatched_remittances) > 0
                or len(unmatched_claims) > 0
            )
            manual_review_count = len(partial_matches) + len(unmatched_remittances)

            # Create output
            output = AutoMatchingOutput(
                matchingComplete=True,
                matchedItems=matched_items,
                unmatchedRemittances=unmatched_remittances,
                unmatchedClaims=unmatched_claims,
                matchingSummary=matching_summary,
                confidenceScores=confidence_scores,
                requiresManualReview=requires_manual_review,
                manualReviewCount=manual_review_count,
            )

            self._logger.info(
                "Auto-matching completed",
                remittance_file=input_data.remittance_file,
                exact_matches=matching_summary.exact_matches,
                fuzzy_matches=matching_summary.fuzzy_matches,
                partial_matches=matching_summary.partial_matches,
                unmatched_remittances=matching_summary.unmatched_remittances,
                unmatched_claims=matching_summary.unmatched_claims,
                matching_rate=str(matching_summary.matching_rate),
            )

            # Return success with output variables
            return WorkerResult.ok(output.model_dump(by_alias=True))

        except ValidationError as e:
            self._logger.error(
                "Matching input validation failed",
                errors=e.errors(),
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_MATCHING_INPUT",
                error_message=f"Matching input validation failed: {e}",
            )

        except MatchingValidationError as e:
            self._logger.error(
                "Matching validation error",
                error=str(e),
                error_code=e.error_code,
            )
            return WorkerResult.bpmn_error(
                error_code=e.error_code,
                error_message=e.message,
            )

        except Exception as e:
            self._logger.error(
                "Unexpected error during auto-matching",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Failed to perform auto-matching: {e}",
                retry=True,
            )

    async def _validate_input(self, input_data: AutoMatchingInput) -> None:
        """
        Validate input data and business rules.

        Args:
            input_data: Validated input data

        Raises:
            MatchingValidationError: If validation fails
        """
        # Validate remittance items are not empty
        if not input_data.remittance_items:
            raise MatchingValidationError(
                "Remittance items list cannot be empty",
                details={"remittance_file": input_data.remittance_file},
            )

        # Validate tolerance is reasonable
        if input_data.matching_tolerance < 0 or input_data.matching_tolerance > Decimal("1000"):
            raise MatchingValidationError(
                "Matching tolerance must be between R$0 and R$1000",
                details={"matching_tolerance": str(input_data.matching_tolerance)},
            )

        # Validate fuzzy threshold
        if input_data.fuzzy_threshold < Decimal("0.5") or input_data.fuzzy_threshold > Decimal("1.0"):
            raise MatchingValidationError(
                "Fuzzy threshold must be between 0.5 and 1.0",
                details={"fuzzy_threshold": str(input_data.fuzzy_threshold)},
            )

    async def _perform_matching(
        self,
        input_data: AutoMatchingInput,
    ) -> tuple[list[MatchedItem], list[RemittanceItem], list[UnmatchedClaim]]:
        """
        Perform matching between remittance items and claims.

        Args:
            input_data: Matching input data

        Returns:
            Tuple of (matched_items, unmatched_remittances, unmatched_claims)
        """
        matched_items: list[MatchedItem] = []
        unmatched_remittances: list[RemittanceItem] = []
        matched_claim_ids: set[str] = set()

        # Process each remittance item
        for remittance_item in input_data.remittance_items:
            # Try to find a match
            match = await self._find_best_match(
                remittance_item,
                input_data.unmatched_claims,
                matched_claim_ids,
                input_data.matching_tolerance,
                input_data.fuzzy_threshold,
            )

            if match:
                matched_items.append(match)
                matched_claim_ids.add(match.matched_claim.claim_id)
            else:
                unmatched_remittances.append(remittance_item)

        # Identify unmatched claims
        unmatched_claims = [
            claim
            for claim in input_data.unmatched_claims
            if claim.claim_id not in matched_claim_ids
        ]

        return matched_items, unmatched_remittances, unmatched_claims

    async def _find_best_match(
        self,
        remittance_item: RemittanceItem,
        claims: list[UnmatchedClaim],
        already_matched: set[str],
        tolerance: Decimal,
        fuzzy_threshold: Decimal,
    ) -> Optional[MatchedItem]:
        """
        Find the best matching claim for a remittance item.

        Args:
            remittance_item: Remittance item to match
            claims: Available claims
            already_matched: Set of already matched claim IDs
            tolerance: Amount matching tolerance
            fuzzy_threshold: Minimum confidence for fuzzy matches

        Returns:
            MatchedItem if a suitable match is found, None otherwise
        """
        best_match: Optional[MatchedItem] = None
        best_score = Decimal("0")

        for claim in claims:
            # Skip already matched claims
            if claim.claim_id in already_matched:
                continue

            # Calculate match score and type
            match_type, score, reasons = self._calculate_match_score(
                remittance_item,
                claim,
                tolerance,
            )

            # Update best match if this score is higher
            if score > best_score:
                best_score = score
                best_match = MatchedItem(
                    remittanceItem=remittance_item,
                    matchedClaim=claim,
                    matchType=match_type,
                    confidenceScore=score,
                    matchReasons=reasons,
                )

        # Return match only if it meets the threshold
        if best_match:
            # Exact matches always qualify
            if best_match.match_type == MatchType.EXACT:
                return best_match
            # Fuzzy matches must exceed threshold
            elif best_match.match_type == MatchType.FUZZY and best_score >= fuzzy_threshold:
                return best_match
            # Partial matches are returned for manual review
            elif best_match.match_type == MatchType.PARTIAL and best_score >= Decimal("0.5"):
                return best_match

        return None

    def _calculate_match_score(
        self,
        remittance_item: RemittanceItem,
        claim: UnmatchedClaim,
        tolerance: Decimal,
    ) -> tuple[MatchType, Decimal, list[str]]:
        """
        Calculate match score and type for a remittance-claim pair.

        Scoring weights:
        - Claim number match: 0.4
        - Patient name similarity: 0.3
        - Service date match: 0.2
        - Amount match (within tolerance): 0.1

        Args:
            remittance_item: Remittance item
            claim: Claim to match
            tolerance: Amount tolerance

        Returns:
            Tuple of (match_type, confidence_score, match_reasons)
        """
        score = Decimal("0")
        reasons: list[str] = []

        # 1. Claim number match (weight: 0.4)
        claim_number_match = False
        if remittance_item.claim_number and remittance_item.claim_number == claim.claim_number:
            score += Decimal("0.4")
            claim_number_match = True
            reasons.append("Claim number exact match")

        # 2. Patient name similarity (weight: 0.3)
        name_similarity = self._calculate_string_similarity(
            remittance_item.patient_name.lower(),
            claim.patient_name.lower(),
        )
        name_score = Decimal(str(name_similarity)) * Decimal("0.3")
        score += name_score
        if name_similarity >= 0.9:
            reasons.append(f"Patient name high similarity ({name_similarity:.2f})")
        elif name_similarity >= 0.7:
            reasons.append(f"Patient name moderate similarity ({name_similarity:.2f})")

        # 3. Service date match (weight: 0.2)
        date_match = False
        if remittance_item.service_date == claim.service_date:
            score += Decimal("0.2")
            date_match = True
            reasons.append("Service date exact match")

        # 4. Amount match (weight: 0.1)
        amount_match = False
        amount_diff = abs(remittance_item.paid_amount - claim.billed_amount)
        if amount_diff <= tolerance:
            score += Decimal("0.1")
            amount_match = True
            reasons.append(f"Amount within tolerance (diff: R${amount_diff})")
        else:
            reasons.append(f"Amount variance: R${amount_diff}")

        # Determine match type
        if claim_number_match and amount_match:
            match_type = MatchType.EXACT
        elif name_similarity >= 0.8 and date_match and amount_diff <= tolerance:
            match_type = MatchType.FUZZY
        elif score >= Decimal("0.5"):
            match_type = MatchType.PARTIAL
        else:
            match_type = MatchType.NONE

        return match_type, score, reasons

    def _calculate_string_similarity(self, str1: str, str2: str) -> float:
        """
        Calculate similarity between two strings using SequenceMatcher.

        Args:
            str1: First string
            str2: Second string

        Returns:
            Similarity ratio (0-1)
        """
        return SequenceMatcher(None, str1, str2).ratio()

    def _calculate_summary(
        self,
        input_data: AutoMatchingInput,
        matched_items: list[MatchedItem],
        unmatched_remittances: list[RemittanceItem],
        unmatched_claims: list[UnmatchedClaim],
    ) -> MatchingSummary:
        """
        Calculate summary statistics for matching operation.

        Args:
            input_data: Input data
            matched_items: Matched items
            unmatched_remittances: Unmatched remittances
            unmatched_claims: Unmatched claims

        Returns:
            MatchingSummary with statistics
        """
        # Count by match type
        exact_matches = sum(1 for item in matched_items if item.match_type == MatchType.EXACT)
        fuzzy_matches = sum(1 for item in matched_items if item.match_type == MatchType.FUZZY)
        partial_matches = sum(1 for item in matched_items if item.match_type == MatchType.PARTIAL)

        # Calculate total amounts
        total_paid_amount = sum(
            (item.paid_amount for item in input_data.remittance_items),
            Decimal("0"),
        )
        total_matched_amount = sum(
            (item.remittance_item.paid_amount for item in matched_items),
            Decimal("0"),
        )

        # Calculate matching rate
        total_items = len(input_data.remittance_items)
        if total_items > 0:
            matching_rate = (Decimal(len(matched_items)) / Decimal(total_items)) * Decimal("100")
            matching_rate = matching_rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            matching_rate = Decimal("0")

        return MatchingSummary(
            totalRemittanceItems=len(input_data.remittance_items),
            totalClaims=len(input_data.unmatched_claims),
            exactMatches=exact_matches,
            fuzzyMatches=fuzzy_matches,
            partialMatches=partial_matches,
            unmatchedRemittances=len(unmatched_remittances),
            unmatchedClaims=len(unmatched_claims),
            totalPaidAmount=total_paid_amount,
            totalMatchedAmount=total_matched_amount,
            matchingRate=matching_rate,
        )
