"""Worker: Detect duplicate payments before processing."""
from __future__ import annotations

from typing import Any, Protocol

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.revenue_cycle.collection.exceptions import DuplicatePaymentError

logger = get_logger(__name__)


class PaymentRepository(Protocol):
    """    Protocol for payment repository (dependency injection).
    
        Archetype: FINANCIAL_CALCULATION
        """

    async def find_by_transaction_id(self, transaction_id: str) -> Any | None:
        """Find payment by transaction_id."""
        ...

    async def find_by_nosso_numero(self, nosso_numero: str) -> Any | None:
        """Find payment by nosso_numero (bank reference)."""
        ...

    async def find_by_composite_key(
        self, amount: str, payment_date: str, payer_document: str
    ) -> Any | None:
        """Find payment by composite key (amount+date+payer)."""
        ...


class DetectDuplicatePaymentWorker:
    """Detects duplicate payments using multiple strategies."""

    WORKER_TYPE = "collection.detect_duplicate_payment"

    def __init__(self, repository: PaymentRepository | None = None) -> None:
        """Initialize worker with payment repository.

        Args:
            repository: Payment repository for duplicate checks.
        """
        self.repository = repository
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

    @track_task_execution(metric_name="detect_duplicate_payment")
    async def execute(self, task_variables: dict) -> dict:
        """Execute duplicate payment detection.

        Args:
            task_variables: Payment data to check.

        Returns:
            Dict with duplicate_check_passed=True.

        Raises:
            DuplicatePaymentError: If duplicate detected.
        """
        transaction_id = task_variables.get("transaction_id", "")
        nosso_numero = task_variables.get("nosso_numero", "")
        gross_amount = task_variables.get("gross_amount", "")
        payment_date_str = task_variables.get("payment_date", "")
        payer_document = task_variables.get("payer_document", "")

        logger.info("duplicate_check_started", transaction_id=transaction_id)

        if not self.repository:
            logger.warning("no_repository_configured_skipping_duplicate_check")
            return {**task_variables, "duplicate_check_passed": True}

        # Strategy 1: Check by transaction_id
        if transaction_id:
            existing = await self.repository.find_by_transaction_id(transaction_id)
            if existing:
                logger.warning("duplicate_payment_transaction_id", transaction_id=transaction_id)
                raise DuplicatePaymentError(
                    _("Pagamento duplicado detectado por transaction_id: {id}").format(
                        id=transaction_id
                    ),
                    details={"transaction_id": transaction_id},
                )

        # Strategy 2: Check by nosso_numero
        if nosso_numero:
            existing = await self.repository.find_by_nosso_numero(nosso_numero)
            if existing:
                logger.warning("duplicate_payment_nosso_numero", nosso_numero=nosso_numero)
                raise DuplicatePaymentError(
                    _("Pagamento duplicado detectado por nosso_numero: {num}").format(
                        num=nosso_numero
                    ),
                    details={"nosso_numero": nosso_numero},
                )

        # Strategy 3: Check by composite key (amount + date + payer)
        if gross_amount and payment_date_str and payer_document:
            existing = await self.repository.find_by_composite_key(
                amount=gross_amount,
                payment_date=payment_date_str,
                payer_document=payer_document,
            )
            if existing:
                logger.warning(
                    "duplicate_payment_composite",
                    amount=gross_amount,
                    date=payment_date_str,
                    payer=payer_document[:8],
                )
                raise DuplicatePaymentError(
                    _("Pagamento duplicado detectado por valor+data+pagador"),
                    details={
                        "amount": gross_amount,
                        "payment_date": payment_date_str,
                        "payer_document": payer_document,
                    },
                )

        logger.info("duplicate_check_passed", transaction_id=transaction_id)
        return {**task_variables, "duplicate_check_passed": True}
