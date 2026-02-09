"""
RegisterRecoveryWorker - Registers successful glosa recovery with CPC 25/47 compliance.

This worker implements the complete recovery registration process:
- Creates recovery record
- Reverses financial provisions (if exists)
- Creates revenue recognition entries
- Updates glosa status to RECOVERED
- Tracks recovery metrics
- Notifies stakeholders

Business Rule: RN-RegisterRecoveryDelegate.md
Regulatory Compliance:
    - CPC 25 (provision reversal)
    - CPC 47 (revenue recognition)
    - ANS RN 424/2017 (appeal resolution tracking)
Migrated from: com.hospital.revenuecycle.delegates.glosa.RegisterRecoveryDelegate
Topic: register-recovery
BPMN Task: Task_Register_Recovery (Registrar Recuperacao)
"""

from __future__ import annotations

import time
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

import structlog

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.domain.value_objects.provision import (
    AccountCode,
    ProvisionStatus,
)
from revenue_cycle.services.accounting import AccountingService
from revenue_cycle.services.database import DatabaseService, get_database_service
from revenue_cycle.services.kafka_producer import KafkaProducer
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


class RecoveryMethod(str, Enum):
    """Recovery methods for glosa resolution."""

    APPEAL = "APPEAL"  # Administrative appeal
    RESUBMISSION = "RESUBMISSION"  # Resubmission with corrections
    NEGOTIATION = "NEGOTIATION"  # Direct negotiation
    LITIGATION = "LITIGATION"  # Judicial process
    MEDIATION = "MEDIATION"  # Mediation/arbitration


class GlosaStatus(str, Enum):
    """Glosa lifecycle statuses."""

    IDENTIFIED = "IDENTIFIED"
    UNDER_REVIEW = "UNDER_REVIEW"
    PROVISIONED = "PROVISIONED"
    APPEALED = "APPEALED"
    RECOVERED = "RECOVERED"
    LOST = "LOST"


