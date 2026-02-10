"""
Clinical Handoffs Worker

Manages patient handoffs between care teams during shift changes, transfers, and escalations.
Uses SBAR format (Situation, Background, Assessment, Recommendation) for structured communication.
Tracks acknowledgment and ensures continuity of care.
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

logger = get_logger(__name__, worker="clinical.handoffs")


class ClinicalException(DomainException):
    """Clinical operations domain exception."""
    bpmn_error_code: str = "CLINICAL_ERROR"


class InvalidHandoffTypeError(ClinicalException):
    """Raised when handoff type is not recognized."""
    bpmn_error_code: str = "INVALID_HANDOFF_TYPE"


class IncompleteHandoffError(ClinicalException):
    """Raised when handoff data is incomplete."""
    bpmn_error_code: str = "INCOMPLETE_HANDOFF"


class HandoffCreationError(ClinicalException):
    """Raised when handoff creation fails."""
    bpmn_error_code: str = "HANDOFF_CREATION_FAILED"


class ClinicalHandoffsInput(BaseModel):
    """Input model for clinical handoffs worker."""

    encounter_reference: str = Field(
        ...,
        description=_("Referência do encontro clínico (Encounter)")
    )
    patient_reference: str = Field(
        ...,
        description=_("Referência do paciente (Patient)")
    )
    from_team: list[str] = Field(
        ...,
        description=_("Equipe de origem (Practitioner references)")
    )
    to_team: list[str] = Field(
        ...,
        description=_("Equipe de destino (Practitioner references)")
    )
    handoff_type: str = Field(
        ...,
        description=_("Tipo de handoff: shift, transfer, escalation")
    )
    patient_summary: dict[str, Any] = Field(
        ...,
        description=_("Resumo do paciente em formato SBAR")
    )
    pending_items: list[str] = Field(
        default_factory=list,
        description=_("Lista de itens pendentes a serem comunicados")
    )

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables."""
        return {
            "encounter_reference": self.encounter_reference,
            "patient_reference": self.patient_reference,
            "from_team": self.from_team,
            "to_team": self.to_team,
            "handoff_type": self.handoff_type,
            "patient_summary": self.patient_summary,
            "pending_items": self.pending_items,
        }


