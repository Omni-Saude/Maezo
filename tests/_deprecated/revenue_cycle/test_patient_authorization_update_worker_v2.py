"""Tests for PatientAuthorizationUpdateWorker v2 (ARCHETYPE: OPERATIONAL_ROUTING).

DMN contrato validado:
  Input:  authorization_status (string)   ← snake_case (worker → DMN)
  Output: destino (string), prioridade (number), restricao (string)

Variáveis BPMN de entrada (camelCase — convenção BPMN/CIB Seven):
  patientId, phoneNumber, authorizationId, procedureName, authorizationStatus

Variáveis BPMN de saída (camelCase):
  notificationSent, messageId, sentAt, destino, prioridade, nextSteps
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskStatus
from healthcare_platform.revenue_cycle.production.workers.patient_authorization_update_worker_v2 import (
    PatientAuthorizationUpdateWorker,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_dmn():
    mock = MagicMock()
    mock.evaluate.return_value = {
        "destino": "whatsapp",
        "prioridade": 3,
        "restricao": "Agende sua consulta",
    }
    return mock


@pytest.fixture
def mock_whatsapp():
    mock = MagicMock()
    mock.send_template.return_value = "msg_001"
    return mock


@pytest.fixture
def worker(mock_dmn, mock_whatsapp):
    return PatientAuthorizationUpdateWorker(
        whatsapp_client=mock_whatsapp,
        dmn_service=mock_dmn,
        metrics=MagicMock(),
    )


def make_context(status: str = "approved", **overrides) -> TaskContext:
    variables = {
        "patientId": "pat_001",
        "phoneNumber": "+5511999990000",
        "authorizationId": "auth_001",
        "procedureName": "Ressonância Magnética",
        "authorizationStatus": status,
        **overrides,
    }
    return TaskContext(
        task_id="task_001",
        process_instance_id="proc_001",
        tenant_id="HOSPITAL_A",
        variables=variables,
        worker_id="financial.auth_update",
    )


# ── Testes de contrato DMN ───────────────────────────────────────────────────

def test_dmn_recebe_authorization_status_correto(worker, mock_dmn):
    """Worker deve enviar 'authorization_status' ao DMN (não 'status')."""
    context = make_context(status="approved")
    worker.execute(context)

    call_kwargs = mock_dmn.evaluate.call_args
    inputs = call_kwargs.kwargs.get("inputs", call_kwargs[1].get("inputs", {}))
    assert "authorization_status" in inputs, "DMN deve receber variável 'authorization_status'"
    assert inputs["authorization_status"] == "approved"
    assert "status" not in inputs, "DMN não deve receber 'status' (nome errado)"


def test_dmn_nao_recebe_variaveis_irrelevantes(worker, mock_dmn):
    """Worker não deve vazar patient_id, phone_number etc. para o DMN."""
    context = make_context(status="pending")
    worker.execute(context)

    inputs = mock_dmn.evaluate.call_args.kwargs.get(
        "inputs", mock_dmn.evaluate.call_args[1].get("inputs", {})
    )
    assert "patient_id" not in inputs
    assert "phone_number" not in inputs
    assert "procedure_name" not in inputs


# ── Happy paths ──────────────────────────────────────────────────────────────

def test_approved_envia_notificacao(worker, mock_whatsapp):
    """Status approved: notificação enviada com sucesso."""
    result = worker.execute(make_context(status="approved"))

    assert result.status == TaskStatus.SUCCESS
    assert result.variables["notificationSent"] is True
    assert result.variables["messageId"] == "msg_001"
    mock_whatsapp.send_template.assert_called_once()


def test_denied_alta_prioridade(worker, mock_dmn):
    """Status denied: DMN deve retornar prioridade 1."""
    mock_dmn.evaluate.return_value = {
        "destino": "whatsapp",
        "prioridade": 1,
        "restricao": "Ligue 0800 para recurso",
    }
    result = worker.execute(make_context(status="denied"))

    assert result.status == TaskStatus.SUCCESS
    assert result.variables["prioridade"] == 1
    assert result.variables["nextSteps"] == "Ligue 0800 para recurso"


def test_pending_prioridade_media(worker, mock_dmn):
    """Status pending: prioridade 2 do DMN."""
    mock_dmn.evaluate.return_value = {
        "destino": "whatsapp",
        "prioridade": 2,
        "restricao": "Aguarde 5 dias uteis",
    }
    result = worker.execute(make_context(status="pending"))

    assert result.status == TaskStatus.SUCCESS
    assert result.variables["prioridade"] == 2


def test_cancelled_status_via_dmn(worker, mock_dmn):
    """Status cancelled: tratado via regra de fallback do DMN."""
    mock_dmn.evaluate.return_value = {
        "destino": "whatsapp",
        "prioridade": 1,
        "restricao": "Autorizacao cancelada",
    }
    result = worker.execute(make_context(status="cancelled"))

    assert result.status == TaskStatus.SUCCESS
    assert result.variables["notificationSent"] is True


# ── Validação de input ───────────────────────────────────────────────────────

def test_sem_patient_id_retorna_bpmn_error(worker):
    """Falta patientId → ERR_INVALID_INPUT."""
    context = make_context()
    context.variables.pop("patientId")

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "ERR_INVALID_INPUT"


def test_sem_phone_number_retorna_bpmn_error(worker):
    """Falta phoneNumber → ERR_INVALID_INPUT."""
    context = make_context()
    context.variables.pop("phoneNumber")

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "ERR_INVALID_INPUT"


def test_sem_status_retorna_bpmn_error(worker):
    """Falta authorizationStatus → ERR_INVALID_INPUT."""
    context = make_context()
    context.variables.pop("authorizationStatus")

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "ERR_INVALID_INPUT"


# ── Resiliência ──────────────────────────────────────────────────────────────

def test_dmn_falha_retorna_bpmn_error(worker, mock_dmn):
    """Falha no DMN capturada e retornada como BPMN error."""
    mock_dmn.evaluate.side_effect = RuntimeError("DMN indisponível")

    result = worker.execute(make_context(status="approved"))

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "ERR_AUTH_UPDATE_NOTIFICATION"


def test_sem_whatsapp_client_nao_quebra(mock_dmn):
    """Worker sem whatsapp_client não deve quebrar — message_id será None."""
    worker = PatientAuthorizationUpdateWorker(
        whatsapp_client=None,
        dmn_service=mock_dmn,
        metrics=MagicMock(),
    )
    result = worker.execute(make_context(status="approved"))

    assert result.status == TaskStatus.SUCCESS
    assert result.variables["notificationSent"] is True
    assert result.variables["messageId"] is None


def test_output_contem_campos_esperados(worker):
    """Resultado de sucesso deve conter todos os campos obrigatórios."""
    result = worker.execute(make_context(status="approved"))

    assert result.status == TaskStatus.SUCCESS
    for campo in ("notificationSent", "messageId", "sentAt", "destino", "prioridade", "nextSteps"):
        assert campo in result.variables, f"Campo ausente no resultado: {campo}"
