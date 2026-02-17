from __future__ import annotations

from typing import Any
from uuid import uuid4

from healthcare_platform.revenue_cycle.collection.enums import CollectionAction, CollectionStatus
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class EscalateToLegalWorker:
    """    Escalona caso para departamento jurídico (180+ dias ou >R$50k).
    
        Archetype: FINANCIAL_CALCULATION
        """

    WORKER_TYPE = "escalate_to_legal"

    ESCALATION_THRESHOLD_DAYS = 180
    ESCALATION_THRESHOLD_AMOUNT = 50000.0

    def __init__(self) -> None:
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

    @track_task_execution(metric_name="escalate_to_legal")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Escalona caso para departamento jurídico.

        Args:
            task_variables: {
                "collection_case_id": str,
                "amount_due": float,
                "currency": str,
                "days_overdue": int,
                "patient_name": str,
                "patient_cpf": str,
                "claim_id": str,
                "collection_attempts": int,
                "reason": str (optional)
            }

        Returns:
            {
                "collection_case_id": str,
                "legal_case_id": str,
                "escalated": bool,
                "escalation_reason": str,
                "escalated_at": str
            }
        """
        from datetime import datetime, timezone

        collection_case_id = task_variables["collection_case_id"]
        amount_due = task_variables["amount_due"]
        currency = task_variables.get("currency", "BRL")
        days_overdue = task_variables["days_overdue"]
        reason = task_variables.get("reason")

        logger.info(
            _("Avaliando escalação para jurídico"),
            extra={
                "collection_case_id": collection_case_id,
                "amount_due": amount_due,
                "days_overdue": days_overdue,
            },
        )

        # Determine if escalation is warranted
        should_escalate, escalation_reason = self._should_escalate(
            days_overdue, amount_due, reason
        )

        if not should_escalate:
            logger.info(
                _("Caso não atende critérios para escalação jurídica"),
                extra={
                    "collection_case_id": collection_case_id,
                    "reason": escalation_reason,
                },
            )
            return {
                "collection_case_id": collection_case_id,
                "legal_case_id": None,
                "escalated": False,
                "escalation_reason": escalation_reason,
                "escalated_at": None,
            }

        # Create legal case
        legal_case_id = f"LEGAL-{uuid4().hex[:12].upper()}"
        escalated_at = datetime.now(timezone.utc).isoformat()

        # Prepare legal case data
        legal_case_data = {
            "legal_case_id": legal_case_id,
            "collection_case_id": collection_case_id,
            "patient_name": task_variables["patient_name"],
            "patient_cpf": task_variables["patient_cpf"],
            "claim_id": task_variables["claim_id"],
            "amount_due": amount_due,
            "currency": currency,
            "days_overdue": days_overdue,
            "collection_attempts": task_variables.get("collection_attempts", 0),
            "escalation_reason": escalation_reason,
            "status": "pending_review",
            "created_at": escalated_at,
        }

        logger.info(
            _("Caso escalonado para departamento jurídico"),
            extra={
                "collection_case_id": collection_case_id,
                "legal_case_id": legal_case_id,
                "escalation_reason": escalation_reason,
                "amount_due": amount_due,
            },
        )

        return {
            "collection_case_id": collection_case_id,
            "legal_case_id": legal_case_id,
            "escalated": True,
            "escalation_reason": escalation_reason,
            "escalated_at": escalated_at,
            "legal_case_data": legal_case_data,
            "new_status": CollectionStatus.LEGAL.value,
            "action_taken": CollectionAction.ESCALATE_TO_LEGAL.value,
        }

    def _should_escalate(
        self, days_overdue: int, amount_due: float, explicit_reason: str | None
    ) -> tuple[bool, str]:
        """Determina se caso deve ser escalonado para jurídico."""
        # Explicit reason provided
        if explicit_reason:
            return True, explicit_reason

        # Days overdue threshold
        if days_overdue >= self.ESCALATION_THRESHOLD_DAYS:
            return (
                True,
                _(
                    "Vencido há {days} dias (limite: {threshold} dias)"
                ).format(days=days_overdue, threshold=self.ESCALATION_THRESHOLD_DAYS),
            )

        # Amount threshold
        if amount_due >= self.ESCALATION_THRESHOLD_AMOUNT:
            return (
                True,
                _(
                    "Valor devido R$ {amount:.2f} excede limite de R$ {threshold:.2f}"
                ).format(amount=amount_due, threshold=self.ESCALATION_THRESHOLD_AMOUNT),
            )

        return False, _("Caso não atende critérios para escalação jurídica")
