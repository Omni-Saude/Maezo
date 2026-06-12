"""Generic WhatsApp escalation worker for SLA breach events.

TOPIC: platform.whatsapp_escalation

Each BPMN process defines cdModelo as a camunda:inputParameter on the
service task, selecting the Tasy WhatsApp template to use.

Supported templates
-------------------
CD_MODELO_AUTORIZACAO_PENDENTE (99)     — maezo_rc_autorizacao_pendente
    Notifica equipe quando autorização excede SLA (RC-002, timer 48h).
    BPMN must set: nomeResponsavel, nomeOperadora, nmProcedimento,
                   tempoEsperaPendente, slaPrazo
    FHIR: yes (patientFhirId, encounterFhirId)

CD_MODELO_CONTA_PENDENCIAS (100)        — maezo_rc_conta_pendencias
    Notifica médico sobre pendências de conta (RC-003).
    BPMN must set: nomeResponsavel, qtPendencias, dsPendencias,
                   dtLimitePendencias
    FHIR: yes (patientFhirId, encounterFhirId)

CD_MODELO_AUTORIZACAO_RESUMO_DIARIO (101) — maezo_rc_autorizacao_resumo_diario
    Resumo diário de autorizações pendentes para a equipe gestora.
    BPMN must set: qtAutorizacoesPendentes, qtAutorizacoesTotais30Dias,
                   nrTelefoneDestino (telefone da equipe, sem formatação)
    FHIR: no (agregado, sem paciente específico)

Phase 1: austa-hospital only.
Other tenants: warning + success (no notification sent).
"""
from __future__ import annotations

import json
import os
import re

import httpx

from healthcare_platform.shared.domain.exceptions import ExternalServiceException
from healthcare_platform.shared.integrations.whatsapp_notification_client import (
    WhatsAppNotificationClient,
    WhatsAppNotificationPayload,
    WhatsAppNotificationSettings,
)
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)

TOPIC = "platform.whatsapp_escalation"
_AUSTA_HOSPITAL = "austa-hospital"

# Tasy cd_modelo — provisional values (100, 101 pending Meta approval)
CD_MODELO_AUTORIZACAO_PENDENTE = 99       # maezo_rc_autorizacao_pendente
CD_MODELO_CONTA_PENDENCIAS = 100          # maezo_rc_conta_pendencias
CD_MODELO_AUTORIZACAO_RESUMO_DIARIO = 101  # maezo_rc_autorizacao_resumo_diario

# Templates that require FHIR lookup (patient/encounter specific)
_FHIR_REQUIRED = {CD_MODELO_AUTORIZACAO_PENDENTE, CD_MODELO_CONTA_PENDENCIAS}


# ---------------------------------------------------------------------------
# FHIR helpers
# ---------------------------------------------------------------------------

def _fhir_get(fhir_base_url: str, resource_type: str, resource_id: str) -> dict:
    url = f"{fhir_base_url}/{resource_type}/{resource_id}"
    resp = httpx.get(url, timeout=10.0, headers={"Accept": "application/fhir+json"})
    resp.raise_for_status()
    return resp.json()


def _extract_identifier(identifiers: list[dict], system: str) -> str:
    for ident in identifiers:
        if ident.get("system") == system:
            return str(ident.get("value", ""))
    return ""


def _extract_phone(telecoms: list[dict]) -> int:
    for telecom in telecoms:
        if telecom.get("system") == "phone":
            digits = re.sub(r"\D", "", str(telecom.get("value", "")))
            return int(digits) if digits else 0
    return 0


def _patient_display_name(patient: dict) -> str:
    """Extract display name from FHIR Patient.name (HumanName)."""
    names = patient.get("name", [])
    if not names:
        return ""
    name = names[0]
    given = " ".join(name.get("given", []))
    family = name.get("family", "")
    return f"{given} {family}".strip()


# ---------------------------------------------------------------------------
# Template parameter builders
# ds_parametros: JSON array of strings matching {{1}}, {{2}}, ... in order
# ---------------------------------------------------------------------------

def _params_autorizacao_pendente(variables: dict, nome_paciente: str) -> str:
    """
    maezo_rc_autorizacao_pendente — 6 parâmetros
    {{1}} Olá <nomeResponsavel>
    {{2}} Paciente: <nomePaciente>
    {{3}} Operadora: <nomeOperadora>
    {{4}} Procedimento: <nmProcedimento>
    {{5}} Pendente há: <tempoEsperaPendente>
    {{6}} SLA: <slaPrazo>
    """
    return json.dumps([
        variables.get("nomeResponsavel", ""),
        nome_paciente,
        variables.get("nomeOperadora", variables.get("payerId", "")),
        variables.get("nmProcedimento", ""),
        variables.get("tempoEsperaPendente", ""),
        variables.get("slaPrazo", "48 horas"),
    ], ensure_ascii=False)


def _params_conta_pendencias(variables: dict, nome_paciente: str) -> str:
    """
    maezo_rc_conta_pendencias — 5 parâmetros
    {{1}} Olá <nomeResponsavel>
    {{2}} <qtPendencias> pendência(s)
    {{3}} Paciente: <nomePaciente>
    {{4}} <dsPendencias> (bullet list já formatada pelo processo)
    {{5}} Data limite: <dtLimitePendencias>
    """
    return json.dumps([
        variables.get("nomeResponsavel", ""),
        str(variables.get("qtPendencias", "")),
        nome_paciente,
        variables.get("dsPendencias", ""),
        variables.get("dtLimitePendencias", ""),
    ], ensure_ascii=False)


