"""Worker: Validate payment data before processing."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from platform.shared.i18n import _
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution
from platform.revenue_cycle.collection.exceptions import PaymentValidationError

logger = get_logger(__name__)


class PaymentDataDTO(BaseModel):
    """Payment data for validation."""

    transaction_id: str = Field(..., min_length=1)
    gross_amount: Decimal = Field(..., gt=0)
    currency: str = Field(..., pattern=r"^[A-Z]{3}$")
    payment_date: str | None = None
    payer_name: str = Field(..., min_length=1)
    payer_document: str = Field(..., min_length=1)
    bank_code: str = Field(..., min_length=1)

    @field_validator("payment_date")
    @classmethod
    def validate_date(cls, v: str | None) -> str | None:
        """Validate payment date is not in future."""
        if v is None:
            return v
        try:
            payment_dt = datetime.fromisoformat(v).date()
            if payment_dt > date.today():
                raise ValueError("Data de pagamento não pode ser futura")
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Data de pagamento inválida: {exc}")
        return v


class ValidatePaymentDataWorker:
    """Validates payment data before processing."""

    WORKER_TYPE = "validate_payment_data"

    @track_task_execution(metric_name="validate_payment_data")
    async def execute(self, task_variables: dict) -> dict:
        """Execute payment data validation.

        Args:
            task_variables: Payment data to validate.

        Returns:
            Dict with validation_status='valid'.

        Raises:
            PaymentValidationError: If validation fails.
        """
        logger.info("payment_validation_started", transaction_id=task_variables.get("transaction_id"))

        # Validate required fields
        required_fields = [
            "transaction_id",
            "gross_amount",
            "currency",
            "payer_name",
            "payer_document",
            "bank_code",
        ]
        missing = [f for f in required_fields if not task_variables.get(f)]
        if missing:
            raise PaymentValidationError(
                _("Campos obrigatórios ausentes: {fields}").format(fields=", ".join(missing))
            )

        # Validate using Pydantic
        try:
            payment = PaymentDataDTO(
                transaction_id=task_variables["transaction_id"],
                gross_amount=Decimal(str(task_variables["gross_amount"])),
                currency=task_variables["currency"],
                payment_date=task_variables.get("payment_date"),
                payer_name=task_variables["payer_name"],
                payer_document=task_variables["payer_document"],
                bank_code=task_variables["bank_code"],
            )
        except Exception as exc:
            logger.error("payment_validation_failed", error=str(exc))
            raise PaymentValidationError(
                _("Validação de dados de pagamento falhou: {err}").format(err=str(exc))
            ) from exc

        # Business rules validation
        if payment.currency != "BRL":
            logger.warning("non_brl_payment", currency=payment.currency)

        if payment.gross_amount <= 0:
            raise PaymentValidationError(
                _("Valor do pagamento deve ser maior que zero: {amount}").format(
                    amount=payment.gross_amount
                )
            )

        logger.info(
            "payment_validation_success",
            transaction_id=payment.transaction_id,
            amount=str(payment.gross_amount),
        )

        return {
            **task_variables,
            "validation_status": "valid",
            "validated_at": datetime.utcnow().isoformat(),
        }
