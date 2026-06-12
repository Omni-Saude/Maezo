"""Submit prior authorization request to payer for clinical procedures.

TOPIC: revenue_cycle.request_authorization
ARCHETYPE: ADMIN_ADJUDICATION

Fluxo:
  1. DMN authorization_channel_001 decide o canal com base em:
       - payer_id            (convênio: UNIMED_SP, BRADESCO_SAUDE, ...)
       - cd_estabelecimento  (4 = Austa, 5 = AMH, ...)
       - authorization_type  (consulta, cirurgia, exame)
     → retorna authorization_channel ("rpa" | "dmn") + rpa_type

  2a. Canal "rpa"  → fire-and-forget para o robô indicado por rpa_type
       Payload em formato FHIR-inspired (cobertura, prestador, atendimento,
       procedimentos). O RPA usa esses dados para preencher o portal — não
       consulta Oracle para dados de entrada.
       Worker retorna imediatamente com rpaJobId + rpaType.
       Processo BPMN pausa no receiveTask "Aguardar Automação RPA"
       (messageRef="Message_AuthCompleted", messageName="AuthorizationCompleted").
       RPA correlaciona resultado via POST /engine-rest/message com processInstanceId.

  2b. Canal "dmn"  → adjudicação interna via DMN (2 steps)
       1. auth_complexity_001       (authorization/)        → requiresAuth, authLevel
       2. authorization_status_adjudication (pricing/authorization/) → resultado, acao, risco

Variáveis BPMN esperadas (canal RPA):
    Cobertura : carteirinha, cdConvenio, dsConvenio
    Prestador : cdPrestador, nrCrm
    Atendimento: nrAtendimento, nrSequencia, cdEstabelecimento, dtEntrada,
                 dsCaraterAtendimento, ieConsultaEmergencia,
                 ieTipoConsulta, ieTipoAtendimento, ieRegimeAtendimento,
                 tpAcidente, dsIndClinica, dsObservacao, cdAusenciaValBenef
    Procedimentos: enrichedProcedures  [{code, display, quantity, category}]
    Diagnósticos : diagnosisCodes      [CID-10]

ADR Compliance:
- ADR-002: Tenant resolution via context
- ADR-003: BaseExternalTaskWorker inheritance
- ADR-007: DMN federation for tenant overrides
"""
from __future__ import annotations

import json
from typing import Optional

from healthcare_platform.shared.integrations.rpa_client import (
    RpaAtendimento,
    RpaAuthorizationRequest,
    RpaClientProtocol,
    RpaCobertura,
    RpaPrestador,
    RpaProcedimento,
    make_rpa_client,
)
from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


