"""Tests for CaptureProcedureWorker v2 (ARCHETYPE: OPERATIONAL_ROUTING)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskStatus
from healthcare_platform.revenue_cycle.production.workers.capture_procedure_worker_v2 import (
    CaptureProcedureWorker,
)


@pytest.fixture
def mock_dmn():
    return MagicMock()


@pytest.fixture
def mock_tasy():
    mock = MagicMock()
    proc = MagicMock()
    proc.procedure_id = "P1"
    proc.encounter_id = "E1"
    proc.patient_id = "PAT1"
    proc.code = "40101010"
    proc.display = "Consulta"
    proc.status = "completed"
    proc.performed_date = None
    mock.get_procedures.return_value = [proc]
    return mock


@pytest.fixture
def mock_mv():
    mock = MagicMock()
    item = MagicMock()
    item.item_id = "I1"
    item.encounter_id = "E1"
    item.item_code = "40201010"
    item.item_description = "Consulta especializada"
    item.status = "completed"
    item.service_date = "2026-01-01"
    mock.get_billing_items.return_value = [item]
    return mock


@pytest.fixture
def context():
    return TaskContext(
        task_id="task_1",
        process_instance_id="proc_1",
        tenant_id="HOSPITAL_A",
        variables={},
        worker_id="production.capture_procedure",
    )


@pytest.fixture
def worker(mock_dmn, mock_tasy, mock_mv):
    return CaptureProcedureWorker(
        tasy_client=mock_tasy,
        mv_soul_client=mock_mv,
        dmn_service=mock_dmn,
        metrics=MagicMock(),
    )


def test_happy_path_tasy_routing(worker, context, mock_dmn):
    """DMN routes to TASY and procedures are captured."""
    mock_dmn.evaluate.return_value = {
        "destino": "tasy",
        "prioridade": "NORMAL",
        "restricao": "",
    }
    context.variables = {"encounter_reference": "Encounter/123"}

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert result.variables["erp_system"] == "tasy"
    assert result.variables["procedure_count"] == 1


def test_mv_soul_routing(worker, context, mock_dmn):
    """DMN routes to MV Soul."""
    mock_dmn.evaluate.return_value = {
        "destino": "mv_soul",
        "prioridade": "NORMAL",
        "restricao": "",
    }
    context.variables = {"encounter_reference": "Encounter/456"}

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert result.variables["erp_system"] == "mv_soul"


def test_missing_encounter_reference(worker, context):
    """Missing encounter_reference triggers CODING_ERROR."""
    context.variables = {}

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "CODING_ERROR"


def test_no_procedures_found(worker, context, mock_dmn, mock_tasy):
    """Empty result from ERP triggers error."""
    mock_dmn.evaluate.return_value = {"destino": "tasy", "prioridade": "NORMAL"}
    mock_tasy.get_procedures.return_value = []
    context.variables = {"encounter_reference": "Encounter/999"}

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "CODING_ERROR"


def test_dmn_evaluator_failure(worker, context, mock_dmn):
    """DMN service exception is caught."""
    mock_dmn.evaluate.side_effect = RuntimeError("DMN failed")
    context.variables = {"encounter_reference": "Encounter/123"}

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "EXTERNAL_SERVICE_ERROR"


def test_erp_client_exception(worker, context, mock_dmn, mock_tasy):
    """ERP client exception is caught."""
    mock_dmn.evaluate.return_value = {"destino": "tasy", "prioridade": "NORMAL"}
    mock_tasy.get_procedures.side_effect = ConnectionError("ERP down")
    context.variables = {"encounter_reference": "Encounter/123"}

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "EXTERNAL_SERVICE_ERROR"
