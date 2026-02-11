"""
Operating Room Turnover Worker

CIB7 External Task Topic: surgical.or_turnover
BPMN Error Code: CLINICAL_OPERATIONS_ERROR

Initiates and tracks operating room turnover and cleaning procedures
between surgical cases via TASY adapter integration.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.integrations.tasy_adapters.surgical_adapter import (
    TasySurgicalAdapter,
)
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


def _(message: str) -> str:
    """Translation helper for Portuguese error messages."""
    return message


class ClinicalOperationsException(DomainException):
    """Exception for clinical operations errors."""

    def __init__(
        self, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(
            message=message,
            details=details,
            bpmn_error_code="CLINICAL_OPERATIONS_ERROR",
        )
        self.code = "CLINICAL_OPERATIONS_ERROR"


class ORTurnoverInput(BaseModel):
    """Input model for OR turnover initiation."""

    operating_room_id: str = Field(..., description="Operating room identifier")
    previous_surgery_id: str = Field(
        ..., description="TASY surgery ID that just completed"
    )
    next_surgery_id: str | None = Field(
        None, description="TASY surgery ID scheduled next (if known)"
    )
    turnover_type: str = Field(
        ...,
        pattern="^(standard|deep_clean|terminal)$",
        description="Type of turnover/cleaning required",
    )
    estimated_minutes: int | None = Field(
        None, ge=5, le=240, description="Estimated turnover duration in minutes"
    )


class ORTurnoverOutput(BaseModel):
    """Output model for OR turnover tracking."""

    turnover_id: str = Field(..., description="TASY OR turnover tracking ID")
    operating_room_id: str = Field(..., description="Operating room identifier")
    status: str = Field(
        ..., description="Turnover status (cleaning/ready/delayed)"
    )
    estimated_completion: str = Field(
        ..., description="ISO 8601 timestamp for estimated completion"
    )
    started_at: str = Field(
        ..., description="ISO 8601 timestamp when turnover started"
    )


class ORTurnoverWorker:
    """
    Worker to initiate and track operating room turnover.

    Validates turnover request, initiates cleaning procedures via TASY,
    and tracks room status until ready for next case.
    """

    TOPIC = "surgical.or_turnover"

    # Typical turnover durations by type (in minutes)
    TURNOVER_DURATIONS = {
        "standard": 20,
        "deep_clean": 45,
        "terminal": 90,
    }

    def __init__(self, tasy_adapter: TasySurgicalAdapter | None = None) -> None:
        """
        Initialize worker with TASY surgical adapter.

        Args:
            tasy_adapter: TASY surgical adapter for OR management.
                         Defaults to stub implementation for testing.
        """
        self._tasy_adapter = tasy_adapter

    @require_tenant
    @track_task_execution(task_type="surgical.or_turnover")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute OR turnover initiation.

        Args:
            task_variables: Task variables containing turnover request details

        Returns:
            Dictionary with turnover tracking results

        Raises:
            ClinicalOperationsException: If turnover initiation fails
        """
        tenant = get_required_tenant()

        # Validate input
        try:
            input_data = ORTurnoverInput.model_validate(task_variables)
        except Exception as e:
            logger.error(
                "Validation failed for OR turnover input",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                _("Dados de entrada inválidos para rotatividade de sala cirúrgica"),
                details={"validation_error": str(e)},
            ) from e

        # Determine estimated duration if not provided
        estimated_minutes = input_data.estimated_minutes or self.TURNOVER_DURATIONS.get(
            input_data.turnover_type, 20
        )

        # Log turnover initiation
        logger.info(
            "Processing OR turnover initiation",
            extra={
                "tenant_id": tenant.tenant_id,
                "operating_room_id": input_data.operating_room_id,
                "previous_surgery_id": input_data.previous_surgery_id,
                "turnover_type": input_data.turnover_type,
                "estimated_minutes": estimated_minutes,
            },
        )

        # Call TASY API to initiate turnover
        try:
            tasy_data = await self._call_tasy_api(input_data, estimated_minutes)

            # Use adapter to convert TASY data to FHIR if needed
            if self._tasy_adapter:
                adapted_data = await self._tasy_adapter.adapt(tasy_data)
                logger.debug(
                    "Adapted TASY OR turnover to FHIR",
                    extra={
                        "tenant_id": tenant.tenant_id,
                        "turnover_id": tasy_data["turnover_id"],
                    },
                )
            else:
                adapted_data = tasy_data

            logger.info(
                "OR turnover initiated successfully",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "operating_room_id": input_data.operating_room_id,
                    "turnover_id": adapted_data["turnover_id"],
                    "status": adapted_data["status"],
                    "estimated_completion": adapted_data["estimated_completion"],
                },
            )

            # Build output
            output = ORTurnoverOutput(
                turnover_id=adapted_data["turnover_id"],
                operating_room_id=adapted_data["operating_room_id"],
                status=adapted_data["status"],
                estimated_completion=adapted_data["estimated_completion"],
                started_at=datetime.now(UTC).isoformat(),
            )

            return output.model_dump()

        except Exception as e:
            logger.error(
                "Failed to initiate OR turnover",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "operating_room_id": input_data.operating_room_id,
                    "previous_surgery_id": input_data.previous_surgery_id,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                _("Falha ao iniciar rotatividade de sala cirúrgica"),
                details={
                    "operating_room_id": input_data.operating_room_id,
                    "previous_surgery_id": input_data.previous_surgery_id,
                    "error": str(e),
                },
            ) from e

    async def _call_tasy_api(
        self, input_data: ORTurnoverInput, estimated_minutes: int
    ) -> dict[str, Any]:
        """
        Call TASY API to initiate OR turnover (stub implementation).

        Args:
            input_data: Validated turnover input
            estimated_minutes: Calculated estimated duration

        Returns:
            Mock TASY OR turnover data
        """
        # Stub: In production, this would call TASY REST API
        # For now, return mock data that matches TASY schema
        started_at = datetime.now(UTC)
        estimated_completion = started_at + timedelta(minutes=estimated_minutes)

        return {
            "operation_type": "turnover_status",
            "turnover_id": f"TURN-{started_at.strftime('%Y%m%d%H%M%S')}",
            "operating_room_id": input_data.operating_room_id,
            "previous_surgery_id": input_data.previous_surgery_id,
            "next_surgery_id": input_data.next_surgery_id,
            "turnover_type": input_data.turnover_type,
            "status": "cleaning",
            "estimated_completion": estimated_completion.isoformat(),
            "estimated_minutes": estimated_minutes,
        }
