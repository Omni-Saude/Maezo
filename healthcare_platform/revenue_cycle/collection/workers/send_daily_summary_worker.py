"""Worker for sending daily revenue collection summary."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.whatsapp_client import WhatsAppClient
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class SendDailySummaryWorker:
    """    Envia resumo diário de cobrança via email e WhatsApp.
    
        Archetype: FINANCIAL_CALCULATION
        """

    WORKER_TYPE = "send_daily_summary"

    def __init__(self, whatsapp_client: WhatsAppClient | None = None):
        """Initialize with optional WhatsApp client."""
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

    @track_task_execution(metric_name="send_daily_summary")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Envia resumo diário com métricas chave em português.

        Args:
            task_variables: {
                "date": str (ISO),
                "collection_rate": float,
                "dso": float,
                "amount_collected_today": float,
                "amount_billed_today": float,
                "overdue_count": int,
                "overdue_amount": float,
                "recipients": list[str] (phone numbers for WhatsApp),
                "email_recipients": list[str] (optional)
            }

        Returns:
            {
                "messages_sent": int,
                "emails_sent": int,
                "status": str,
                "failed_recipients": list[str]
            }
        """
        date_str = task_variables["date"]
        collection_rate = task_variables["collection_rate"]
        dso = task_variables["dso"]
        amount_collected = Decimal(str(task_variables["amount_collected_today"]))
        amount_billed = Decimal(str(task_variables["amount_billed_today"]))
        overdue_count = task_variables["overdue_count"]
        overdue_amount = Decimal(str(task_variables["overdue_amount"]))
        recipients = task_variables["recipients"]

        logger.info(
            _("Enviando resumo diário de cobrança"),
            extra={
                "date": date_str,
                "recipients_count": len(recipients),
            },
        )

        # Format summary message in Portuguese
        summary_message = self._format_summary_message(
            date_str,
            collection_rate,
            dso,
            amount_collected,
            amount_billed,
            overdue_count,
            overdue_amount,
        )

        # Send via WhatsApp
        messages_sent = 0
        failed_recipients: list[str] = []

        for recipient in recipients:
            try:
                await self.whatsapp_client.send_message(
                    to=recipient,
                    message=summary_message,
                )
                messages_sent += 1
                logger.debug(
                    _("Resumo enviado via WhatsApp"),
                    extra={"recipient": recipient},
                )
            except Exception as e:
                logger.error(
                    _("Falha ao enviar resumo via WhatsApp"),
                    extra={"recipient": recipient, "error": str(e)},
                )
                failed_recipients.append(recipient)

        # TODO: Send via email (requires email client integration)
        emails_sent = 0

        status = "success" if messages_sent > 0 else "failed"

        logger.info(
            _("Resumo diário enviado"),
            extra={
                "messages_sent": messages_sent,
                "failed": len(failed_recipients),
            },
        )

        return {
            "messages_sent": messages_sent,
            "emails_sent": emails_sent,
            "status": status,
            "failed_recipients": failed_recipients,
        }

    def _format_summary_message(
        self,
        date_str: str,
        collection_rate: float,
        dso: float,
        amount_collected: Decimal,
        amount_billed: Decimal,
        overdue_count: int,
        overdue_amount: Decimal,
    ) -> str:
        """Format daily summary message in Portuguese."""
        return _(
            "📊 *Resumo de Cobrança - {date}*\n\n"
            "💰 *Arrecadado Hoje:* R$ {collected:,.2f}\n"
            "📋 *Faturado Hoje:* R$ {billed:,.2f}\n"
            "📈 *Taxa de Cobrança:* {rate:.1f}%\n"
            "⏱️ *DSO (Prazo Médio):* {dso:.0f} dias\n\n"
            "⚠️ *Valores Vencidos:*\n"
            "   • Quantidade: {overdue_count} casos\n"
            "   • Valor: R$ {overdue_amount:,.2f}\n\n"
            "_Atualizado automaticamente pelo sistema_"
        ).format(
            date=date_str,
            collected=float(amount_collected),
            billed=float(amount_billed),
            rate=collection_rate,
            dso=dso,
            overdue_count=overdue_count,
            overdue_amount=float(overdue_amount),
        )
