"""Tests for ValidateProcedureWorker v2 (ARCHETYPE: ADMIN_ADJUDICATION)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskStatus
from healthcare_platform.revenue_cycle.production.workers.validate_procedure_worker_v2 import (
    ValidateProcedureWorker,
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
        worker_id="production.validate_procedure",
    )


@pytest.fixture
def worker(mock_dmn):
    return ValidateProcedureWorker(dmn_service=mock_dmn, metrics=MagicMock())


def test_happy_path_prosseguir(worker, context, mock_dmn):
    """All procedure codes are valid."""
    mock_dmn.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "Codigo valido",
        "risco": "BAIXO",
        "coverageType": "ambulatorial",
        "procedureName": "Consulta medica",
    }
    context.variables = {
        "procedure_codes": ["40101010", "40201010"],
        "coverage_type": "ambulatorial",
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert result.variables["all_valid"] is True
    assert len(result.variables["validated_procedures"]) == 2


def test_bloquear_invalid_code(worker, context, mock_dmn):
    """DMN BLOQUEAR for invalid procedure code."""
    mock_dmn.evaluate.return_value = {
        "resultado": "BLOQUEAR",
        "acao": "Codigo nao encontrado na tabela TUSS",
        "risco": "ALTO",
    }
    context.variables = {
        "procedure_codes": ["99999999"],
        "coverage_type": "ambulatorial",
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "INVALID_PROCEDURE_CODE"
    assert "99999999" in result.variables["invalid_codes"]


def test_mixed_valid_and_invalid(worker, context, mock_dmn):
    """First code valid, second invalid."""
    call_count = [0]

    def side_effect(**kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return {"resultado": "PROSSEGUIR", "acao": "OK", "risco": "BAIXO"}
        return {"resultado": "BLOQUEAR", "acao": "Invalid", "risco": "ALTO"}

    mock_dmn.evaluate.side_effect = side_effect
    context.variables = {
        "procedure_codes": ["40101010", "99999999"],
        "coverage_type": "ambulatorial",
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert "99999999" in result.variables["invalid_codes"]


def test_empty_codes_error(worker, context):
    """Empty procedure_codes triggers CODING_ERROR."""
    context.variables = {"procedure_codes": []}

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "CODING_ERROR"


def test_dmn_evaluator_failure(worker, context, mock_dmn):
    """DMN service exception is caught."""
    mock_dmn.evaluate.side_effect = RuntimeError("DMN evaluation failed")
    context.variables = {
        "procedure_codes": ["40101010"],
        "coverage_type": "ambulatorial",
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "CODING_ERROR"


def test_no_coverage_type(worker, context, mock_dmn):
    """Works without coverage_type."""
    mock_dmn.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "OK",
        "risco": "BAIXO",
        "coverageType": "",
        "procedureName": "Test",
    }
    context.variables = {"procedure_codes": ["40101010"]}

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert result.variables["all_valid"] is True
