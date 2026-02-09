"""Submit TISS guide to payer worker."""
from __future__ import annotations

from typing import Any

from platform.revenue_cycle.billing.workers.base import BaseWorker, WorkerResult, worker
from platform.shared.domain.exceptions import ClaimSubmissionError
from platform.shared.i18n import _
from platform.shared.integrations.tiss_client import TISSClientProtocol
from platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


@worker(topic="billing-submit-to-payer")
class SubmitToPayerWorker(BaseWorker):
    """Worker to submit TISS XML guide to payer via TISS client."""

    def __init__(self, tiss_client: TISSClientProtocol) -> None:
        """
        Initialize worker with TISS client.

        Args:
            tiss_client: TISS client implementation for submission
        """
        super().__init__()
        self._tiss_client = tiss_client

    @property
    def operation_name(self) -> str:
        """Get human-readable operation name."""
        return _("Submeter guia TISS à operadora")

    async def process_task(self, job: Any, variables: dict[str, Any]) -> WorkerResult:
        """
        Submit TISS XML to payer.

        Input variables:
            - tiss_xml: TISS XML content to submit
            - payer_id: Target payer identifier
            - claim_id: Claim identifier for tracking

        Output variables:
            - submission_success: Boolean indicating submission success
            - protocol_number: Protocol number from payer
            - submission_timestamp: ISO timestamp of submission
            - payer_response_code: Response code from payer

        Args:
            job: Job object from workflow engine
            variables: Process variables

        Returns:
            WorkerResult with submission outcome

        Raises:
            ClaimSubmissionError: If submission fails (retryable)
        """
        tiss_xml = variables.get("tiss_xml")
        payer_id = variables.get("payer_id")
        claim_id = variables.get("claim_id")

        # Validate required inputs
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

        if not claim_id:
            return WorkerResult.bpmn_error(
                error_code="MISSING_CLAIM_ID",
                error_message=_("Identificador da fatura não fornecido")
            )

        self._logger.info(
            "Submitting TISS guide to payer",
            claim_id=claim_id,
            payer_id=payer_id
        )

        try:
            # Submit guide to payer
            result = await self._tiss_client.submit_guide(tiss_xml, payer_id)

            if not result.success:
                # Submission failed - raise retryable error
                error_msg = result.payer_response_message or _("Falha na submissão da guia")
                self._logger.warning(
                    "TISS submission failed",
                    claim_id=claim_id,
                    payer_id=payer_id,
                    response_code=result.payer_response_code,
                    error_message=error_msg
                )
                raise ClaimSubmissionError(
                    _("Falha ao submeter guia à operadora: {error}").format(error=error_msg),
                    details={
                        "claim_id": claim_id,
                        "payer_id": payer_id,
                        "response_code": result.payer_response_code,
                        "validation_errors": result.validation_errors,
                        "processing_errors": result.processing_errors
                    }
                )

            # Success - extract result data
            output = {
                "submission_success": True,
                "protocol_number": result.protocol_number,
                "submission_timestamp": result.submission_timestamp.isoformat() if result.submission_timestamp else None,
                "payer_response_code": result.payer_response_code or "OK",
                "payer_response_message": result.payer_response_message
            }

            self._logger.info(
                "TISS guide submitted successfully",
                claim_id=claim_id,
                payer_id=payer_id,
                protocol_number=result.protocol_number
            )

            return WorkerResult.ok(output)

        except ClaimSubmissionError:
            # Re-raise domain exceptions as-is
            raise

        except Exception as e:
            # Wrap unexpected errors
            self._logger.error(
                "Unexpected error submitting TISS guide",
                claim_id=claim_id,
                payer_id=payer_id,
                error=str(e),
                exc_info=True
            )
            raise ClaimSubmissionError(
                _("Erro inesperado ao submeter guia: {error}").format(error=str(e)),
                details={"claim_id": claim_id, "payer_id": payer_id}
            ) from e
