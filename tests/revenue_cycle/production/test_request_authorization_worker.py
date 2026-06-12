"""Testes para RequestAuthorizationWorker.

O roteamento (RPA vs DMN) é decidido pelo DMN authorization_channel_001,
que recebe payer_id + cd_estabelecimento + authorization_type e retorna
authorization_channel + rpa_type.

O payload RPA agora segue formato FHIR-inspired (cobertura, prestador,
atendimento, procedimentos) — o RPA não consulta Oracle para dados de entrada.

Cobre:
  - Roteamento via DMN de canal (variáveis obrigatórias, canal retornado)
  - Caminho RPA (fire-and-forget, payload FHIR montado corretamente)
  - Caminho DMN de adjudicação
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from healthcare_platform.revenue_cycle.production.workers.request_authorization_worker import (
    RequestAuthorizationWorker,
)
from healthcare_platform.shared.integrations.rpa_client import StubRpaClient
from healthcare_platform.shared.workers.base import TaskContext, TaskStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def context():
    return TaskContext(
        task_id="task-auth-001",
        process_instance_id="proc-abc-123",
        tenant_id="HOSPITAL_A",
        variables={},
        worker_id="revenue_cycle.request_authorization",
    )


@pytest.fixture
def procedures():
    return [
        {"code": "10101012", "display": "Consulta PA", "category": "cirurgia", "quantity": 1, "authorization_status": "pending"},
        {"code": "20101034", "display": "Anestesia", "category": "anestesia", "quantity": 1, "authorization_status": "pending"},
    ]


def make_worker(rpa_client=None):
    worker = RequestAuthorizationWorker(rpa_client=rpa_client)
    worker.evaluate_dmn = MagicMock()
    return worker


def base_vars(**kwargs):
    """Variáveis mínimas válidas para o worker."""
    return {
        # DMN channel routing
        "payerId": "UNIMED_SP",
        "cdEstabelecimento": 4,
        "authorizationType": "consulta",
        # Cobertura (FHIR Coverage)
        "carteirinha": "00123456789012345",
        "cdConvenio": 27,
        "dsConvenio": "Unimed",
        # Prestador (FHIR Practitioner)
        "cdPrestador": "110020",
        "nrCrm": "12345",
        # Atendimento (FHIR Encounter)
        "nrAtendimento": 316211,
        "nrSequencia": 98765,
        "dtEntrada": "2026-03-24T10:00:00",
        "dsCaraterAtendimento": "Urgência/Emergência",
        "ieConsultaEmergencia": "True",
        "ieTipoConsulta": "Primeira consulta",
        "ieTipoAtendimento": "Consulta",
        "ieRegimeAtendimento": "Pronto Socorro",
        "tpAcidente": "Não acidente",
        # Diagnósticos
        "diagnosisCodes": ["K35"],
        **kwargs,
    }


# ---------------------------------------------------------------------------
# Roteamento via DMN de canal
# ---------------------------------------------------------------------------


class TestRoteamentoDMN:

    def test_dmn_channel_recebe_tres_inputs(self, context):
        """O DMN de canal deve receber payer_id, cd_estabelecimento e authorization_type."""
        worker = make_worker(rpa_client=StubRpaClient())
        worker.evaluate_dmn.return_value = {
            "authorization_channel": "rpa",
            "rpa_type": "autorizacao_pa",
        }

        context.variables = base_vars(
            enrichedProcedures=[{"code": "10101012", "display": "", "quantity": 1, "category": ""}],
        )

        worker.execute(context)

        channel_call = worker.evaluate_dmn.call_args_list[0]
        assert channel_call.kwargs["decision_key"] == "authorization_channel_001"
        assert channel_call.kwargs["variables"]["payer_id"] == "UNIMED_SP"
        assert channel_call.kwargs["variables"]["cd_estabelecimento"] == 4
        assert channel_call.kwargs["variables"]["authorization_type"] == "consulta"

    @pytest.mark.parametrize("missing_var,error_code", [
        ("payerId",          "MISSING_PAYER_ID"),
        ("cdEstabelecimento","MISSING_CD_ESTABELECIMENTO"),
        ("authorizationType","MISSING_AUTHORIZATION_TYPE"),
    ])
    def test_erro_variavel_obrigatoria_ausente(self, context, missing_var, error_code):
        """Qualquer variável obrigatória ausente → bpmn_error sem chamar o DMN."""
        worker = make_worker()
        variables = base_vars(enrichedProcedures=[])
        del variables[missing_var]
        context.variables = variables

        result = worker.execute(context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == error_code
        worker.evaluate_dmn.assert_not_called()

    def test_canal_rpa_roteia_para_rpa(self, context, procedures):
        """DMN retorna channel=rpa → worker aciona RpaClient."""
        stub = StubRpaClient(rpa_execution_id="exec-001")
        worker = make_worker(rpa_client=stub)
        worker.evaluate_dmn.return_value = {
            "authorization_channel": "rpa",
            "rpa_type": "autorizacao_pa",
        }

        context.variables = base_vars(enrichedProcedures=procedures)

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["authorizationChannel"] == "rpa"
        assert len(stub.calls) == 1

    def test_canal_dmn_roteia_para_dmn(self, context, procedures):
        """DMN retorna channel=dmn → worker usa adjudicação interna."""
        worker = make_worker()
        worker.evaluate_dmn.side_effect = [
            {"authorization_channel": "dmn", "rpa_type": ""},
            {"requires_auth": False, "auth_level": "none"},
            {"resultado": "PROSSEGUIR", "acao": "OK", "risco": "BAIXO"},
            {"requires_auth": False, "auth_level": "none"},
            {"resultado": "PROSSEGUIR", "acao": "OK", "risco": "BAIXO"},
        ]

        context.variables = base_vars(
            payerId="BRADESCO_SAUDE",
            enrichedProcedures=procedures,
        )

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["authorizationChannel"] == "dmn"

    def test_canal_desconhecido_cai_em_dmn(self, context, procedures):
        """Valor inesperado no authorization_channel → fallback para DMN."""
        worker = make_worker()
        worker.evaluate_dmn.side_effect = [
            {"authorization_channel": "desconhecido", "rpa_type": ""},
            {"requires_auth": False, "auth_level": "none"},
            {"resultado": "PROSSEGUIR", "acao": "OK", "risco": "BAIXO"},
        ]

        context.variables = base_vars(enrichedProcedures=[procedures[0]])

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["authorizationChannel"] == "dmn"


# ---------------------------------------------------------------------------
# Caminho RPA — payload FHIR-inspired
# ---------------------------------------------------------------------------


class TestCaminhoRpa:

    def _worker_rpa(self, stub, rpa_type="autorizacao_pa"):
        worker = make_worker(rpa_client=stub)
        worker.evaluate_dmn.return_value = {
            "authorization_channel": "rpa",
            "rpa_type": rpa_type,
        }
        return worker

    @pytest.mark.parametrize("authorization_type,rpa_type", [
        ("consulta",  "autorizacao_pa"),
        ("cirurgia",  "autorizacao_cirurgia"),
        ("exame",     "autorizacao_exames"),
    ])
    def test_rpa_type_propagado_por_tipo_autorizacao(
        self, context, procedures, authorization_type, rpa_type
    ):
        """rpaType no resultado deve refletir o rpa_type retornado pelo DMN."""
        stub = StubRpaClient(rpa_execution_id="exec-001")
        worker = self._worker_rpa(stub, rpa_type=rpa_type)

        context.variables = base_vars(
            authorizationType=authorization_type,
            enrichedProcedures=procedures,
        )

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["rpaType"] == rpa_type
        assert result.variables["authorizationChannel"] == "rpa"
        assert result.variables["rpaJobId"] == "exec-001"

    def test_payload_fhir_cobertura_enviada(self, context, procedures):
        """Campos de cobertura (FHIR Coverage) devem estar no request enviado ao RPA."""
        stub = StubRpaClient()
        worker = self._worker_rpa(stub)

        context.variables = base_vars(
            carteirinha="00123456789012345",
            cdConvenio=27,
            dsConvenio="Unimed",
            enrichedProcedures=procedures,
        )

        worker.execute(context)

        req = stub.calls[0]
        assert req.cobertura.carteirinha == "00123456789012345"
        assert req.cobertura.cd_convenio == 27
        assert req.cobertura.ds_convenio == "Unimed"

    def test_payload_fhir_prestador_enviado(self, context, procedures):
        """Campos de prestador (FHIR Practitioner) devem estar no request."""
        stub = StubRpaClient()
        worker = self._worker_rpa(stub)

        context.variables = base_vars(
            cdPrestador="110020",
            nrCrm="12345SP",
            enrichedProcedures=procedures,
        )

        worker.execute(context)

        req = stub.calls[0]
        assert req.prestador.cd_prestador == "110020"
        assert req.prestador.nr_crm == "12345SP"

    def test_payload_fhir_atendimento_enviado(self, context, procedures):
        """Campos de atendimento (FHIR Encounter) devem estar no request."""
        stub = StubRpaClient()
        worker = self._worker_rpa(stub)

        context.variables = base_vars(
            nrAtendimento=316211,
            nrSequencia=98765,
            dtEntrada="2026-03-24T10:00:00",
            enrichedProcedures=procedures,
        )

        worker.execute(context)

        req = stub.calls[0]
        assert req.atendimento.nr_atendimento == 316211
        assert req.atendimento.nr_sequencia == 98765
        assert req.atendimento.dt_entrada == "2026-03-24T10:00:00"

    def test_payload_fhir_procedimentos_enviados(self, context, procedures):
        """Lista de procedimentos deve ser enviada no request."""
        stub = StubRpaClient()
        worker = self._worker_rpa(stub)

        context.variables = base_vars(enrichedProcedures=procedures)

        worker.execute(context)

        req = stub.calls[0]
        assert len(req.procedimentos) == 2
        assert req.procedimentos[0].code == "10101012"
        assert req.procedimentos[1].code == "20101034"

    def test_sem_resultado_de_autorizacao_imediato(self, context, procedures):
        """Worker não deve retornar authorizationResults — RPA ainda processando."""
        stub = StubRpaClient()
        worker = self._worker_rpa(stub)

        context.variables = base_vars(enrichedProcedures=procedures)

        result = worker.execute(context)

        assert "authorizationResults" not in result.variables
        assert "authNumber" not in result.variables

    def test_rpa_sem_client_configurado(self, context, procedures):
        """canal=rpa mas rpa_client=None → RPA_NOT_CONFIGURED."""
        worker = make_worker(rpa_client=None)
        worker.evaluate_dmn.return_value = {
            "authorization_channel": "rpa",
            "rpa_type": "autorizacao_pa",
        }

        context.variables = base_vars(enrichedProcedures=procedures)

        result = worker.execute(context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "RPA_NOT_CONFIGURED"

    def test_rpa_sem_procedimentos(self, context):
        """canal=rpa + lista de procedimentos vazia → CODING_ERROR."""
        stub = StubRpaClient()
        worker = self._worker_rpa(stub)

        context.variables = base_vars(enrichedProcedures=[])

        result = worker.execute(context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "CODING_ERROR"
        assert len(stub.calls) == 0

    def test_rpa_excecao_no_cliente(self, context, procedures):
        """Exceção no RpaClient → RPA_DISPATCH_ERROR."""
        stub = StubRpaClient(raise_error=True)
        worker = self._worker_rpa(stub)

        context.variables = base_vars(enrichedProcedures=procedures)

        result = worker.execute(context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "RPA_DISPATCH_ERROR"


# ---------------------------------------------------------------------------
# Caminho DMN (adjudicação interna)
# ---------------------------------------------------------------------------


class TestCaminhoDmn:

    def _dmn_effects(self, *procedure_pairs):
        """Monta side_effects: 1 canal + N×2 DMNs (complexity + adjudication)."""
        effects = [{"authorization_channel": "dmn", "rpa_type": ""}]
        for complexity, adjudication in procedure_pairs:
            effects.append(complexity)
            effects.append(adjudication)
        return effects

    def test_prosseguir_retorna_success(self, context, procedures):
        """Todos PROSSEGUIR → success com allAuthorized=True e channel=dmn."""
        worker = make_worker()
        worker.evaluate_dmn.side_effect = self._dmn_effects(
            ({"requires_auth": False, "auth_level": "none"},
             {"resultado": "PROSSEGUIR", "acao": "OK", "risco": "BAIXO"}),
            ({"requires_auth": False, "auth_level": "none"},
             {"resultado": "PROSSEGUIR", "acao": "OK", "risco": "BAIXO"}),
        )

        context.variables = base_vars(
            payerId="BRADESCO_SAUDE",
            enrichedProcedures=procedures,
            existingAuthNumber="AUTH-001",
        )

        result = worker.execute(context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["allAuthorized"] is True
        assert result.variables["authorizationChannel"] == "dmn"
        assert result.variables["authNumber"] == "AUTH-001"

    def test_bloquear_retorna_bpmn_error(self, context):
        """BLOQUEAR → AUTH_DENIED com código em deniedCodes."""
        worker = make_worker()
        worker.evaluate_dmn.side_effect = self._dmn_effects(
            ({"requires_auth": True, "auth_level": "prior"},
             {"resultado": "BLOQUEAR", "acao": "Procedimento não coberto", "risco": "ALTO"}),
        )

        context.variables = base_vars(
            payerId="SULAMERICA",
            authorizationType="exame",
            enrichedProcedures=[{"code": "40101010", "display": "", "category": "exame", "quantity": 1, "authorization_status": "pending"}],
        )

        result = worker.execute(context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "AUTH_DENIED"
        assert "40101010" in result.variables["deniedCodes"]

    def test_sem_procedimentos(self, context):
        """Procedimentos vazios no caminho DMN → CODING_ERROR (1 chamada DMN apenas)."""
        worker = make_worker()
        worker.evaluate_dmn.side_effect = [
            {"authorization_channel": "dmn", "rpa_type": ""},
        ]

        context.variables = base_vars(payerId="HAPVIDA", enrichedProcedures=[])

        result = worker.execute(context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "CODING_ERROR"
        assert worker.evaluate_dmn.call_count == 1

    def test_evaluate_dmn_chamado_correto_numero_de_vezes(self, context, procedures):
        """1 (canal) + 2 procedimentos × 2 (complexity + adjudication) = 5 chamadas."""
        worker = make_worker()
        worker.evaluate_dmn.return_value = {
            "authorization_channel": "dmn",
            "rpa_type": "",
            "resultado": "PROSSEGUIR",
            "acao": "OK",
            "risco": "BAIXO",
            "requires_auth": False,
            "auth_level": "none",
        }

        context.variables = base_vars(payerId="AMIL", enrichedProcedures=procedures)

        worker.execute(context)

        assert worker.evaluate_dmn.call_count == 5
