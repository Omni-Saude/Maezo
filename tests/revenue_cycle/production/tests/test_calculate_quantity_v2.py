"""Tests for CalculateQuantityWorker (v2)."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock
import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.revenue_cycle.production.workers.calculate_quantity_worker_v2 import (
    CalculateQuantityWorker,
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
    """Create CalculateQuantityWorker."""
    worker = CalculateQuantityWorker()
    worker.logger = MagicMock()
    return worker


def test_calculate_quantity_happy_path(worker):
    """Test successful quantity calculation."""
    # Mock DMN evaluation
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "PROSSEGUIR",
            "quantity": 2,
            "quantityMethod": "duration_based",
            "quantityCapped": False,
        }
    )

    start_time = datetime.now()
    end_time = start_time + timedelta(hours=2)

    context = make_context(
        {
            "enriched_procedures": [
                {
                    "code": "40301010",
                    "description": "Consulta médica",
                    "requiresDuration": True,
                }
            ],
            "encounter_start": start_time.isoformat(),
            "encounter_end": end_time.isoformat(),
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert "quantified_procedures" in result.variables
    assert result.variables["total_items"] == 2
    assert len(result.variables["quantified_procedures"]) == 1
    assert result.variables["quantified_procedures"][0]["quantity"] == 2


def test_calculate_quantity_no_procedures_error(worker):
    """Test error when no procedures provided."""
    worker.evaluate_dmn = MagicMock()

    context = make_context(
        {
            "enriched_procedures": [],
            "encounter_start": datetime.now().isoformat(),
            "encounter_end": (datetime.now() + timedelta(hours=1)).isoformat(),
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "CODING_ERROR"
    assert "no procedures" in result.error_message.lower()


def test_calculate_quantity_duration_calculation(worker):
    """Test duration-based quantity calculation."""
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "PROSSEGUIR",
            "quantity": 3,
            "quantityMethod": "duration_based",
            "quantityCapped": False,
        }
    )

    # 3 hour encounter
    start_time = datetime(2026, 1, 15, 10, 0, 0)
    end_time = datetime(2026, 1, 15, 13, 0, 0)

    context = make_context(
        {
            "enriched_procedures": [
                {
                    "code": "40301010",
                    "description": "Consulta médica",
                    "requiresDuration": True,
                }
            ],
            "encounter_start": start_time.isoformat(),
            "encounter_end": end_time.isoformat(),
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert result.variables["quantified_procedures"][0]["quantity"] == 3
    assert result.variables["quantified_procedures"][0]["duration_minutes"] == 180.0


def test_calculate_quantity_dmn_block(worker):
    """Test DMN blocking quantity calculation."""
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "BLOQUEAR",
            "quantity": 0,
            "quantityMethod": "blocked",
            "quantityCapped": False,
            "acao": "Quantity exceeds contract limit",
        }
    )

    context = make_context(
        {
            "enriched_procedures": [
                {
                    "code": "40301010",
                    "description": "Consulta médica",
                    "requiresDuration": False,
                }
            ],
            "encounter_start": datetime.now().isoformat(),
            "encounter_end": (datetime.now() + timedelta(hours=1)).isoformat(),
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "CODING_ERROR"
    assert "quantity exceeds contract limit" in result.error_message.lower()


def test_calculate_quantity_capped(worker):
    """Test quantity capping due to DMN rules."""
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "PROSSEGUIR",
            "quantity": 10,
            "quantityMethod": "capped",
            "quantityCapped": True,
            "originalQuantity": 15,
        }
    )

    start_time = datetime.now()
    end_time = start_time + timedelta(hours=15)

    context = make_context(
        {
            "enriched_procedures": [
                {
                    "code": "40301010",
                    "description": "Consulta médica",
                    "requiresDuration": True,
                }
            ],
            "encounter_start": start_time.isoformat(),
            "encounter_end": end_time.isoformat(),
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert result.variables["quantified_procedures"][0]["quantity"] == 10
    assert result.variables["quantified_procedures"][0]["quantity_capped"] is True


def test_calculate_quantity_fixed_quantity(worker):
    """Test fixed quantity (not duration-based)."""
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "PROSSEGUIR",
            "quantity": 1,
            "quantityMethod": "fixed",
            "quantityCapped": False,
        }
    )

    context = make_context(
        {
            "enriched_procedures": [
                {
                    "code": "40301010",
                    "description": "Consulta médica",
                    "requiresDuration": False,
                }
            ],
            "encounter_start": datetime.now().isoformat(),
            "encounter_end": (datetime.now() + timedelta(hours=1)).isoformat(),
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert result.variables["quantified_procedures"][0]["quantity"] == 1
    assert result.variables["quantified_procedures"][0]["quantity_method"] == "fixed"


def test_calculate_quantity_exception_handling(worker):
    """Test handling of unexpected exceptions."""
    worker.evaluate_dmn = MagicMock(
        side_effect=Exception("DMN service unavailable")
    )

    context = make_context(
        {
            "enriched_procedures": [{"code": "40301010"}],
            "encounter_start": datetime.now().isoformat(),
            "encounter_end": (datetime.now() + timedelta(hours=1)).isoformat(),
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "CODING_ERROR"
    assert "dmn service unavailable" in result.error_message.lower()
