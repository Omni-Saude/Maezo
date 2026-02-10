"""Apply clinical protocols and guidelines based on diagnosis.

CIB7 External Task Topic: clinical.protocols
BPMN Error Codes: CLINICAL_ERROR
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.tasy_api_client import TasyApiClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService, get_dmn_service


# ── Constants & Validation ────────────────────────────────────────────


class ClinicalException(DomainException):
    """Exception for clinical operations."""

    bpmn_error_code: str = "CLINICAL_ERROR"


CID10_SYSTEM = "http://www.saude.gov.br/cid-10"


# ── Data Transfer Objects ─────────────────────────────────────────────


class ProtocolStep(BaseModel):
    """A step within a clinical protocol."""

    sequence: int = Field(..., description="Step sequence number")
    action: str = Field(..., description="Action to perform")
    timing: str = Field(..., description="When to perform (e.g., '0h', '6h', '24h')")
    mandatory: bool = Field(default=True, description="Is this step mandatory")


class ClinicalProtocol(BaseModel):
    """Clinical protocol definition."""

    protocol_id: str = Field(..., description="Protocol identifier")
    name: str = Field(..., description="Protocol name")
    version: str = Field(..., description="Protocol version")
    applicable_conditions: list[str] = Field(
        default_factory=list, description="CID-10 codes this applies to"
    )
    steps: list[ProtocolStep] = Field(default_factory=list)
    compliance_requirements: list[str] = Field(
        default_factory=list, description="Regulatory compliance requirements"
    )


class ClinicalProtocolsInput(BaseModel):
    """Input variables for clinical protocols."""

    encounter_reference: str = Field(..., description="FHIR Encounter reference")
    diagnosis_codes: list[dict[str, Any]] = Field(
        default_factory=list, description="CID-10 diagnosis codes"
    )
    encounter_class: str = Field(
        default="ambulatorio", description="Encounter class (ambulatorio/internacao/urgencia)"
    )
    tenant_id: str = Field(default="")


class ClinicalProtocolsOutput(BaseModel):
    """Output variables for clinical protocols."""

    applicable_protocols: list[dict[str, Any]]
    protocol_steps: list[dict[str, Any]]
    compliance_requirements: list[str]

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda task variables."""
        return {
            "applicable_protocols": self.applicable_protocols,
            "protocol_steps": self.protocol_steps,
            "compliance_requirements": self.compliance_requirements,
        }


# ── Protocol ──────────────────────────────────────────────────────────


class ProtocolEngine(ABC):
    """Protocol for clinical protocol engines."""

    @abstractmethod
    def find_protocols(
        self,
        diagnosis_codes: list[dict[str, Any]],
        encounter_class: str,
    ) -> list[ClinicalProtocol]:
        """Find applicable clinical protocols for diagnosis.

        Args:
            diagnosis_codes: CID-10 diagnosis codes
            encounter_class: Type of encounter

        Returns:
            List of applicable clinical protocols
        """
        ...


# ── DMN Implementation ───────────────────────────────────────────────


class DMNProtocolEngine(ProtocolEngine):
    """DMN-backed clinical protocol engine using FederatedDMNService."""

    def __init__(self, dmn_service: FederatedDMNService | None = None) -> None:
        self._dmn = dmn_service or get_dmn_service()
        self._logger = get_logger(__name__, component="dmn_protocols")
        self._fallback = StubProtocolEngine()

    def find_protocols(
        self,
        diagnosis_codes: list[dict[str, Any]],
        encounter_class: str,
    ) -> list[ClinicalProtocol]:
        """Find applicable protocols via DMN decision tables."""
        tenant_id = get_required_tenant().tenant_id
        protocols: list[ClinicalProtocol] = []

        for diag in diagnosis_codes:
            code = diag.get("code", "")
            try:
                result = self._dmn.evaluate(
                    tenant_id=tenant_id,
                    category="clinical_safety",
                    table_name="safety/protocol_selection_001",
                    inputs={
                        "diagnosis_code": code,
                        "encounter_class": encounter_class,
                    },
                )
                if result and result.get("protocol_id"):
                    protocols.append(
                        ClinicalProtocol(
                            protocol_id=result["protocol_id"],
                            name=result.get("name", result["protocol_id"]),
                            version=result.get("version", "1.0"),
                            applicable_conditions=[code],
                            steps=[
                                ProtocolStep(
                                    sequence=i + 1,
                                    action=s.get("action", ""),
                                    timing=s.get("timing", ""),
                                    mandatory=s.get("mandatory", True),
                                )
                                for i, s in enumerate(
                                    result.get("steps", [])
                                )
                            ],
                        )
                    )
            except (FileNotFoundError, ValueError):
                continue
            except Exception as exc:
                self._logger.warning(
                    "dmn_protocol_error", code=code, error=str(exc),
                )

        if not protocols:
            return self._fallback.find_protocols(diagnosis_codes, encounter_class)
        return protocols


