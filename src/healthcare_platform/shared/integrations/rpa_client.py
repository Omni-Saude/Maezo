"""Cliente HTTP síncrono para o projeto de automação RPA de autorização.

O RPA é um projeto Python separado (clean architecture — hos_austa_autorizacaopre)
que recebe uma requisição de autorização em formato FHIR-inspired e retorna
202 Accepted imediatamente (fire-and-forget). O resultado final é enviado de volta
ao CIB Seven pelo próprio RPA via POST /engine-rest/message com
messageName="AuthorizationCompleted" e processInstanceId como chave de correlação.

Variáveis de processo retornadas pelo callback do RPA:
    rpaStatus   — status TASY ("APROVADO" | "IMPEDIMENTO" | "FALHA")
    rpaProtocol — código de requisição ou guia
    rpaMensagem — mensagem legível do resultado
    rpaCodGuia  — código da guia de autorização

Estrutura do payload (FHIR-inspired):
    cobertura   → FHIR Coverage  (carteirinha, convênio)
    prestador   → FHIR Practitioner (CRM, cod_prestador)
    atendimento → FHIR Encounter  (nr_atendimento, estabelecimento, datas, tipo)
    procedimentos → FHIR ServiceRequest[] (códigos TUSS)
    diagnoses   → FHIR Condition[] (CID-10)

Variáveis de ambiente:
    RPA_UNIMED_URL     — URL do serviço RPA  (default: http://rpa-unimed:8000)
    RPA_UNIMED_TIMEOUT — Timeout em segundos (default: 30)
"""
from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from healthcare_platform.shared.domain.exceptions import ExternalServiceException
from healthcare_platform.shared.integrations.base import IntegrationSettings
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# DTOs — estrutura FHIR-inspired
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RpaCobertura:
    """FHIR Coverage — dados do plano/convênio do beneficiário."""

    carteirinha: str      # Coverage.subscriberId  (17 dígitos zero-padded)
    cd_convenio: int      # Coverage.class[group].value  (27 = Unimed PA)
    ds_convenio: str      # Coverage.payor[0].display    ("Unimed")


@dataclass(frozen=True)
class RpaPrestador:
    """FHIR Practitioner + PractitionerRole — médico/prestador."""

    cd_prestador: str     # PractitionerRole.identifier[cd-prestador].value
    nr_crm: str           # Practitioner.identifier[crm].value


@dataclass(frozen=True)
class RpaAtendimento:
    """FHIR Encounter — dados do atendimento hospitalar."""

    nr_atendimento: int         # Encounter.identifier[tasy-nr-atendimento].value
    nr_sequencia: int           # Chave Oracle interna — necessária para procedures TASY
    cd_estabelecimento: int     # Encounter.serviceProvider.identifier[cd-est].value
    dt_entrada: str             # Encounter.period.start  (ISO 8601)
    ds_carater_atendimento: str # Encounter.priority.text  ("Urgência/Emergência")
    ie_consulta_emergencia: str # Encounter.priority.code → "True"/"False"
    ie_tipo_consulta: str       # portal-specific  ("Primeira consulta")
    ie_tipo_atendimento: str    # Encounter.type[0].text  ("Consulta")
    ie_regime_atendimento: str  # Encounter.hospitalization.admitSource.text  ("Pronto Socorro")
    tp_acidente: str            # Encounter.extension[tipo-acidente]  ("Não acidente")
    ds_ind_clinica: str = ""    # portal Austa — clínica indicada
    ds_observacao: str = ""     # Encounter.text.div
    cd_ausencia_val_benef: str = ""  # motivo ausência token beneficiário


@dataclass(frozen=True)
class RpaProcedimento:
    """FHIR ServiceRequest — procedimento a autorizar."""

    code: str             # ServiceRequest.code.coding[tuss].code
    display: str = ""     # ServiceRequest.code.coding[tuss].display
    quantity: int = 1     # ServiceRequest.quantity.value
    category: str = ""    # ServiceRequest.category.text


@dataclass(frozen=True)
class RpaAuthorizationRequest:
    """Payload completo enviado ao RPA para iniciar a autorização.

    Todos os dados necessários para preencher o portal Unimed (SPSADT)
    são enviados pelo MAEZO — o RPA não consulta o Oracle para obter dados
    de entrada; apenas usa Oracle para gravar o resultado via procedures TASY.
    """

    process_instance_id: str
    tenant_id: str
    rpa_type: str                    # "autorizacao_pa" | "autorizacao_cirurgia" | "autorizacao_exames"
    cobertura: RpaCobertura
    prestador: RpaPrestador
    atendimento: RpaAtendimento
    procedimentos: list[RpaProcedimento]
    diagnoses: list[str] = field(default_factory=list)  # CID-10
    message_name: str = "AuthorizationCompleted"


