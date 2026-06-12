"""Tests for PersistProductionWorker v2 (ARCHETYPE: ADMIN_ADJUDICATION)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskStatus
from healthcare_platform.revenue_cycle.production.workers.persist_production_worker_v2 import (
    PersistProductionWorker,
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
        worker_id="production.persist_production",
    )


@pytest.fixture
def worker(mock_dmn):
    return PersistProductionWorker(
        fhir_client=MagicMock(),
        dmn_service=mock_dmn,
        metrics=MagicMock(),
    )


def test_happy_path_prosseguir(worker, context, mock_dmn):
    """Persistence succeeds with valid data."""
    mock_dmn.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "Ready to persist",
        "risco": "BAIXO",
    }
    context.variables = {
        "breakdown": [
            {"code": "40101010", "quantity": 1, "unit_price": "150.00", "total_price": "150.00"},
        ],
        "encounter": "Encounter/123",
        "patientReference": "Patient/456",
        "value": "150.00",
        "diagnosis_codes": ["J18.9"],
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert "claim_reference" in result.variables
    assert "production_id" in result.variables
    assert "persisted_at" in result.variables
    assert "productionId" in result.variables


def test_bloquear_blocks_persistence(worker, context, mock_dmn):
    """DMN BLOQUEAR prevents persistence."""
    mock_dmn.evaluate.return_value = {
        "resultado": "BLOQUEAR",
        "acao": "No procedures to persist",
        "risco": "ALTO",
    }
    context.variables = {
        "breakdown": [],
        "value": "0.00",
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "BILLING_ERROR"


def test_revisar_flags_review(worker, context, mock_dmn):
    """DMN REVISAR succeeds but flags for review."""
    mock_dmn.evaluate.return_value = {
        "resultado": "REVISAR",
        "acao": "Verify total amount",
        "risco": "MEDIO",
    }
    context.variables = {
        "breakdown": [
            {"code": "40101010", "quantity": 1, "unit_price": "150.00", "total_price": "150.00"},
        ],
        "encounter": "Encounter/123",
        "patientReference": "Patient/456",
        "value": "150.00",
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert result.variables["requiresReview"] is True


def test_empty_procedures_via_dmn(worker, context, mock_dmn):
    """Empty procedures are caught by DMN validation."""
    mock_dmn.evaluate.return_value = {
        "resultado": "BLOQUEAR",
        "acao": "Empty procedure list",
    }
    context.variables = {"breakdown": [], "value": "0.00"}

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR


def test_dmn_evaluator_failure(worker, context, mock_dmn):
    """DMN service exception is caught."""
    mock_dmn.evaluate.side_effect = RuntimeError("DMN evaluation failed")
    context.variables = {
        "breakdown": [{"code": "40101010"}],
        "value": "100.00",
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "EXTERNAL_SERVICE_ERROR"


def test_charge_items_created_for_procedures(worker, context, mock_dmn):
    """ChargeItem references created for each procedure."""
    mock_dmn.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "OK",
        "risco": "BAIXO",
    }
    context.variables = {
        "breakdown": [
            {"code": "40101010", "quantity": 1, "unit_price": "100.00", "total_price": "100.00"},
            {"code": "40201010", "quantity": 2, "unit_price": "50.00", "total_price": "100.00"},
        ],
        "encounter": "Encounter/123",
        "patientReference": "Patient/456",
        "value": "200.00",
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert len(result.variables["charge_item_references"]) == 2
