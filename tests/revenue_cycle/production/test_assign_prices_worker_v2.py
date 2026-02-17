"""Tests for AssignPricesWorker v2 (ARCHETYPE: NONE - no DMN)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskStatus
from healthcare_platform.revenue_cycle.production.workers.assign_prices_worker_v2 import (
    AssignPricesWorker,
)


@pytest.fixture
def context():
    return TaskContext(
        task_id="task_1",
        process_instance_id="proc_1",
        tenant_id="HOSPITAL_A",
        variables={},
        worker_id="production.assign_prices",
    )


@pytest.fixture
def mock_tasy():
    return MagicMock()


@pytest.fixture
def mock_fhir():
    return MagicMock()


@pytest.fixture
def worker(mock_tasy, mock_fhir):
    return AssignPricesWorker(
        fhir_client=mock_fhir,
        tasy_api_client=mock_tasy,
        dmn_service=MagicMock(),
        metrics=MagicMock(),
    )


def test_happy_path_tasy_pricing(worker, context, mock_tasy):
    """TASY returns valid prices for all procedures."""
    mock_tasy.get_procedure_price.return_value = {"unit_price": "150.00"}
    context.variables = {
        "quantified_procedures": [
            {"code": "40101010", "quantity": 2},
        ],
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert result.variables["total_amount"] == "300.00"
    assert result.variables["currency"] == "BRL"
    assert len(result.variables["priced_procedures"]) == 1


def test_missing_price_returns_bpmn_error(worker, context, mock_tasy, mock_fhir):
    """Price not found triggers CONTRACT_RULE_VIOLATION."""
    mock_tasy.get_procedure_price.side_effect = Exception("not found")
    mock_fhir.search.return_value = []
    context.variables = {
        "quantified_procedures": [{"code": "99999999", "quantity": 1}],
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "CONTRACT_RULE_VIOLATION"


def test_fhir_fallback_when_tasy_fails(worker, context, mock_tasy, mock_fhir):
    """Falls back to FHIR when TASY lookup fails."""
    mock_tasy.get_procedure_price.side_effect = Exception("unavailable")
    mock_fhir.search.return_value = [
        {"propertyGroup": [{"priceComponent": [{"type": "base", "amount": {"value": 75.0}}]}]}
    ]
    context.variables = {
        "quantified_procedures": [{"code": "40101010", "quantity": 1}],
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert Decimal(result.variables["total_amount"]) == Decimal("75.0")


def test_empty_procedures_returns_error(worker, context):
    """No procedures triggers BILLING_ERROR."""
    context.variables = {"quantified_procedures": []}

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "BILLING_ERROR"


def test_missing_input_key(worker, context):
    """Missing quantified_procedures key triggers error."""
    context.variables = {}

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR


def test_multiple_procedures_total(worker, context, mock_tasy):
    """Multiple procedures accumulate total correctly."""
    mock_tasy.get_procedure_price.return_value = {"unit_price": "100.00"}
    context.variables = {
        "quantified_procedures": [
            {"code": "40101010", "quantity": 3},
            {"code": "40201010", "quantity": 2},
        ],
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert Decimal(result.variables["total_amount"]) == Decimal("500.00")
    assert len(result.variables["priced_procedures"]) == 2


def test_topic_constant():
    """TOPIC matches original worker."""
    assert AssignPricesWorker.TOPIC == "production.assign_prices"