@dataclass(frozen=True)
class RpaJobAccepted:
    """Confirmação imediata (202 Accepted) do RPA após receber o job.

    O RPA processa em background e, ao terminar, chama o CIB Seven via:
        POST /engine-rest/message
        {
            "messageName": "AuthorizationCompleted",
            "processInstanceId": "<process_instance_id>",
            "processVariables": {
                "rpaStatus":   {"value": "APROVADO",    "type": "String"},
                "rpaProtocol": {"value": "REQ-001",     "type": "String"},
                "rpaMensagem": {"value": "Autorizado",  "type": "String"},
                "rpaCodGuia":  {"value": "UNI-2026-XX", "type": "String"}
            }
        }
    """

    rpa_execution_id: str


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class RpaClientProtocol(Protocol):
    """Interface do cliente RPA — permite substituição em testes."""

    def request_authorization(
        self, request: RpaAuthorizationRequest
    ) -> RpaJobAccepted: ...


# ---------------------------------------------------------------------------
# Implementação HTTP síncrona
# ---------------------------------------------------------------------------


class RpaClient:
    """Chama o serviço RPA via HTTP síncrono (fire-and-forget).

    O RPA responde com 202 Accepted imediatamente e processa em background.
    Usa httpx.Client (síncrono) pois é invocado a partir de workers síncronos
    (BaseExternalTaskWorker.execute).
    """

    SERVICE_NAME = "rpa_authorization"

    def __init__(self, settings: IntegrationSettings) -> None:
        self._settings = settings
        self._logger = get_logger(f"integration.{self.SERVICE_NAME}")

    def request_authorization(
        self, request: RpaAuthorizationRequest
    ) -> RpaJobAccepted:
        """Dispara o job de autorização no RPA e retorna imediatamente.

        Serializa o request completo como JSON usando dataclasses.asdict(),
        que converte recursivamente todos os dataclasses aninhados.

        Returns:
            RpaJobAccepted com o rpa_execution_id para rastreamento.

        Raises:
            ExternalServiceException: em caso de falha HTTP ou timeout.
        """
        payload = dataclasses.asdict(request)

        self._logger.info(
            "rpa_authorization_dispatched",
            rpa_type=request.rpa_type,
            cd_convenio=request.cobertura.cd_convenio,
            nr_atendimento=request.atendimento.nr_atendimento,
            process_instance_id=request.process_instance_id,
        )

        try:
            with httpx.Client(
                base_url=self._settings.base_url,
                timeout=httpx.Timeout(self._settings.timeout_seconds),
            ) as client:
                resp = client.post("/api/v1/authorize", json=payload)
                resp.raise_for_status()

        except httpx.HTTPStatusError as exc:
            raise ExternalServiceException(
                f"RPA retornou {exc.response.status_code}",
                service_name=self.SERVICE_NAME,
                operation="request_authorization",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.TimeoutException as exc:
            raise ExternalServiceException(
                "RPA tempo limite excedido ao despachar job",
                service_name=self.SERVICE_NAME,
                operation="request_authorization",
            ) from exc

        data = resp.json()
        rpa_execution_id = data.get("rpa_execution_id", "")

        self._logger.info(
            "rpa_job_accepted",
            rpa_execution_id=rpa_execution_id,
            process_instance_id=request.process_instance_id,
        )

        return RpaJobAccepted(rpa_execution_id=rpa_execution_id)


# ---------------------------------------------------------------------------
# Factory — lê env vars, usada pelo worker em produção
# ---------------------------------------------------------------------------


def make_rpa_client() -> RpaClient:
    """Cria RpaClient a partir das variáveis de ambiente."""
    url = os.environ.get("RPA_UNIMED_URL", "http://rpa-unimed:8000")
    timeout = float(os.environ.get("RPA_UNIMED_TIMEOUT", "30"))
    return RpaClient(
        settings=IntegrationSettings(base_url=url, timeout_seconds=timeout)
    )


# ---------------------------------------------------------------------------
# Stub para testes
# ---------------------------------------------------------------------------


class StubRpaClient:
    """Stub em memória para testes unitários."""

    def __init__(
        self,
        rpa_execution_id: str = "stub-exec-001",
        raise_error: bool = False,
    ) -> None:
        self._rpa_execution_id = rpa_execution_id
        self._raise_error = raise_error
        self.calls: list[RpaAuthorizationRequest] = []

    def request_authorization(
        self, request: RpaAuthorizationRequest
    ) -> RpaJobAccepted:
        self.calls.append(request)

        if self._raise_error:
            raise ExternalServiceException(
                "Stub RPA: erro simulado",
                service_name="rpa_authorization",
                operation="request_authorization",
            )

        return RpaJobAccepted(
            rpa_execution_id=self._rpa_execution_id or f"stub-exec-{request.process_instance_id}",
        )
