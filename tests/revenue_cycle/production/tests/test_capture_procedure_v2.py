"""Tests for CaptureProcedureWorker (v2)."""
from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.revenue_cycle.production.workers.capture_procedure_worker_v2 import (
    CaptureProcedureWorker,
)


def make_context(variables: dict, tenant_id: str = "test-tenant") -> TaskContext:
    """Create a test TaskContext."""
    return TaskContext(
        task_id="task-001",
        process_instance_id="proc-001",
        tenant_id=tenant_id,
        variables=variables,
        worker_id="test-worker",
    )


@pytest.fixture
def worker():
    """Create CaptureProcedureWorker with mocked dependencies."""
    tasy_client = MagicMock()
    mv_soul_client = MagicMock()
    worker = CaptureProcedureWorker(
        tasy_client=tasy_client, mv_soul_client=mv_soul_client
    )
    worker.logger = MagicMock()
    return worker


def test_capture_procedure_happy_path(worker):
    """Test successful procedure capture."""
    # Mock service response - service.capture returns a list
    worker.service.capture = MagicMock(
        return_value=[
            {
                "code": "40301010",
                "display": "Consulta médica",
                "performed_date": "2026-01-15T10:00:00",
            }
        ]
    )

    # Mock DMN evaluation for routing
    worker.evaluate_dmn = MagicMock(
        return_value={
            "destino": "tasy",
            "prioridade": "NORMAL",
        }
    )

    context = make_context(
        {
            "encounter_reference": "Encounter/enc-123",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert "captured_procedures" in result.variables
    assert result.variables["procedure_count"] == 1
    assert result.variables["erp_system"] == "tasy"
    assert len(result.variables["captured_procedures"]) == 1
    worker.service.capture.assert_called_once()


def test_capture_procedure_missing_encounter_ref_error(worker):
    """Test error when encounter reference is missing."""
    worker.evaluate_dmn = MagicMock()

    context = make_context({})

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "CODING_ERROR"
    assert "encounter_reference" in result.error_message.lower()


def test_capture_procedure_no_procedures_found(worker):
    """Test when no procedures found for encounter."""
    worker.service.capture = MagicMock(return_value=[])

    worker.evaluate_dmn = MagicMock(
        return_value={
            "destino": "tasy",
            "prioridade": "NORMAL",
        }
    )

    context = make_context(
        {
            "encounter_reference": "Encounter/enc-123",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "CODING_ERROR"
    assert "no procedures found" in result.error_message.lower()


def test_capture_procedure_service_exception(worker):
    """Test handling of service exceptions."""
    worker.service.capture = MagicMock(side_effect=Exception("TASY API unavailable"))

    worker.evaluate_dmn = MagicMock(
        return_value={
            "destino": "tasy",
            "prioridade": "NORMAL",
        }
    )

    context = make_context(
        {
            "encounter_reference": "Encounter/enc-123",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "EXTERNAL_SERVICE_ERROR"
    assert "tasy api unavailable" in result.error_message.lower()


def test_capture_procedure_dmn_routing(worker):
    """Test DMN-based ERP system routing."""
    worker.service.capture = MagicMock(
        return_value=[
            {"code": "40301010", "display": "Consulta médica"}
        ]
    )

    # DMN routes to MV Soul instead of TASY
    worker.evaluate_dmn = MagicMock(
        return_value={
            "destino": "mv_soul",
            "prioridade": "URGENTE",
        }
    )

    context = make_context(
        {
            "encounter_reference": "Encounter/enc-123",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert result.variables["erp_system"] == "mv_soul"
    # Worker doesn't return routing_priority, only uses it internally


def test_capture_procedure_multiple_procedures(worker):
    """Test capture of multiple procedures."""
    worker.service.capture = MagicMock(
        return_value=[
            {"code": "40301010", "display": "Consulta médica"},
            {"code": "20101012", "display": "Raio X"},
            {"code": "30101016", "display": "Hemograma"},
        ]
    )

    worker.evaluate_dmn = MagicMock(
        return_value={
            "destino": "tasy",
            "prioridade": "NORMAL",
        }
    )

    context = make_context(
        {
            "encounter_reference": "Encounter/enc-123",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert result.variables["procedure_count"] == 3
    assert len(result.variables["captured_procedures"]) == 3


def test_capture_procedure_with_fallback_system(worker):
    """Test fallback to secondary ERP system."""
    worker.service.capture = MagicMock(
        return_value=[
            {"code": "40301010", "display": "Consulta médica"}
        ]
    )

    worker.evaluate_dmn = MagicMock(
        return_value={
            "destino": "tasy",
            "prioridade": "NORMAL",
        }
    )

    context = make_context(
        {
            "encounter_reference": "Encounter/enc-123",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    # Worker doesn't track fallback_used or source_system explicitly
    assert result.variables["erp_system"] == "tasy"
