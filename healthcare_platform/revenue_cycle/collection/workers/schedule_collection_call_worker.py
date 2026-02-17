from __future__ import annotations

from typing import Any
from uuid import uuid4

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class ScheduleCollectionCallWorker:
    """    Agenda ligação de cobrança como human task no CIB7.
    
        Archetype: FINANCIAL_CALCULATION
        """

    WORKER_TYPE = "schedule_collection_call"

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

    @track_task_execution(metric_name="schedule_collection_call")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Cria human task para ligação de cobrança.

        Args:
            task_variables: {
                "collection_case_id": str,
                "patient_name": str,
                "patient_phone": str,
                "amount_due": float,
                "currency": str,
                "days_overdue": int,
                "priority": str,
                "assigned_to": str (optional - user/group)
            }

        Returns:
            {
                "collection_case_id": str,
                "task_id": str,
                "task_type": "human_task",
                "status": str,
                "created_at": str,
                "assigned_to": str
            }
        """
        from datetime import datetime, timezone

        collection_case_id = task_variables["collection_case_id"]
        patient_name = task_variables["patient_name"]
        patient_phone = task_variables["patient_phone"]
        amount_due = task_variables["amount_due"]
        currency = task_variables.get("currency", "BRL")
        days_overdue = task_variables["days_overdue"]
        priority = task_variables.get("priority", "MEDIUM")
        assigned_to = task_variables.get("assigned_to", "collection_team")

        logger.info(
            _("Agendando ligação de cobrança"),
            extra={
                "collection_case_id": collection_case_id,
                "priority": priority,
                "days_overdue": days_overdue,
            },
        )

        # Generate task ID
        task_id = f"CALL-{uuid4().hex[:12].upper()}"

        # Prepare task data for CIB7
        task_data = {
            "task_id": task_id,
            "task_type": "human_task",
            "task_name": _("Ligação de Cobrança"),
            "description": self._build_task_description(
                collection_case_id, amount_due, currency, days_overdue
            ),
            "priority": priority,
            "collection_case_id": collection_case_id,
            "patient_name": patient_name,
            "patient_phone": patient_phone,
            "amount_due": amount_due,
            "currency": currency,
            "days_overdue": days_overdue,
            "assigned_to": assigned_to,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "due_by": self._calculate_due_by(days_overdue, priority),
        }

        logger.info(
            _("Tarefa de ligação de cobrança criada"),
            extra={
                "collection_case_id": collection_case_id,
                "task_id": task_id,
                "assigned_to": assigned_to,
                "priority": priority,
            },
        )

        return {
            "collection_case_id": collection_case_id,
            "task_id": task_id,
            "task_type": "human_task",
            "status": "pending",
            "created_at": task_data["created_at"],
            "assigned_to": assigned_to,
            "due_by": task_data["due_by"],
        }

    def _build_task_description(
        self,
        collection_case_id: str,
        amount_due: float,
        currency: str,
        days_overdue: int,
    ) -> str:
        """Constrói descrição da tarefa de cobrança."""
        return _(
            "Realizar ligação de cobrança para o caso {case_id}. "
            "Valor devido: {currency} {amount:.2f}. "
            "Vencido há {days} dias. "
            "Objetivo: Negociar pagamento ou acordo de parcelamento."
        ).format(
            case_id=collection_case_id,
            currency=currency,
            amount=amount_due,
            days=days_overdue,
        )

    def _calculate_due_by(self, days_overdue: int, priority: str) -> str:
        """Calcula prazo para execução da tarefa baseado na urgência."""
        from datetime import datetime, timedelta, timezone

        # Priority-based SLA (business hours)
        sla_hours = {
            "CRITICAL": 4,  # 4 hours
            "HIGH": 24,  # 1 day
            "MEDIUM": 48,  # 2 days
            "LOW": 72,  # 3 days
        }

        # Further urgency if severely overdue
        if days_overdue > 90:
            hours = min(sla_hours.get(priority, 48), 8)
        else:
            hours = sla_hours.get(priority, 48)

        due_by = datetime.now(timezone.utc) + timedelta(hours=hours)
        return due_by.isoformat()
