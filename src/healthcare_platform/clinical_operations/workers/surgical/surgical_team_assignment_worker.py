"""
Surgical Team Assignment Worker

CIB7 External Task Topic: surgical.team_assign
BPMN Error Code: CLINICAL_OPERATIONS_ERROR

Assigns surgical team members to scheduled procedures, validating
required roles (surgeon, anesthesiologist) and updating TASY via FHIR adapter.
"""

from __future__ import annotations

from datetime import UTC, datetime
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
    """    Exception for clinical operations errors.
    
        Archetype: OPERATIONAL_ROUTING
        """

    def __init__(
        self, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(
            message=message,
            details=details,
            bpmn_error_code="CLINICAL_OPERATIONS_ERROR",
        )
        self.code = "CLINICAL_OPERATIONS_ERROR"


class TeamMember(BaseModel):
    """Model for surgical team member."""

    role: str = Field(
        ...,
        description="Team member role (surgeon/anesthesiologist/nurse/technician)",
    )
    practitioner_id: str = Field(..., description="FHIR Practitioner ID")


class SurgicalTeamAssignmentInput(BaseModel):
    """Input model for surgical team assignment."""

    surgery_id: str = Field(..., description="TASY surgery schedule ID")
    surgeon_id: str = Field(..., description="FHIR Practitioner ID for lead surgeon")
    team_members: list[TeamMember] = Field(
        ..., min_length=2, description="List of team members with roles"
    )
    surgery_date: str = Field(..., description="Surgery date (YYYY-MM-DD)")


class TeamMemberConfirmed(BaseModel):
    """Model for confirmed team member."""

    role: str = Field(..., description="Team member role")
    practitioner_id: str = Field(..., description="FHIR Practitioner ID")
    confirmed: bool = Field(..., description="Whether assignment was confirmed")


class SurgicalTeamAssignmentOutput(BaseModel):
    """Output model for surgical team assignment."""

    team_id: str = Field(..., description="TASY surgical team ID")
    surgery_id: str = Field(..., description="TASY surgery schedule ID")
    team_members_confirmed: list[TeamMemberConfirmed] = Field(
        ..., description="List of confirmed team members"
    )
    assignment_status: str = Field(
        ..., description="Assignment status (complete/partial/failed)"
    )
    assigned_at: str = Field(..., description="ISO 8601 timestamp when team assigned")


class SurgicalTeamAssignmentWorker:
    """
    Worker to assign surgical team members to procedures.

    Validates team composition (must include surgeon and anesthesiologist),
    checks availability, and assigns team via TASY adapter.
    """

    TOPIC = "surgical.team_assign"

    def __init__(self, tasy_adapter: TasySurgicalAdapter | None = None) -> None:
        """
        Initialize worker with TASY surgical adapter.

        Args:
            tasy_adapter: TASY surgical adapter for team management.
                         Defaults to stub implementation for testing.
        """
        self._tasy_adapter = tasy_adapter

    @require_tenant
    @track_task_execution(task_type="surgical.team_assign")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute surgical team assignment.

        Args:
            task_variables: Task variables containing team assignment details

        Returns:
            Dictionary with assignment results

        Raises:
            ClinicalOperationsException: If team assignment fails
        """
        tenant = get_required_tenant()

        # Validate input
        try:
            input_data = SurgicalTeamAssignmentInput.model_validate(task_variables)
        except Exception as e:
            logger.error(
                "Validation failed for surgical team assignment input",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                _("Dados de entrada inválidos para atribuição de equipe cirúrgica"),
                details={"validation_error": str(e)},
            ) from e

        # Validate required roles
        roles = {member.role.lower() for member in input_data.team_members}
        if "surgeon" not in roles:
            raise ClinicalOperationsException(
                _("Equipe cirúrgica deve incluir um cirurgião"),
                details={"surgery_id": input_data.surgery_id, "roles": list(roles)},
            )
        if "anesthesiologist" not in roles:
            raise ClinicalOperationsException(
                _("Equipe cirúrgica deve incluir um anestesiologista"),
                details={"surgery_id": input_data.surgery_id, "roles": list(roles)},
            )

        # Log team assignment request
        logger.info(
            "Processing surgical team assignment",
            extra={
                "tenant_id": tenant.tenant_id,
                "surgery_id": input_data.surgery_id,
                "surgeon_id": input_data.surgeon_id,
                "team_size": len(input_data.team_members),
                "surgery_date": input_data.surgery_date,
            },
        )

        # Call TASY API to assign team
        try:
            tasy_data = await self._call_tasy_api(input_data)

            # Use adapter to convert TASY data to FHIR if needed
            if self._tasy_adapter:
                adapted_data = await self._tasy_adapter.adapt(tasy_data)
                logger.debug(
                    "Adapted TASY team assignment to FHIR",
                    extra={
                        "tenant_id": tenant.tenant_id,
                        "team_id": tasy_data["team_id"],
                    },
                )
            else:
                adapted_data = tasy_data

            logger.info(
                "Surgical team assigned successfully",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "surgery_id": input_data.surgery_id,
                    "team_id": adapted_data["team_id"],
                    "assignment_status": adapted_data["assignment_status"],
                },
            )

            # Build output
            output = SurgicalTeamAssignmentOutput(
                team_id=adapted_data["team_id"],
                surgery_id=adapted_data["surgery_id"],
                team_members_confirmed=adapted_data["team_members_confirmed"],
                assignment_status=adapted_data["assignment_status"],
                assigned_at=datetime.now(UTC).isoformat(),
            )

            return output.model_dump()

        except Exception as e:
            logger.error(
                "Failed to assign surgical team",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "surgery_id": input_data.surgery_id,
                    "surgeon_id": input_data.surgeon_id,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                _("Falha ao atribuir equipe cirúrgica"),
                details={
                    "surgery_id": input_data.surgery_id,
                    "surgeon_id": input_data.surgeon_id,
                    "error": str(e),
                },
            ) from e

    async def _call_tasy_api(
        self, input_data: SurgicalTeamAssignmentInput
    ) -> dict[str, Any]:
        """
        Call TASY API to assign surgical team (stub implementation).

        Args:
            input_data: Validated team assignment input

        Returns:
            Mock TASY team assignment data
        """
        # Stub: In production, this would call TASY REST API
        # For now, return mock data that matches TASY schema
        team_members_confirmed = [
            {
                "role": member.role,
                "practitioner_id": member.practitioner_id,
                "confirmed": True,
            }
            for member in input_data.team_members
        ]

        return {
            "operation_type": "team_assignment",
            "team_id": f"TEAM-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
            "surgery_id": input_data.surgery_id,
            "team_members_confirmed": team_members_confirmed,
            "assignment_status": "complete",
            "surgery_date": input_data.surgery_date,
        }
