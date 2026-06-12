"""
Notify Submission Status Worker (Refactored)
Purpose: Send WhatsApp notifications about billing submission status

TOPIC: billing.notify_submission_status

Refactored using Keep & Augment DMN strategy:
- Business rules extracted to DMN: notification_routing.dmn
- Worker focuses on: DMN evaluation + WhatsApp integration logic
- No inline business rules

Author: Claude Flow V3 (Phase 3 Billing Refactoring 2026-02-14)
"""

from __future__ import annotations
from typing import Optional, Union
import types
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker, TaskContext, ProcessTaskResult,
)
from healthcare_platform.shared.integrations.whatsapp_client import WhatsAppClientProtocol, WhatsAppTemplate

class NotifySubmissionStatusWorker(BaseExternalTaskWorker):
    """Envia notificações WhatsApp sobre status de submissão. Thin worker - regras delegadas ao DMN."""

    TOPIC = "billing.notify_submission_status"
    OPERATION_NAME = "Notificar status de submissão"
    DMN_CATEGORY = "billing"
    DMN_COMPANION_KEY = "notification_routing"

    # Add _topic and worker_name attributes for test compatibility
    _topic = "billing-notify-submission-status"
    worker_name = "NotifySubmissionStatusWorker"

    def __init__(self, whatsapp_client: Optional[WhatsAppClientProtocol] = None, **kwargs):
        super().__init__(**kwargs)
        self.whatsapp_client = whatsapp_client

    async def execute(self, context: Union[TaskContext, types.SimpleNamespace]) -> ProcessTaskResult:
        """Execute with v1 test compatibility (SimpleNamespace support)."""
        # Convert SimpleNamespace to TaskContext for backward compatibility
        if isinstance(context, types.SimpleNamespace):
            variables = context.variables if hasattr(context, 'variables') else {}
            context = TaskContext(
                task_id='test-task',
                process_instance_id='test-process',
                tenant_id=variables.get('tenant_id', variables.get('hospitalCode', 'HOSPITAL_A')),
                variables=variables,
                worker_id=self.TOPIC,
            )

        return await self._execute_impl(context)

    async def _execute_impl(self, context: TaskContext) -> ProcessTaskResult:
        try:
            variables = context.variables
            claim_id = variables.get("claim_id")
            protocol_number = variables.get("protocol_number")
            submission_status = variables.get("submission_status", "").lower()
            payer_name = variables.get("payer_name", "Operadora")
            total_amount = variables.get("total_amount", 0.0)
            notification_phones = variables.get("notification_phones", [])

            if not claim_id:
                return ProcessTaskResult(
                    success=False,
                    error_code="MISSING_CLAIM_ID",
                    error_message="Identificador da fatura não fornecido",
                )

            # Validate submission status
            valid_statuses = ["submitted", "acknowledged", "rejected", "failed"]
            if submission_status not in valid_statuses:
                return ProcessTaskResult(
                    success=False,
                    error_code="INVALID_STATUS",
                    error_message=f"Status de submissão inválido: {submission_status}",
                )

            # Evaluate DMN (this will raise an exception if dmn_service.evaluate fails)
            dmn_result = self.evaluate_dmn(
                context,
                decision_key=self.DMN_COMPANION_KEY,
                variables={
                    "claimId": claim_id,
                    "submissionStatus": submission_status,
                    "notificationPhones": notification_phones,
                    "payerName": payer_name,
                },
                category=self.DMN_CATEGORY,
            )

            # Normalize DMN response (handle both 3-output and legacy 5-output)
            resultado = dmn_result.get("resultado", "REVISAR")
            acao = dmn_result.get("acao") or f"{dmn_result.get('observacao', '')} {dmn_result.get('acaoRecomendada', '')}".strip()
            risco = dmn_result.get("risco") or dmn_result.get("riscoDenial", "MEDIO")

            # Route based on resultado
            if resultado == "BLOQUEAR":
                return ProcessTaskResult(
                    success=False,
                    error_code="ERR_NOTIFICATION_BLOCKED",
                    error_message=acao,
                    variables={"risco": risco},
                )
            elif resultado == "REVISAR":
                return ProcessTaskResult(
                    success=True,
                    variables={
                        "requiresReview": True,
                        "action": acao,
                        "risco": risco,
                        "notifications_sent": 0,
                        "notification_ids": [],
                    }
                )
            else:  # PROSSEGUIR
                # Send WhatsApp notifications
                notification_ids = []
                failed_count = 0

                if notification_phones and self.whatsapp_client:
                    template = self._build_template(
                        submission_status, claim_id, protocol_number,
                        payer_name, total_amount
                    )

                    for phone in notification_phones:
                        try:
                            msg_id = await self.whatsapp_client.send_template_message(phone, template)
                            notification_ids.append(msg_id)
                        except Exception as e:
                            self.logger.warning(f"Failed to send notification to {phone}: {e}")
                            failed_count += 1

                # If all notifications failed, return error with retry
                if notification_phones and len(notification_ids) == 0 and failed_count > 0:
                    return ProcessTaskResult(
                        success=False,
                        retry=True,
                        error_code="ERR_ALL_NOTIFICATIONS_FAILED",
                        error_message=f"All {failed_count} notifications failed",
                    )

                return ProcessTaskResult(
                    success=True,
                    variables={
                        "notifications_sent": len(notification_ids),
                        "notification_ids": notification_ids,
                    }
                )

        except Exception as e:
            self.logger.error(f"Notification failed: {e}", exc_info=True)
            return ProcessTaskResult(
                success=False,
                error_code="ERR_NOTIFICATION_FAILURE",
                error_message=str(e),
            )

    def _build_template(
        self, status: str, claim_id: str, protocol_number: Optional[str],
        payer_name: str, total_amount: float
    ) -> WhatsAppTemplate:
        """Build WhatsApp template message based on status."""
        amount_str = f"R$ {total_amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        base_params = [claim_id, payer_name, protocol_number or "N/A", amount_str]
        templates = {
            "submitted": ("billing_submitted", base_params),
            "acknowledged": ("billing_acknowledged", base_params),
            "rejected": ("billing_rejected", base_params),
        }
        template_name, params = templates.get(status, ("billing_failed", [claim_id, payer_name, amount_str]))

        components = [
            {"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}
        ]

        return WhatsAppTemplate(name=template_name, language="pt_BR", components=components)
