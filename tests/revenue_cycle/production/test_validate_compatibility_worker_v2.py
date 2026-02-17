"""Tests for ValidateCompatibilityWorker v2 (ARCHETYPE: ADMIN_ADJUDICATION)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskStatus
from healthcare_platform.revenue_cycle.production.workers.validate_compatibility_worker_v2 import (
    ValidateCompatibilityWorker,
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
        worker_id="production.validate_compatibility",
    )


@pytest.fixture
def worker(mock_dmn):
    return ValidateCompatibilityWorker(dmn_service=mock_dmn, metrics=MagicMock())


def test_happy_path_prosseguir(worker, context, mock_dmn):
    """All procedures compatible."""
    mock_dmn.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "All compatible",
        "risco": "BAIXO",
    }
    context.variables = {
        "priced_procedures": [
            {"code": "40101010"},
            {"code": "40301010"},
        ],
        "patient_gender": "male",
        "patient_age_years": 35,
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert result.variables["all_compatible"] is True


def test_bloquear_incompatible_codes(worker, context, mock_dmn):
    """DMN detects incompatible procedure pair."""
    mock_dmn.evaluate.return_value = {
        "resultado": "BLOQUEAR",
        "acao": "Procedures 40101010 and 40101028 are mutually exclusive",
        "risco": "ALTO",
    }
    context.variables = {
        "priced_procedures": [
            {"code": "40101010"},
            {"code": "40101028"},
        ],
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "INCOMPATIBLE_CODES"


def test_revisar_adds_warning(worker, context, mock_dmn):
    """DMN REVISAR adds warning but passes."""
    mock_dmn.evaluate.return_value = {
        "resultado": "REVISAR",
        "acao": "Gender restriction may apply",
        "risco": "MEDIO",
    }
    context.variables = {
        "priced_procedures": [{"code": "40601013"}],
        "patient_gender": "female",
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert len(result.variables["compatibility_warnings"]) > 0


def test_empty_procedures_error(worker, context):
    """No procedures triggers CODING_ERROR."""
    context.variables = {"priced_procedures": []}

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "CODING_ERROR"


def test_dmn_evaluator_failure(worker, context, mock_dmn):
    """DMN service exception is caught."""
    mock_dmn.evaluate.side_effect = RuntimeError("DMN evaluation failed")
    context.variables = {
        "priced_procedures": [{"code": "40101010"}],
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR


def test_duplicate_code_warning(worker, context, mock_dmn):
    """Duplicate codes generate a warning."""
    mock_dmn.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "OK",
        "risco": "BAIXO",
    }
    context.variables = {
        "priced_procedures": [
            {"code": "40101010"},
            {"code": "40101010"},
        ],
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert any("40101010" in w and "2 times" in w for w in result.variables["compatibility_warnings"])


def test_no_gender_or_age(worker, context, mock_dmn):
    """Works without patient gender or age."""
    mock_dmn.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "OK",
        "risco": "BAIXO",
    }
    context.variables = {
        "priced_procedures": [{"code": "40101010"}],
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
