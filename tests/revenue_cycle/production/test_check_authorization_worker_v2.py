"""Tests for CheckAuthorizationWorker v2 (ARCHETYPE: ADMIN_ADJUDICATION)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskStatus
from healthcare_platform.revenue_cycle.production.workers.check_authorization_worker_v2 import (
    CheckAuthorizationWorker,
)


@pytest.fixture
def mock_dmn():
    return MagicMock()


@pytest.fixture
def context():
    return TaskContext(
        task_id="task_1",
        process_instance_id="proc_1",
        tenant_id="HOSPITAL_A",
        variables={},
        worker_id="production.check_authorization",
    )


@pytest.fixture
def worker(mock_dmn):
    return CheckAuthorizationWorker(dmn_service=mock_dmn, metrics=MagicMock())


def test_happy_path_prosseguir(worker, context, mock_dmn):
    """All procedures authorized (PROSSEGUIR)."""
    mock_dmn.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "Autorizado",
        "risco": "BAIXO",
    }
    context.variables = {
        "enriched_procedures": [{"code": "40101010", "quantity": 1}],
        "patient_reference": "Patient/123",
        "payer_id": "UNIMED",
        "existing_auth_number": "AUTH001",
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert result.variables["all_authorized"] is True


def test_bloquear_denied(worker, context, mock_dmn):
    """DMN returns BLOQUEAR triggers AUTH_DENIED."""
    mock_dmn.evaluate.return_value = {
        "resultado": "BLOQUEAR",
        "acao": "Procedimento nao coberto",
        "risco": "ALTO",
    }
    context.variables = {
        "enriched_procedures": [{"code": "99999999", "quantity": 1}],
        "payer_id": "UNIMED",
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "AUTH_DENIED"


def test_revisar_requires_review(worker, context, mock_dmn):
    """DMN returns REVISAR triggers AUTH_DENIED (not all authorized)."""
    mock_dmn.evaluate.return_value = {
        "resultado": "REVISAR",
        "acao": "Requires manual review",
        "risco": "MEDIO",
    }
    context.variables = {
        "enriched_procedures": [{"code": "40101010", "quantity": 1}],
        "payer_id": "BRADESCO",
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "AUTH_DENIED"


def test_empty_procedures_error(worker, context):
    """No procedures triggers error."""
    context.variables = {"enriched_procedures": []}

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR


def test_dmn_evaluator_failure(worker, context, mock_dmn):
    """DMN service exception is caught."""
    mock_dmn.evaluate.side_effect = RuntimeError("DMN evaluation failed")
    context.variables = {
        "enriched_procedures": [{"code": "40101010", "quantity": 1}],
        "payer_id": "UNIMED",
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "AUTH_NOT_FOUND"


def test_multiple_procedures_mixed(worker, context, mock_dmn):
    """First procedure passes, second blocks."""
    call_count = [0]

    def side_effect(**kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return {"resultado": "PROSSEGUIR", "acao": "OK", "risco": "BAIXO"}
        return {"resultado": "BLOQUEAR", "acao": "Denied", "risco": "ALTO"}

    mock_dmn.evaluate.side_effect = side_effect
    context.variables = {
        "enriched_procedures": [
            {"code": "40101010", "quantity": 1},
            {"code": "99999999", "quantity": 1},
        ],
        "payer_id": "UNIMED",
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "AUTH_DENIED"
