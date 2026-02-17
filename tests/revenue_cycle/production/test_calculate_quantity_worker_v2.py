"""Tests for CalculateQuantityWorker v2 (ARCHETYPE: ADMIN_ADJUDICATION)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskStatus
from healthcare_platform.revenue_cycle.production.workers.calculate_quantity_worker_v2 import (
    CalculateQuantityWorker,
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
        worker_id="production.calculate_quantity",
    )


@pytest.fixture
def worker(mock_dmn):
    return CalculateQuantityWorker(dmn_service=mock_dmn, metrics=MagicMock())


def test_happy_path_prosseguir(worker, context, mock_dmn):
    """DMN returns PROSSEGUIR with calculated quantity."""
    mock_dmn.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "quantity": 4,
        "quantityMethod": "duration",
        "quantityCapped": False,
    }
    context.variables = {
        "enriched_procedures": [{"code": "20101012", "quantity": 1}],
        "encounter_start": "2026-01-01T08:00:00",
        "encounter_end": "2026-01-01T09:00:00",
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert result.variables["quantified_procedures"][0]["quantity"] == 4
    assert result.variables["total_items"] == 4


def test_bloquear_returns_error(worker, context, mock_dmn):
    """DMN returns BLOQUEAR blocks quantity calculation."""
    mock_dmn.evaluate.return_value = {
        "resultado": "BLOQUEAR",
        "acao": "Quantity exceeds maximum allowed",
    }
    context.variables = {
        "enriched_procedures": [{"code": "40101010", "quantity": 100}],
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "CODING_ERROR"


def test_capped_quantity(worker, context, mock_dmn):
    """DMN returns capped quantity."""
    mock_dmn.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "quantity": 48,
        "quantityMethod": "duration",
        "quantityCapped": True,
    }
    context.variables = {
        "enriched_procedures": [{"code": "20101012", "quantity": 1}],
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert result.variables["quantified_procedures"][0]["quantity_capped"] is True


def test_empty_procedures_error(worker, context):
    """No procedures triggers error."""
    context.variables = {"enriched_procedures": []}

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "CODING_ERROR"


def test_dmn_evaluator_failure(worker, context, mock_dmn):
    """DMN service exception is caught."""
    mock_dmn.evaluate.side_effect = RuntimeError("DMN evaluation failed")
    context.variables = {
        "enriched_procedures": [{"code": "40101010", "quantity": 1}],
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR


def test_no_encounter_times(worker, context, mock_dmn):
    """Works without encounter start/end times."""
    mock_dmn.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "quantity": 1,
        "quantityMethod": "direct",
        "quantityCapped": False,
    }
    context.variables = {
        "enriched_procedures": [{"code": "40101010", "quantity": 1}],
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert result.variables["quantified_procedures"][0]["quantity_method"] == "direct"


def test_multiple_procedures(worker, context, mock_dmn):
    """Multiple procedures are all quantified."""
    mock_dmn.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "quantity": 2,
        "quantityMethod": "direct",
        "quantityCapped": False,
    }
    context.variables = {
        "enriched_procedures": [
            {"code": "40101010", "quantity": 1},
            {"code": "40201010", "quantity": 1},
        ],
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert result.variables["total_items"] == 4