def _params_autorizacao_resumo_diario(variables: dict, nome_paciente: str) -> str:
    """
    maezo_rc_autorizacao_resumo_diario — 2 parâmetros (sem paciente específico)
    {{1}} <qtAutorizacoesPendentes> autorizações pendentes até ontem
    {{2}} <qtAutorizacoesTotais30Dias> total nos últimos 30 dias
    """
    return json.dumps([
        str(variables.get("qtAutorizacoesPendentes", "")),
        str(variables.get("qtAutorizacoesTotais30Dias", "")),
    ], ensure_ascii=False)


_PARAM_BUILDERS = {
    CD_MODELO_AUTORIZACAO_PENDENTE: _params_autorizacao_pendente,
    CD_MODELO_CONTA_PENDENCIAS: _params_conta_pendencias,
    CD_MODELO_AUTORIZACAO_RESUMO_DIARIO: _params_autorizacao_resumo_diario,
}


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

def _build_notification_client() -> WhatsAppNotificationClient:
    return WhatsAppNotificationClient(
        WhatsAppNotificationSettings(
            base_url=os.environ["WHATSAPP_NOTIFICATION_API_URL"],
            api_key=os.environ["WHATSAPP_NOTIFICATION_API_KEY"],
        )
    )


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class SlaWhatsAppEscalationWorker(BaseExternalTaskWorker):
    """WhatsApp escalation for SLA breach. Generic: cd_modelo set per BPMN process."""

    TOPIC = TOPIC

    def __init__(
        self,
        notification_client: WhatsAppNotificationClient | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._notification_client = notification_client or _build_notification_client()

    def execute(self, context: TaskContext) -> TaskResult:
        variables = context.variables
        tenant_id = context.tenant_id

        if tenant_id != _AUSTA_HOSPITAL:
            self.logger.warning(
                "WhatsApp escalation not configured for tenant — skipping",
                extra={"tenant_id": tenant_id, "topic": TOPIC},
            )
            return TaskResult.success(
                {"slaEscalated": True, "escalationType": "WHATSAPP_SKIPPED"}
            )

        payer_id = variables.get("payerId", "")
        cd_modelo = int(variables.get("cdModelo", CD_MODELO_AUTORIZACAO_PENDENTE))

        param_builder = _PARAM_BUILDERS.get(cd_modelo)
        if param_builder is None:
            self.logger.error(
                "cd_modelo without registered template builder",
                extra={"cd_modelo": cd_modelo, "tenant_id": tenant_id},
            )
            return TaskResult.failure(
                f"Template cd_modelo={cd_modelo} não registrado no worker",
                error_code="ERR_TEMPLATE_NAO_REGISTRADO",
            )

        # Resolve patient data — only for patient-specific templates
        nr_atendimento = ""
        nr_seq_segurado = 0
        nr_telefone = 0
        nome_paciente = ""

        if cd_modelo in _FHIR_REQUIRED:
            encounter_fhir_id = variables.get("encounterFhirId", "")
            patient_fhir_id = variables.get("patientFhirId", "")
            fhir_base = os.environ.get("FHIR_BASE_URL", "http://fhir:8080/fhir")

            try:
                encounter = _fhir_get(fhir_base, "Encounter", encounter_fhir_id)
                patient = _fhir_get(fhir_base, "Patient", patient_fhir_id)
            except httpx.HTTPError as exc:
                self.logger.error(
                    "FHIR lookup failed during SLA escalation",
                    extra={"encounter_fhir_id": encounter_fhir_id, "error": str(exc)},
                )
                return TaskResult.failure(
                    f"FHIR lookup error: {exc}", error_code="ERR_FHIR_LOOKUP"
                )

            nr_atendimento = _extract_identifier(
                encounter.get("identifier", []), "urn:austa:nr_atendimento"
            )
            nr_seq_str = _extract_identifier(
                patient.get("identifier", []), "urn:austa:nr_seq_segurado"
            )
            nr_seq_segurado = int(nr_seq_str) if nr_seq_str else 0
            nr_telefone = _extract_phone(patient.get("telecom", []))
            nome_paciente = _patient_display_name(patient)
        else:
            # Aggregate templates: telefone destino comes from process variable
            nr_telefone = int(re.sub(r"\D", "", str(variables.get("nrTelefoneDestino", "0"))) or "0")

        ds_parametros = param_builder(variables, nome_paciente)

        payload = WhatsAppNotificationPayload(
            tenant_id=tenant_id,
            cd_modelo=cd_modelo,
            nr_telefone=nr_telefone,
            nr_atendimento=nr_atendimento,
            nr_seq_segurado=nr_seq_segurado,
            payer_id=payer_id,
            ds_parametros=ds_parametros,
        )

        try:
            result = self._notification_client.send_whatsapp_notification(payload)
        except ExternalServiceException as exc:
            self.logger.error(
                "WhatsApp notification API failed",
                extra={"tenant_id": tenant_id, "error": str(exc)},
            )
            return TaskResult.failure(str(exc), error_code="ERR_WHATSAPP_NOTIFICATION")

        return TaskResult.success(
            {
                "slaEscalated": True,
                "escalationType": "WHATSAPP_NOTIFICATION",
                "whatsappNrSequencia": result.get("nr_sequencia"),
            }
        )
