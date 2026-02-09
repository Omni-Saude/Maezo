"""Worker: Persist validated payment to database."""
from __future__ import annotations

from collections.abc import Protocol
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from platform.shared.domain.enums import TenantCode
from platform.shared.domain.value_objects import FHIRReference, Money
from platform.shared.i18n import _
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution
from platform.revenue_cycle.collection.entities import Payment
from platform.revenue_cycle.collection.enums import (
    CNABFormat,
    PaymentMethod,
    PaymentStatus,
    PaymentType,
)
from platform.revenue_cycle.collection.exceptions import CollectionException

logger = get_logger(__name__)


class PaymentRepository(Protocol):
    """Protocol for payment repository (dependency injection)."""

    async def save(self, payment: Payment) -> UUID:
        """Save payment and return UUID."""
        ...


class PersistPaymentWorker:
    """Persists validated Payment entity to database."""

    WORKER_TYPE = "persist_payment"

    def __init__(self, repository: PaymentRepository | None = None) -> None:
        """Initialize worker with payment repository.

        Args:
            repository: Payment repository for persistence.
        """
        self.repository = repository

    @track_task_execution(metric_name="persist_payment")
    async def execute(self, task_variables: dict) -> dict:
        """Execute payment persistence.

        Args:
            task_variables: Complete payment data.

        Returns:
            Dict with payment_id (UUID string).

        Raises:
            CollectionException: If persistence fails.
        """
        if not self.repository:
            raise CollectionException(
                _("Repositório de pagamento não configurado"),
                bpmn_error_code="PAYMENT_REPO_NOT_CONFIGURED",
            )

        logger.info("payment_persistence_started", transaction_id=task_variables.get("transaction_id"))

        # Build Payment entity
        try:
            payment = Payment(
                tenant_id=TenantCode(task_variables.get("tenant_id", "hospital_a")),
                status=PaymentStatus.RECEIVED,
                payment_type=PaymentType(task_variables.get("payment_type", "full")),
                payment_method=PaymentMethod(task_variables.get("payment_method", "bank_transfer")),
                gross_amount=Money.brl(task_variables.get("gross_amount", "0")),
                net_amount=Money.brl(task_variables.get("net_amount", "0")),
                fees=Money.brl(task_variables.get("bank_fees", "0")),
                payer_reference=self._build_payer_reference(task_variables),
                bank_code=task_variables.get("bank_code", ""),
                agency=task_variables.get("agency", ""),
                account=task_variables.get("account", ""),
                transaction_id=task_variables.get("transaction_id", ""),
                cnab_format=self._parse_cnab_format(task_variables.get("cnab_format")),
                cnab_line_number=task_variables.get("cnab_line_number"),
                payment_date=self._parse_date(task_variables.get("payment_date")),
                received_at=datetime.utcnow(),
                source_file=task_variables.get("source_file", ""),
                currency=task_variables.get("currency", "BRL"),
                notes=task_variables.get("notes", ""),
            )
        except Exception as exc:
            logger.error("payment_entity_creation_failed", error=str(exc))
            raise CollectionException(
                _("Falha ao criar entidade Payment: {err}").format(err=str(exc)),
                bpmn_error_code="PAYMENT_ENTITY_ERROR",
            ) from exc

        # Persist to database
        try:
            payment_id = await self.repository.save(payment)
        except Exception as exc:
            logger.error("payment_persistence_failed", error=str(exc))
            raise CollectionException(
                _("Falha ao persistir pagamento: {err}").format(err=str(exc)),
                bpmn_error_code="PAYMENT_PERSISTENCE_ERROR",
                retryable=True,
            ) from exc

        logger.info(
            "payment_persisted",
            payment_id=str(payment_id),
            transaction_id=payment.transaction_id,
            net_amount=str(payment.net_amount.amount),
        )

        return {
            **task_variables,
            "payment_id": str(payment_id),
            "payment_status": payment.status.value,
        }

    def _build_payer_reference(self, variables: dict) -> FHIRReference | None:
        """Build payer FHIR reference if payer info available."""
        payer_id = variables.get("payer_id")
        if not payer_id:
            return None
        return FHIRReference(
            reference=f"Organization/{payer_id}",
            type="Organization",
            display=variables.get("payer_name", ""),
        )

    def _parse_cnab_format(self, format_str: str | None) -> CNABFormat | None:
        """Parse CNAB format from string."""
        if not format_str:
            return None
        try:
            return CNABFormat(format_str)
        except ValueError:
            return None

    def _parse_date(self, date_str: str | None) -> Any:
        """Parse date from ISO string."""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str).date()
        except (ValueError, TypeError):
            return None
