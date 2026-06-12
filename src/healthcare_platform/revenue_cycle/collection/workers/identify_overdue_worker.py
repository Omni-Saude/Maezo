from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from healthcare_platform.revenue_cycle.collection.entities import CollectionCase
from healthcare_platform.revenue_cycle.collection.enums import CollectionPriority, CollectionStatus
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.value_objects import Money, FHIRReference
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class IdentifyOverdueWorker:
    """    Identifica cobranças vencidas e cria casos de cobrança.
    
        Archetype: FINANCIAL_CALCULATION
        """

    WORKER_TYPE = "collection.identify_overdue"

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

    @track_task_execution(metric_name="identify_overdue")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Identifica claims vencidos e cria casos de cobrança.

        Args:
            task_variables: {
                "claim_id": str,
                "amount_due": float,
                "currency": str,
                "due_date": str (ISO format),
                "payer_id": str,
                "patient_id": str,
                "facility_id": str
            }

        Returns:
            {
                "collection_case_id": str,
                "days_overdue": int,
                "amount_due": float,
                "status": str
            }
        """
        claim_id = task_variables["claim_id"]
        due_date_str = task_variables["due_date"]
        amount_due = task_variables["amount_due"]
        currency = task_variables.get("currency", "BRL")

        logger.info(
            _("Verificando vencimento do claim"),
            extra={"claim_id": claim_id, "due_date": due_date_str},
        )

        # Parse due date
        due_date = datetime.fromisoformat(due_date_str.replace("Z", "+00:00"))
        current_date = datetime.now(timezone.utc)

        # Calculate days overdue
        days_overdue = (current_date - due_date).days

        if days_overdue <= 0:
            logger.info(
                _("Claim ainda não está vencido"),
                extra={"claim_id": claim_id, "days_until_due": abs(days_overdue)},
            )
            return {
                "collection_case_id": None,
                "days_overdue": days_overdue,
                "amount_due": amount_due,
                "status": "not_overdue",
            }

        # Create collection case
        collection_case = CollectionCase(
            id=f"CC-{claim_id}",
            claim_reference=FHIRReference(
                reference=f"Claim/{claim_id}",
                display=f"Claim {claim_id}",
            ),
            payer_reference=FHIRReference(
                reference=f"Organization/{task_variables['payer_id']}",
                display=task_variables.get("payer_name", ""),
            ),
            patient_reference=FHIRReference(
                reference=f"Patient/{task_variables['patient_id']}",
                display=task_variables.get("patient_name", ""),
            ),
            facility_reference=FHIRReference(
                reference=f"Organization/{task_variables['facility_id']}",
                display=task_variables.get("facility_name", ""),
            ),
            amount_due=Money(value=amount_due, currency=currency),
            original_due_date=due_date,
            days_overdue=days_overdue,
            status=CollectionStatus.NEW,
            priority=CollectionPriority.MEDIUM,  # Will be recalculated by prioritize worker
            created_at=current_date,
            updated_at=current_date,
        )

        logger.info(
            _("Caso de cobrança criado com sucesso"),
            extra={
                "collection_case_id": collection_case.id,
                "claim_id": claim_id,
                "days_overdue": days_overdue,
                "amount_due": amount_due,
            },
        )

        return {
            "collection_case_id": collection_case.id,
            "days_overdue": days_overdue,
            "amount_due": amount_due,
            "currency": currency,
            "status": "overdue",
            "created_at": current_date.isoformat(),
        }
