"""
OR Scheduling Optimization Worker - Operating room utilization optimization.

CIB7 External Task Topic: surgical.or_optimization
BPMN Error Code: SURGICAL_OPERATIONS_ERROR

Optimizes operating room scheduling for maximum utilization.
Considers procedure duration, turnover time, and resource availability.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.tasy_adapters.surgical_adapter import TasySurgicalAdapter
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__, worker="surgical.or_optimization")

TOPIC = "surgical.or_optimization"


class SurgicalOperationsException(DomainException):
    """Surgical operations domain exception."""

    bpmn_error_code = "SURGICAL_OPERATIONS_ERROR"

    def __init__(
        self,
        message: str,
        details: Optional[dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        super().__init__(message=message, details=details, cause=cause)


class ScheduledProcedure(BaseModel):
    """Scheduled surgical procedure model."""

    procedure_id: str = Field(..., description="Unique procedure identifier")
    procedure_code: str = Field(..., description="Procedure code (CPT/ICD)")
    estimated_duration_minutes: int = Field(
        ...,
        gt=0,
        description="Estimated procedure duration in minutes"
    )
    priority: str = Field(
        ...,
        description="Procedure priority (elective/urgent/emergency)"
    )
    surgeon_id: str = Field(..., description="Surgeon identifier")
    required_equipment: List[str] = Field(
        default_factory=list,
        description="List of required equipment"
    )

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        """Validate priority is one of the allowed values."""
        allowed = {"elective", "urgent", "emergency"}
        if v.lower() not in allowed:
            raise ValueError(
                f"Priority must be one of {allowed}, got '{v}'"
            )
        return v.lower()


class ORSchedulingInput(BaseModel):
    """Input model for OR scheduling optimization."""

    operating_room_id: str = Field(..., description="Operating room identifier")
    date: datetime = Field(..., description="Date for scheduling")
    available_start: datetime = Field(..., description="OR available start time")
    available_end: datetime = Field(..., description="OR available end time")
    procedures: List[ScheduledProcedure] = Field(
        default_factory=list,
        description="List of procedures to schedule"
    )
    turnover_time_minutes: int = Field(
        default=30,
        ge=0,
        description="Turnover time between procedures in minutes"
    )
    cleaning_time_minutes: int = Field(
        default=15,
        ge=0,
        description="Deep cleaning time in minutes"
    )

    @field_validator("available_end")
    @classmethod
    def validate_time_range(cls, v: datetime, info) -> datetime:
        """Validate end time is after start time."""
        if "available_start" in info.data and v <= info.data["available_start"]:
            raise ValueError("available_end must be after available_start")
        return v


class ORSchedulingOutput(BaseModel):
    """Output model for OR scheduling optimization."""

    optimization_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique optimization run identifier"
    )
    operating_room_id: str = Field(..., description="Operating room identifier")
    date: datetime = Field(..., description="Scheduled date")
    scheduled_slots: List[dict] = Field(
        default_factory=list,
        description="List of scheduled procedure slots"
    )
    utilization_percentage: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="OR utilization percentage"
    )
    unscheduled_procedures: List[str] = Field(
        default_factory=list,
        description="List of procedure IDs that didn't fit"
    )
    total_or_minutes: int = Field(
        ...,
        ge=0,
        description="Total available OR minutes"
    )
    idle_minutes: int = Field(
        ...,
        ge=0,
        description="Total idle minutes"
    )
    optimization_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When optimization was performed"
    )


class ORSchedulingOptimizationWorker:
    """Worker for optimizing OR scheduling and utilization."""

    def __init__(self, tasy_adapter: Optional[TasySurgicalAdapter] = None):
        """Initialize the OR scheduling optimization worker.

        Args:
            tasy_adapter: Optional TASY surgical adapter for integration
        """
        self.tasy_adapter = tasy_adapter or TasySurgicalAdapter()
        logger.info("Initialized ORSchedulingOptimizationWorker")

    @require_tenant
    @track_task_execution(task_type="surgical.or_optimization")
    async def execute(self, variables: dict[str, Any]) -> dict[str, Any]:
        """Execute OR scheduling optimization.

        Args:
            variables: Task variables containing scheduling parameters

        Returns:
            Dictionary containing optimization results

        Raises:
            SurgicalOperationsException: If optimization fails
        """
        tenant_id = get_required_tenant()

        try:
            # Parse input
            input_data = ORSchedulingInput(**variables)

            logger.info(
                "Starting OR scheduling optimization",
                extra={
                    "tenant_id": tenant_id,
                    "operating_room_id": input_data.operating_room_id,
                    "date": input_data.date.isoformat(),
                    "procedure_count": len(input_data.procedures),
                }
            )

            # Sort procedures by priority
            sorted_procedures = self._sort_procedures_by_priority(
                input_data.procedures
            )

            logger.debug(
                "Sorted procedures by priority",
                extra={
                    "procedure_order": [p.procedure_id for p in sorted_procedures],
                }
            )

            # Schedule procedures greedily
            scheduled_slots, unscheduled = self._schedule_procedures(
                procedures=sorted_procedures,
                available_start=input_data.available_start,
                available_end=input_data.available_end,
                turnover_time_minutes=input_data.turnover_time_minutes,
            )

            # Calculate utilization metrics
            total_minutes = int(
                (input_data.available_end - input_data.available_start).total_seconds() / 60
            )

            used_minutes = sum(
                slot["duration_minutes"] + slot["turnover_after"]
                for slot in scheduled_slots
            )

            idle_minutes = total_minutes - used_minutes
            utilization_percentage = (
                (used_minutes / total_minutes * 100.0) if total_minutes > 0 else 0.0
            )

            # Create output
            output = ORSchedulingOutput(
                operating_room_id=input_data.operating_room_id,
                date=input_data.date,
                scheduled_slots=scheduled_slots,
                utilization_percentage=round(utilization_percentage, 2),
                unscheduled_procedures=unscheduled,
                total_or_minutes=total_minutes,
                idle_minutes=idle_minutes,
            )

            logger.info(
                "OR scheduling optimization completed",
                extra={
                    "tenant_id": tenant_id,
                    "optimization_id": output.optimization_id,
                    "scheduled_count": len(scheduled_slots),
                    "unscheduled_count": len(unscheduled),
                    "utilization_percentage": output.utilization_percentage,
                }
            )

            return output.model_dump(mode="json")

        except ValueError as e:
            logger.error(
                "Invalid input for OR scheduling optimization",
                extra={"tenant_id": tenant_id, "error": str(e)},
                exc_info=True,
            )
            raise SurgicalOperationsException(
                message=_("Invalid OR scheduling parameters: {error}").format(
                    error=str(e)
                ),
                details={"validation_error": str(e)},
                cause=e,
            )
        except Exception as e:
            logger.error(
                "OR scheduling optimization failed",
                extra={"tenant_id": tenant_id, "error": str(e)},
                exc_info=True,
            )
            raise SurgicalOperationsException(
                message=_("Failed to optimize OR scheduling: {error}").format(
                    error=str(e)
                ),
                details={"error": str(e)},
                cause=e,
            )

    def _sort_procedures_by_priority(
        self,
        procedures: List[ScheduledProcedure]
    ) -> List[ScheduledProcedure]:
        """Sort procedures by priority (emergency > urgent > elective).

        Args:
            procedures: List of procedures to sort

        Returns:
            Sorted list of procedures
        """
        priority_order = {"emergency": 0, "urgent": 1, "elective": 2}

        return sorted(
            procedures,
            key=lambda p: priority_order.get(p.priority.lower(), 3)
        )

    def _schedule_procedures(
        self,
        procedures: List[ScheduledProcedure],
        available_start: datetime,
        available_end: datetime,
        turnover_time_minutes: int,
    ) -> tuple[List[dict], List[str]]:
        """Schedule procedures greedily into available time slots.

        Args:
            procedures: List of procedures to schedule (priority-sorted)
            available_start: OR available start time
            available_end: OR available end time
            turnover_time_minutes: Turnover time between procedures

        Returns:
            Tuple of (scheduled_slots, unscheduled_procedure_ids)
        """
        scheduled_slots: List[dict] = []
        unscheduled: List[str] = []

        current_time = available_start

        for procedure in procedures:
            # Calculate end time for this procedure
            procedure_duration = timedelta(
                minutes=procedure.estimated_duration_minutes
            )
            procedure_end = current_time + procedure_duration

            # Check if procedure fits
            if procedure_end <= available_end:
                # Schedule the procedure
                slot = {
                    "procedure_id": procedure.procedure_id,
                    "procedure_code": procedure.procedure_code,
                    "start": current_time.isoformat(),
                    "end": procedure_end.isoformat(),
                    "duration_minutes": procedure.estimated_duration_minutes,
                    "priority": procedure.priority,
                    "surgeon_id": procedure.surgeon_id,
                    "turnover_after": turnover_time_minutes,
                }
                scheduled_slots.append(slot)

                # Move current time forward (procedure + turnover)
                current_time = procedure_end + timedelta(
                    minutes=turnover_time_minutes
                )

                logger.debug(
                    "Scheduled procedure",
                    extra={
                        "procedure_id": procedure.procedure_id,
                        "start": slot["start"],
                        "end": slot["end"],
                    }
                )
            else:
                # Procedure doesn't fit
                unscheduled.append(procedure.procedure_id)

                logger.debug(
                    "Procedure doesn't fit in available time",
                    extra={
                        "procedure_id": procedure.procedure_id,
                        "required_end": procedure_end.isoformat(),
                        "available_end": available_end.isoformat(),
                    }
                )

        return scheduled_slots, unscheduled
