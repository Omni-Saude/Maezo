from __future__ import annotations

from typing import Any

from healthcare_platform.revenue_cycle.collection.enums import CollectionPriority
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class PrioritizeCollectionWorker:
    """    Calcula prioridade de cobrança baseado em múltiplos fatores.
    
        Archetype: FINANCIAL_CALCULATION
        """

    WORKER_TYPE = "prioritize_collection"

    # Score weights
    AMOUNT_WEIGHT = 0.40
    DAYS_OVERDUE_WEIGHT = 0.30
    PAYER_HISTORY_WEIGHT = 0.20
    CLAIM_TYPE_WEIGHT = 0.10

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

    @track_task_execution(metric_name="prioritize_collection")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Calcula score de prioridade e atribui prioridade.

        Args:
            task_variables: {
                "collection_case_id": str,
                "amount_due": float,
                "days_overdue": int,
                "payer_default_rate": float (0-1),
                "claim_type": str ("inpatient"|"outpatient"|"emergency")
            }

        Returns:
            {
                "collection_case_id": str,
                "priority": str,
                "priority_score": float,
                "score_breakdown": dict
            }
        """
        collection_case_id = task_variables["collection_case_id"]
        amount_due = task_variables["amount_due"]
        days_overdue = task_variables["days_overdue"]
        payer_default_rate = task_variables.get("payer_default_rate", 0.0)
        claim_type = task_variables.get("claim_type", "outpatient")

        logger.info(
            _("Calculando prioridade de cobrança"),
            extra={
                "collection_case_id": collection_case_id,
                "amount_due": amount_due,
                "days_overdue": days_overdue,
            },
        )

        # Calculate individual scores (normalized 0-100)
        amount_score = self._calculate_amount_score(amount_due)
        days_overdue_score = self._calculate_days_overdue_score(days_overdue)
        payer_history_score = self._calculate_payer_history_score(payer_default_rate)
        claim_type_score = self._calculate_claim_type_score(claim_type)

        # Calculate weighted total score
        priority_score = (
            amount_score * self.AMOUNT_WEIGHT
            + days_overdue_score * self.DAYS_OVERDUE_WEIGHT
            + payer_history_score * self.PAYER_HISTORY_WEIGHT
            + claim_type_score * self.CLAIM_TYPE_WEIGHT
        )

        # Assign priority based on score
        if priority_score >= 80:
            priority = CollectionPriority.CRITICAL
        elif priority_score >= 60:
            priority = CollectionPriority.HIGH
        elif priority_score >= 40:
            priority = CollectionPriority.MEDIUM
        else:
            priority = CollectionPriority.LOW

        score_breakdown = {
            "amount_score": round(amount_score, 2),
            "days_overdue_score": round(days_overdue_score, 2),
            "payer_history_score": round(payer_history_score, 2),
            "claim_type_score": round(claim_type_score, 2),
        }

        logger.info(
            _("Prioridade de cobrança calculada"),
            extra={
                "collection_case_id": collection_case_id,
                "priority": priority.value,
                "priority_score": round(priority_score, 2),
            },
        )

        return {
            "collection_case_id": collection_case_id,
            "priority": priority.value,
            "priority_score": round(priority_score, 2),
            "score_breakdown": score_breakdown,
        }

    def _calculate_amount_score(self, amount: float) -> float:
        """Calcula score baseado no valor (0-100)."""
        # R$ 0-1000: 0-30, R$ 1000-5000: 30-60, R$ 5000-10000: 60-80, R$ 10000+: 80-100
        if amount < 1000:
            return (amount / 1000) * 30
        elif amount < 5000:
            return 30 + ((amount - 1000) / 4000) * 30
        elif amount < 10000:
            return 60 + ((amount - 5000) / 5000) * 20
        else:
            return min(80 + ((amount - 10000) / 10000) * 20, 100)

    def _calculate_days_overdue_score(self, days: int) -> float:
        """Calcula score baseado em dias vencidos (0-100)."""
        # 0-30: 0-25, 31-60: 25-50, 61-90: 50-75, 91+: 75-100
        if days <= 30:
            return (days / 30) * 25
        elif days <= 60:
            return 25 + ((days - 30) / 30) * 25
        elif days <= 90:
            return 50 + ((days - 60) / 30) * 25
        else:
            return min(75 + ((days - 90) / 90) * 25, 100)

    def _calculate_payer_history_score(self, default_rate: float) -> float:
        """Calcula score baseado no histórico do pagador (0-100)."""
        # Higher default rate = higher score (more urgent)
        return default_rate * 100

    def _calculate_claim_type_score(self, claim_type: str) -> float:
        """Calcula score baseado no tipo de atendimento (0-100)."""
        type_scores = {
            "emergency": 100,  # Emergência: alta prioridade
            "inpatient": 70,  # Internação: média-alta prioridade
            "outpatient": 40,  # Ambulatorial: média prioridade
        }
        return type_scores.get(claim_type.lower(), 40)
