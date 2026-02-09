"""
CreateProvisionWorker - Creates CPC 25 compliant financial provisions for glosas.

This is the Python equivalent of the Java CreateProvisionDelegate.

Business Rule: RN-GLOSA-003-CreateProvision.md
Regulatory Compliance: CPC 25 (financial provisions), ANS RN 424/2017
Migrated from: com.hospital.revenuecycle.delegates.glosa.CreateProvisionDelegate

Input Variables:
    glosaId (str): Unique identifier of the glosa (required)
    glosaAmount (Decimal): Monetary value of the glosa (required, > 0)
    accountingPeriod (str, optional): Accounting period (YYYY-MM format, defaults to current)

Output Variables:
    provisionId (str): Unique provision identifier
    provisionAmount (Decimal): Amount provisioned
    provisionCreated (bool): Success indicator
    provisionDate (datetime): Creation timestamp
    accountingPeriod (str): Accounting period used

BPMN Errors:
    MISSING_VARIABLE: Required variable not provided
    INVALID_GLOSA_DATA: Glosa data is invalid
    PROVISION_CREATION_FAILED: Provision creation failed
    GLOSA_NOT_FOUND: Referenced glosa not found

Compliance:
    CPC 25 - Provisoes, Passivos Contingentes e Ativos Contingentes
    NBC TG 25 - Brazilian accounting standard equivalent to IAS 37
"""

from __future__ import annotations

import time
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

import structlog

from revenue_cycle.domain.exceptions import BpmnErrorException, EntityNotFoundException
from revenue_cycle.domain.value_objects.provision import (
    AccountCode,
    CPC25Category,
    ERPSyncStatus,
    ProvisionStatus,
    ProvisionType,
)
from revenue_cycle.services.accounting import AccountingService
from revenue_cycle.services.database import DatabaseService, get_database_service
from revenue_cycle.services.erp_client import ERPClient
from revenue_cycle.services.kafka_producer import KafkaProducer, ProvisionCreatedEvent
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


