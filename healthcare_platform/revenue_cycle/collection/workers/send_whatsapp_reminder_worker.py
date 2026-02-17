from __future__ import annotations

from typing import Any

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.whatsapp_client import WhatsAppClient, WhatsAppTemplate
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class SendWhatsAppReminderWorker:
    """    Envia lembretes de pagamento via WhatsApp (LGPD compliant).
    
        Archetype: FINANCIAL_CALCULATION
        """

    WORKER_TYPE = "send_whatsapp_reminder"

    def __init__(self, whatsapp_client: WhatsAppClient | None = None):
        """
        Initialize worker with WhatsApp client.

        Args:
            whatsapp_client: Client for WhatsApp integration (injected for testing)
        """
        self.whatsapp_client = whatsapp_client or WhatsAppClient()
        self.dmn_service = FederatedDMNService()
        self._logger = get_logger(__name__)

    def _evaluate_cash_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate cash_operations DMN decision table via federation service."""
        try:
            return self.dmn_service.evaluate(
                tenant_id='default',
                category='cash_operations',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    @track_task_execution(metric_name="send_whatsapp_reminder")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Envia lembrete de pagamento via WhatsApp.

        Args:
            task_variables: {
                "collection_case_id": str,
                "patient_phone": str,
                "patient_first_name": str,
                "amount_due": float,
                "currency": str,
                "days_overdue": int,
                "payment_link": str (optional)
            }

        Returns:
            {
                "collection_case_id": str,
                "message_id": str,
                "status": str,
                "sent_at": str
            }
        """
        from datetime import datetime, timezone

        collection_case_id = task_variables["collection_case_id"]
        patient_phone = task_variables["patient_phone"]
        patient_first_name = task_variables["patient_first_name"]
        amount_due = task_variables["amount_due"]
        currency = task_variables.get("currency", "BRL")
        days_overdue = task_variables["days_overdue"]
        payment_link = task_variables.get("payment_link")

        # LGPD compliance: only log non-PII
        logger.info(
            _("Enviando lembrete de pagamento via WhatsApp"),
            extra={
                "collection_case_id": collection_case_id,
                "days_overdue": days_overdue,
                "amount": amount_due,
            },
        )

        # Select template based on days overdue
        template_name = self._select_template(days_overdue)

        # Prepare template parameters (no PII in logs)
        template_params = {
            "patient_first_name": patient_first_name,
            "amount": f"{currency} {amount_due:.2f}",
            "days_overdue": str(days_overdue),
        }

        if payment_link:
            template_params["payment_link"] = payment_link

        # Create WhatsApp template
        template = WhatsAppTemplate(
            name=template_name,
            language="pt_BR",
            parameters=template_params,
        )

        # Send message
        result = await self.whatsapp_client.send_template_message(
            phone_number=patient_phone,
            template=template,
        )

        sent_at = datetime.now(timezone.utc).isoformat()

        logger.info(
            _("Lembrete de pagamento enviado com sucesso"),
            extra={
                "collection_case_id": collection_case_id,
                "message_id": result.get("message_id"),
                "status": result.get("status"),
            },
        )

        return {
            "collection_case_id": collection_case_id,
            "message_id": result.get("message_id"),
            "status": result.get("status", "sent"),
            "sent_at": sent_at,
            "template_name": template_name,
        }

    def _select_template(self, days_overdue: int) -> str:
        """Seleciona template de WhatsApp baseado em dias vencidos."""
        if days_overdue <= 7:
            return "payment_reminder_gentle"
        elif days_overdue <= 30:
            return "payment_reminder_urgent"
        else:
            return "payment_reminder_final"
