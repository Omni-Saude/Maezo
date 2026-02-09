"""
UpdateStatusWorker - Camunda 8 External Task Worker.

Updates claim/billing entity status with state machine validation:
- State machine validation (prevent invalid transitions)
- Audit trail creation for all status changes
- Multi-entity type support (CLAIM|BILLING|ENCOUNTER)
- Timestamp tracking for compliance

This worker handles status updates with complete audit trail.

Business Rule: RN-BIL-007-UpdateStatus.md
Regulatory Compliance: ANS RN 439/2015, TISS 4.01.00, Sarbanes-Oxley Act
Migrated from: com.hospital.revenuecycle.delegates.UpdateStatusDelegate

Section references:
- Claim/billing status state machine
- Valid status transitions
- Audit trail and timestamp tracking
- Compliance logging for financial records

BPMN Task: Task_Update_Status in SUB_06_Billing_Submission
Zeebe Topic: update-status
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

import structlog

from revenue_cycle.domain.exceptions import (
    BpmnErrorException,
    BusinessRuleException,
)
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker
from revenue_cycle.workers.billing.models import (
    UpdateStatusInput,
    UpdateStatusOutput,
    EntityType,
)

logger = structlog.get_logger(__name__)


# Valid status transitions state machine
VALID_TRANSITIONS = {
    "PENDING": ["IN_PROGRESS", "HELD", "CANCELLED"],
    "IN_PROGRESS": ["COMPLETED", "HELD", "REJECTED", "FAILED"],
    "HELD": ["IN_PROGRESS", "REJECTED", "CANCELLED"],
    "COMPLETED": ["PAID", "PARTIALLY_PAID", "DISPUTED"],
    "PARTIALLY_PAID": ["PAID", "DISPUTED", "HELD"],
    "PAID": ["DISPUTED"],  # Can only dispute after payment
    "DISPUTED": ["RESOLVED", "REJECTED"],
    "RESOLVED": ["PAID", "HELD"],
    "REJECTED": ["HELD"],  # Can only retry from hold
    "FAILED": ["PENDING", "HELD"],  # Can retry or hold
    "CANCELLED": [],  # Terminal state
}


class InvalidStatusTransitionError(BusinessRuleException):
    """Raised when status transition is not allowed."""

    def __init__(
        self,
        entity_id: str,
        entity_type: str,
        current_status: str,
        new_status: str,
    ):
        super().__init__(
            message=(
                f"Cannot transition {entity_type} {entity_id} from "
                f"{current_status} to {new_status}"
            ),
            rule_name="STATUS_TRANSITION",
            code="INVALID_STATUS_TRANSITION",
            details={
                "entity_id": entity_id,
                "entity_type": entity_type,
                "current_status": current_status,
                "new_status": new_status,
                "allowed_transitions": VALID_TRANSITIONS.get(current_status, []),
            },
        )


class InvalidEntityTypeError(BusinessRuleException):
    """Raised when entity type is not supported."""

    def __init__(self, entity_type: str):
        super().__init__(
            message=f"Entity type not supported: {entity_type}",
            rule_name="INVALID_ENTITY_TYPE",
            code="INVALID_ENTITY_TYPE",
            details={
                "entity_type": entity_type,
                "supported_types": ["CLAIM", "BILLING", "ENCOUNTER"],
            },
        )


@worker(
    topic="update-status",
    lock_duration=30000,  # 30 seconds
    max_jobs=32,
)
class UpdateStatusWorker(BaseWorker):
    """
    Zeebe worker for updating entity status with state machine validation.

    Validates all status transitions using defined state machine rules.
    Creates complete audit trail for all status changes.

    Supports multiple entity types:
    - CLAIM: Claim status updates
    - BILLING: Billing statement updates
    - ENCOUNTER: Encounter status updates

    Input Variables:
        entityId: Identifier of entity to update
        entityType: Type of entity (CLAIM|BILLING|ENCOUNTER)
        currentStatus: Current entity status
        newStatus: Desired new status
        reason: Reason for status change

    Output Variables:
        previousStatus: Status before change
        currentStatus: Status after change
        statusChangeDate: ISO timestamp of change
        auditTrailId: Unique audit trail entry identifier
        transitionAllowed: Whether transition was valid
        auditEntry: Full audit trail entry details

    BPMN Errors:
        INVALID_STATUS_TRANSITION: Status change not allowed
        INVALID_ENTITY_TYPE: Entity type not supported
    """

    def __init__(self, settings: Any = None, **kwargs: Any):
        """
        Initialize the worker.

        Args:
            settings: Application settings
            **kwargs: Additional arguments for BaseWorker
        """
        super().__init__(settings=settings)
        self._logger = logger.bind(worker=self.worker_name)

    @property
    def operation_name(self) -> str:
        """Get the operation name for idempotency and logging."""
        return "update_status"

    @property
    def requires_idempotency(self) -> bool:
        """
        Status updates must be idempotent.

        Same entity + same status = same result (idempotent).
        """
        return True

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the update-status task.

        Main processing flow:
        1. Parse and validate input variables
        2. Validate entity type
        3. Validate status transition via state machine
        4. Generate audit trail entry
        5. Build output with audit information

        Args:
            job: Camunda external task
            variables: Job variables from the process

        Returns:
            WorkerResult with status update and audit trail

        Raises:
            InvalidEntityTypeError: If entity type invalid
            InvalidStatusTransitionError: If transition not allowed
        """
        job_key = str(getattr(job, "key", "unknown"))

        self._logger.info(
            "Starting status update",
            job_key=job_key,
        )

        try:
            # 1. Parse and validate input
            input_data = self._parse_input(variables)

            self._logger.info(
                "Processing status update",
                entity_id=input_data.entity_id,
                entity_type=input_data.entity_type,
                current_status=input_data.current_status,
                new_status=input_data.new_status,
                reason=input_data.reason,
            )

            # 2. Validate entity type
            self._validate_entity_type(input_data.entity_type)

            # 3. Validate status transition
            self._validate_transition(input_data)

            # 4. Generate audit trail entry
            audit_trail_id = self._generate_audit_trail_id(input_data)
            status_change_date = datetime.utcnow()

            # 5. Create audit entry
            audit_entry = self._create_audit_entry(
                input_data,
                audit_trail_id,
                status_change_date,
            )

            # 6. Build output
            output = UpdateStatusOutput(
                previous_status=input_data.current_status,
                current_status=input_data.new_status,
                status_change_date=status_change_date,
                audit_trail_id=audit_trail_id,
                entity_id=input_data.entity_id,
                entity_type=input_data.entity_type,
                reason=input_data.reason,
                audit_entry=audit_entry,
            )

            self._logger.info(
                "Status updated successfully",
                entity_id=input_data.entity_id,
                entity_type=input_data.entity_type,
                from_status=input_data.current_status,
                to_status=input_data.new_status,
                audit_trail_id=audit_trail_id,
            )

            return WorkerResult.ok(output.model_dump(by_alias=True))

        except InvalidEntityTypeError as e:
            self._logger.warning(
                "Invalid entity type",
                entity_type=variables.get("entityType"),
                details=e.details,
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_ENTITY_TYPE",
                error_message=str(e),
                variables=e.details,
            )

        except InvalidStatusTransitionError as e:
            self._logger.warning(
                "Invalid status transition",
                entity_id=variables.get("entityId"),
                details=e.details,
            )
            return WorkerResult.bpmn_error(
                error_code="INVALID_STATUS_TRANSITION",
                error_message=str(e),
                variables=e.details,
            )

        except Exception as e:
            self._logger.exception(
                "Status update failed",
                error=str(e),
            )
            raise

    def _parse_input(self, variables: dict[str, Any]) -> UpdateStatusInput:
        """
        Parse and validate input variables.

        Args:
            variables: Job variables

        Returns:
            Validated input model

        Raises:
            BpmnErrorException: If validation fails
        """
        try:
            return UpdateStatusInput.model_validate(variables)
        except Exception as e:
            raise BpmnErrorException(
                error_code="INVALID_INPUT",
                message=f"Invalid input data: {e}",
            )

    def _validate_entity_type(self, entity_type: str) -> None:
        """
        Validate entity type is supported.

        Args:
            entity_type: Type of entity

        Raises:
            InvalidEntityTypeError: If type not supported
        """
        supported_types = ["CLAIM", "BILLING", "ENCOUNTER"]

        if entity_type not in supported_types:
            raise InvalidEntityTypeError(entity_type)

        self._logger.debug(
            "Entity type validated",
            entity_type=entity_type,
        )

    def _validate_transition(self, input_data: UpdateStatusInput) -> None:
        """
        Validate status transition using state machine.

        Args:
            input_data: Parsed input with status info

        Raises:
            InvalidStatusTransitionError: If transition not allowed
        """
        current = input_data.current_status
        new = input_data.new_status

        # Check if transition is in valid transitions map
        allowed = VALID_TRANSITIONS.get(current, [])

        if new not in allowed:
            raise InvalidStatusTransitionError(
                input_data.entity_id,
                input_data.entity_type,
                current,
                new,
            )

        self._logger.debug(
            "Status transition validated",
            entity_id=input_data.entity_id,
            current_status=current,
            new_status=new,
        )

    def _generate_audit_trail_id(
        self, input_data: UpdateStatusInput
    ) -> str:
        """
        Generate unique audit trail entry identifier.

        Format: {entityType}-{entityId}-{timestamp}

        Args:
            input_data: Input with entity info

        Returns:
            Unique audit trail identifier
        """
        timestamp = int(datetime.utcnow().timestamp() * 1000)
        audit_id = (
            f"{input_data.entity_type}-{input_data.entity_id}-{timestamp}"
        )

        self._logger.debug(
            "Audit trail ID generated",
            audit_trail_id=audit_id,
        )

        return audit_id

    def _create_audit_entry(
        self,
        input_data: UpdateStatusInput,
        audit_trail_id: str,
        timestamp: datetime,
    ) -> dict[str, Any]:
        """
        Create audit trail entry record.

        Args:
            input_data: Input with change information
            audit_trail_id: Unique audit trail ID
            timestamp: Change timestamp

        Returns:
            Audit entry dictionary
        """
        entry = {
            "audit_trail_id": audit_trail_id,
            "entity_type": input_data.entity_type,
            "entity_id": input_data.entity_id,
            "status_from": input_data.current_status,
            "status_to": input_data.new_status,
            "change_reason": input_data.reason,
            "changed_at": timestamp.isoformat(),
            "changed_by": "system",  # Could be enhanced with user context
            "change_type": "STATUS_UPDATE",
        }

        self._logger.debug(
            "Audit entry created",
            audit_trail_id=audit_trail_id,
            entry=entry,
        )

        return entry

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """
        Extract parameters for idempotency key generation.

        Uses entity_id, entity_type and new_status for deterministic key.

        Args:
            variables: Job variables

        Returns:
            String representation of key parameters
        """
        entity_id = variables.get("entityId", "")
        entity_type = variables.get("entityType", "")
        new_status = variables.get("newStatus", "")
        process_instance = variables.get("processInstanceKey", "")
        return f"{process_instance}:{entity_type}:{entity_id}:{new_status}"


# Worker registration function for use with Zeebe client
def create_update_status_worker(settings: Any = None) -> UpdateStatusWorker:
    """
    Factory function to create UpdateStatusWorker.

    Args:
        settings: Optional application settings

    Returns:
        Configured worker instance
    """
    return UpdateStatusWorker(settings=settings)
