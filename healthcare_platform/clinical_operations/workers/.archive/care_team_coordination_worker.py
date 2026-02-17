"""
Care Team Coordination Worker

Coordinates care team communications and collaboration.
Manages messages between care team members and tracks acknowledgments.
Uses FHIR CareTeam resource for team composition.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.fhir_client import FHIRClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService, get_dmn_service

logger = get_logger(__name__, worker="clinical.care_team")


class ClinicalException(DomainException):
    """    Clinical operations domain exception.
    
        Archetype: OPERATIONAL_ROUTING
        """
    bpmn_error_code: str = "CLINICAL_ERROR"


class InvalidMessageTypeError(ClinicalException):
    """Raised when message type is not recognized."""
    bpmn_error_code: str = "INVALID_MESSAGE_TYPE"


class CareTeamNotFoundError(ClinicalException):
    """Raised when care team is not found."""
    bpmn_error_code: str = "CARE_TEAM_NOT_FOUND"


class CoordinationError(ClinicalException):
    """Raised when coordination fails."""
    bpmn_error_code: str = "COORDINATION_FAILED"


class CareTeamCoordinationInput(BaseModel):
    """Input model for care team coordination worker."""

    encounter_reference: str = Field(
        ...,
        description=_("Referência do encontro clínico (Encounter)")
    )
    care_team_members: list[str] = Field(
        ...,
        description=_("Lista de referências de membros do time (Practitioner)")
    )
    message_type: str = Field(
        ...,
        description=_("Tipo de mensagem: urgent, routine, consultation, update")
    )
    message_content: str = Field(
        ...,
        description=_("Conteúdo da mensagem")
    )
    sender_reference: str | None = Field(
        None,
        description=_("Referência do remetente (Practitioner)")
    )
    priority: str = Field(
        default="routine",
        description=_("Prioridade: urgent, high, routine, low")
    )

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables."""
        return {
            "encounter_reference": self.encounter_reference,
            "care_team_members": self.care_team_members,
            "message_type": self.message_type,
            "message_content": self.message_content,
            "sender_reference": self.sender_reference,
            "priority": self.priority,
        }