# ── Stub Implementation ──────────────────────────────────────────────

# Clinical protocols database
_CLINICAL_PROTOCOLS: dict[str, ClinicalProtocol] = {
    "SEPSE_2024": ClinicalProtocol(
        protocol_id="SEPSE_2024",
        name="Protocolo de Sepse e Choque Séptico - 2024",
        version="1.0",
        applicable_conditions=["A41", "A40"],  # Septicemia
        steps=[
            ProtocolStep(
                sequence=1,
                action="Coletar hemoculturas (2 pares) antes de antibiótico",
                timing="0h",
                mandatory=True,
            ),
            ProtocolStep(
                sequence=2,
                action="Iniciar antibioticoterapia de amplo espectro",
                timing="1h",
                mandatory=True,
            ),
            ProtocolStep(
                sequence=3,
                action="Ressuscitação volêmica com 30ml/kg de cristaloide",
                timing="3h",
                mandatory=True,
            ),
            ProtocolStep(
                sequence=4,
                action="Medir lactato sérico",
                timing="0h",
                mandatory=True,
            ),
            ProtocolStep(
                sequence=5,
                action="Reavaliar lactato se inicial > 2mmol/L",
                timing="6h",
                mandatory=False,
            ),
        ],
        compliance_requirements=[
            "Notificação obrigatória à CCIH",
            "Registro em prontuário eletrônico",
            "Seguir bundle Surviving Sepsis Campaign",
        ],
    ),
    "IAM_2024": ClinicalProtocol(
        protocol_id="IAM_2024",
        name="Protocolo de Infarto Agudo do Miocárdio - 2024",
        version="1.0",
        applicable_conditions=["I21", "I22"],  # Infarto agudo do miocárdio
        steps=[
            ProtocolStep(
                sequence=1,
                action="ECG de 12 derivações",
                timing="10min",
                mandatory=True,
            ),
            ProtocolStep(
                sequence=2,
                action="AAS 200mg mastigável",
                timing="0h",
                mandatory=True,
            ),
            ProtocolStep(
                sequence=3,
                action="Clopidogrel 300mg ou Ticagrelor 180mg",
                timing="0h",
                mandatory=True,
            ),
            ProtocolStep(
                sequence=4,
                action="Solicitar troponina e CKMB",
                timing="0h",
                mandatory=True,
            ),
            ProtocolStep(
                sequence=5,
                action="Ativar hemodinâmica para angioplastia primária",
                timing="30min",
                mandatory=True,
            ),
        ],
        compliance_requirements=[
            "Tempo porta-balão < 90 minutos",
            "Notificação à cardiologia de plantão",
            "Registro de tempos em prontuário",
        ],
    ),
    "AVC_2024": ClinicalProtocol(
        protocol_id="AVC_2024",
        name="Protocolo de Acidente Vascular Cerebral - 2024",
        version="1.0",
        applicable_conditions=["I63", "I64"],  # AVC isquêmico
        steps=[
            ProtocolStep(
                sequence=1,
                action="Aplicar escala NIHSS",
                timing="10min",
                mandatory=True,
            ),
            ProtocolStep(
                sequence=2,
                action="TC de crânio sem contraste",
                timing="25min",
                mandatory=True,
            ),
            ProtocolStep(
                sequence=3,
                action="Glicemia capilar e pressão arterial",
                timing="0h",
                mandatory=True,
            ),
            ProtocolStep(
                sequence=4,
                action="Avaliar critérios para trombólise",
                timing="30min",
                mandatory=True,
            ),
            ProtocolStep(
                sequence=5,
                action="Administrar rtPA se indicado (< 4,5h de sintomas)",
                timing="60min",
                mandatory=False,
            ),
        ],
        compliance_requirements=[
            "Tempo porta-agulha < 60 minutos se trombólise",
            "Acionar neurologista de plantão",
            "Monitorização em UTI/stroke unit",
        ],
    ),
    "PNEUMONIA_2024": ClinicalProtocol(
        protocol_id="PNEUMONIA_2024",
        name="Protocolo de Pneumonia Adquirida na Comunidade - 2024",
        version="1.0",
        applicable_conditions=["J18"],  # Pneumonia
        steps=[
            ProtocolStep(
                sequence=1,
                action="Raio-X de tórax PA e perfil",
                timing="2h",
                mandatory=True,
            ),
            ProtocolStep(
                sequence=2,
                action="Hemograma e PCR",
                timing="0h",
                mandatory=True,
            ),
            ProtocolStep(
                sequence=3,
                action="Gasometria arterial se SpO2 < 90%",
                timing="0h",
                mandatory=False,
            ),
            ProtocolStep(
                sequence=4,
                action="Calcular escore CURB-65",
                timing="0h",
                mandatory=True,
            ),
            ProtocolStep(
                sequence=5,
                action="Iniciar antibiótico conforme gravidade (CURB-65)",
                timing="4h",
                mandatory=True,
            ),
        ],
        compliance_requirements=[
            "Antibiótico na primeira dose em < 4 horas",
            "Reavaliar em 48-72h",
            "Considerar vacinação pneumocócica na alta",
        ],
    ),
}


