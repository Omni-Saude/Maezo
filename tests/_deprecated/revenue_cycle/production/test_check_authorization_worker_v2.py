"""Tests for CheckAuthorizationWorker v2 (ARCHETYPE: ADMIN_ADJUDICATION).

Fluxo DMN por procedimento (2 chamadas encadeadas):
  1. auth_complexity_001 → requires_auth, auth_level, review_type
     Input:  procedure_code (string), procedure_category (string)
  2. authorization_status_adjudication → resultado, acao, risco
     Input:  authorization_status (string), authorization_number (string), requires_auth (boolean)

Variáveis BPMN de entrada (camelCase — convenção BPMN/CIB Seven):
  enrichedProcedures: list[{code, category, authorization_status, ...}]
  existingAuthNumber: str

Variáveis BPMN de saída (camelCase):
  authorizationResults, allAuthorized, authNumber
  authorizationResults, deniedCodes  (em caso de AUTH_DENIED)
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskStatus
from healthcare_platform.revenue_cycle.production.workers.check_authorization_worker_v2 import (
    CheckAuthorizationWorker,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_dmn():
    return MagicMock()


@pytest.fixture
def worker(mock_dmn):
    return CheckAuthorizationWorker(dmn_service=mock_dmn, metrics=MagicMock())


def make_context(procedures=None, existing_auth="AUTH001") -> TaskContext:
    if procedures is None:
        procedures = [{"code": "40101010", "category": "cardiovascular_surgery", "authorization_status": "approved"}]
    return TaskContext(
        task_id="task_1",
        process_instance_id="proc_1",
        tenant_id="HOSPITAL_A",
        variables={
            "enrichedProcedures": procedures,
            "existingAuthNumber": existing_auth,
        },
        worker_id="revenue_cycle.production.check_authorization",
    )


def make_dmn_responses(complexity=None, adjudication=None):
    """Cria side_effect para 2 chamadas DMN sequenciais."""
    complexity = complexity or {"requires_auth": True, "auth_level": "high", "review_type": "clinical_review"}
    adjudication = adjudication or {"resultado": "PROSSEGUIR", "acao": "Autorizado", "risco": "BAIXO"}
    responses = iter([complexity, adjudication])

    def side_effect(**kwargs):
        return next(responses)

    return side_effect


# ── Contrato de variáveis DMN ─────────────────────────────────────────────────

def test_primeira_chamada_dmn_recebe_procedure_code_e_procedure_category(worker, mock_dmn):
    """1ª chamada (auth_complexity_001) deve receber procedure_code e procedure_category."""
    mock_dmn.evaluate.side_effect = make_dmn_responses()
    worker.execute(make_context())

    first_call = mock_dmn.evaluate.call_args_list[0]
    inputs = first_call.kwargs.get("inputs", first_call[1].get("inputs", {}))
    assert "procedure_code" in inputs, "auth_complexity_001 deve receber 'procedure_code'"
    assert "procedure_category" in inputs, "auth_complexity_001 deve receber 'procedure_category'"
    assert inputs["procedure_code"] == "40101010"
    assert inputs["procedure_category"] == "cardiovascular_surgery"


def test_segunda_chamada_dmn_recebe_variaveis_de_adjudicacao(worker, mock_dmn):
    """2ª chamada (authorization_status_adjudication) deve receber authorization_status, authorization_number, requires_auth."""
    mock_dmn.evaluate.side_effect = make_dmn_responses()
    worker.execute(make_context())

    second_call = mock_dmn.evaluate.call_args_list[1]
    inputs = second_call.kwargs.get("inputs", second_call[1].get("inputs", {}))
    assert "authorization_status" in inputs, "adjudication deve receber 'authorization_status'"
    assert "authorization_number" in inputs, "adjudication deve receber 'authorization_number'"
    assert "requires_auth" in inputs, "adjudication deve receber 'requires_auth'"


def test_segunda_chamada_nao_recebe_procedure_code(worker, mock_dmn):
    """2ª chamada não deve receber variáveis de lookup de procedimento."""
    mock_dmn.evaluate.side_effect = make_dmn_responses()
    worker.execute(make_context())

    second_call = mock_dmn.evaluate.call_args_list[1]
    inputs = second_call.kwargs.get("inputs", second_call[1].get("inputs", {}))
    assert "procedure_code" not in inputs
    assert "payer_id" not in inputs


def test_dmn_chamado_duas_vezes_por_procedimento(worker, mock_dmn):
    """Deve haver exatamente 2 chamadas DMN por procedimento."""
    mock_dmn.evaluate.side_effect = make_dmn_responses()
    worker.execute(make_context())

    assert mock_dmn.evaluate.call_count == 2


def test_dois_procedimentos_fazem_quatro_chamadas_dmn(worker, mock_dmn):
    """2 procedimentos = 4 chamadas DMN (2 por procedimento)."""
    complexity = {"requires_auth": True, "auth_level": "high", "review_type": "clinical_review"}
    adjudication = {"resultado": "PROSSEGUIR", "acao": "OK", "risco": "BAIXO"}
    mock_dmn.evaluate.side_effect = iter([complexity, adjudication, complexity, adjudication])

    worker.execute(make_context(procedures=[
        {"code": "40101010", "category": "cardiovascular", "authorization_status": "approved"},
        {"code": "40202020", "category": "oncology", "authorization_status": "approved"},
    ]))

    assert mock_dmn.evaluate.call_count == 4


# ── Happy paths ───────────────────────────────────────────────────────────────

def test_happy_path_prosseguir(worker, mock_dmn):
    """Todos os procedimentos autorizados → SUCCESS."""
    mock_dmn.evaluate.side_effect = make_dmn_responses()
    result = worker.execute(make_context())

    assert result.status == TaskStatus.SUCCESS
    assert result.variables["allAuthorized"] is True
    assert len(result.variables["authorizationResults"]) == 1


def test_resultado_contem_auth_level_e_requires_auth(worker, mock_dmn):
    """Resultado por procedimento deve incluir auth_level e requires_auth do complexity DMN."""
    mock_dmn.evaluate.side_effect = make_dmn_responses(
        complexity={"requires_auth": True, "auth_level": "high", "review_type": "clinical_review"},
    )
    result = worker.execute(make_context())

    proc_result = result.variables["authorizationResults"][0]
    assert proc_result["auth_level"] == "high"
    assert proc_result["requires_auth"] is True


# ── BLOQUEAR / REVISAR ────────────────────────────────────────────────────────

def test_bloquear_gera_auth_denied(worker, mock_dmn):
    """DMN retorna BLOQUEAR → AUTH_DENIED."""
    mock_dmn.evaluate.side_effect = make_dmn_responses(
        adjudication={"resultado": "BLOQUEAR", "acao": "Não coberto", "risco": "CRITICO"},
    )
    result = worker.execute(make_context())

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "AUTH_DENIED"
    assert "deniedCodes" in result.variables


def test_revisar_gera_auth_denied(worker, mock_dmn):
    """DMN retorna REVISAR → AUTH_DENIED (não totalmente autorizado)."""
    mock_dmn.evaluate.side_effect = make_dmn_responses(
        adjudication={"resultado": "REVISAR", "acao": "Revisão manual", "risco": "MEDIO"},
    )
    result = worker.execute(make_context())

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "AUTH_DENIED"


# ── Validação de input ────────────────────────────────────────────────────────

def test_sem_procedures_retorna_coding_error(worker, mock_dmn):
    """Lista vazia de procedures → CODING_ERROR sem chamar DMN."""
    result = worker.execute(make_context(procedures=[]))

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "CODING_ERROR"
    mock_dmn.evaluate.assert_not_called()


# ── Resiliência ───────────────────────────────────────────────────────────────

def test_dmn_falha_retorna_auth_not_found(worker, mock_dmn):
    """Falha na chamada DMN → AUTH_NOT_FOUND."""
    mock_dmn.evaluate.side_effect = RuntimeError("DMN indisponível")

    result = worker.execute(make_context())

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "AUTH_NOT_FOUND"


def test_multiplos_procedimentos_mixed(worker, mock_dmn):
    """1º procedimento PROSSEGUIR, 2º BLOQUEAR → AUTH_DENIED com denied_codes correto."""
    complexity = {"requires_auth": True, "auth_level": "high", "review_type": "clinical_review"}
    mock_dmn.evaluate.side_effect = iter([
        complexity, {"resultado": "PROSSEGUIR", "acao": "OK", "risco": "BAIXO"},
        complexity, {"resultado": "BLOQUEAR", "acao": "Negado", "risco": "CRITICO"},
    ])

    result = worker.execute(make_context(procedures=[
        {"code": "40101010", "category": "cardiovascular", "authorization_status": "approved"},
        {"code": "99999999", "category": "experimental", "authorization_status": "denied"},
    ]))

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "AUTH_DENIED"
    assert "99999999" in result.variables["deniedCodes"]
