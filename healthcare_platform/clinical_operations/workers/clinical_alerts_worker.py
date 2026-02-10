"""
Clinical Alerts Worker

Handles critical alerts and notifications for clinical events.
Supports critical lab results, vital signs, medication alerts, and allergies.
Manages severity levels and escalation workflows.
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

logger = get_logger(__name__, worker="clinical.alerts")


class ClinicalException(DomainException):
    """Clinical operations domain exception."""
    bpmn_error_code: str = "CLINICAL_ERROR"


class InvalidAlertTypeError(ClinicalException):
    """Raised when alert type is not recognized."""
    bpmn_error_code: str = "INVALID_ALERT_TYPE"


class InvalidSeverityError(ClinicalException):
    """Raised when severity level is invalid."""
    bpmn_error_code: str = "INVALID_SEVERITY"


class AlertCreationError(ClinicalException):
    """Raised when alert creation fails."""
    bpmn_error_code: str = "ALERT_CREATION_FAILED"


class ClinicalAlertsInput(BaseModel):
    """Input model for clinical alerts worker."""

    encounter_reference: str = Field(
        ...,
        description=_("Referência do encontro clínico (Encounter)")
    )
    patient_reference: str | None = Field(
        None,
        description=_("Referência do paciente (Patient)")
    )
    alert_type: str = Field(
        ...,
        description=_("Tipo de alerta: critical_lab, vital_sign, medication, allergy")
    )
    alert_data: dict[str, Any] = Field(
        ...,
        description=_("Dados específicos do alerta")
    )
    severity: str = Field(
        ...,
        description=_("Severidade: critical, high, medium, low")
    )
    description: str | None = Field(
        None,
        description=_("Descrição adicional do alerta")
    )

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables."""
        return {
            "encounter_reference": self.encounter_reference,
            "patient_reference": self.patient_reference,
            "alert_type": self.alert_type,
            "alert_data": self.alert_data,
            "severity": self.severity,
            "description": self.description,
        }


class ClinicalAlertsOutput(BaseModel):
    """Output model for clinical alerts worker."""

    alert_id: str = Field(
        ...,
        description=_("ID do alerta criado")
    )
    alert_status: str = Field(
        ...,
        description=_("Status do alerta: active, acknowledged, resolved")
    )
    notification_targets: list[str] = Field(
        default_factory=list,
        description=_("Lista de destinatários notificados")
    )
    escalation_required: bool = Field(
        ...,
        description=_("Se requer escalação para níveis superiores")
    )
    created_at: str = Field(
        ...,
        description=_("Data/hora de criação (ISO 8601)")
    )

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables."""
        return {
            "alert_id": self.alert_id,
            "alert_status": self.alert_status,
            "notification_targets": self.notification_targets,
            "escalation_required": self.escalation_required,
            "created_at": self.created_at,
        }


class ClinicalAlertsProtocol(ABC):
    """Protocol for clinical alerts operations."""

    @abstractmethod
    async def create_alert(
        self,
        encounter_reference: str,
        alert_type: str,
        alert_data: dict[str, Any],
        severity: str,
        patient_reference: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a clinical alert.

        Args:
            encounter_reference: Reference to the clinical encounter
            alert_type: Type of alert (critical_lab, vital_sign, medication, allergy)
            alert_data: Alert-specific data
            severity: Severity level (critical, high, medium, low)
            patient_reference: Reference to the patient
            description: Additional description

        Returns:
            Dictionary containing alert details

        Raises:
            InvalidAlertTypeError: If alert type is invalid
            InvalidSeverityError: If severity is invalid
            AlertCreationError: If alert creation fails
        """
        pass