class StubProtocolEngine(ProtocolEngine):
    """CID-10-based protocol matching engine for development/testing.

    Matches diagnosis codes to institutional clinical protocols.
    """

    def find_protocols(
        self,
        diagnosis_codes: list[dict[str, Any]],
        encounter_class: str,
    ) -> list[ClinicalProtocol]:
        """Find protocols using CID-10 matching."""
        matched_protocols: dict[str, ClinicalProtocol] = {}

        for diagnosis in diagnosis_codes:
            code = diagnosis.get("code", "")
            # Match on CID-10 chapter (first 3 chars)
            prefix = code[:3] if len(code) >= 3 else code

            for protocol in _CLINICAL_PROTOCOLS.values():
                # Check if this protocol applies to this diagnosis
                for applicable in protocol.applicable_conditions:
                    if code.startswith(applicable) or prefix == applicable:
                        if protocol.protocol_id not in matched_protocols:
                            matched_protocols[protocol.protocol_id] = protocol

        return list(matched_protocols.values())


# ── Worker ────────────────────────────────────────────────────────────


class ClinicalProtocolsWorker:
    """Applies clinical protocols based on diagnosis.

    Identifies applicable clinical protocols and guidelines for
    the patient's condition and generates step-by-step care instructions.
    """

    TOPIC = "clinical.protocols"

    def __init__(
        self,
        protocol_engine: ProtocolEngine | None = None,
        tasy_api_client: TasyApiClientProtocol | None = None,
    ) -> None:
        self._engine = protocol_engine or DMNProtocolEngine()
        self._tasy_api_client = tasy_api_client
        self._logger = get_logger(__name__, worker=self.TOPIC)

    @require_tenant
    @track_task_execution(metric_name="clinical_protocols")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Find and apply clinical protocols for diagnosis.

        Task Variables (input):
            encounter_reference: str - FHIR Encounter reference
            diagnosis_codes: list[dict] - CID-10 diagnosis codes
            encounter_class: str - Encounter classification
            tenant_id: str - Tenant identifier (set via context)

        Returns:
            applicable_protocols: list[dict] - Applicable clinical protocols
            protocol_steps: list[dict] - All steps from all protocols
            compliance_requirements: list[str] - Regulatory requirements
        """
        ctx = get_required_tenant()
        encounter_reference: str = task_variables.get("encounter_reference", "")
        diagnosis_codes: list[dict[str, Any]] = task_variables.get(
            "diagnosis_codes", []
        )
        encounter_class: str = task_variables.get("encounter_class", "ambulatorio")

        if not encounter_reference:
            raise ClinicalException(
                _("Referência de encontro é obrigatória"),
                bpmn_error_code="CLINICAL_ERROR",
            )

        if not diagnosis_codes:
            raise ClinicalException(
                _("Códigos de diagnóstico são obrigatórios para aplicação de protocolos"),
                bpmn_error_code="CLINICAL_ERROR",
            )

        self._logger.info(
            "searching_clinical_protocols",
            encounter_reference=encounter_reference,
            diagnosis_count=len(diagnosis_codes),
            encounter_class=encounter_class,
            tenant_id=ctx.tenant_id,
        )

        # ── Integrate TASY ventilator management scoring (optional) ──

        vent_data = None
        if self._tasy_api_client:
            try:
                # Extract encounter ID from reference (e.g., "Encounter/123" -> "123")
                encounter_id = encounter_reference.split("/")[-1]
                vent_data = await self._tasy_api_client.get_vent_management_score(encounter_id)
                self._logger.info(
                    "tasy_vent_data_retrieved",
                    encounter_id=encounter_id,
                    vent_data=vent_data,
                    tenant_id=ctx.tenant_id,
                )
            except Exception as e:
                self._logger.warning(
                    "tasy_vent_data_failed",
                    encounter_reference=encounter_reference,
                    error=str(e),
                    tenant_id=ctx.tenant_id,
                )

        # ── Find applicable protocols ────────────────────────────────

        protocols = self._engine.find_protocols(
            diagnosis_codes=diagnosis_codes,
            encounter_class=encounter_class,
        )

        if not protocols:
            self._logger.info(
                "no_protocols_found",
                diagnosis_codes=[d.get("code") for d in diagnosis_codes],
                tenant_id=ctx.tenant_id,
            )

        # ── Aggregate protocol data ──────────────────────────────────

        applicable_protocols_list: list[dict[str, Any]] = []
        all_steps: list[dict[str, Any]] = []
        all_compliance: set[str] = set()

        for protocol in protocols:
            applicable_protocols_list.append(
                {
                    "protocol_id": protocol.protocol_id,
                    "name": protocol.name,
                    "version": protocol.version,
                    "steps_count": len(protocol.steps),
                }
            )

            # Add steps with protocol context
            for step in protocol.steps:
                all_steps.append(
                    {
                        "protocol_id": protocol.protocol_id,
                        "protocol_name": protocol.name,
                        "sequence": step.sequence,
                        "action": step.action,
                        "timing": step.timing,
                        "mandatory": step.mandatory,
                    }
                )

            # Aggregate compliance requirements
            for requirement in protocol.compliance_requirements:
                all_compliance.add(requirement)

        # Sort steps by protocol and sequence
        all_steps.sort(key=lambda s: (s["protocol_id"], s["sequence"]))

        # Add ventilator management steps if patient is on ventilator
        if vent_data and vent_data.get("on_ventilator"):
            all_steps.append(
                {
                    "protocol_id": "TASY_VENT_MANAGEMENT",
                    "protocol_name": "TASY Ventilator Management",
                    "sequence": 1,
                    "action": _(
                        "Seguir protocolo de ventilação mecânica. "
                        "TASY score: {score}, Status: {status}"
                    ).format(
                        score=vent_data.get("score", "N/A"),
                        status=vent_data.get("status", "N/A"),
                    ),
                    "timing": "continuous",
                    "mandatory": True,
                }
            )
            all_compliance.add(_("Monitorar protocolo de ventilação mecânica via TASY"))

        output = ClinicalProtocolsOutput(
            applicable_protocols=applicable_protocols_list,
            protocol_steps=all_steps,
            compliance_requirements=list(all_compliance),
        )

        # Convert to variables and add TASY vent data if available
        output_vars = output.to_variables()
        if vent_data:
            output_vars["tasy_vent_data"] = vent_data

        self._logger.info(
            "clinical_protocols_applied",
            protocols_count=len(protocols),
            total_steps=len(all_steps),
            compliance_requirements_count=len(all_compliance),
            tasy_vent_data_present=vent_data is not None,
            tenant_id=ctx.tenant_id,
        )

        return output_vars
