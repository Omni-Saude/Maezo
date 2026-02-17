"""Tests for PersistProductionWorker (v2)."""
from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.revenue_cycle.production.workers.persist_production_worker_v2 import (
    PersistProductionWorker,
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
    """Create PersistProductionWorker with mocked dependencies."""
    fhir_client = MagicMock()
    worker = PersistProductionWorker(fhir_client=fhir_client)
    worker.logger = MagicMock()
    return worker


def test_persist_production_happy_path(worker):
    """Test successful production persistence."""
    # Mock service response - service.persist returns dict
    worker.service.persist = MagicMock(
        return_value={
            "claim_reference": "Claim/test-123",
            "charge_item_references": ["ChargeItem/1", "ChargeItem/2"],
            "production_id": "test-123",
            "persisted_at": "2026-02-16T12:00:00",
        }
    )

    # Mock DMN evaluation
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "PROSSEGUIR",
        }
    )

    context = make_context(
        {
            "compatible_procedures": [
                {
                    "code": "40301010",
                    "description": "Consulta médica",
                    "quantity": 1,
                    "unit_price": "150.00",
                    "total_price": "150.00",
                },
                {
                    "code": "20101012",
                    "description": "Raio X",
                    "quantity": 1,
                    "unit_price": "200.00",
                    "total_price": "200.00",
                },
            ],
            "encounter_reference": "Encounter/enc-123",
            "patient_reference": "Patient/pat-123",
            "total_amount": "350.00",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert "claim_reference" in result.variables
    assert "charge_item_references" in result.variables
    assert len(result.variables["charge_item_references"]) == 2
    worker.service.persist.assert_called_once()


def test_persist_production_dmn_block(worker):
    """Test DMN blocking persistence."""
    worker.service = MagicMock()

    # DMN blocks persistence
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "BLOQUEAR",
            "validation_passed": False,
            "risk_level": "ALTO",
            "acao": "Total amount exceeds contract limit",
        }
    )

    context = make_context(
        {
            "compatible_procedures": [{"code": "40301010"}],
            "encounter_reference": "Encounter/enc-123",
            "patient_reference": "Patient/pat-123",
            "total_amount": "10000.00",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "BILLING_ERROR"
    assert "contract limit" in result.error_message.lower()


def test_persist_production_dmn_review(worker):
    """Test DMN review with warning."""
    worker.service.persist = MagicMock(
        return_value={
            "claim_reference": "Claim/test-123",
            "charge_item_references": ["ChargeItem/1"],
            "production_id": "test-123",
            "persisted_at": "2026-02-16T12:00:00",
        }
    )

    # DMN suggests review but doesn't block
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "REVISAR",
            "acao": "High-value charge requires audit",
        }
    )

    context = make_context(
        {
            "compatible_procedures": [
                {
                    "code": "40301010",
                    "total_price": "5000.00",
                }
            ],
            "encounter_reference": "Encounter/enc-123",
            "patient_reference": "Patient/pat-123",
            "total_amount": "5000.00",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    # When resultado is REVISAR, worker sets requiresReview and clears charge_item_references
    assert result.variables["requiresReview"] is True
    assert result.variables["charge_item_references"] == []


def test_persist_production_service_exception(worker):
    """Test handling of service exceptions."""
    worker.service.persist = MagicMock(side_effect=Exception("FHIR server error"))

    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "PROSSEGUIR",
        }
    )

    context = make_context(
        {
            "compatible_procedures": [{"code": "40301010"}],
            "encounter_reference": "Encounter/enc-123",
            "patient_reference": "Patient/pat-123",
            "total_amount": "150.00",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "EXTERNAL_SERVICE_ERROR"
    assert "fhir server error" in result.error_message.lower()


def test_persist_production_empty_procedures(worker):
    """Test with empty procedures - DMN should handle validation."""
    worker.service.persist = MagicMock(
        return_value={
            "claim_reference": "Claim/test-123",
            "charge_item_references": [],
            "production_id": "test-123",
            "persisted_at": "2026-02-16T12:00:00",
        }
    )

    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "PROSSEGUIR",
        }
    )

    context = make_context(
        {
            "compatible_procedures": [],
            "encounter_reference": "Encounter/enc-123",
            "patient_reference": "Patient/pat-123",
            "total_amount": "0.00",
        }
    )

    result = worker.execute(context)

    # Worker doesn't validate empty procedures itself - DMN does
    assert result.status == TaskStatus.SUCCESS


def test_persist_production_missing_references(worker):
    """Test with missing references - worker uses empty strings."""
    worker.service.persist = MagicMock(
        return_value={
            "claim_reference": "Claim/test-123",
            "charge_item_references": ["ChargeItem/1"],
            "production_id": "test-123",
            "persisted_at": "2026-02-16T12:00:00",
        }
    )

    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "PROSSEGUIR",
        }
    )

    context = make_context(
        {
            "compatible_procedures": [{"code": "40301010"}],
            "total_amount": "150.00",
        }
    )

    result = worker.execute(context)

    # Worker doesn't validate references - it passes them to service
    assert result.status == TaskStatus.SUCCESS


def test_persist_production_with_account_creation(worker):
    """Test persistence - service returns standard fields."""
    worker.service.persist = MagicMock(
        return_value={
            "claim_reference": "Claim/test-123",
            "charge_item_references": ["ChargeItem/1"],
            "production_id": "test-123",
            "persisted_at": "2026-02-16T12:00:00",
        }
    )

    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "PROSSEGUIR",
        }
    )

    context = make_context(
        {
            "compatible_procedures": [{"code": "40301010", "total_price": "150.00"}],
            "encounter_reference": "Encounter/enc-123",
            "patient_reference": "Patient/pat-123",
            "total_amount": "150.00",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert "claim_reference" in result.variables
    assert result.variables["production_id"] == "test-123"