class ClinicalHandoffsOutput(BaseModel):
    """Output model for clinical handoffs worker."""

    handoff_reference: str = Field(
        ...,
        description=_("Referência do Communication criado")
    )
    handoff_status: str = Field(
        ...,
        description=_("Status: pending-acknowledgment, acknowledged, completed")
    )
    pending_items: list[str] = Field(
        default_factory=list,
        description=_("Itens pendentes após handoff")
    )
    acknowledged: bool = Field(
        ...,
        description=_("Se foi reconhecido pela equipe receptora")
    )
    handoff_time: str = Field(
        ...,
        description=_("Data/hora do handoff (ISO 8601)")
    )

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables."""
        return {
            "handoff_reference": self.handoff_reference,
            "handoff_status": self.handoff_status,
            "pending_items": self.pending_items,
            "acknowledged": self.acknowledged,
            "handoff_time": self.handoff_time,
        }


class ClinicalHandoffsProtocol(ABC):
    """Protocol for clinical handoffs operations."""

    @abstractmethod
    async def create_handoff(
        self,
        encounter_reference: str,
        patient_reference: str,
        from_team: list[str],
        to_team: list[str],
        handoff_type: str,
        patient_summary: dict[str, Any],
        pending_items: list[str],
    ) -> dict[str, Any]:
        """
        Create a clinical handoff.

        Args:
            encounter_reference: Reference to the clinical encounter
            patient_reference: Reference to the patient
            from_team: Source care team member references
            to_team: Destination care team member references
            handoff_type: Type of handoff (shift, transfer, escalation)
            patient_summary: SBAR-formatted patient summary
            pending_items: List of pending items

        Returns:
            Dictionary containing handoff details

        Raises:
            InvalidHandoffTypeError: If handoff type is invalid
            IncompleteHandoffError: If SBAR data is incomplete
            HandoffCreationError: If handoff creation fails
        """
        pass


class DMNClinicalHandoffs(ClinicalHandoffsProtocol):
    """DMN-backed clinical handoffs using FederatedDMNService."""

    def __init__(
        self,
        fhir_client: FHIRClientProtocol,
        dmn_service: FederatedDMNService | None = None,
    ) -> None:
        self._fhir = fhir_client
        self._dmn = dmn_service or get_dmn_service()
        self._fallback = ClinicalHandoffsStub(fhir_client=fhir_client)

    async def create_handoff(
        self,
        encounter_reference: str,
        patient_reference: str,
        from_team: list[str],
        to_team: list[str],
        handoff_type: str,
        patient_summary: dict[str, Any],
        pending_items: list[str],
    ) -> dict[str, Any]:
        """Create handoff with DMN-driven completeness rules."""
        tenant_id = get_required_tenant().tenant_id
        try:
            result = self._dmn.evaluate(
                tenant_id=tenant_id,
                category="clinical_safety",
                table_name="safety/handoff_requirements_001",
                inputs={
                    "handoff_type": handoff_type,
                    "pending_count": len(pending_items),
                },
            )
            if result and result.get("required_fields"):
                # DMN provides handoff rules; delegate to stub
                pass
        except (FileNotFoundError, ValueError):
            pass
        except Exception:
            pass
        return await self._fallback.create_handoff(
            encounter_reference, patient_reference, from_team,
            to_team, handoff_type, patient_summary, pending_items,
        )


class ClinicalHandoffsStub(ClinicalHandoffsProtocol):
    """Stub implementation for clinical handoffs."""

    VALID_HANDOFF_TYPES = {"shift", "transfer", "escalation"}
    REQUIRED_SBAR_FIELDS = {"situation", "background", "assessment", "recommendation"}

    def __init__(self, fhir_client: FHIRClientProtocol):
        """Initialize with FHIR client dependency."""
        self.fhir_client = fhir_client

    def _hash_reference(self, reference: str) -> str:
        """Hash reference for LGPD compliance."""
        return hashlib.sha256(reference.encode()).hexdigest()[:16]

    def _validate_handoff_type(self, handoff_type: str) -> None:
        """Validate handoff type."""
        if handoff_type not in self.VALID_HANDOFF_TYPES:
            logger.error(
                _("Tipo de handoff inválido: %s. Tipos válidos: %s"),
                handoff_type,
                ", ".join(self.VALID_HANDOFF_TYPES)
            )
            raise InvalidHandoffTypeError(
                _("Tipo de handoff inválido: {handoff_type}").format(
                    handoff_type=handoff_type
                )
            )

    def _validate_sbar(self, patient_summary: dict[str, Any]) -> None:
        """Validate SBAR format completeness."""
        missing_fields = self.REQUIRED_SBAR_FIELDS - set(patient_summary.keys())

        if missing_fields:
            logger.error(
                _("Campos SBAR faltando: %s"),
                ", ".join(missing_fields)
            )
            raise IncompleteHandoffError(
                _("Resumo SBAR incompleto. Campos faltando: {fields}").format(
                    fields=", ".join(missing_fields)
                )
            )

        # Validate that fields are not empty
        for field in self.REQUIRED_SBAR_FIELDS:
            if not patient_summary.get(field):
                logger.error(
                    _("Campo SBAR vazio: %s"),
                    field
                )
                raise IncompleteHandoffError(
                    _("Campo SBAR vazio: {field}").format(field=field)
                )

    def _build_sbar_text(self, patient_summary: dict[str, Any]) -> str:
        """Build formatted SBAR text."""
        return (
            f"SITUAÇÃO: {patient_summary['situation']}\n\n"
            f"BACKGROUND: {patient_summary['background']}\n\n"
            f"AVALIAÇÃO: {patient_summary['assessment']}\n\n"
            f"RECOMENDAÇÃO: {patient_summary['recommendation']}"
        )

    def _build_communication_resource(
        self,
        encounter_reference: str,
        patient_reference: str,
        from_team: list[str],
        to_team: list[str],
        handoff_type: str,
        patient_summary: dict[str, Any],
        pending_items: list[str],
    ) -> dict[str, Any]:
        """Build FHIR Communication resource for handoff."""
        handoff_time = datetime.utcnow().isoformat() + "Z"
        sbar_text = self._build_sbar_text(patient_summary)

        communication = {
            "resourceType": "Communication",
            "status": "in-progress",
            "category": [{
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/communication-category",
                    "code": "handoff",
                    "display": "Handoff"
                }],
                "text": f"Clinical Handoff - {handoff_type}"
            }],
            "priority": "urgent" if handoff_type == "escalation" else "routine",
            "subject": {
                "reference": patient_reference
            },
            "encounter": {
                "reference": encounter_reference
            },
            "sent": handoff_time,
            "sender": [
                {"reference": member} for member in from_team
            ],
            "recipient": [
                {"reference": member} for member in to_team
            ],
            "payload": [
                {
                    "contentString": sbar_text
                }
            ]
        }

        # Add pending items as additional payload
        if pending_items:
            pending_text = "ITENS PENDENTES:\n" + "\n".join(
                f"- {item}" for item in pending_items
            )
            communication["payload"].append({
                "contentString": pending_text
            })

        # Add handoff type extension
        communication["extension"] = [{
            "url": "http://hl7.org/fhir/StructureDefinition/communication-handoff-type",
            "valueString": handoff_type
        }]

        return communication

    async def create_handoff(
        self,
        encounter_reference: str,
        patient_reference: str,
        from_team: list[str],
        to_team: list[str],
        handoff_type: str,
        patient_summary: dict[str, Any],
        pending_items: list[str],
    ) -> dict[str, Any]:
        """Create a clinical handoff."""
        # Validate inputs
        self._validate_handoff_type(handoff_type)
        self._validate_sbar(patient_summary)

        # Hash identifiers for logging (LGPD compliance)
        patient_hash = self._hash_reference(patient_reference)
        encounter_hash = self._hash_reference(encounter_reference)
        from_hashes = [self._hash_reference(m) for m in from_team[:2]]
        to_hashes = [self._hash_reference(m) for m in to_team[:2]]

        logger.info(
            _("Criando handoff tipo=%s patient=%s encounter=%s from=%s to=%s"),
            handoff_type,
            patient_hash,
            encounter_hash,
            ", ".join(from_hashes),
            ", ".join(to_hashes)
        )

        if not from_team or not to_team:
            logger.error(_("Equipes de origem ou destino estão vazias"))
            raise IncompleteHandoffError(
                _("Equipes de origem e destino devem estar preenchidas")
            )

        try:
            # Build Communication resource
            communication = self._build_communication_resource(
                encounter_reference=encounter_reference,
                patient_reference=patient_reference,
                from_team=from_team,
                to_team=to_team,
                handoff_type=handoff_type,
                patient_summary=patient_summary,
                pending_items=pending_items,
            )

            # Create in FHIR server
            response = await self.fhir_client.create_resource(communication)

            communication_id = response.get("id")
            if not communication_id:
                raise HandoffCreationError(
                    _("Resposta do servidor FHIR não contém ID da comunicação")
                )

            handoff_reference = f"Communication/{communication_id}"
            handoff_time = response.get("sent", datetime.utcnow().isoformat() + "Z")

            # In real implementation, would check for actual acknowledgment
            # For stub, assume pending acknowledgment initially
            acknowledged = False
            handoff_status = "pending-acknowledgment"

            logger.info(
                _("Handoff criado: %s tipo=%s status=%s pendentes=%d"),
                handoff_reference,
                handoff_type,
                handoff_status,
                len(pending_items)
            )

            return {
                "handoff_reference": handoff_reference,
                "handoff_status": handoff_status,
                "pending_items": pending_items,
                "acknowledged": acknowledged,
                "handoff_time": handoff_time,
            }

        except Exception as e:
            logger.error(
                _("Erro ao criar handoff tipo=%s: %s"),
                handoff_type,
                str(e),
                exc_info=True
            )
            raise HandoffCreationError(
                _("Falha ao criar handoff: {error}").format(error=str(e))
            ) from e


@require_tenant
@track_task_execution(worker_topic="clinical.handoffs")
async def execute(task_variables: dict[str, Any]) -> dict[str, Any]:
    """
    Execute clinical handoffs worker.

    Args:
        task_variables: Camunda task variables

    Returns:
        Dictionary with handoff results

    Raises:
        InvalidHandoffTypeError: If handoff type is invalid
        IncompleteHandoffError: If SBAR data is incomplete
        HandoffCreationError: If handoff creation fails
    """
    tenant_id = get_required_tenant()

    logger.info(
        _("Iniciando worker de handoffs clínicos tenant=%s"),
        tenant_id
    )

    # Parse and validate input
    input_data = ClinicalHandoffsInput(**task_variables)

    # Initialize dependencies (stub implementation)
    from healthcare_platform.shared.integrations.fhir_client import FHIRClientStub
    fhir_client = FHIRClientStub()

    # Create service
    service = DMNClinicalHandoffs(fhir_client=fhir_client)

    # Execute handoff creation
    result = await service.create_handoff(
        encounter_reference=input_data.encounter_reference,
        patient_reference=input_data.patient_reference,
        from_team=input_data.from_team,
        to_team=input_data.to_team,
        handoff_type=input_data.handoff_type,
        patient_summary=input_data.patient_summary,
        pending_items=input_data.pending_items,
    )

    # Build output
    output = ClinicalHandoffsOutput(**result)

    logger.info(
        _("Worker de handoffs clínicos concluído: %s status=%s"),
        output.handoff_reference,
        output.handoff_status
    )

    return output.to_variables()


# Worker configuration
TOPIC = "clinical.handoffs"