@worker(
    topic="create-provision",
    max_jobs=16,
    lock_duration=60000,  # 1 minute
)
class CreateProvisionWorker(BaseWorker):
    """
    Worker for creating CPC 25 compliant financial provisions for glosas.

    Responsibilities:
    - Validate glosa data and check for existing provisions (idempotency)
    - Calculate provision amount (100% for conservatism principle)
    - Create provision record with journal entries in a transaction
    - Update glosa status to PROVISIONED
    - Queue ERP integration (async)
    - Publish Kafka event (async)

    This worker mirrors the Java CreateProvisionDelegate logic.
    """

    def __init__(
        self,
        db_service: Optional[DatabaseService] = None,
        accounting_service: Optional[AccountingService] = None,
        erp_client: Optional[ERPClient] = None,
        kafka_producer: Optional[KafkaProducer] = None,
    ):
        """
        Initialize the worker with dependencies.

        Args:
            db_service: Database service for persistence
            accounting_service: Service for accounting operations
            erp_client: Client for ERP integration
            kafka_producer: Producer for Kafka events
        """
        super().__init__()
        self._db = db_service or get_database_service()
        self._accounting = accounting_service or AccountingService()
        self._erp_client = erp_client
        self._kafka_producer = kafka_producer
        self._provision_id_counter = 0

    @property
    def operation_name(self) -> str:
        return "create_provision"

    @property
    def requires_idempotency(self) -> bool:
        # Critical financial operation - must be idempotent
        return True

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """
        Extract parameters for idempotency key generation.

        For provisions, use glosaId as the key since each glosa
        can only have one active provision.

        Args:
            variables: Job variables

        Returns:
            String representation of key parameters
        """
        glosa_id = variables.get("glosaId", "")
        return f"provision:{glosa_id}"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Execute the provision creation business logic.

        Algorithm:
        1. Extract and validate input variables
        2. Default accounting period to current month if not provided
        3. Check for existing provision (idempotency)
        4. Calculate provision amount (100% - conservatism principle)
        5. Generate unique provision ID
        6. Execute transaction:
           - Create provision record
           - Create journal entries (debit/credit)
           - Update glosa status
        7. Queue ERP integration (async)
        8. Publish Kafka event (async)
        9. Return result

        Args:
            job: Camunda external task
            variables: Job variables

        Returns:
            WorkerResult with provision details
        """
        self._logger.info(
            "Starting provision creation",
            business_key=variables.get("businessKey"),
        )

        # 1. Extract and validate input variables
        glosa_id = self.get_required_variable(variables, "glosaId", str)
        glosa_amount = self.get_required_amount_variable(variables, "glosaAmount")
        accounting_period = self.get_variable(variables, "accountingPeriod", str)

        # Validate glosa data
        self._validate_glosa_data(glosa_id, glosa_amount)

        # 2. Default accounting period to current month
        if not accounting_period:
            accounting_period = self._accounting.get_current_accounting_period()
        elif not self._accounting.validate_accounting_period(accounting_period):
            raise BpmnErrorException(
                error_code="INVALID_ACCOUNTING_PERIOD",
                message=f"Invalid accounting period format: {accounting_period}. Expected YYYY-MM",
            )

        self._logger.debug(
            "Provision parameters validated",
            glosa_id=glosa_id,
            glosa_amount=str(glosa_amount),
            accounting_period=accounting_period,
        )

        # 3. Check for existing provision (database-level idempotency)
        existing = await self._check_existing_provision(glosa_id)
        if existing:
            self._logger.info(
                "Returning existing provision (idempotent)",
                provision_id=existing["provision_id"],
                glosa_id=glosa_id,
            )
            return self._build_output_from_existing(existing)

        # 4. Calculate provision amount (100% - conservatism principle)
        provision_amount = self._accounting.calculate_provision_amount(
            glosa_amount=glosa_amount,
            provision_type=ProvisionType.GLOSA_FULL,
        )

        # 5. Generate unique provision ID
        provision_id = self._generate_provision_id(glosa_id)

        # Determine CPC 25 category
        cpc25_category = self._accounting.determine_cpc25_category(
            recovery_probability=0,  # Conservative - assume 0% recovery
            provision_type=ProvisionType.GLOSA_FULL,
        )

        # 6. Execute transaction
        try:
            provision_date, accounting_entry_id = await self._create_provision_transaction(
                provision_id=provision_id,
                glosa_id=glosa_id,
                amount=provision_amount,
                period=accounting_period,
                cpc25_category=cpc25_category,
            )
        except Exception as e:
            self._logger.error(
                "Provision transaction failed",
                provision_id=provision_id,
                glosa_id=glosa_id,
                error=str(e),
            )
            raise BpmnErrorException(
                error_code="PROVISION_CREATION_FAILED",
                message=f"Failed to create provision: {e}",
            )

        # 7. Queue ERP integration (async, non-blocking)
        await self._queue_erp_integration(
            provision_id=provision_id,
            glosa_id=glosa_id,
            amount=provision_amount,
            period=accounting_period,
        )

        # 8. Publish Kafka event (async, non-blocking)
        await self._publish_provision_event(
            provision_id=provision_id,
            glosa_id=glosa_id,
            amount=provision_amount,
            period=accounting_period,
        )

        self._logger.info(
            "Provision created successfully",
            provision_id=provision_id,
            glosa_id=glosa_id,
            amount=str(provision_amount),
            accounting_entry_id=accounting_entry_id,
            cpc25_category=cpc25_category.value,
        )

        # 9. Return result
        return WorkerResult.ok({
            "provisionId": provision_id,
            "provisionAmount": float(provision_amount),
            "provisionCreated": True,
            "provisionDate": provision_date.isoformat(),
            "accountingPeriod": accounting_period,
            "accountingEntryId": accounting_entry_id,
            "cpc25Category": cpc25_category.value,
        })

    def _validate_glosa_data(
        self,
        glosa_id: str,
        glosa_amount: Decimal,
    ) -> None:
        """
        Validate glosa input data.

        Args:
            glosa_id: Glosa identifier
            glosa_amount: Glosa amount

        Raises:
            BpmnErrorException: If data is invalid
        """
        if not glosa_id or not glosa_id.strip():
            raise BpmnErrorException.invalid_glosa_data("Glosa ID is required")

        if glosa_amount <= 0:
            raise BpmnErrorException.invalid_glosa_data(
                f"Glosa amount must be positive: {glosa_amount}"
            )

    async def _check_existing_provision(
        self,
        glosa_id: str,
    ) -> Optional[dict[str, Any]]:
        """
        Check for existing active provision for this glosa.

        This ensures idempotency at the database level.

        Args:
            glosa_id: Glosa identifier

        Returns:
            Existing provision record or None
        """
        query = """
            SELECT provision_id, amount, accounting_period, created_at, cpc25_category
            FROM glosa_provisions
            WHERE glosa_id = :glosa_id AND status = :status
        """
        return await self._db.fetch_one(
            query,
            {"glosa_id": glosa_id, "status": ProvisionStatus.ACTIVE.value},
        )

    def _build_output_from_existing(
        self,
        existing: dict[str, Any],
    ) -> WorkerResult:
        """
        Build output from an existing provision record.

        Args:
            existing: Existing provision data

        Returns:
            WorkerResult with existing provision details
        """
        provision_date = existing["created_at"]
        if isinstance(provision_date, str):
            provision_date = datetime.fromisoformat(provision_date)

        return WorkerResult.ok({
            "provisionId": existing["provision_id"],
            "provisionAmount": float(existing["amount"]),
            "provisionCreated": True,
            "provisionDate": provision_date.isoformat(),
            "accountingPeriod": existing["accounting_period"],
            "cpc25Category": existing.get("cpc25_category", CPC25Category.PROVISION_PROBABLE.value),
        })

    def _generate_provision_id(self, glosa_id: str) -> str:
        """
        Generate a unique provision ID.

        Format: PROV-{glosa_id}-{timestamp_ms}_{counter}

        Uses timestamp in milliseconds plus a counter to ensure uniqueness
        even when called in rapid succession.

        Args:
            glosa_id: Glosa identifier

        Returns:
            Unique provision ID
        """
        timestamp = int(time.time() * 1000)
        self._provision_id_counter += 1
        return f"PROV-{glosa_id}-{timestamp}_{self._provision_id_counter}"

    async def _create_provision_transaction(
        self,
        provision_id: str,
        glosa_id: str,
        amount: Decimal,
        period: str,
        cpc25_category: CPC25Category,
    ) -> tuple[datetime, str]:
        """
        Create provision with all related records in a transaction.

        Transaction includes:
        1. Provision record in glosa_provisions
        2. Debit journal entry (expense)
        3. Credit journal entry (liability)
        4. Glosa status update

        Args:
            provision_id: Unique provision ID
            glosa_id: Glosa identifier
            amount: Provision amount
            period: Accounting period
            cpc25_category: CPC 25 classification

        Returns:
            Tuple of (provision_date, accounting_entry_id)
        """
        provision_date = datetime.utcnow()
        accounting_entry_id = self._accounting.generate_accounting_entry_id(provision_id)

        # Create journal entries
        debit_entry, credit_entry = self._accounting.create_provision_entries(
            provision_id=provision_id,
            glosa_id=glosa_id,
            amount=amount,
            period=period,
            provision_type=ProvisionType.GLOSA_FULL,
        )

        async with self._db.transaction() as session:
            # 1. Create provision record
            await self._db.execute_in_transaction(
                session,
                """
                INSERT INTO glosa_provisions (
                    provision_id, glosa_id, amount, accounting_period,
                    status, erp_sync_status, cpc25_category, created_at
                ) VALUES (
                    :provision_id, :glosa_id, :amount, :period,
                    :status, :erp_sync_status, :cpc25_category, :created_at
                )
                """,
                {
                    "provision_id": provision_id,
                    "glosa_id": glosa_id,
                    "amount": amount,
                    "period": period,
                    "status": ProvisionStatus.ACTIVE.value,
                    "erp_sync_status": ERPSyncStatus.PENDING.value,
                    "cpc25_category": cpc25_category.value,
                    "created_at": provision_date,
                },
            )

            # 2. Create debit journal entry (expense)
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
                    "reference": provision_id,
                    "created_at": provision_date,
                },
            )

            # 3. Create credit journal entry (liability)
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
                    "reference": provision_id,
                    "created_at": provision_date,
                },
            )

            # 4. Update glosa status
            await self._db.execute_in_transaction(
                session,
                """
                UPDATE glosas
                SET status = 'PROVISIONED', provisioned = true, updated_at = :updated_at
                WHERE glosa_id = :glosa_id
                """,
                {"glosa_id": glosa_id, "updated_at": provision_date},
            )

            # 5. Create audit log entry
            await self._db.execute_in_transaction(
                session,
                """
                INSERT INTO audit_log (
                    entity_type, entity_id, action, details, created_at
                ) VALUES (
                    'PROVISION', :provision_id, 'CREATE',
                    :details, :created_at
                )
                """,
                {
                    "provision_id": provision_id,
                    "details": f"Provision created for glosa {glosa_id}, amount {amount}, period {period}",
                    "created_at": provision_date,
                },
            )

        self._logger.debug(
            "Provision transaction committed",
            provision_id=provision_id,
            debit_entry=debit_entry.entry_id,
            credit_entry=credit_entry.entry_id,
        )

        return provision_date, accounting_entry_id

    async def _queue_erp_integration(
        self,
        provision_id: str,
        glosa_id: str,
        amount: Decimal,
        period: str,
    ) -> None:
        """
        Queue provision for ERP integration (async, non-blocking).

        Args:
            provision_id: Provision identifier
            glosa_id: Glosa identifier
            amount: Provision amount
            period: Accounting period
        """
        if not self._erp_client:
            self._logger.debug("ERP client not configured, skipping integration")
            return

        try:
            await self._erp_client.queue_provision({
                "provision_id": provision_id,
                "glosa_id": glosa_id,
                "amount": float(amount),
                "accounting_period": period,
                "debit_account": AccountCode.PROVISION_EXPENSE,
                "credit_account": AccountCode.PROVISION_LIABILITY,
            })
            self._logger.debug(
                "ERP integration queued",
                provision_id=provision_id,
            )
        except Exception as e:
            # Non-blocking - will be retried by ERP sync job
            self._logger.warning(
                "Failed to queue ERP integration",
                provision_id=provision_id,
                error=str(e),
            )

    async def _publish_provision_event(
        self,
        provision_id: str,
        glosa_id: str,
        amount: Decimal,
        period: str,
    ) -> None:
        """
        Publish provision event to Kafka (async, non-blocking).

        Args:
            provision_id: Provision identifier
            glosa_id: Glosa identifier
            amount: Provision amount
            period: Accounting period
        """
        if not self._kafka_producer:
            self._logger.debug("Kafka producer not configured, skipping event publication")
            return

        event = ProvisionCreatedEvent(
            provision_id=provision_id,
            glosa_id=glosa_id,
            amount=float(amount),
            accounting_period=period,
            debit_account=AccountCode.PROVISION_EXPENSE,
            credit_account=AccountCode.PROVISION_LIABILITY,
        )

        try:
            await self._kafka_producer.send_provision_event(event)
            self._logger.debug(
                "Provision event published",
                provision_id=provision_id,
                event_id=event.event_id,
            )
        except Exception as e:
            # Non-blocking - event will be in DLQ
            self._logger.warning(
                "Failed to publish provision event",
                provision_id=provision_id,
                error=str(e),
            )
