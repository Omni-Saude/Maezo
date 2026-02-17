"""
Track Appeal Status Worker.

Monitors appeal status with payer via TISS protocol.
Determines follow-up actions based on elapsed time and payer response.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from healthcare_platform.revenue_cycle.billing.workers.base import BaseWorker, WorkerResult, worker
from healthcare_platform.revenue_cycle.glosa.workers.base import GlosaWorkerMixin
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.exceptions import GlosaException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.tiss_client import TISSClientProtocol
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


@worker(topic="glosa.track_appeal_status", max_jobs=10, lock_duration=15000)
class TrackAppealStatusWorker(BaseWorker, GlosaWorkerMixin):
    """
    Track glosa appeal status with payer.

    Checks submission status via TISS, maps payer responses,
    and determines if follow-up is required.
    """

    def __init__(self, tiss_client: TISSClientProtocol) -> None:
        """
        Initialize worker with TISS client dependency.

        Args:
            tiss_client: TISS protocol client for payer communication
        """
        self.tiss_client = tiss_client
        self.dmn_service = FederatedDMNService()

    def _evaluate_glosa_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate glosa_prevention DMN decision table."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=getattr(self, '_tenant_id', 'default'),
                category='glosa_prevention',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    def _evaluate_appeal_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate revenue_recovery DMN decision table."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=getattr(self, '_tenant_id', 'default'),
                category='revenue_recovery',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    # Payer response code to appeal status mapping
    STATUS_MAPPING = {
        "RECEIVED": "PENDING",
        "IN_ANALYSIS": "IN_REVIEW",
        "APPROVED": "APPROVED",
        "PARTIALLY_APPROVED": "PARTIALLY_APPROVED",
        "DENIED": "DENIED",
        "REJECTED": "DENIED",
        "PENDING_INFO": "IN_REVIEW",
    }

    FOLLOW_UP_THRESHOLD_DAYS = 15

    async def process_task(
        self,
        job: Any,
        variables: Dict[str, Any],
    ) -> WorkerResult:
        """
        Check appeal status with payer.

        Args:
            job: Zeebe job instance
            variables: Input variables containing:
                - submissionProtocol: Protocol number from submission
                - claimId: Claim identifier
                - appealDocumentId: Appeal document ID
                - submissionTimestamp: ISO timestamp of submission

        Returns:
            WorkerResult with status details
        """
        try:
            submission_protocol = variables.get("submissionProtocol")
            claim_id = variables.get("claimId")
            appeal_doc_id = variables.get("appealDocumentId")
            submission_timestamp = variables.get("submissionTimestamp")

            logger.info(
                "Tracking appeal status",
                extra={
                    "protocol": submission_protocol,
                    "claim_id": claim_id,
                    "appeal_document_id": appeal_doc_id,
                }
            )

            # Validate required inputs
            if not submission_protocol:
                raise GlosaException(_("Protocolo de envio é obrigatório"))

            if not claim_id:
                raise GlosaException(_("ID da conta é obrigatório"))

            # Calculate elapsed days
            elapsed_days = self._calculate_elapsed_days(submission_timestamp)

            # Check status via TISS
            status_response = await self.tiss_client.check_submission_status(
                protocol_number=submission_protocol,
                guide_type="APPEAL",
            )

            # Map payer response to appeal status
            payer_code = status_response.get("statusCode", "UNKNOWN")
            appeal_status = self.STATUS_MAPPING.get(payer_code, "PENDING")

            # Determine if follow-up needed
            follow_up_required = self._check_follow_up_needed(
                appeal_status=appeal_status,
                elapsed_days=elapsed_days,
                payer_code=payer_code,
            )

            # Generate status message
            status_message = self._generate_status_message(
                appeal_status=appeal_status,
                elapsed_days=elapsed_days,
                follow_up_required=follow_up_required,
                payer_code=payer_code,
            )

            output_vars = {
                "appealStatus": appeal_status,
                "payerResponse": status_response,
                "elapsedDays": elapsed_days,
                "followUpRequired": follow_up_required,
                "statusMessage": status_message,
            }

            logger.info(
                "Appeal status tracked",
                extra={
                    "claim_id": claim_id,
                    "status": appeal_status,
                    "elapsed_days": elapsed_days,
                    "follow_up_required": follow_up_required,
                }
            )

            return WorkerResult.success(output_vars)

        except GlosaException as e:
            logger.error("Glosa exception during appeal tracking", exc_info=e)
            return WorkerResult.failure(error_message=str(e))
        except Exception as e:
            logger.error("Unexpected error tracking appeal status", exc_info=e)
            return WorkerResult.failure(
                error_message=_("Erro ao rastrear status do recurso: {}").format(str(e))
            )

    def _calculate_elapsed_days(self, submission_timestamp: str) -> int:
        """
        Calculate days elapsed since submission.

        Args:
            submission_timestamp: ISO timestamp string

        Returns:
            Number of days elapsed
        """
        try:
            submission_dt = datetime.fromisoformat(submission_timestamp.replace("Z", "+00:00"))
            now_dt = datetime.now(timezone.utc)
            delta = now_dt - submission_dt
            return delta.days
        except (ValueError, AttributeError):
            logger.warning("Invalid submission timestamp, using 0 days")
            return 0

    def _check_follow_up_needed(
        self,
        appeal_status: str,
        elapsed_days: int,
        payer_code: str,
    ) -> bool:
        """
        Determine if follow-up action is required.

        Args:
            appeal_status: Current appeal status
            elapsed_days: Days since submission
            payer_code: Raw payer response code

        Returns:
            True if follow-up needed
        """
        # Final statuses don't need follow-up
        if appeal_status in ["APPROVED", "PARTIALLY_APPROVED", "DENIED"]:
            return False

        # Check threshold for pending/in-review statuses
        if elapsed_days > self.FOLLOW_UP_THRESHOLD_DAYS:
            return True

        # Pending additional info always needs follow-up
        if payer_code == "PENDING_INFO":
            return True

        return False

    def _generate_status_message(
        self,
        appeal_status: str,
        elapsed_days: int,
        follow_up_required: bool,
        payer_code: str,
    ) -> str:
        """
        Generate user-friendly status message in Portuguese.

        Args:
            appeal_status: Current appeal status
            elapsed_days: Days elapsed
            follow_up_required: Whether follow-up needed
            payer_code: Raw payer code

        Returns:
            Status message in Portuguese
        """
        if appeal_status == "APPROVED":
            return _("Recurso aprovado pela operadora. Glosas revertidas.")

        if appeal_status == "PARTIALLY_APPROVED":
            return _("Recurso parcialmente aprovado. Verificar itens aceitos.")

        if appeal_status == "DENIED":
            return _("Recurso negado pela operadora. Avaliar próximas ações.")

        if appeal_status == "IN_REVIEW":
            msg = _("Recurso em análise pela operadora ({} dias).").format(elapsed_days)
            if follow_up_required:
                msg += _(" Acompanhamento necessário.")
            return msg

        if appeal_status == "PENDING":
            msg = _("Recurso pendente de resposta ({} dias).").format(elapsed_days)
            if follow_up_required:
                msg += _(" Prazo de resposta excedido - contatar operadora.")
            return msg

        return _("Status desconhecido: {}").format(payer_code)
