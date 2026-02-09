"""
QualityScoreWorker - Zeebe worker for calculating claim quality score.

This worker computes a comprehensive quality score for claim data based on
multiple factors including completeness, accuracy, and compliance metrics.

This is the Python equivalent of the Java QualityScoreDelegate.

Business Rule: Benchmark - Data quality assessment standards (40% completeness, 30% compliance, 30% accuracy)
Regulatory Compliance: Quality assurance standards per ANS/TISS, internal audit requirements
Migrated from: com.hospital.revenuecycle.delegates.QualityScoreDelegate

Section references:
- Weighted quality calculation (completeness, compliance, documentation)
- Quality level classification (EXCELLENT/GOOD/FAIR/POOR)
- Quality metrics aggregation and reporting

BPMN Task: Task_Quality_Score in Audit_Validation_Workflow
Topic: quality-score
"""

from __future__ import annotations

from typing import Any

import structlog

from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


@worker(topic="quality-score", max_jobs=8, lock_duration=30000)
class QualityScoreWorker(BaseWorker):
    """
    Zeebe worker for calculating claim data quality score.

    BPMN Task: Task_Quality_Score
    Topic: quality-score

    This worker calculates quality score based on:
    - Data completeness (40%)
    - Compliance adherence (30%)
    - Accuracy metrics (20%)
    - Documentation quality (10%)

    Input Variables:
        - claimId: Claim identifier (required)
        - completenessScore: Completeness percentage (0-100)
        - auditScore: Audit quality score (0-100)
        - documentationQuality: Documentation score (0-100)

    Output Variables:
        - qualityScore: Overall quality score (0-100)
        - qualityLevel: Quality level (EXCELLENT/GOOD/FAIR/POOR)
        - scoreComponents: Breakdown of score components
    """

    def __init__(self, settings=None, **kwargs):
        """Initialize the worker."""
        super().__init__(settings=settings)

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "quality_score"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the quality score calculation task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with quality score
        """
        self._logger.info(
            "Processing quality score calculation",
            claim_id=variables.get("claimId"),
        )

        try:
            claim_id = variables.get("claimId")

            # Get component scores
            completeness_score = float(variables.get("completenessScore", 0))
            audit_score = float(variables.get("auditScore", 0))
            documentation_quality = float(variables.get("documentationQuality", 50))

            # Calculate weighted quality score
            quality_score = (
                (completeness_score * 0.40) +
                (audit_score * 0.30) +
                (documentation_quality * 0.30)
            )

            # Round to 2 decimal places
            quality_score = round(quality_score, 2)

            # Determine quality level
            if quality_score >= 90:
                quality_level = "EXCELLENT"
            elif quality_score >= 80:
                quality_level = "GOOD"
            elif quality_score >= 70:
                quality_level = "FAIR"
            else:
                quality_level = "POOR"

            score_components = {
                "completenessScore": completeness_score,
                "auditScore": audit_score,
                "documentationQuality": documentation_quality,
            }

            output = {
                "qualityScore": quality_score,
                "qualityLevel": quality_level,
                "scoreComponents": score_components,
            }

            self._logger.info(
                "Quality score calculated",
                claim_id=claim_id,
                quality_score=quality_score,
                quality_level=quality_level,
            )

            return WorkerResult.ok(output)

        except Exception as e:
            self._logger.error(
                "Error calculating quality score",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Quality score calculation failed: {e}",
                retry=True,
            )
