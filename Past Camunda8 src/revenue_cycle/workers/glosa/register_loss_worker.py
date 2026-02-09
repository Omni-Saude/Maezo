"""
RegisterLossWorker - Zeebe worker for registering unsuccessful glosa appeal.

This worker records denied appeals where the glosa could not be reversed,
tracking loss amounts and appeal methods for analytics and process improvement.

Business Rule: RN-GLOSA-007-RegisterLoss.md
Regulatory Compliance: ANS RN 424/2017 (final appeal determination), CPC 25 (loss recording)
Migrated from: com.hospital.revenuecycle.delegates.glosa.RegisterLossDelegate
Topic: register-loss
BPMN Task: Task_Register_Loss (Registrar Perda)

CPC 25 Compliance:
- Creates write-off journal entries (Bad Debt Expense / Accounts Receivable)
- Realizes provisions (ACTIVE → REALIZED status)
- Updates financial metrics for loss tracking
- Publishes notifications to finance team and management
"""

from __future__ import annotations

import time
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

import structlog

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.domain.value_objects.provision import (
    AccountingEntry,
    ERPSyncStatus,
    ProvisionStatus,
)
from revenue_cycle.services.accounting import AccountingService
from revenue_cycle.services.database import DatabaseService, get_database_service
from revenue_cycle.services.erp_client import ERPClient
from revenue_cycle.services.kafka_producer import KafkaProducer
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