class CareTeamCoordinationOutput(BaseModel):
    """Output model for care team coordination worker."""

    coordination_status: str = Field(
        ...,
        description=_("Status da coordenação: sent, partial, failed")
    )
    notified_members: list[str] = Field(
        default_factory=list,
        description=_("Lista de membros notificados")
    )
    pending_acknowledgments: list[str] = Field(
        default_factory=list,
        description=_("Lista de membros pendentes de confirmação")
    )
    communication_id: str = Field(
        ...,
        description=_("ID da comunicação criada")
    )
    sent_at: str = Field(
        ...,
        description=_("Data/hora de envio (ISO 8601)")
    )

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables."""
        return {
            "coordination_status": self.coordination_status,
            "notified_members": self.notified_members,
            "pending_acknowledgments": self.pending_acknowledgments,
            "communication_id": self.communication_id,
            "sent_at": self.sent_at,
        }


class CareTeamCoordinationProtocol(ABC):
    """Protocol for care team coordination operations."""

    @abstractmethod
    async def coordinate_care_team(
        self,
        encounter_reference: str,
        care_team_members: list[str],
        message_type: str,
        message_content: str,
        sender_reference: str | None = None,
        priority: str = "routine",
    ) -> dict[str, Any]:
        """
        Coordinate care team communications.

        Args:
            encounter_reference: Reference to the clinical encounter
            care_team_members: List of care team member references
            message_type: Type of message (urgent, routine, consultation, update)
            message_content: Content of the message
            sender_reference: Reference to the sender
            priority: Priority level (urgent, high, routine, low)

        Returns:
            Dictionary containing coordination details

        Raises:
            InvalidMessageTypeError: If message type is invalid
            CareTeamNotFoundError: If care team not found
            CoordinationError: If coordination fails
        """
        pass


class DMNCareTeamCoordination(CareTeamCoordinationProtocol):
    """DMN-backed care team coordination using FederatedDMNService."""

    def __init__(
        self,
        fhir_client: FHIRClientProtocol,
        dmn_service: FederatedDMNService | None = None,
    ) -> None:
        self._fhir = fhir_client
        self._dmn = dmn_service or get_dmn_service()
        self._fallback = CareTeamCoordinationStub(fhir_client=fhir_client)

    async def coordinate_care_team(
        self,
        encounter_reference: str,
        care_team_members: list[str],
        message_type: str,
        message_content: str,
        sender_reference: str | None = None,
        priority: str = "routine",
    ) -> dict[str, Any]:
        """Coordinate care team with DMN-driven priority routing."""
        tenant_id = get_required_tenant().tenant_id
        try:
            result = self._dmn.evaluate(
                tenant_id=tenant_id,
                category="clinical_safety",
                table_name="safety/care_team_routing_001",
                inputs={
                    "message_type": message_type,
                    "priority": priority,
                    "team_size": len(care_team_members),
                },
            )
            if result and result.get("escalated_priority"):
                priority = result["escalated_priority"]
        except (FileNotFoundError, ValueError):
            pass
        except Exception:
            pass
        return await self._fallback.coordinate_care_team(
            encounter_reference, care_team_members, message_type,
            message_content, sender_reference, priority,
        )


class CareTeamCoordinationStub(CareTeamCoordinationProtocol):
    """Stub implementation for care team coordination."""

    VALID_MESSAGE_TYPES = {"urgent", "routine", "consultation", "update"}
    VALID_PRIORITIES = {"urgent", "high", "routine", "low"}

    MESSAGE_CATEGORIES = {
        "urgent": {
            "system": "http://terminology.hl7.org/CodeSystem/communication-category",
            "code": "alert",
            "display": "Alert"
        },
        "routine": {
            "system": "http://terminology.hl7.org/CodeSystem/communication-category",
            "code": "notification",
            "display": "Notification"
        },
        "consultation": {
            "system": "http://terminology.hl7.org/CodeSystem/communication-category",
            "code": "instruction",
            "display": "Instruction"
        },
        "update": {
            "system": "http://terminology.hl7.org/CodeSystem/communication-category",
            "code": "notification",
            "display": "Notification"
        }
    }

    def __init__(self, fhir_client: FHIRClientProtocol):
        """Initialize with FHIR client dependency."""
        self.fhir_client = fhir_client

    def _hash_reference(self, reference: str) -> str:
        """Hash reference for LGPD compliance."""
        return hashlib.sha256(reference.encode()).hexdigest()[:16]

    def _validate_message_type(self, message_type: str) -> None:
        """Validate message type."""
        if message_type not in self.VALID_MESSAGE_TYPES:
            logger.error(
                _("Tipo de mensagem inválido: %s. Tipos válidos: %s"),
                message_type,
                ", ".join(self.VALID_MESSAGE_TYPES)
            )
            raise InvalidMessageTypeError(
                _("Tipo de mensagem inválido: {message_type}").format(
                    message_type=message_type
                )
            )

    def _validate_priority(self, priority: str) -> None:
        """Validate priority level."""
        if priority not in self.VALID_PRIORITIES:
            logger.warning(
                _("Prioridade inválida: %s. Usando 'routine'"),
                priority
            )
            return "routine"
        return priority

    def _build_communication_resource(
        self,
        encounter_reference: str,
        care_team_members: list[str],
        message_type: str,
        message_content: str,
        sender_reference: str | None,
        priority: str,
    ) -> dict[str, Any]:
        """Build FHIR Communication resource."""
        category = self.MESSAGE_CATEGORIES[message_type]
        sent_at = datetime.utcnow().isoformat() + "Z"

        communication = {
            "resourceType": "Communication",
            "status": "in-progress",
            "category": [{
                "coding": [{
                    "system": category["system"],
                    "code": category["code"],
                    "display": category["display"]
                }]
            }],
            "priority": priority,
            "sent": sent_at,
            "recipient": [
                {"reference": member} for member in care_team_members
            ],
            "payload": [{
                "contentString": message_content
            }],
            "encounter": {
                "reference": encounter_reference
            }
        }

        if sender_reference:
            communication["sender"] = {
                "reference": sender_reference
            }

        return communication

    def _determine_coordination_status(
        self,
        total_members: int,
        notified_count: int,
    ) -> str:
        """Determine coordination status based on notifications."""
        if notified_count == 0:
            return "failed"
        elif notified_count < total_members:
            return "partial"
        else:
            return "sent"

    async def coordinate_care_team(
        self,
        encounter_reference: str,
        care_team_members: list[str],
        message_type: str,
        message_content: str,
        sender_reference: str | None = None,
        priority: str = "routine",
    ) -> dict[str, Any]:
        """Coordinate care team communications."""
        # Validate inputs
        self._validate_message_type(message_type)
        validated_priority = self._validate_priority(priority)

        # Hash identifiers for logging (LGPD compliance)
        encounter_hash = self._hash_reference(encounter_reference)
        member_hashes = [self._hash_reference(m) for m in care_team_members[:3]]

        logger.info(
            _("Coordenando equipe tipo=%s prioridade=%s encounter=%s membros=%d sample=%s"),
            message_type,
            validated_priority,
            encounter_hash,
            len(care_team_members),
            ", ".join(member_hashes)
        )

        if not care_team_members:
            logger.error(_("Lista de membros da equipe está vazia"))
            raise CareTeamNotFoundError(
                _("Lista de membros da equipe não pode estar vazia")
            )

        try:
            # Build Communication resource
            communication = self._build_communication_resource(
                encounter_reference=encounter_reference,
                care_team_members=care_team_members,
                message_type=message_type,
                message_content=message_content,
                sender_reference=sender_reference,
                priority=validated_priority,
            )

            # Create in FHIR server
            response = await self.fhir_client.create_resource(communication)

            communication_id = response.get("id")
            if not communication_id:
                raise CoordinationError(
                    _("Resposta do servidor FHIR não contém ID da comunicação")
                )

            # In a real implementation, this would track actual notifications
            # For stub, assume all members are notified for non-failed cases
            notified_members = care_team_members.copy()
            pending_acknowledgments = []

            # For urgent messages, track acknowledgments
            if message_type == "urgent":
                pending_acknowledgments = care_team_members.copy()

            coordination_status = self._determine_coordination_status(
                total_members=len(care_team_members),
                notified_count=len(notified_members),
            )

            sent_at = response.get("sent", datetime.utcnow().isoformat() + "Z")

            logger.info(
                _("Coordenação concluída: %s status=%s notificados=%d pendentes=%d"),
                communication_id,
                coordination_status,
                len(notified_members),
                len(pending_acknowledgments)
            )

            return {
                "coordination_status": coordination_status,
                "notified_members": notified_members,
                "pending_acknowledgments": pending_acknowledgments,
                "communication_id": communication_id,
                "sent_at": sent_at,
            }

        except Exception as e:
            logger.error(
                _("Erro ao coordenar equipe tipo=%s: %s"),
                message_type,
                str(e),
                exc_info=True
            )
            raise CoordinationError(
                _("Falha ao coordenar equipe: {error}").format(error=str(e))
            ) from e


@require_tenant
@track_task_execution(task_type="clinical.care_team")
async def execute(task_variables: dict[str, Any]) -> dict[str, Any]:
    """
    Execute care team coordination worker.

    Args:
        task_variables: Camunda task variables

    Returns:
        Dictionary with coordination results

    Raises:
        InvalidMessageTypeError: If message type is invalid
        CareTeamNotFoundError: If care team not found
        CoordinationError: If coordination fails
    """
    tenant_id = get_required_tenant()

    logger.info(
        _("Iniciando worker de coordenação de equipe tenant=%s"),
        tenant_id
    )

    # Parse and validate input
    input_data = CareTeamCoordinationInput(**task_variables)

    # Initialize dependencies (stub implementation)
    from healthcare_platform.shared.integrations.fhir_client import FHIRClientStub
    fhir_client = FHIRClientStub()

    # Create service
    service = DMNCareTeamCoordination(fhir_client=fhir_client)

    # Execute coordination
    result = await service.coordinate_care_team(
        encounter_reference=input_data.encounter_reference,
        care_team_members=input_data.care_team_members,
        message_type=input_data.message_type,
        message_content=input_data.message_content,
        sender_reference=input_data.sender_reference,
        priority=input_data.priority,
    )

    # Build output
    output = CareTeamCoordinationOutput(**result)

    logger.info(
        _("Worker de coordenação de equipe concluído: %s status=%s"),
        output.communication_id,
        output.coordination_status
    )

    return output.to_variables()


# Worker configuration
TOPIC = "clinical.care_team"
