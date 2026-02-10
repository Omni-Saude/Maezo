from __future__ import annotations

from typing import Any

from healthcare_platform.revenue_cycle.collection.enums import AgingBucket
from healthcare_platform.revenue_cycle.collection.templates.collection_letters import render_letter
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class GenerateCollectionLetterWorker:
    """Gera cartas de cobrança em português baseadas no bucket de aging."""

    WORKER_TYPE = "generate_collection_letter"

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

    @track_task_execution(metric_name="generate_collection_letter")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Gera carta de cobrança apropriada baseada no aging bucket.

        Args:
            task_variables: {
                "collection_case_id": str,
                "aging_bucket": str,
                "patient_name": str,
                "amount_due": float,
                "currency": str,
                "days_overdue": int,
                "original_due_date": str,
                "facility_name": str,
                "facility_contact": str
            }

        Returns:
            {
                "collection_case_id": str,
                "letter_type": str,
                "letter_content": str,
                "generated_at": str
            }
        """
        from datetime import datetime, timezone

        collection_case_id = task_variables["collection_case_id"]
        aging_bucket = AgingBucket(task_variables["aging_bucket"])

        logger.info(
            _("Gerando carta de cobrança"),
            extra={
                "collection_case_id": collection_case_id,
                "aging_bucket": aging_bucket.value,
            },
        )

        # Select letter type based on aging bucket
        letter_type = self._select_letter_type(aging_bucket)

        # Prepare letter data
        letter_data = {
            "patient_name": task_variables["patient_name"],
            "amount_due": task_variables["amount_due"],
            "currency": task_variables.get("currency", "BRL"),
            "days_overdue": task_variables["days_overdue"],
            "original_due_date": task_variables["original_due_date"],
            "facility_name": task_variables["facility_name"],
            "facility_contact": task_variables["facility_contact"],
            "collection_case_id": collection_case_id,
        }

        # Generate letter content
        letter_content = render_letter(letter_type, letter_data)

        generated_at = datetime.now(timezone.utc).isoformat()

        logger.info(
            _("Carta de cobrança gerada com sucesso"),
            extra={
                "collection_case_id": collection_case_id,
                "letter_type": letter_type,
                "letter_length": len(letter_content),
            },
        )

        return {
            "collection_case_id": collection_case_id,
            "letter_type": letter_type,
            "letter_content": letter_content,
            "generated_at": generated_at,
        }

    def _select_letter_type(self, aging_bucket: AgingBucket) -> str:
        """Seleciona tipo de carta baseado no bucket de aging."""
        if aging_bucket in (AgingBucket.DAYS_0_30, AgingBucket.DAYS_31_60):
            return "first_notice"
        elif aging_bucket in (AgingBucket.DAYS_61_90, AgingBucket.DAYS_91_120):
            return "second_notice"
        else:  # 121+ days
            return "final_notice"
