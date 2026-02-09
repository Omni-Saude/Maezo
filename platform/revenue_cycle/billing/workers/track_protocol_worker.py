"""Track protocol number worker."""
from __future__ import annotations

from typing import Any
from datetime import datetime

from platform.revenue_cycle.billing.workers.base import BaseWorker, WorkerResult, worker
from platform.shared.i18n import _
from platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


@worker(topic="billing-track-protocol")
class TrackProtocolWorker(BaseWorker):
    """Worker to track protocol number from payer submission."""

    def __init__(self) -> None:
        """Initialize worker with in-memory protocol storage."""
        super().__init__()
        # Simulated database storage - in production this would be a real repository
        self._protocol_db: dict[str, dict[str, Any]] = {}
        self._tracking_counter = 1000

    @property
    def operation_name(self) -> str:
        """Get human-readable operation name."""
        return _("Registrar protocolo de submissão")

    async def process_task(self, job: Any, variables: dict[str, Any]) -> WorkerResult:
        """
        Store protocol number for audit trail.

        Input variables:
            - claim_id: Claim identifier
            - protocol_number: Protocol number from payer
            - payer_id: Payer identifier
            - submission_timestamp: ISO timestamp of submission

        Output variables:
            - protocol_tracked: Boolean indicating tracking success
            - tracking_id: Internal tracking identifier

        Args:
            job: Job object from workflow engine
            variables: Process variables

        Returns:
            WorkerResult with tracking outcome
        """
        claim_id = variables.get("claim_id")
        protocol_number = variables.get("protocol_number")
        payer_id = variables.get("payer_id")
        submission_timestamp = variables.get("submission_timestamp")

        # Validate required inputs
        if not claim_id:
            return WorkerResult.bpmn_error(
                error_code="MISSING_CLAIM_ID",
                error_message=_("Identificador da fatura não fornecido")
            )

        if not protocol_number or not protocol_number.strip():
            return WorkerResult.bpmn_error(
                error_code="MISSING_PROTOCOL_NUMBER",
                error_message=_("Número de protocolo não fornecido")
            )

        if not payer_id:
            return WorkerResult.bpmn_error(
                error_code="MISSING_PAYER_ID",
                error_message=_("Identificador da operadora não fornecido")
            )

        self._logger.info(
            "Tracking protocol number",
            claim_id=claim_id,
            protocol_number=protocol_number,
            payer_id=payer_id
        )

        try:
            # Generate tracking ID
            tracking_id = f"TRACK-{self._tracking_counter}"
            self._tracking_counter += 1

            # Store protocol information
            protocol_record = {
                "tracking_id": tracking_id,
                "claim_id": claim_id,
                "protocol_number": protocol_number,
                "payer_id": payer_id,
                "submission_timestamp": submission_timestamp,
                "tracked_at": datetime.utcnow().isoformat(),
            }

            self._protocol_db[protocol_number] = protocol_record

            # Log for audit trail
            self._logger.info(
                "Protocol tracked successfully",
                tracking_id=tracking_id,
                claim_id=claim_id,
                protocol_number=protocol_number,
                payer_id=payer_id,
                audit_trail=True  # Mark as audit event
            )

            output = {
                "protocol_tracked": True,
                "tracking_id": tracking_id
            }

            return WorkerResult.ok(output)

        except Exception as e:
            self._logger.error(
                "Failed to track protocol",
                claim_id=claim_id,
                protocol_number=protocol_number,
                error=str(e),
                exc_info=True
            )
            return WorkerResult.failure(
                error_message=_("Erro ao registrar protocolo: {error}").format(error=str(e)),
                retry=False  # No point retrying if storage fails
            )

    def get_protocol_record(self, protocol_number: str) -> dict[str, Any] | None:
        """
        Retrieve protocol record by protocol number.

        Args:
            protocol_number: Protocol number to retrieve

        Returns:
            Protocol record or None if not found
        """
        return self._protocol_db.get(protocol_number)