class RequestAuthorizationWorker(BaseExternalTaskWorker):
    """Submete pedido de autorização prévia via RPA ou DMN.

    O canal e o robô são determinados pelo DMN authorization_channel_001,
    que cruza o convênio (payer_id), o estabelecimento (cd_estabelecimento)
    e o tipo de autorização (authorization_type).

    Injeção de dependência:
        rpa_client: RpaClientProtocol — cliente do robô de automação.
                    Obrigatório quando o DMN retornar channel="rpa".
    """

    TOPIC = "revenue_cycle.request_authorization"

    DMN_CHANNEL_KEY = "authorization_channel_001"
    DMN_CHANNEL_CATEGORY = "authorization"

    DMN_COMPLEXITY_KEY = "auth_complexity_001"
    DMN_COMPLEXITY_CATEGORY = "authorization"

    DMN_ADJUDICATION_KEY = "authorization_status_adjudication"
    DMN_ADJUDICATION_CATEGORY = "pricing/authorization"

    def __init__(
        self,
        rpa_client: Optional[RpaClientProtocol] = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        import os
        if rpa_client is None and os.environ.get("RPA_UNIMED_URL"):
            self._rpa_client = make_rpa_client()
        else:
            self._rpa_client = rpa_client

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def execute(self, context: TaskContext) -> TaskResult:
        routing_or_error = self._resolve_channel(context)
        if isinstance(routing_or_error, TaskResult):
            return routing_or_error  # erro de validação antes do DMN

        if routing_or_error["channel"] == "rpa":
            return self._execute_via_rpa(context, routing_or_error["rpa_type"])
        return self._execute_via_dmn(context)

    # ------------------------------------------------------------------
    # Roteamento via DMN
    # ------------------------------------------------------------------

    def _resolve_channel(self, context: TaskContext) -> dict | TaskResult:
        """Lê o resultado do DMN authorization_channel_001 avaliado pelo CIB Seven.

        O DMN é executado na Business Rule Task anterior (task_dmn_auth_channel)
        pelo motor BPMN com suporte completo a FEEL. O resultado é armazenado
        na variável de processo 'authChannelResult' (camunda:resultVariable).

        O worker apenas lê essa variável — não re-avalia o DMN localmente.
        """
        variables = context.variables
        auth_channel_result = variables.get("authChannelResult")

        if not auth_channel_result or not isinstance(auth_channel_result, dict):
            return TaskResult.bpmn_error(
                error_code="MISSING_AUTH_CHANNEL_RESULT",
                error_message=(
                    "Variável 'authChannelResult' ausente ou inválida — "
                    "o DMN authorization_channel_001 deve ser executado antes "
                    "deste worker via Business Rule Task no BPMN"
                ),
            )

        channel = auth_channel_result.get("authorization_channel", "dmn")
        rpa_type = auth_channel_result.get("rpa_type", "")

        self.logger.info(
            "Canal de autorização resolvido via DMN (authChannelResult)",
            extra={
                "authorization_channel": channel,
                "rpa_type": rpa_type,
                "tenant_id": context.tenant_id,
            },
        )

        return {"channel": channel, "rpa_type": rpa_type}

    # ------------------------------------------------------------------
    # Caminho 1: RPA (fire-and-forget) — payload FHIR-inspired
    # ------------------------------------------------------------------

    def _execute_via_rpa(self, context: TaskContext, rpa_type: str) -> TaskResult:
        """Dispara o job de autorização no RPA com payload FHIR-inspired.

        Todos os dados necessários para o portal Unimed (SPSADT) são extraídos
        das variáveis BPMN e enviados ao RPA. O RPA não consulta Oracle para
        dados de entrada — apenas para gravar o resultado.

        O processo BPMN avança para o Message Catch Event e aguarda
        o callback do RPA via 'rpa_authorization_result'.
        """
        if self._rpa_client is None:
            return TaskResult.bpmn_error(
                error_code="RPA_NOT_CONFIGURED",
                error_message="RpaClient não injetado — necessário para autorizações via RPA",
            )

        variables = context.variables
        raw_procedures = variables.get("enrichedProcedures", [])
        procedures = json.loads(raw_procedures) if isinstance(raw_procedures, str) else raw_procedures

        raw_diagnoses = variables.get("diagnosisCodes", [])
        diagnoses = json.loads(raw_diagnoses) if isinstance(raw_diagnoses, str) else raw_diagnoses

        if not procedures:
            return TaskResult.bpmn_error(
                error_code="CODING_ERROR",
                error_message="Nenhum procedimento para autorizar",
            )

        self.logger.info(
            "Despachando job de autorização para RPA (payload FHIR)",
            extra={
                "tenant_id": context.tenant_id,
                "process_instance_id": context.process_instance_id,
                "procedure_count": len(procedures),
                "payer_id": variables.get("payerId", ""),
                "cd_estabelecimento": variables.get("cdEstabelecimento"),
                "rpa_type": rpa_type,
            },
        )

        try:
            rpa_request = RpaAuthorizationRequest(
                process_instance_id=context.process_instance_id,
                tenant_id=context.tenant_id,
                rpa_type=rpa_type,
                message_name=variables.get("rpaMessageName", "AuthorizationCompleted"),
                cobertura=RpaCobertura(
                    carteirinha=variables.get("carteirinha", ""),
                    cd_convenio=variables.get("cdConvenio", 0),
                    ds_convenio=variables.get("dsConvenio", ""),
                ),
                prestador=RpaPrestador(
                    cd_prestador=variables.get("cdPrestador", ""),
                    nr_crm=variables.get("nrCrm", ""),
                ),
                atendimento=RpaAtendimento(
                    nr_atendimento=variables.get("nrAtendimento", 0),
                    nr_sequencia=variables.get("nrSequencia", 0),
                    cd_estabelecimento=variables.get("cdEstabelecimento", 4),
                    dt_entrada=variables.get("dtEntrada", ""),
                    ds_carater_atendimento=variables.get("dsCaraterAtendimento", "Urgência/Emergência"),
                    ie_consulta_emergencia=variables.get("ieConsultaEmergencia", "True"),
                    ie_tipo_consulta=variables.get("ieTipoConsulta", "Primeira consulta"),
                    ie_tipo_atendimento=variables.get("ieTipoAtendimento", "Consulta"),
                    ie_regime_atendimento=variables.get("ieRegimeAtendimento", "Pronto Socorro"),
                    tp_acidente=variables.get("tpAcidente", "Não acidente"),
                    ds_ind_clinica=variables.get("dsIndClinica", ""),
                    ds_observacao=variables.get("dsObservacao", ""),
                    cd_ausencia_val_benef=variables.get("cdAusenciaValBenef", ""),
                ),
                procedimentos=[
                    RpaProcedimento(
                        code=p.get("code", ""),
                        display=p.get("display", ""),
                        quantity=p.get("quantity", 1),
                        category=p.get("category", ""),
                    )
                    for p in procedures
                ],
                diagnoses=diagnoses,
            )

            rpa_job = self._rpa_client.request_authorization(rpa_request)

        except Exception as e:
            self.logger.error(f"Falha ao despachar job para RPA ({rpa_type}): {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="RPA_DISPATCH_ERROR",
                error_message=str(e),
            )

        self.logger.info(
            "Job RPA despachado — aguardando callback via Message Catch Event",
            extra={
                "rpa_execution_id": rpa_job.rpa_execution_id,
                "rpa_type": rpa_type,
                "process_instance_id": context.process_instance_id,
            },
        )

        return TaskResult.success({
            "rpaJobId": rpa_job.rpa_execution_id,
            "rpaType": rpa_type,
            "authorizationChannel": "rpa",
        })

    # ------------------------------------------------------------------
    # Caminho 2: DMN (adjudicação interna)
    # ------------------------------------------------------------------

    def _execute_via_dmn(self, context: TaskContext) -> TaskResult:
        """Adjudicação via DMN para convênios sem RPA configurado."""
        variables = context.variables
        raw_procedures = variables.get("enrichedProcedures", [])
        procedures = json.loads(raw_procedures) if isinstance(raw_procedures, str) else raw_procedures
        existing_auth = variables.get("existingAuthNumber", "")

        if not procedures:
            return TaskResult.bpmn_error(
                error_code="CODING_ERROR",
                error_message="Nenhum procedimento para autorizar",
            )

        self.logger.info(
            f"Verificando autorização via DMN: {len(procedures)} procedimento(s)",
            extra={"tenant_id": context.tenant_id},
        )

        results = []
        all_authorized = True

        for proc in procedures:
            code = proc.get("code", "")
            category = proc.get("category", "")
            auth_status = proc.get("authorization_status", "pending")

            complexity = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_COMPLEXITY_KEY,
                variables={"procedure_code": code, "procedure_category": category},
                category=self.DMN_COMPLEXITY_CATEGORY,
            )
            requires_auth = complexity.get("requires_auth", True)
            auth_level = complexity.get("auth_level", "none")

            adjudication = self.evaluate_dmn(
                context=context,
                decision_key=self.DMN_ADJUDICATION_KEY,
                variables={
                    "authorization_status": auth_status,
                    "authorization_number": existing_auth,
                    "requires_auth": requires_auth,
                },
                category=self.DMN_ADJUDICATION_CATEGORY,
            )

            resultado = adjudication.get("resultado", "REVISAR")
            acao = adjudication.get("acao", "")
            risco = adjudication.get("risco", "MEDIO")

            results.append({
                "code": code,
                "authorized": resultado == "PROSSEGUIR",
                "auth_number": existing_auth,
                "auth_level": auth_level,
                "requires_auth": requires_auth,
                "status": resultado,
                "message": acao,
                "risk": risco,
                "channel": "dmn",
            })

            if resultado in ("BLOQUEAR", "REVISAR"):
                all_authorized = False

        if not all_authorized:
            denied = [r for r in results if not r["authorized"]]
            return TaskResult.bpmn_error(
                error_code="AUTH_DENIED",
                error_message=denied[0]["message"] if denied else "Autorização negada",
                variables={
                    "authorizationResults": results,
                    "deniedCodes": [d["code"] for d in denied],
                },
            )

        return TaskResult.success({
            "authorizationResults": results,
            "allAuthorized": True,
            "authNumber": existing_auth,
            "authorizationChannel": "dmn",
        })
