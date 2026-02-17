"""Unit tests for GenericAdminAdjudicationWorker.

Verifies:
- Default error_strategy is always fail_closed
- Missing 'action' in DMN output defaults to REVISAR
- Valid 'action' passes through unchanged
- ARCHETYPE constant is correct
- No-decisions path returns BPMN error
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.shared.workers.generic.admin_adjudication import GenericAdminAdjudicationWorker


def _make_worker(registry_config, mock_logger=None):
    """Helper: construct worker with mocked dependencies."""
    return GenericAdminAdjudicationWorker(
        topic="billing.validate_claim",
        registry_config=registry_config,
        logger=mock_logger or MagicMock(),
    )


def _make_context(**var_overrides):
    """Helper: create a minimal TaskContext."""
    variables = {"claimId": "CLM-001", "amount": 500.0}
    variables.update(var_overrides)
    return TaskContext(
        task_id="t-001",
        process_instance_id="p-001",
        tenant_id="hospital-a",
        variables=variables,
        worker_id="billing.validate_claim",
    )


# ---------------------------------------------------------------------------
# Archetype constant
# ---------------------------------------------------------------------------

class TestArchetypeConstant:
    def test_archetype_constant(self):
        assert GenericAdminAdjudicationWorker.ARCHETYPE == "ADMIN_ADJUDICATION"


# ---------------------------------------------------------------------------
# Default error strategy
# ---------------------------------------------------------------------------

class TestDefaultErrorStrategy:
    def test_default_error_strategy_is_fail_closed_when_not_set(self):
        config = {"decisions": [{"key": "some_decision", "category": "billing", "inputs": {}}]}
        worker = _make_worker(config)
        assert worker.error_strategy == "fail_closed"

    def test_explicit_fail_safe_is_respected(self):
        config = {
            "decisions": [{"key": "some_decision", "category": "billing", "inputs": {}}],
            "error_strategy": "fail_safe",
        }
        worker = _make_worker(config)
        assert worker.error_strategy == "fail_safe"

    def test_fail_closed_preserved_when_already_set(self):
        config = {
            "decisions": [{"key": "some_decision", "category": "billing", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        assert worker.error_strategy == "fail_closed"


# ---------------------------------------------------------------------------
# _validate_admin_result
# ---------------------------------------------------------------------------

class TestValidateAdminResult:
    def test_missing_action_defaults_to_revisar(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._validate_admin_result({})
        assert result["action"] == "REVISAR"
        assert "reason" in result

    def test_empty_string_action_defaults_to_revisar(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._validate_admin_result({"action": ""})
        assert result["action"] == "REVISAR"

    def test_valid_action_passes_through(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._validate_admin_result({"action": "BLOQUEAR"})
        assert result["action"] == "BLOQUEAR"

    def test_prosseguir_passes_through(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._validate_admin_result({"action": "PROSSEGUIR"})
        assert result["action"] == "PROSSEGUIR"


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
            "decisions": [{"key": "claim_validation", "category": "billing", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "evaluate_dmn", return_value={"action": "PROSSEGUIR"}):
            result = worker.execute(ctx)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["action"] == "PROSSEGUIR"

    def test_dmn_error_with_fail_closed_returns_bpmn_error(self):
        """fail_closed: DMN errors return TaskResult.bpmn_error with BLOQUEAR."""
        config = {
            "decisions": [{"key": "claim_validation", "category": "billing", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "evaluate_dmn", side_effect=RuntimeError("connection lost")):
            result = worker.execute(ctx)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "DMN_ERROR_BLOCKED"
        assert result.variables["resultado"] == "BLOQUEAR"
        assert "connection lost" in result.error_message