class DMNClinicalAlerts(ClinicalAlertsProtocol):
    """DMN-backed clinical alerts using FederatedDMNService."""

    def __init__(
        self,
        fhir_client: FHIRClientProtocol,
        dmn_service: FederatedDMNService | None = None,
    ) -> None:
        self._fhir = fhir_client
        self._dmn = dmn_service or get_dmn_service()
        self._fallback = ClinicalAlertsStub(fhir_client=fhir_client)

    async def create_alert(
        self,
        encounter_reference: str,
        alert_type: str,
        alert_data: dict[str, Any],
        severity: str,
        patient_reference: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create clinical alert with DMN-driven severity escalation."""
        tenant_id = get_required_tenant().tenant_id
        try:
            result = self._dmn.evaluate(
                tenant_id=tenant_id,
                category="clinical_safety",
                table_name="safety/alert_escalation_001",
                inputs={"alert_type": alert_type, "severity": severity},
            )
            if result and result.get("escalated_severity"):
                severity = result["escalated_severity"]
        except (FileNotFoundError, ValueError):
            pass
        except Exception:
            pass
        return await self._fallback.create_alert(
            encounter_reference, alert_type, alert_data,
            severity, patient_reference, description,
        )


class ClinicalAlertsStub(ClinicalAlertsProtocol):
    """Stub implementation for clinical alerts."""

    VALID_ALERT_TYPES = {"critical_lab", "vital_sign", "medication", "allergy"}
    VALID_SEVERITIES = {"critical", "high", "medium", "low"}

    SEVERITY_PRIORITY = {
        "critical": 1,
        "high": 2,
        "medium": 3,
        "low": 4,
    }

    ALERT_CODE_SYSTEMS = {
        "critical_lab": {
            "system": "http://terminology.hl7.org/CodeSystem/observation-category",
            "code": "laboratory",
            "display": "Laboratory"
        },
        "vital_sign": {
            "system": "http://terminology.hl7.org/CodeSystem/observation-category",
            "code": "vital-signs",
            "display": "Vital Signs"
        },
        "medication": {
            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
            "code": "MEDLIST",
            "display": "Medication List"
        },
        "allergy": {
            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
            "code": "ALLERGYLIST",
            "display": "Allergy List"
        }
    }

    def __init__(self, fhir_client: FHIRClientProtocol):
        """Initialize with FHIR client dependency."""
        self.fhir_client = fhir_client

    def _hash_reference(self, reference: str) -> str:
        """Hash reference for LGPD compliance."""
        return hashlib.sha256(reference.encode()).hexdigest()[:16]

    def _validate_alert_type(self, alert_type: str) -> None:
        """Validate alert type."""
        if alert_type not in self.VALID_ALERT_TYPES:
            logger.error(
                _("Tipo de alerta inválido: %s. Tipos válidos: %s"),
                alert_type,
                ", ".join(self.VALID_ALERT_TYPES)
            )
            raise InvalidAlertTypeError(
                _("Tipo de alerta inválido: {alert_type}").format(alert_type=alert_type)
            )

    def _validate_severity(self, severity: str) -> None:
        """Validate severity level."""
        if severity not in self.VALID_SEVERITIES:
            logger.error(
                _("Severidade inválida: %s. Severidades válidas: %s"),
                severity,
                ", ".join(self.VALID_SEVERITIES)
            )
            raise InvalidSeverityError(
                _("Severidade inválida: {severity}").format(severity=severity)
            )

    def _determine_notification_targets(
        self,
        alert_type: str,
        severity: str,
    ) -> list[str]:
        """Determine notification targets based on alert type and severity."""
        targets = []

        # Base targets for all alerts
        targets.append("attending-physician")

        # Add nursing staff for critical and high severity
        if severity in ["critical", "high"]:
            targets.append("nursing-supervisor")

        # Alert-specific targets
        if alert_type == "critical_lab":
            targets.append("laboratory-supervisor")
            if severity == "critical":
                targets.append("medical-director")
        elif alert_type == "medication":
            targets.append("pharmacy-supervisor")
        elif alert_type == "allergy":
            targets.append("pharmacy-supervisor")
            targets.append("nursing-supervisor")

        return targets

    def _requires_escalation(self, severity: str, alert_type: str) -> bool:
        """Determine if alert requires escalation."""
        # Critical alerts always require escalation
        if severity == "critical":
            return True

        # High severity critical labs require escalation
        if severity == "high" and alert_type == "critical_lab":
            return True

        return False

    def _build_flag_resource(
        self,
        encounter_reference: str,
        patient_reference: str | None,
        alert_type: str,
        alert_data: dict[str, Any],
        severity: str,
        description: str | None,
    ) -> dict[str, Any]:
        """Build FHIR Flag resource for alert."""
        code_info = self.ALERT_CODE_SYSTEMS[alert_type]
        created_at = datetime.utcnow().isoformat() + "Z"

        flag = {
            "resourceType": "Flag",
            "status": "active",
            "category": [{
                "coding": [{
                    "system": code_info["system"],
                    "code": code_info["code"],
                    "display": code_info["display"]
                }]
            }],
            "code": {
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/flag-category",
                    "code": "clinical",
                    "display": "Clinical"
                }],
                "text": description or f"{alert_type} alert"
            },
            "period": {
                "start": created_at
            },
            "encounter": {
                "reference": encounter_reference
            }
        }

        if patient_reference:
            flag["subject"] = {
                "reference": patient_reference
            }

        # Add severity as extension
        flag["extension"] = [{
            "url": "http://hl7.org/fhir/StructureDefinition/flag-priority",
            "valueCodeableConcept": {
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/flag-priority-code",
                    "code": severity,
                    "display": severity.capitalize()
                }]
            }
        }]

        return flag

    async def create_alert(
        self,
        encounter_reference: str,
        alert_type: str,
        alert_data: dict[str, Any],
        severity: str,
        patient_reference: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a clinical alert."""
        # Validate inputs
        self._validate_alert_type(alert_type)
        self._validate_severity(severity)

        # Hash identifiers for logging (LGPD compliance)
        encounter_hash = self._hash_reference(encounter_reference)
        patient_hash = self._hash_reference(patient_reference) if patient_reference else "N/A"

        logger.info(
            _("Criando alerta clínico tipo=%s severidade=%s encounter=%s patient=%s"),
            alert_type,
            severity,
            encounter_hash,
            patient_hash
        )

        try:
            # Build Flag resource
            flag = self._build_flag_resource(
                encounter_reference=encounter_reference,
                patient_reference=patient_reference,
                alert_type=alert_type,
                alert_data=alert_data,
                severity=severity,
                description=description,
            )

            # Create in FHIR server
            response = await self.fhir_client.create_resource(flag)

            alert_id = response.get("id")
            if not alert_id:
                raise AlertCreationError(
                    _("Resposta do servidor FHIR não contém ID do alerta")
                )

            # Determine notification targets
            notification_targets = self._determine_notification_targets(
                alert_type=alert_type,
                severity=severity,
            )

            # Check if escalation is required
            escalation_required = self._requires_escalation(
                severity=severity,
                alert_type=alert_type,
            )

            created_at = response.get("period", {}).get("start", datetime.utcnow().isoformat() + "Z")

            logger.info(
                _("Alerta criado: %s tipo=%s severidade=%s escalation=%s targets=%d"),
                alert_id,
                alert_type,
                severity,
                escalation_required,
                len(notification_targets)
            )

            return {
                "alert_id": alert_id,
                "alert_status": "active",
                "notification_targets": notification_targets,
                "escalation_required": escalation_required,
                "created_at": created_at,
            }

        except Exception as e:
            logger.error(
                _("Erro ao criar alerta tipo=%s severidade=%s: %s"),
                alert_type,
                severity,
                str(e),
                exc_info=True
            )
            raise AlertCreationError(
                _("Falha ao criar alerta clínico: {error}").format(error=str(e))
            ) from e


@require_tenant
@track_task_execution(worker_topic="clinical.alerts")
async def execute(task_variables: dict[str, Any]) -> dict[str, Any]:
    """
    Execute clinical alerts worker.

    Args:
        task_variables: Camunda task variables

    Returns:
        Dictionary with alert results

    Raises:
        InvalidAlertTypeError: If alert type is invalid
        InvalidSeverityError: If severity is invalid
        AlertCreationError: If alert creation fails
    """
    tenant_id = get_required_tenant()

    logger.info(
        _("Iniciando worker de alertas clínicos tenant=%s"),
        tenant_id
    )

    # Parse and validate input
    input_data = ClinicalAlertsInput(**task_variables)

    # Initialize dependencies (stub implementation)
    from healthcare_platform.shared.integrations.fhir_client import FHIRClientStub
    fhir_client = FHIRClientStub()

    # Create service (DMN-backed with Stub fallback)
    service = DMNClinicalAlerts(fhir_client=fhir_client)

    # Execute alert creation
    result = await service.create_alert(
        encounter_reference=input_data.encounter_reference,
        alert_type=input_data.alert_type,
        alert_data=input_data.alert_data,
        severity=input_data.severity,
        patient_reference=input_data.patient_reference,
        description=input_data.description,
    )

    # Build output
    output = ClinicalAlertsOutput(**result)

    logger.info(
        _("Worker de alertas clínicos concluído: %s status=%s"),
        output.alert_id,
        output.alert_status
    )

    return output.to_variables()


# Worker configuration
TOPIC = "clinical.alerts"
