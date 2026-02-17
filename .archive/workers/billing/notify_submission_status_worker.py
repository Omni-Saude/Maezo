"""Notify submission status via WhatsApp worker."""
from __future__ import annotations

from typing import Any

from healthcare_platform.revenue_cycle.billing.workers.base import BaseWorker, WorkerResult, worker
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.whatsapp_client import WhatsAppClientProtocol, WhatsAppTemplate
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


@worker(topic="billing-notify-submission-status")
class NotifySubmissionStatusWorker(BaseWorker):
    """Worker to send WhatsApp notifications about submission status."""

    def __init__(self, whatsapp_client: WhatsAppClientProtocol) -> None:
        """
        Initialize worker with WhatsApp client.

        Args:
            whatsapp_client: WhatsApp client implementation
        """
        super().__init__()
        self._whatsapp_client = whatsapp_client
        self.dmn_service = FederatedDMNService()

    @property
    def operation_name(self) -> str:
        """Get human-readable operation name."""
        return _("Notificar status de submissão")

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
        Send WhatsApp notification about submission status.

        Input variables:
            - claim_id: Claim identifier
            - protocol_number: Protocol number from submission
            - submission_status: "submitted", "acknowledged", "rejected", or "failed"
            - payer_name: Name of payer
            - total_amount: Total billing amount
            - notification_phones: List of E.164 phone numbers

        Output variables:
            - notifications_sent: Number of notifications sent successfully
            - notification_ids: List of WhatsApp message IDs

        Args:
            job: Job object from workflow engine
            variables: Process variables

        Returns:
            WorkerResult with notification outcome
        """
        claim_id = variables.get("claim_id")
        protocol_number = variables.get("protocol_number")
        submission_status = variables.get("submission_status", "").lower()
        payer_name = variables.get("payer_name", "Operadora")
        total_amount = variables.get("total_amount", 0.0)
        notification_phones = variables.get("notification_phones", [])

        # Validate required inputs
        if not claim_id:
            return WorkerResult.bpmn_error(
                error_code="MISSING_CLAIM_ID",
                error_message=_("Identificador da fatura não fornecido")
            )

        if submission_status not in ("submitted", "acknowledged", "rejected", "failed"):
            return WorkerResult.bpmn_error(
                error_code="INVALID_STATUS",
                error_message=_("Status de submissão inválido: {status}").format(status=submission_status)
            )

        if not notification_phones or not isinstance(notification_phones, list):
            self._logger.warning(
                "No notification phones provided",
                claim_id=claim_id
            )
            return WorkerResult.ok({
                "notifications_sent": 0,
                "notification_ids": []
            })

        self._logger.info(
            "Sending submission status notifications",
            claim_id=claim_id,
            submission_status=submission_status,
            recipient_count=len(notification_phones)
        )

        # Build template based on status
        template = self._build_template(
            submission_status, claim_id, protocol_number, payer_name, total_amount
        )

        # Send notifications to all phones
        notification_ids = []
        failed_count = 0

        for phone in notification_phones:
            try:
                message_id = await self._whatsapp_client.send_template_message(
                    phone=phone,
                    template=template
                )
                notification_ids.append(message_id)
                self._logger.info(
                    "Notification sent",
                    claim_id=claim_id,
                    message_id=message_id
                )
            except Exception as e:
                failed_count += 1
                self._logger.error(
                    "Failed to send notification",
                    claim_id=claim_id,
                    error=str(e),
                    exc_info=True
                )

        notifications_sent = len(notification_ids)

        if notifications_sent == 0:
            return WorkerResult.failure(
                error_message=_("Falha ao enviar todas as notificações"),
                retry=True
            )

        if failed_count > 0:
            self._logger.warning(
                "Some notifications failed",
                claim_id=claim_id,
                sent=notifications_sent,
                failed=failed_count
            )

        output = {
            "notifications_sent": notifications_sent,
            "notification_ids": notification_ids
        }

        self._logger.info(
            "Submission status notifications sent",
            claim_id=claim_id,
            notifications_sent=notifications_sent
        )

        return WorkerResult.ok(output)

    def _build_template(
        self,
        status: str,
        claim_id: str,
        protocol_number: str | None,
        payer_name: str,
        total_amount: float
    ) -> WhatsAppTemplate:
        """
        Build WhatsApp template message based on status.

        Args:
            status: Submission status
            claim_id: Claim identifier
            protocol_number: Protocol number (may be None for failed)
            payer_name: Payer name
            total_amount: Total amount

        Returns:
            WhatsApp template configuration
        """
        # Format amount in Brazilian Real
        amount_str = f"R$ {total_amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        # Build template parameters based on status
        if status == "submitted":
            template_name = "billing_submitted"
            params = [
                claim_id,
                payer_name,
                protocol_number or "N/A",
                amount_str
            ]
        elif status == "acknowledged":
            template_name = "billing_acknowledged"
            params = [
                claim_id,
                payer_name,
                protocol_number or "N/A",
                amount_str
            ]
        elif status == "rejected":
            template_name = "billing_rejected"
            params = [
                claim_id,
                payer_name,
                protocol_number or "N/A",
                amount_str
            ]
        else:  # failed
            template_name = "billing_failed"
            params = [
                claim_id,
                payer_name,
                amount_str
            ]

        # Build components in WhatsApp template format
        components = [
            {
                "type": "body",
                "parameters": [{"type": "text", "text": param} for param in params]
            }
        ]

        return WhatsAppTemplate(
            name=template_name,
            language="pt_BR",
            components=components
        )
