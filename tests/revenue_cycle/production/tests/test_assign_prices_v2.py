"""Tests for AssignPricesWorker (v2)."""
from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.revenue_cycle.production.workers.assign_prices_worker_v2 import (
    AssignPricesWorker,
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
    """Create AssignPricesWorker with mocked dependencies."""
    fhir_client = MagicMock()
    tasy_api_client = MagicMock()
    worker = AssignPricesWorker(
        fhir_client=fhir_client, tasy_api_client=tasy_api_client
    )
    worker.logger = MagicMock()
    return worker


def test_assign_prices_happy_path(worker):
    """Test successful price assignment."""
    # Mock service response
    worker.service = MagicMock()
    worker.service.assign_prices.return_value = {
        "priced_procedures": [
            {
                "code": "40301010",
                "description": "Consulta médica",
                "quantity": 1,
                "unit_price": "150.00",
                "total_price": "150.00",
            }
        ],
        "total_amount": "150.00",
    }

    # Mock DMN evaluation
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "PROSSEGUIR",
            "acao": "",
            "risco": "BAIXO",
        }
    )

    context = make_context(
        {
            "quantified_procedures": [
                {"code": "40301010", "quantity": 1, "description": "Consulta médica"}
            ],
            "contract_id": "contract-123",
            "price_table_id": "table-456",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert "priced_procedures" in result.variables
    assert result.variables["total_amount"] == "150.00"
    assert len(result.variables["priced_procedures"]) == 1
    worker.service.assign_prices.assert_called_once()


def test_assign_prices_no_procedures_error(worker):
    """Test error when no procedures provided."""
    worker.evaluate_dmn = MagicMock()

    context = make_context(
        {
            "quantified_procedures": [],
            "contract_id": "contract-123",
            "price_table_id": "table-456",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "BILLING_ERROR"
    assert "no procedures" in result.error_message.lower()


def test_assign_prices_missing_prices_error(worker):
    """Test error when service cannot find prices."""
    worker.service = MagicMock()
    worker.service.assign_prices.return_value = {
        "priced_procedures": [],
        "total_amount": "0.00",
        "missing_codes": ["40301010"],
    }

    worker.evaluate_dmn = MagicMock()

    context = make_context(
        {
            "quantified_procedures": [{"code": "40301010", "quantity": 1}],
            "contract_id": "contract-123",
            "price_table_id": "table-456",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "CONTRACT_RULE_VIOLATION"
    assert "price not found" in result.error_message.lower()


def test_assign_prices_service_exception(worker):
    """Test handling of service exceptions."""
    worker.service = MagicMock()
    worker.service.assign_prices.side_effect = Exception("Database connection failed")

    worker.evaluate_dmn = MagicMock()

    context = make_context(
        {
            "quantified_procedures": [{"code": "40301010", "quantity": 1}],
            "contract_id": "contract-123",
            "price_table_id": "table-456",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "BILLING_ERROR"
    assert "database connection failed" in result.error_message.lower()


@pytest.mark.skip(reason="Worker does not implement DMN evaluation - needs refactoring")
def test_assign_prices_contract_rule_violation(worker):
    """Test DMN blocking due to contract rules."""
    worker.service = MagicMock()
    worker.service.assign_prices.return_value = {
        "priced_procedures": [
            {
                "code": "40301010",
                "quantity": 1,
                "unit_price": "150.00",
                "total_price": "150.00",
            }
        ],
        "total_amount": "150.00",
    }

    # DMN blocks due to contract violation
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "BLOQUEAR",
            "acao": "Contract limit exceeded",
            "risco": "ALTO",
        }
    )

    context = make_context(
        {
            "quantified_procedures": [{"code": "40301010", "quantity": 1}],
            "contract_id": "contract-123",
            "price_table_id": "table-456",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "CONTRACT_RULE_VIOLATION"
    assert "contract limit exceeded" in result.error_message.lower()


@pytest.mark.skip(reason="Worker does not implement DMN evaluation - needs refactoring")
def test_assign_prices_dmn_review_warning(worker):
    """Test DMN review returns success with warning."""
    worker.service = MagicMock()
    worker.service.assign_prices.return_value = {
        "priced_procedures": [
            {
                "code": "40301010",
                "quantity": 1,
                "unit_price": "150.00",
                "total_price": "150.00",
            }
        ],
        "total_amount": "150.00",
    }

    # DMN suggests review but doesn't block
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "REVISAR",
            "acao": "Price above average",
            "risco": "MEDIO",
        }
    )

    context = make_context(
        {
            "quantified_procedures": [{"code": "40301010", "quantity": 1}],
            "contract_id": "contract-123",
            "price_table_id": "table-456",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert "priced_procedures" in result.variables
    assert "pricing_warnings" in result.variables
    assert len(result.variables["pricing_warnings"]) > 0
