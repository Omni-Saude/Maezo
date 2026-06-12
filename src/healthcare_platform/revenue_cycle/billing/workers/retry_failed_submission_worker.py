"""Retry failed submission worker with exponential backoff."""
from __future__ import annotations

from typing import Any

from healthcare_platform.revenue_cycle.billing.workers.base import BaseWorker, WorkerResult, worker
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.tiss_client import TISSClientProtocol
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


@worker(topic="billing-retry-failed-submission")
class RetryFailedSubmissionWorker(BaseWorker):
    """Worker to retry failed submissions with exponential backoff.

    Archetype: FINANCIAL_CALCULATION"""

    def __init__(self, tiss_client: TISSClientProtocol) -> None:
        """
        Initialize worker with TISS client.

        Args:
            tiss_client: TISS client implementation for submission
        """
        super().__init__()
        self._tiss_client = tiss_client
        self.dmn_service = FederatedDMNService()

    @property
    def operation_name(self) -> str:
        """Get human-readable operation name."""
        return _("Retentar submissão falhada")

    def _evaluate_billing_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate billing DMN decision table via federation service."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=getattr(self, '_tenant_id', 'default'),
                category='billing',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    async def process_task(self, job: Any, variables: dict[str, Any]) -> WorkerResult:
        """
        Retry failed submission with exponential backoff.

        Input variables:
            - claim_id: Claim identifier
            - tiss_xml: TISS XML content to submit
            - payer_id: Target payer identifier
            - attempt_number: Current attempt number (1-based)
            - max_attempts: Maximum retry attempts (default 5)
            - last_error: Error message from last attempt

        Output variables:
            - retry_success: Boolean indicating retry success
            - protocol_number: Protocol number if successful
            - next_attempt_number: Next attempt number
            - backoff_ms: Milliseconds to wait before next retry
            - max_attempts_reached: Boolean indicating if max attempts reached

        Args:
            job: Job object from workflow engine
            variables: Process variables

        Returns:
            WorkerResult with retry outcome
        """
        claim_id = variables.get("claim_id")
        tiss_xml = variables.get("tiss_xml")
        payer_id = variables.get("payer_id")
        attempt_number = variables.get("attempt_number", 1)
        max_attempts = variables.get("max_attempts", 5)
        last_error = variables.get("last_error", "")

        # Validate required inputs
        if not claim_id:
            return WorkerResult.bpmn_error(
                error_code="MISSING_CLAIM_ID",
                error_message=_("Identificador da fatura não fornecido")
            )

        if not tiss_xml:
            return WorkerResult.bpmn_error(
                error_code="MISSING_TISS_XML",
                error_message=_("XML TISS não fornecido")
            )

        if not payer_id:
            return WorkerResult.bpmn_error(
                error_code="MISSING_PAYER_ID",
                error_message=_("Identificador da operadora não fornecido")
            )

        # Check if max attempts reached
        if attempt_number >= max_attempts:
            self._logger.error(
                "Max retry attempts reached",
                claim_id=claim_id,
                payer_id=payer_id,
                attempt_number=attempt_number,
                max_attempts=max_attempts,
                last_error=last_error
            )
            return WorkerResult.ok({
                "retry_success": False,
                "protocol_number": None,
                "next_attempt_number": attempt_number + 1,
                "backoff_ms": 0,
                "max_attempts_reached": True
            })

        # Calculate exponential backoff: min(2^attempt * 1000, 300000) ms
        backoff_ms = min(2 ** attempt_number * 1000, 300000)

        self._logger.info(
            "Retrying failed submission",
            claim_id=claim_id,
            payer_id=payer_id,
            attempt_number=attempt_number,
            max_attempts=max_attempts,
            backoff_ms=backoff_ms
        )

        try:
            # Attempt submission
            result = await self._tiss_client.submit_guide(tiss_xml, payer_id)

            if not result.success:
                # Retry failed - increment attempt
                error_msg = result.payer_response_message or _("Falha na submissão")
                self._logger.warning(
                    "Retry attempt failed",
                    claim_id=claim_id,
                    payer_id=payer_id,
                    attempt_number=attempt_number,
                    error=error_msg
                )

                output = {
                    "retry_success": False,
                    "protocol_number": None,
                    "next_attempt_number": attempt_number + 1,
                    "backoff_ms": backoff_ms,
                    "max_attempts_reached": False,
                    "last_error": error_msg
                }

                # If this was the last attempt, mark as exhausted
                if attempt_number + 1 >= max_attempts:
                    output["max_attempts_reached"] = True
                    self._logger.error(
                        "All retry attempts exhausted",
                        claim_id=claim_id,
                        payer_id=payer_id,
                        total_attempts=max_attempts
                    )

                return WorkerResult.ok(output)

            # Success - return protocol
            self._logger.info(
                "Retry attempt succeeded",
                claim_id=claim_id,
                payer_id=payer_id,
                attempt_number=attempt_number,
                protocol_number=result.protocol_number
            )

            output = {
                "retry_success": True,
                "protocol_number": result.protocol_number,
                "submission_timestamp": result.submission_timestamp.isoformat() if result.submission_timestamp else None,
                "payer_response_code": result.payer_response_code or "OK",
                "next_attempt_number": attempt_number + 1,
                "backoff_ms": 0,
                "max_attempts_reached": False
            }

            return WorkerResult.ok(output)

        except Exception as e:
            # Unexpected error during retry
            self._logger.error(
                "Unexpected error during retry",
                claim_id=claim_id,
                payer_id=payer_id,
                attempt_number=attempt_number,
                error=str(e),
                exc_info=True
            )

            output = {
                "retry_success": False,
                "protocol_number": None,
                "next_attempt_number": attempt_number + 1,
                "backoff_ms": backoff_ms,
                "max_attempts_reached": attempt_number + 1 >= max_attempts,
                "last_error": str(e)
            }

            return WorkerResult.ok(output)
