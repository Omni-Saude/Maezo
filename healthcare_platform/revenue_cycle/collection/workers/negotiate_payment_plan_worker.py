from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from healthcare_platform.revenue_cycle.collection.entities import PaymentPlan
from healthcare_platform.revenue_cycle.collection.exceptions import PaymentPlanError
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.value_objects import Money
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class NegotiatePaymentPlanWorker:
    """Negocia plano de pagamento parcelado (max 12x, mínimo R$100/parcela)."""

    WORKER_TYPE = "negotiate_payment_plan"

    MAX_INSTALLMENTS = 12
    MIN_INSTALLMENT_AMOUNT = 100.0

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

    @track_task_execution(metric_name="negotiate_payment_plan")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Cria plano de pagamento parcelado.

        Args:
            task_variables: {
                "collection_case_id": str,
                "amount_due": float,
                "currency": str,
                "num_installments": int,
                "first_payment_date": str (ISO format, optional),
                "interest_rate": float (optional, default 0)
            }

        Returns:
            {
                "payment_plan_id": str,
                "collection_case_id": str,
                "num_installments": int,
                "installment_amount": float,
                "total_amount": float,
                "schedule": list[dict]
            }
        """
        collection_case_id = task_variables["collection_case_id"]
        amount_due = task_variables["amount_due"]
        currency = task_variables.get("currency", "BRL")
        num_installments = task_variables["num_installments"]
        interest_rate = task_variables.get("interest_rate", 0.0)

        logger.info(
            _("Negociando plano de pagamento"),
            extra={
                "collection_case_id": collection_case_id,
                "amount_due": amount_due,
                "num_installments": num_installments,
            },
        )

        # Validate installments
        if num_installments < 1:
            raise PaymentPlanError(_("Número de parcelas deve ser no mínimo 1"))

        if num_installments > self.MAX_INSTALLMENTS:
            raise PaymentPlanError(
                _("Número de parcelas não pode exceder {max}").format(
                    max=self.MAX_INSTALLMENTS
                )
            )

        # Calculate installment amount
        total_amount = amount_due * (1 + interest_rate)
        installment_amount = total_amount / num_installments

        # Validate minimum installment
        if installment_amount < self.MIN_INSTALLMENT_AMOUNT:
            raise PaymentPlanError(
                _(
                    "Valor da parcela (R$ {amount:.2f}) é menor que o mínimo permitido (R$ {min:.2f})"
                ).format(amount=installment_amount, min=self.MIN_INSTALLMENT_AMOUNT)
            )

        # Parse first payment date
        first_payment_str = task_variables.get("first_payment_date")
        if first_payment_str:
            first_payment_date = datetime.fromisoformat(
                first_payment_str.replace("Z", "+00:00")
            )
        else:
            # Default: 7 days from now
            first_payment_date = datetime.now(timezone.utc) + timedelta(days=7)

        # Generate payment schedule
        schedule = self._generate_schedule(
            num_installments, installment_amount, currency, first_payment_date
        )

        # Create PaymentPlan entity
        payment_plan_id = f"PP-{uuid4().hex[:12].upper()}"
        payment_plan = PaymentPlan(
            id=payment_plan_id,
            collection_case_id=collection_case_id,
            total_amount=Money(value=total_amount, currency=currency),
            num_installments=num_installments,
            installment_amount=Money(value=installment_amount, currency=currency),
            interest_rate=interest_rate,
            first_payment_date=first_payment_date,
            schedule=schedule,
            created_at=datetime.now(timezone.utc),
        )

        logger.info(
            _("Plano de pagamento criado com sucesso"),
            extra={
                "payment_plan_id": payment_plan_id,
                "collection_case_id": collection_case_id,
                "num_installments": num_installments,
                "installment_amount": installment_amount,
            },
        )

        return {
            "payment_plan_id": payment_plan_id,
            "collection_case_id": collection_case_id,
            "num_installments": num_installments,
            "installment_amount": installment_amount,
            "total_amount": total_amount,
            "currency": currency,
            "schedule": [
                {
                    "installment_number": item["installment_number"],
                    "due_date": item["due_date"].isoformat(),
                    "amount": item["amount"],
                }
                for item in schedule
            ],
        }

    def _generate_schedule(
        self,
        num_installments: int,
        installment_amount: float,
        currency: str,
        first_payment_date: datetime,
    ) -> list[dict[str, Any]]:
        """Gera cronograma de pagamento mensal."""
        schedule = []
        current_date = first_payment_date

        for i in range(1, num_installments + 1):
            schedule.append(
                {
                    "installment_number": i,
                    "due_date": current_date,
                    "amount": installment_amount,
                    "currency": currency,
                    "status": "pending",
                }
            )
            # Next installment: 30 days later
            current_date = current_date + timedelta(days=30)

        return schedule
