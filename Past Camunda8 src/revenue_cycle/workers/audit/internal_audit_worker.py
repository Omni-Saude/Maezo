"""
InternalAuditWorker - Zeebe worker for performing internal audit checks.

This worker performs detailed audit validation on claim data including
compliance checks, business rule validation, and data integrity verification.

This is the Python equivalent of the Java InternalAuditDelegate.

Business Rule: Benchmark - Internal audit standards (SOX compliance, internal controls)
Regulatory Compliance: SOX 404 (internal controls), CNJ audit standards, ANS compliance requirements
Migrated from: com.hospital.revenuecycle.delegates.InternalAuditDelegate

Section references:
- Data integrity verification
- Business rule validation
- Provider and service code compliance
- Audit scoring and findings documentation

BPMN Task: Task_Internal_Audit in Audit_Validation_Workflow
Topic: internal-audit
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


@worker(topic="internal-audit", max_jobs=8, lock_duration=45000)
class InternalAuditWorker(BaseWorker):
    """
    Zeebe worker for performing internal audit checks on claims.

    BPMN Task: Task_Internal_Audit
    Topic: internal-audit

    This worker performs:
    - Compliance verification
    - Business rule validation
    - Data integrity checks
    - Provider validation
    - Service code verification

    Input Variables:
        - claimId: Claim identifier (required)
        - claimData: Full claim data (required)
        - providerCode: Provider identifier

    Output Variables:
        - auditPassed: Whether audit was successful (boolean)
        - auditFindings: List of audit issues found
        - auditScore: Audit quality score (0-100)
        - auditDate: Date audit was performed
    """

    def __init__(self, settings=None, **kwargs):
        """Initialize the worker."""
        super().__init__(settings=settings)

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "internal_audit"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the internal audit task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with audit outcome
        """
        self._logger.info(
            "Processing internal audit",
            claim_id=variables.get("claimId"),
        )

        try:
            claim_id = variables.get("claimId")
            claim_data = variables.get("claimData", {})

            # Perform audit checks
            findings = []
            audit_score = 100

            # Check service date validity
            service_date = claim_data.get("serviceDate")
            if not service_date:
                findings.append("Missing service date")
                audit_score -= 20

            # Check amount validity
            amount = claim_data.get("amount")
            if not amount or float(amount) <= 0:
                findings.append("Invalid or missing amount")
                audit_score -= 25

            # Check provider code
            provider_code = claim_data.get("providerCode")
            if not provider_code:
                findings.append("Missing provider code")
                audit_score -= 15

            # Check service code
            service_code = claim_data.get("serviceCode")
            if not service_code:
                findings.append("Missing service code")
                audit_score -= 15

            # Ensure audit score is not negative
            audit_score = max(0, audit_score)
            audit_passed = audit_score >= 80 and len(findings) == 0

            output = {
                "auditPassed": audit_passed,
                "auditFindings": findings,
                "auditScore": audit_score,
                "auditDate": datetime.utcnow().isoformat(),
            }

            self._logger.info(
                "Internal audit completed",
                claim_id=claim_id,
                audit_passed=audit_passed,
                audit_score=audit_score,
            )

            return WorkerResult.ok(output)

        except Exception as e:
            self._logger.error(
                "Error performing internal audit",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Internal audit failed: {e}",
                retry=True,
            )