@worker(topic="register-recovery", max_jobs=16, lock_duration=60000)
class RegisterRecoveryWorker(BaseWorker):
    """
    Zeebe worker for registering successful glosa recovery with full accounting.

    BPMN Task: Task_Register_Recovery
    Topic: register-recovery

    Responsibilities:
    1. Validate recovery data and check for duplicates (idempotency)
    2. Check for active provision and create reversal entries if exists
    3. Create revenue recognition accounting entries
    4. Update glosa status to RECOVERED
    5. Create recovery record with metrics
    6. Update recovery metrics (rate, time, amounts)
    7. Publish Kafka event to stakeholders

    Input Variables:
        - glosaId: Glosa identifier (required)
        - recoveredAmount: Amount successfully recovered (required)
        - recoveryMethod: Method used (APPEAL/RESUBMISSION/NEGOTIATION/LITIGATION/MEDIATION)
        - recoveryNotes: Additional notes about recovery (optional)

    Output Variables:
        - recoveryId: Unique recovery record identifier
        - recoveryRegistered: Success indicator (boolean)
        - recoveryDate: Timestamp of registration
        - finalGlosaStatus: Final status (RECOVERED)
        - provisionReversed: Whether provision was reversed (boolean)
        - revenueRecognized: Amount recognized as revenue

    Accounting Entries:
        Revenue Recognition (always):
            Dr: Accounts Receivable (1101) - Asset
            Cr: Patient Service Revenue (4101) - Revenue

        Provision Reversal (if provision exists):
            Dr: Provision for Glosas (2101) - Liability
            Cr: Reversal of Provision (6302) - Revenue
    """

    def __init__(
        self,
        settings=None,
        db_service: Optional[DatabaseService] = None,
        accounting_service: Optional[AccountingService] = None,
        kafka_producer: Optional[KafkaProducer] = None,
        **kwargs
    ):
        """
        Initialize the worker with dependencies.

        Args:
            settings: Optional worker settings
            db_service: Database service for persistence
            accounting_service: Service for accounting operations
            kafka_producer: Producer for Kafka events
        """
        super().__init__(settings=settings)
        self._db = db_service or get_database_service()
        self._accounting = accounting_service or AccountingService()
        self._kafka_producer = kafka_producer
        self._recovery_id_counter = 0

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "register_recovery"

    @property
    def requires_idempotency(self) -> bool:
        """Critical financial operation - must be idempotent."""
        return True

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """
        Extract parameters for idempotency key generation.

        For recoveries, use glosaId as the key since each glosa
        can only be recovered once.

        Args:
            variables: Job variables

        Returns:
            String representation of key parameters
        """
        glosa_id = variables.get("glosaId", "")
        return f"recovery:{glosa_id}"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Execute the recovery registration business logic.

        Algorithm:
        1. Extract and validate input variables
        2. Check for existing recovery (idempotency)
        3. Generate unique recovery ID
        4. Check for active provision
        5. Execute transaction:
           - Create recovery record
           - Update glosa status to RECOVERED
           - If provision exists: create reversal entries
           - Create revenue recognition entries
           - Update recovery metrics
        6. Publish Kafka event
        7. Return result

        Args:
            job: Camunda external task
            variables: Job variables

        Returns:
            WorkerResult with recovery details
        """
        self._logger.info(
            "Starting recovery registration",
            business_key=variables.get("businessKey"),
        )

        # 1. Extract and validate input
        glosa_id = self.get_required_variable(variables, "glosaId", str)
        recovered_amount = self.get_required_amount_variable(variables, "recoveredAmount")
        recovery_method = self.get_variable(variables, "recoveryMethod", str) or RecoveryMethod.APPEAL.value
        recovery_notes = self.get_variable(variables, "recoveryNotes", str) or ""

        # Validate recovery data
        self._validate_recovery_data(glosa_id, recovered_amount, recovery_method)

        self._logger.debug(
            "Recovery parameters validated",
            glosa_id=glosa_id,
            recovered_amount=str(recovered_amount),
            recovery_method=recovery_method,
        )

        # 2. Check for existing recovery (database-level idempotency)
        existing = await self._check_existing_recovery(glosa_id)
        if existing:
            self._logger.info(
                "Returning existing recovery (idempotent)",
                recovery_id=existing["recovery_id"],
                glosa_id=glosa_id,
            )
            return self._build_output_from_existing(existing)

        # 3. Generate unique recovery ID
        recovery_id = self._generate_recovery_id(glosa_id)

        # 4. Check for active provision
        active_provision = await self._check_active_provision(glosa_id)

        # 5. Execute transaction
        try:
            recovery_date, provision_reversed = await self._create_recovery_transaction(
                recovery_id=recovery_id,
                glosa_id=glosa_id,
                recovered_amount=recovered_amount,
                recovery_method=recovery_method,
                recovery_notes=recovery_notes,
                active_provision=active_provision,
            )
        except Exception as e:
            self._logger.error(
                "Recovery transaction failed",
                recovery_id=recovery_id,
                glosa_id=glosa_id,
                error=str(e),
            )
            raise BpmnErrorException(
                error_code="RECOVERY_REGISTRATION_FAILED",
                message=f"Failed to register recovery: {e}",
            )

        # 6. Publish Kafka event (async, non-blocking)
        await self._publish_recovery_event(
            recovery_id=recovery_id,
            glosa_id=glosa_id,
            recovered_amount=recovered_amount,
            recovery_method=recovery_method,
            recovery_notes=recovery_notes,
        )

        self._logger.info(
            "Recovery registered successfully",
            recovery_id=recovery_id,
            glosa_id=glosa_id,
            amount=str(recovered_amount),
            provision_reversed=provision_reversed,
        )

        # 7. Return result
        return WorkerResult.ok({
            "recoveryId": recovery_id,
            "recoveryRegistered": True,
            "recoveryDate": recovery_date.isoformat(),
            "finalGlosaStatus": GlosaStatus.RECOVERED.value,
            "provisionReversed": provision_reversed,
            "revenueRecognized": float(recovered_amount),
            "recoveryMethod": recovery_method,
        })

    def _validate_recovery_data(
        self,
        glosa_id: str,
        recovered_amount: Decimal,
        recovery_method: str,
    ) -> None:
        """
        Validate recovery input data.

        Args:
            glosa_id: Glosa identifier
            recovered_amount: Recovered amount
            recovery_method: Recovery method

        Raises:
            BpmnErrorException: If data is invalid
        """
        if not glosa_id or not glosa_id.strip():
            raise BpmnErrorException(
                error_code="INVALID_GLOSA_DATA",
                message="Glosa ID is required",
            )

        if recovered_amount <= 0:
            raise BpmnErrorException(
                error_code="INVALID_GLOSA_DATA",
                message=f"Recovered amount must be positive: {recovered_amount}",
            )

        # Validate recovery method
        try:
            RecoveryMethod(recovery_method)
        except ValueError:
            valid_methods = ", ".join([m.value for m in RecoveryMethod])
            raise BpmnErrorException(
                error_code="INVALID_RECOVERY_METHOD",
                message=f"Invalid recovery method: {recovery_method}. Valid: {valid_methods}",
            )

    async def _check_existing_recovery(
        self,
        glosa_id: str,
    ) -> Optional[dict[str, Any]]:
        """
        Check for existing recovery for this glosa.

        This ensures idempotency at the database level.

        Args:
            glosa_id: Glosa identifier

        Returns:
            Existing recovery record or None
        """
        query = """
            SELECT recovery_id, recovered_amount, recovery_method, created_at
            FROM glosa_recoveries
            WHERE glosa_id = :glosa_id
        """
        return await self._db.fetch_one(query, {"glosa_id": glosa_id})

    async def _check_active_provision(
        self,
        glosa_id: str,
    ) -> Optional[dict[str, Any]]:
        """
        Check for active provision for this glosa.

        Args:
            glosa_id: Glosa identifier

        Returns:
            Active provision record or None
        """
        query = """
            SELECT provision_id, amount
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
        Build output from an existing recovery record.

        Args:
            existing: Existing recovery data

        Returns:
            WorkerResult with existing recovery details
        """
        recovery_date = existing["created_at"]
        if isinstance(recovery_date, str):
            recovery_date = datetime.fromisoformat(recovery_date)

        return WorkerResult.ok({
            "recoveryId": existing["recovery_id"],
            "recoveryRegistered": True,
            "recoveryDate": recovery_date.isoformat(),
            "finalGlosaStatus": GlosaStatus.RECOVERED.value,
            "provisionReversed": True,  # Assume provision was reversed
            "revenueRecognized": float(existing["recovered_amount"]),
            "recoveryMethod": existing["recovery_method"],
        })

    def _generate_recovery_id(self, glosa_id: str) -> str:
        """
        Generate a unique recovery ID.

        Format: REC-{glosa_id}-{timestamp_ms}

        Args:
            glosa_id: Glosa identifier

        Returns:
            Unique recovery ID
        """
        timestamp = int(time.time() * 1000)
        return f"REC-{glosa_id}-{timestamp}"

    async def _create_recovery_transaction(
        self,
        recovery_id: str,
        glosa_id: str,
        recovered_amount: Decimal,
        recovery_method: str,
        recovery_notes: str,
        active_provision: Optional[dict[str, Any]],
    ) -> tuple[datetime, bool]:
        """
        Create recovery with all related records in a transaction.

        Transaction includes:
        1. Recovery record in glosa_recoveries
        2. Glosa status update to RECOVERED
        3. If provision exists:
           - Provision reversal (Dr: 2101, Cr: 6302)
           - Update provision status to REVERSED
        4. Revenue recognition entries (Dr: 1101, Cr: 4101)
        5. Update recovery metrics

        Args:
            recovery_id: Unique recovery ID
            glosa_id: Glosa identifier
            recovered_amount: Amount recovered
            recovery_method: Method of recovery
            recovery_notes: Additional notes
            active_provision: Active provision record if exists

        Returns:
            Tuple of (recovery_date, provision_reversed)
        """
        recovery_date = datetime.utcnow()
        provision_reversed = active_provision is not None

        async with self._db.transaction() as session:
            # 1. Create recovery record
            await self._db.execute_in_transaction(
                session,
                """
                INSERT INTO glosa_recoveries (
                    recovery_id, glosa_id, recovered_amount, recovery_method,
                    notes, created_at
                ) VALUES (
                    :recovery_id, :glosa_id, :amount, :method,
                    :notes, :created_at
                )
                """,
                {
                    "recovery_id": recovery_id,
                    "glosa_id": glosa_id,
                    "amount": recovered_amount,
                    "method": recovery_method,
                    "notes": recovery_notes,
                    "created_at": recovery_date,
                },
            )

            # 2. Update glosa status
            await self._db.execute_in_transaction(
                session,
                """
                UPDATE glosas
                SET status = :status,
                    recovered = true,
                    recovery_date = :recovery_date,
                    recovered_amount = :amount,
                    updated_at = :updated_at
                WHERE glosa_id = :glosa_id
                """,
                {
                    "status": GlosaStatus.RECOVERED.value,
                    "recovery_date": recovery_date,
                    "amount": recovered_amount,
                    "updated_at": recovery_date,
                    "glosa_id": glosa_id,
                },
            )

            # 3. If provision exists, create reversal entries
            if active_provision:
                provision_id = active_provision["provision_id"]

                # Dr: Provision for Glosas (2101)
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
                        "entry_id": f"{recovery_id}-PROV-REV-DR",
                        "account": "2101",  # Provision for Glosas
                        "debit": recovered_amount,
                        "period": recovery_date.strftime("%Y-%m"),
                        "reference": recovery_id,
                        "created_at": recovery_date,
                    },
                )

                # Cr: Reversal of Provision (6302)
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
                        "entry_id": f"{recovery_id}-PROV-REV-CR",
                        "account": "6302",  # Reversal of Provision
                        "credit": recovered_amount,
                        "period": recovery_date.strftime("%Y-%m"),
                        "reference": recovery_id,
                        "created_at": recovery_date,
                    },
                )

                # Update provision status
                await self._db.execute_in_transaction(
                    session,
                    """
                    UPDATE glosa_provisions
                    SET status = 'REVERSED', updated_at = :updated_at
                    WHERE provision_id = :provision_id
                    """,
                    {"provision_id": provision_id, "updated_at": recovery_date},
                )

            # 4. Revenue recognition entries
            # Dr: Accounts Receivable (1101)
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
                    "entry_id": f"{recovery_id}-REV-DR",
                    "account": "1101",  # Accounts Receivable
                    "debit": recovered_amount,
                    "period": recovery_date.strftime("%Y-%m"),
                    "reference": recovery_id,
                    "created_at": recovery_date,
                },
            )

            # Cr: Patient Service Revenue (4101)
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
                    "entry_id": f"{recovery_id}-REV-CR",
                    "account": "4101",  # Patient Service Revenue
                    "credit": recovered_amount,
                    "period": recovery_date.strftime("%Y-%m"),
                    "reference": recovery_id,
                    "created_at": recovery_date,
                },
            )

            # 5. Update recovery metrics
            await self._db.execute_in_transaction(
                session,
                """
                INSERT INTO recovery_metrics (total_recovered, recovery_count, updated_at)
                VALUES (:amount, 1, :updated_at)
                ON CONFLICT DO UPDATE SET
                    total_recovered = recovery_metrics.total_recovered + :amount,
                    recovery_count = recovery_metrics.recovery_count + 1,
                    updated_at = :updated_at
                """,
                {"amount": recovered_amount, "updated_at": recovery_date},
            )

        self._logger.debug(
            "Recovery transaction committed",
            recovery_id=recovery_id,
            provision_reversed=provision_reversed,
        )

        return recovery_date, provision_reversed

    async def _publish_recovery_event(
        self,
        recovery_id: str,
        glosa_id: str,
        recovered_amount: Decimal,
        recovery_method: str,
        recovery_notes: str,
    ) -> None:
        """
        Publish recovery event to Kafka (async, non-blocking).

        Args:
            recovery_id: Recovery identifier
            glosa_id: Glosa identifier
            recovered_amount: Amount recovered
            recovery_method: Method of recovery
            recovery_notes: Additional notes
        """
        if not self._kafka_producer:
            self._logger.debug("Kafka producer not configured, skipping event publication")
            return

        event = {
            "eventType": "RECOVERY_REGISTERED",
            "recoveryId": recovery_id,
            "glosaId": glosa_id,
            "recoveredAmount": float(recovered_amount),
            "recoveryMethod": recovery_method,
            "recoveryNotes": recovery_notes,
            "timestamp": datetime.utcnow().isoformat(),
            "stakeholders": ["RECOVERY_TEAM", "FINANCE", "CLINICAL_TEAM"],
        }

        try:
            await self._kafka_producer.send(
                topic="glosa-recoveries",
                message=event,
                key=recovery_id,
            )
            self._logger.debug(
                "Recovery event published",
                recovery_id=recovery_id,
            )
        except Exception as e:
            # Non-blocking - event will be in DLQ
            self._logger.warning(
                "Failed to publish recovery event",
                recovery_id=recovery_id,
                error=str(e),
            )
