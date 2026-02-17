"""Unit tests for GenericFinancialCalculationWorker.

Verifies:
- Default error_strategy is always fail_closed (financial errors must block)
- _round_currency_fields() rounds to 2 decimal places for all currency fields
- _round_currency_fields() raises ValueError for non-numeric currency fields
- Non-currency fields pass through unchanged
- ARCHETYPE constant is correct
- No-decisions path returns BPMN error
- DMN errors with fail_closed re-raise (incorrect amounts must never be produced silently)
- DMN errors with fail_safe return success
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.shared.workers.generic.financial_calculation import (
    GenericFinancialCalculationWorker,
    _CURRENCY_FIELDS,
)


def _make_worker(registry_config, mock_logger=None):
    """Helper: construct worker with mocked dependencies."""
    return GenericFinancialCalculationWorker(
        topic="billing.pricing_calculation",
        registry_config=registry_config,
        logger=mock_logger or MagicMock(),
    )


def _make_context(**var_overrides):
    """Helper: create a TaskContext with financial variables."""
    variables = {
        "claimId": "CLM-789",
        "procedureCode": "10.01.08-0",
        "quantity": 3,
        "basePrice": 150.0,
        "patientId": "PAT-004",
        "timestamp": "2026-02-17T13:00:00Z",
    }
    variables.update(var_overrides)
    return TaskContext(
        task_id="t-financial-001",
        process_instance_id="p-financial-001",
        tenant_id="hospital-a",
        variables=variables,
        worker_id="billing.pricing_calculation",
    )


# ---------------------------------------------------------------------------
# Archetype constant
# ---------------------------------------------------------------------------

class TestArchetypeConstant:
    def test_archetype_constant(self):
        assert GenericFinancialCalculationWorker.ARCHETYPE == "FINANCIAL_CALCULATION"


# ---------------------------------------------------------------------------
# Default error strategy
# ---------------------------------------------------------------------------

class TestDefaultErrorStrategy:
    def test_default_error_strategy_is_fail_closed_when_not_set(self):
        config = {"decisions": [{"key": "pricing_rules", "category": "billing", "inputs": {}}]}
        worker = _make_worker(config)
        assert worker.error_strategy == "fail_closed"

    def test_explicit_fail_safe_is_respected(self):
        config = {
            "decisions": [{"key": "pricing_rules", "category": "billing", "inputs": {}}],
            "error_strategy": "fail_safe",
        }
        worker = _make_worker(config)
        assert worker.error_strategy == "fail_safe"

    def test_fail_closed_preserved_when_already_set(self):
        config = {
            "decisions": [{"key": "pricing_rules", "category": "billing", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        assert worker.error_strategy == "fail_closed"


# ---------------------------------------------------------------------------
# _round_currency_fields
# ---------------------------------------------------------------------------

class TestRoundCurrencyFields:
    def test_amount_rounded_to_two_decimals(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._round_currency_fields({"amount": 150.123})
        assert result["amount"] == 150.12

    def test_total_rounded_to_two_decimals(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._round_currency_fields({"total": 99.999})
        assert result["total"] == 100.0

    def test_price_rounded_to_two_decimals(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._round_currency_fields({"price": 9.995})
        assert result["price"] == round(9.995, 2)

    def test_discount_rounded_to_two_decimals(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._round_currency_fields({"discount": 10.5678})
        assert result["discount"] == 10.57

    def test_penalty_rounded_to_two_decimals(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._round_currency_fields({"penalty": 25.0})
        assert result["penalty"] == 25.0

    def test_reimbursement_rounded_to_two_decimals(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._round_currency_fields({"reimbursement": 300.009})
        assert result["reimbursement"] == round(300.009, 2)

    def test_copay_rounded_to_two_decimals(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._round_currency_fields({"copay": 50.0})
        assert result["copay"] == 50.0

    def test_deductible_rounded_to_two_decimals(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._round_currency_fields({"deductible": 1000.001})
        assert result["deductible"] == round(1000.001, 2)

    def test_non_numeric_amount_raises_value_error(self):
        """Non-numeric currency fields must raise ValueError (fail_closed)."""
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        with pytest.raises(ValueError, match="non-numeric value"):
            worker._round_currency_fields({"amount": "INVALID"})

    def test_none_amount_raises_value_error(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        with pytest.raises(ValueError):
            worker._round_currency_fields({"amount": None})

    def test_non_currency_fields_pass_through_unchanged(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._round_currency_fields({"action": "PROSSEGUIR", "reason": "OK"})
        assert result["action"] == "PROSSEGUIR"
        assert result["reason"] == "OK"

    def test_multiple_currency_fields_rounded_together(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._round_currency_fields({
            "amount": 100.123,
            "discount": 10.456,
            "total": 89.667,
        })
        assert result["amount"] == 100.12
        assert result["discount"] == 10.46
        assert result["total"] == 89.67

    def test_currency_fields_constant_covers_all_expected_fields(self):
        """Verify the module-level _CURRENCY_FIELDS tuple contains all expected field names."""
        expected_fields = {"amount", "total", "price", "discount", "penalty", "reimbursement", "copay", "deductible"}
        assert set(_CURRENCY_FIELDS) == expected_fields


# ---------------------------------------------------------------------------
# execute() integration-level unit tests
# ---------------------------------------------------------------------------

class TestExecute:
    def test_no_decisions_returns_bpmn_error(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        ctx = _make_context()
        result = worker.execute(ctx)
        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "NO_DECISIONS_CONFIGURED"

    def test_successful_dmn_returns_success(self):
        config = {
            "decisions": [{"key": "pricing_rules", "category": "billing", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "evaluate_dmn", return_value={
            "amount": 450.0,
            "discount": 45.0,
            "total": 405.0,
            "action": "PROSSEGUIR",
        }):
            result = worker.execute(ctx)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["amount"] == 450.0
        assert result.variables["total"] == 405.0

    def test_successful_dmn_rounds_currency_fields(self):
        """DMN output with unrounded values gets rounded by post-processing."""
        config = {
            "decisions": [{"key": "pricing_rules", "category": "billing", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "evaluate_dmn", return_value={"amount": 100.129, "total": 100.129}):
            result = worker.execute(ctx)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["amount"] == 100.13

    def test_dmn_error_with_fail_closed_returns_bpmn_error(self):
        """fail_closed: DMN errors surface as BPMN error so Camunda triggers error boundary."""
        config = {
            "decisions": [{"key": "pricing_rules", "category": "billing", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "evaluate_dmn", side_effect=RuntimeError("DMN service down")):
            result = worker.execute(ctx)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "DMN_ERROR_BLOCKED"
        assert result.variables["resultado"] == "BLOQUEAR"

    def test_dmn_error_with_fail_safe_returns_success(self):
        """fail_safe: DMN error is handled, pipeline continues."""
        config = {
            "decisions": [{"key": "pricing_rules", "category": "billing", "inputs": {}}],
            "error_strategy": "fail_safe",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "evaluate_dmn", side_effect=RuntimeError("DMN unreachable")):
            result = worker.execute(ctx)

        assert result.status == TaskStatus.SUCCESS

    def test_exception_outside_dmn_eval_returns_bpmn_error_for_fail_closed(self):
        """Non-DMN exceptions in execute() surface as BPMN error for fail_closed."""
        config = {
            "decisions": [{"key": "pricing_rules", "category": "billing", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "_execute_dmn_pipeline", side_effect=RuntimeError("internal error")):
            result = worker.execute(ctx)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "DMN_ERROR_BLOCKED"