@worker(topic="register-loss", max_jobs=8, lock_duration=60000)
class RegisterLossWorker(BaseWorker):
    """
    Zeebe worker for registering unsuccessful glosa appeals with CPC 25 accounting.

    BPMN Task: Task_Register_Loss
    Topic: register-loss

    This worker performs:
    1. Creates loss record in glosa_losses table
    2. Creates CPC 25 write-off journal entries:
       - Dr: Bad Debt Expense (6401)
       - Cr: Accounts Receivable (1101)
    3. Realizes provision (ACTIVE → REALIZED)
    4. Updates glosa status to LOSS_REGISTERED
    5. Updates accounts receivable balance
    6. Publishes Kafka notification to finance team

    Input Variables:
        - claimId: Claim identifier (required)
        - glosaCaseId: Glosa case identifier (required)
        - glosaId: Glosa identifier (required)
        - denialAmount: Amount of unsuccessful claim (required)
        - appealMethod: Method attempted
        - denialReason: Original reason for denial
        - accountingPeriod: Accounting period (YYYY-MM, defaults to current)

    Output Variables:
        - lossId: Unique loss record identifier
        - lossRecorded: Whether loss was recorded successfully
        - lossDate: Date of final loss determination
        - lossAmount: Confirmed loss amount
        - accountingEntryId: Journal entry identifier
        - provisionRealized: Whether provision was realized
    """

    def __init__(
        self,
        settings=None,
        db_service: Optional[DatabaseService] = None,
        accounting_service: Optional[AccountingService] = None,
        erp_client: Optional[ERPClient] = None,
        kafka_producer: Optional[KafkaProducer] = None,
        **kwargs,
    ):
        """
        Initialize the worker with dependencies.

        Args:
            settings: Application settings
            db_service: Database service for persistence
            accounting_service: Service for accounting operations
            erp_client: Client for ERP integration
            kafka_producer: Producer for Kafka events
        """
        super().__init__(settings=settings)
        self._db = db_service or get_database_service()
        self._accounting = accounting_service or AccountingService()
        self._erp_client = erp_client
        self._kafka_producer = kafka_producer
        self._loss_id_counter = 0

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "register_loss"

    @property
    def requires_idempotency(self) -> bool:
        """Critical financial operation - must be idempotent."""
        return True

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """
        Extract parameters for idempotency key generation.

        For loss registration, use glosaId + claimId as the key since
        each glosa can only have one loss record.

        Args:
            variables: Job variables

        Returns:
            String representation of key parameters
        """
        glosa_id = variables.get("glosaId", "")
        claim_id = variables.get("claimId", "")
        return f"loss:{glosa_id}:{claim_id}"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the loss registration task with CPC 25 accounting compliance.

        Algorithm:
        1. Extract and validate input variables
        2. Default accounting period to current month if not provided
        3. Check for existing loss record (idempotency)
        4. Generate unique loss ID
        5. Execute transaction:
           - Create loss record
           - Create write-off journal entries (Dr: 6401, Cr: 1101)
           - Realize provision (ACTIVE → REALIZED)
           - Update glosa status to LOSS_REGISTERED
           - Update accounts receivable
           - Create audit log
        6. Queue ERP integration (async)
        7. Publish Kafka notification (async)
        8. Return result

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with loss details and accounting entry
        """
        self._logger.info(
            "Starting loss registration with CPC 25 accounting",
            business_key=variables.get("businessKey"),
            claim_id=variables.get("claimId"),
        )

        # 1. Extract and validate input variables
        claim_id = self.get_required_variable(variables, "claimId", str)
        glosa_id = self.get_required_variable(variables, "glosaId", str)
        glosa_case_id = self.get_variable(variables, "glosaCaseId", str) or ""
        denial_amount = self.get_required_amount_variable(variables, "denialAmount")
        appeal_method = self.get_variable(variables, "appealMethod", str) or "UNKNOWN"
        denial_reason = self.get_variable(variables, "denialReason", str) or ""
        accounting_period = self.get_variable(variables, "accountingPeriod", str)

        # Validate data
        self._validate_loss_data(claim_id, glosa_id, denial_amount)

        # 2. Default accounting period to current month
        if not accounting_period:
            accounting_period = self._accounting.get_current_accounting_period()
        elif not self._accounting.validate_accounting_period(accounting_period):
            raise BpmnErrorException(
                error_code="INVALID_ACCOUNTING_PERIOD",
                message=f"Invalid accounting period format: {accounting_period}. Expected YYYY-MM",
            )

        self._logger.debug(
            "Loss registration parameters validated",
            claim_id=claim_id,
            glosa_id=glosa_id,
            denial_amount=str(denial_amount),
            accounting_period=accounting_period,
        )

        # 3. Check for existing loss record (database-level idempotency)
        existing = await self._check_existing_loss(glosa_id, claim_id)
        if existing:
            self._logger.info(
                "Returning existing loss record (idempotent)",
                loss_id=existing["loss_id"],
                glosa_id=glosa_id,
            )
            return self._build_output_from_existing(existing)

        # 4. Generate unique loss ID
        loss_id = self._generate_loss_id(claim_id, glosa_id)

        # 5. Execute transaction
        try:
            loss_date, accounting_entry_id, provision_realized = await self._create_loss_transaction(
                loss_id=loss_id,
                claim_id=claim_id,
                glosa_id=glosa_id,
                glosa_case_id=glosa_case_id,
                amount=denial_amount,
                period=accounting_period,
                appeal_method=appeal_method,
                denial_reason=denial_reason,
            )
        except Exception as e:
            self._logger.error(
                "Loss registration transaction failed",
                loss_id=loss_id,
                glosa_id=glosa_id,
                error=str(e),
            )
            raise BpmnErrorException(
                error_code="LOSS_REGISTRATION_FAILED",
                message=f"Failed to register loss: {e}",
            )

        # 6. Queue ERP integration (async, non-blocking)
        await self._queue_erp_integration(
            loss_id=loss_id,
            glosa_id=glosa_id,
            claim_id=claim_id,
            amount=denial_amount,
            period=accounting_period,
        )

        # 7. Publish Kafka notification (async, non-blocking)
        await self._publish_loss_notification(
            loss_id=loss_id,
            glosa_id=glosa_id,
            claim_id=claim_id,
            amount=denial_amount,
            appeal_method=appeal_method,
            denial_reason=denial_reason,
        )

        self._logger.info(
            "Loss registered successfully with CPC 25 accounting",
            loss_id=loss_id,
            glosa_id=glosa_id,
            amount=str(denial_amount),
            accounting_entry_id=accounting_entry_id,
            provision_realized=provision_realized,
        )

        # 8. Return result
        return WorkerResult.ok({
            "lossId": loss_id,
            "lossRecorded": True,
            "lossDate": loss_date.isoformat(),
            "lossAmount": float(denial_amount),
            "accountingEntryId": accounting_entry_id,
            "provisionRealized": provision_realized,
            "appealMethod": appeal_method,
            "denialReason": denial_reason,
            "glosaCaseId": glosa_case_id,
            "accountingPeriod": accounting_period,
        })

    def _validate_loss_data(
        self,
        claim_id: str,
        glosa_id: str,
        denial_amount: Decimal,
    ) -> None:
        """
        Validate loss registration input data.

        Args:
            claim_id: Claim identifier
            glosa_id: Glosa identifier
            denial_amount: Denial amount

        Raises:
            BpmnErrorException: If data is invalid
        """
        if not claim_id or not claim_id.strip():
            raise BpmnErrorException(
                error_code="INVALID_LOSS_DATA",
                message="Claim ID is required",
            )

        if not glosa_id or not glosa_id.strip():
            raise BpmnErrorException(
                error_code="INVALID_LOSS_DATA",
                message="Glosa ID is required",
            )

        if denial_amount <= 0:
            raise BpmnErrorException(
                error_code="INVALID_LOSS_DATA",
                message=f"Denial amount must be positive: {denial_amount}",
            )

    async def _check_existing_loss(
        self,
        glosa_id: str,
        claim_id: str,
    ) -> Optional[dict[str, Any]]:
        """
        Check for existing loss record for this glosa/claim.

        This ensures idempotency at the database level.

        Args:
            glosa_id: Glosa identifier
            claim_id: Claim identifier

        Returns:
            Existing loss record or None
        """
        query = """
            SELECT loss_id, amount, accounting_period, created_at,
                   accounting_entry_id, provision_realized
            FROM glosa_losses
            WHERE glosa_id = :glosa_id AND claim_id = :claim_id
        """
        return await self._db.fetch_one(
            query,
            {"glosa_id": glosa_id, "claim_id": claim_id},
        )

    def _build_output_from_existing(
        self,
        existing: dict[str, Any],
    ) -> WorkerResult:
        """
        Build output from an existing loss record.

        Args:
            existing: Existing loss data

        Returns:
            WorkerResult with existing loss details
        """
        loss_date = existing["created_at"]
        if isinstance(loss_date, str):
            loss_date = datetime.fromisoformat(loss_date)

        return WorkerResult.ok({
            "lossId": existing["loss_id"],
            "lossRecorded": True,
            "lossDate": loss_date.isoformat(),
            "lossAmount": float(existing["amount"]),
            "accountingEntryId": existing.get("accounting_entry_id", ""),
            "provisionRealized": existing.get("provision_realized", False),
        })

    def _generate_loss_id(self, claim_id: str, glosa_id: str) -> str:
        """
        Generate a unique loss ID.

        Format: LOSS-{glosa_id}-{claim_id}-{timestamp_ms}_{counter}

        Uses timestamp in milliseconds plus a counter to ensure uniqueness
        even when called in rapid succession.

        Args:
            claim_id: Claim identifier
            glosa_id: Glosa identifier

        Returns:
            Unique loss ID
        """
        timestamp = int(time.time() * 1000)
        self._loss_id_counter += 1
        return f"LOSS-{glosa_id}-{claim_id}-{timestamp}_{self._loss_id_counter}"

    async def _create_loss_transaction(
        self,
        loss_id: str,
        claim_id: str,
        glosa_id: str,
        glosa_case_id: str,
        amount: Decimal,
        period: str,
        appeal_method: str,
        denial_reason: str,
    ) -> tuple[datetime, str, bool]:
        """
        Create loss record with all related records in a transaction.

        Transaction includes:
        1. Loss record in glosa_losses
        2. Debit journal entry (Bad Debt Expense - 6401)
        3. Credit journal entry (Accounts Receivable - 1101)
        4. Provision realization (ACTIVE → REALIZED) if exists
        5. Glosa status update to LOSS_REGISTERED
        6. Accounts receivable balance update
        7. Audit log entry

        Args:
            loss_id: Unique loss ID
            claim_id: Claim identifier
            glosa_id: Glosa identifier
            glosa_case_id: Glosa case identifier
            amount: Loss amount
            period: Accounting period
            appeal_method: Appeal method attempted
            denial_reason: Denial reason

        Returns:
            Tuple of (loss_date, accounting_entry_id, provision_realized)
        """
        loss_date = datetime.utcnow()
        accounting_entry_id = f"AE-{loss_id}-{time.time_ns() % 100000:05d}"

        # Create write-off journal entries
        debit_entry, credit_entry = self._create_writeoff_entries(
            loss_id=loss_id,
            glosa_id=glosa_id,
            amount=amount,
            period=period,
        )

        provision_realized = False

        async with self._db.transaction() as session:
            # 1. Create loss record
            await self._db.execute_in_transaction(
                session,
                """
                INSERT INTO glosa_losses (
                    loss_id, claim_id, glosa_id, glosa_case_id,
                    amount, accounting_period, appeal_method,
                    denial_reason, accounting_entry_id, created_at
                ) VALUES (
                    :loss_id, :claim_id, :glosa_id, :glosa_case_id,
                    :amount, :period, :appeal_method,
                    :denial_reason, :accounting_entry_id, :created_at
                )
                """,
                {
                    "loss_id": loss_id,
                    "claim_id": claim_id,
                    "glosa_id": glosa_id,
                    "glosa_case_id": glosa_case_id,
                    "amount": amount,
                    "period": period,
                    "appeal_method": appeal_method,
                    "denial_reason": denial_reason,
                    "accounting_entry_id": accounting_entry_id,
                    "created_at": loss_date,
                },
            )

            # 2. Create debit journal entry (Bad Debt Expense - 6401)
            await self._db.execute_in_transaction(
                session,
                """
                INSERT INTO journal_entries (
                    entry_id, account_code, debit, credit, period, reference, created_at
                ) VALUES (
                    :entry_id, :account, :debit, 0, :period, :reference, :created_at
                )
                """,
                {
                    "entry_id": debit_entry.entry_id,
                    "account": debit_entry.account_code,
                    "debit": debit_entry.debit,
                    "period": period,
                    "reference": loss_id,
                    "created_at": loss_date,
                },
            )

            # 3. Create credit journal entry (Accounts Receivable - 1101)
            await self._db.execute_in_transaction(
                session,
                """
                INSERT INTO journal_entries (
                    entry_id, account_code, debit, credit, period, reference, created_at
                ) VALUES (
                    :entry_id, :account, 0, :credit, :period, :reference, :created_at
                )
                """,
                {
                    "entry_id": credit_entry.entry_id,
                    "account": credit_entry.account_code,
                    "credit": credit_entry.credit,
                    "period": period,
                    "reference": loss_id,
                    "created_at": loss_date,
                },
            )

            # 4. Realize provision if exists (ACTIVE → REALIZED)
            provision_result = await self._db.execute_in_transaction(
                session,
                """
                UPDATE glosa_provisions
                SET status = :realized_status,
                    realized_at = :realized_at,
                    loss_id = :loss_id,
                    updated_at = :updated_at
                WHERE glosa_id = :glosa_id AND status = :active_status
                """,
                {
                    "realized_status": ProvisionStatus.UTILIZED.value,
                    "realized_at": loss_date,
                    "loss_id": loss_id,
                    "updated_at": loss_date,
                    "glosa_id": glosa_id,
                    "active_status": ProvisionStatus.ACTIVE.value,
                },
            )
            provision_realized = provision_result.rowcount > 0 if hasattr(provision_result, "rowcount") else False

            # 5. Update glosa status to LOSS_REGISTERED
            await self._db.execute_in_transaction(
                session,
                """
                UPDATE glosas
                SET status = 'LOSS_REGISTERED',
                    loss_registered = true,
                    loss_amount = :amount,
                    updated_at = :updated_at
                WHERE glosa_id = :glosa_id
                """,
                {"glosa_id": glosa_id, "amount": amount, "updated_at": loss_date},
            )

            # 6. Update accounts receivable balance (reduce by loss amount)
            await self._db.execute_in_transaction(
                session,
                """
                UPDATE accounts_receivable
                SET balance = balance - :amount,
                    bad_debt_writeoff = bad_debt_writeoff + :amount,
                    updated_at = :updated_at
                WHERE claim_id = :claim_id
                """,
                {"claim_id": claim_id, "amount": amount, "updated_at": loss_date},
            )

            # 7. Create audit log entry
            await self._db.execute_in_transaction(
                session,
                """
                INSERT INTO audit_log (
                    entity_type, entity_id, action, details, created_at
                ) VALUES (
                    'LOSS', :loss_id, 'CREATE',
                    :details, :created_at
                )
                """,
                {
                    "loss_id": loss_id,
                    "details": f"Loss registered for glosa {glosa_id}, claim {claim_id}, amount {amount}, period {period}. Provision realized: {provision_realized}",
                    "created_at": loss_date,
                },
            )

        self._logger.debug(
            "Loss transaction committed",
            loss_id=loss_id,
            debit_entry=debit_entry.entry_id,
            credit_entry=credit_entry.entry_id,
            provision_realized=provision_realized,
        )

        return loss_date, accounting_entry_id, provision_realized

    def _create_writeoff_entries(
        self,
        loss_id: str,
        glosa_id: str,
        amount: Decimal,
        period: str,
    ) -> tuple[AccountingEntry, AccountingEntry]:
        """
        Create CPC 25 compliant write-off journal entries.

        Write-off entries:
        - Debit: Bad Debt Expense (6401)
        - Credit: Accounts Receivable (1101)

        Args:
            loss_id: Loss identifier
            glosa_id: Glosa identifier
            amount: Write-off amount
            period: Accounting period

        Returns:
            Tuple of (debit_entry, credit_entry)
        """
        # Generate entry IDs
        entry_id_debit = f"JE-{loss_id}-D"
        entry_id_credit = f"JE-{loss_id}-C"

        # Account codes for write-off
        bad_debt_expense = "6401"  # Despesa com Perdas (Bad Debt Expense)
        accounts_receivable = "1101"  # Contas a Receber (Accounts Receivable)

        # Create debit entry (Bad Debt Expense)
        debit_entry = AccountingEntry(
            entry_id=entry_id_debit,
            account_code=bad_debt_expense,
            account_name="Despesa com Perdas",
            debit=amount,
            credit=Decimal("0"),
            period=period,
            reference=loss_id,
            description=f"Baixa de perda - Glosa {glosa_id}",
        )

        # Create credit entry (Accounts Receivable)
        credit_entry = AccountingEntry(
            entry_id=entry_id_credit,
            account_code=accounts_receivable,
            account_name="Contas a Receber",
            debit=Decimal("0"),
            credit=amount,
            period=period,
            reference=loss_id,
            description=f"Baixa de perda - Glosa {glosa_id}",
        )

        self._logger.info(
            "Created write-off journal entries",
            loss_id=loss_id,
            glosa_id=glosa_id,
            amount=str(amount),
            period=period,
            debit_account=bad_debt_expense,
            credit_account=accounts_receivable,
        )

        return debit_entry, credit_entry

    async def _queue_erp_integration(
        self,
        loss_id: str,
        glosa_id: str,
        claim_id: str,
        amount: Decimal,
        period: str,
    ) -> None:
        """
        Queue loss for ERP integration (async, non-blocking).

        Args:
            loss_id: Loss identifier
            glosa_id: Glosa identifier
            claim_id: Claim identifier
            amount: Loss amount
            period: Accounting period
        """
        if not self._erp_client:
            self._logger.debug("ERP client not configured, skipping integration")
            return

        try:
            await self._erp_client.queue_loss({
                "loss_id": loss_id,
                "glosa_id": glosa_id,
                "claim_id": claim_id,
                "amount": float(amount),
                "accounting_period": period,
                "debit_account": "6401",  # Bad Debt Expense
                "credit_account": "1101",  # Accounts Receivable
            })
            self._logger.debug(
                "ERP integration queued",
                loss_id=loss_id,
            )
        except Exception as e:
            # Non-blocking - will be retried by ERP sync job
            self._logger.warning(
                "Failed to queue ERP integration",
                loss_id=loss_id,
                error=str(e),
            )

    async def _publish_loss_notification(
        self,
        loss_id: str,
        glosa_id: str,
        claim_id: str,
        amount: Decimal,
        appeal_method: str,
        denial_reason: str,
    ) -> None:
        """
        Publish loss notification to Kafka (async, non-blocking).

        Notifies:
        - Finance team (for accounting impact)
        - Management (for loss tracking)
        - Analytics (for process improvement)

        Args:
            loss_id: Loss identifier
            glosa_id: Glosa identifier
            claim_id: Claim identifier
            amount: Loss amount
            appeal_method: Appeal method attempted
            denial_reason: Denial reason
        """
        if not self._kafka_producer:
            self._logger.debug("Kafka producer not configured, skipping notification")
            return

        event = {
            "event_type": "LossRegistered",
            "event_id": f"evt-{loss_id}-{time.time_ns() % 1000000:06d}",
            "loss_id": loss_id,
            "glosa_id": glosa_id,
            "claim_id": claim_id,
            "amount": float(amount),
            "appeal_method": appeal_method,
            "denial_reason": denial_reason,
            "debit_account": "6401",
            "credit_account": "1101",
            "created_at": datetime.utcnow().isoformat(),
            "version": "1.0",
            "recipients": ["finance-team", "management", "analytics"],
        }

        try:
            await self._kafka_producer.send("financial-losses", event)
            self._logger.debug(
                "Loss notification published",
                loss_id=loss_id,
                event_id=event["event_id"],
            )
        except Exception as e:
            # Non-blocking - event will be in DLQ
            self._logger.warning(
                "Failed to publish loss notification",
                loss_id=loss_id,
                error=str(e),
            )
