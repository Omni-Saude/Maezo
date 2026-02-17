"""Unit tests for GenericOperationalRoutingWorker.

Verifies:
- Default error_strategy is always fail_closed
- _validate_routing_result() defaults next_state to PENDING when missing
- _validate_routing_result() defaults assigned_to to UNASSIGNED when missing
- Valid routing fields pass through unchanged
- ARCHETYPE constant is correct
- No-decisions path returns BPMN error
- DMN errors with fail_closed re-raise (deterministic routing must not fail silently)
- DMN errors with fail_safe return success
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.shared.workers.generic.operational_routing import GenericOperationalRoutingWorker


def _make_worker(registry_config, mock_logger=None):
    """Helper: construct worker with mocked dependencies."""
    return GenericOperationalRoutingWorker(
        topic="clinical.triage_routing",
        registry_config=registry_config,
        logger=mock_logger or MagicMock(),
    )


def _make_context(**var_overrides):
    """Helper: create a TaskContext with routing-relevant variables."""
    variables = {
        "patientId": "PAT-002",
        "triageLevel": "URGENT",
        "arrivalMode": "AMBULANCE",
        "timestamp": "2026-02-17T11:00:00Z",
    }
    variables.update(var_overrides)
    return TaskContext(
        task_id="t-routing-001",
        process_instance_id="p-routing-001",
        tenant_id="hospital-a",
        variables=variables,
        worker_id="clinical.triage_routing",
    )


# ---------------------------------------------------------------------------
# Archetype constant
# ---------------------------------------------------------------------------

class TestArchetypeConstant:
    def test_archetype_constant(self):
        assert GenericOperationalRoutingWorker.ARCHETYPE == "OPERATIONAL_ROUTING"


# ---------------------------------------------------------------------------
# Default error strategy
# ---------------------------------------------------------------------------

class TestDefaultErrorStrategy:
    def test_default_error_strategy_is_fail_closed_when_not_set(self):
        config = {"decisions": [{"key": "triage_routing", "category": "clinical_safety", "inputs": {}}]}
        worker = _make_worker(config)
        assert worker.error_strategy == "fail_closed"

    def test_explicit_fail_safe_is_respected(self):
        config = {
            "decisions": [{"key": "triage_routing", "category": "clinical_safety", "inputs": {}}],
            "error_strategy": "fail_safe",
        }
        worker = _make_worker(config)
        assert worker.error_strategy == "fail_safe"

    def test_fail_closed_preserved_when_already_set(self):
        config = {
            "decisions": [{"key": "triage_routing", "category": "clinical_safety", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        assert worker.error_strategy == "fail_closed"


# ---------------------------------------------------------------------------
# _validate_routing_result
# ---------------------------------------------------------------------------

class TestValidateRoutingResult:
    def test_missing_next_state_defaults_to_pending(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._validate_routing_result({})
        assert result["next_state"] == "PENDING"

    def test_empty_next_state_defaults_to_pending(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._validate_routing_result({"next_state": ""})
        assert result["next_state"] == "PENDING"

    def test_missing_assigned_to_defaults_to_unassigned(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._validate_routing_result({})
        assert result["assigned_to"] == "UNASSIGNED"

    def test_empty_assigned_to_defaults_to_unassigned(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._validate_routing_result({"assigned_to": ""})
        assert result["assigned_to"] == "UNASSIGNED"

    def test_valid_next_state_passes_through(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._validate_routing_result({"next_state": "ICU", "assigned_to": "ICU_TEAM"})
        assert result["next_state"] == "ICU"

    def test_valid_assigned_to_passes_through(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._validate_routing_result({"next_state": "WARD_A", "assigned_to": "NURSE_3"})
        assert result["assigned_to"] == "NURSE_3"

    def test_both_fields_missing_both_get_defaults(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._validate_routing_result({})
        assert result["next_state"] == "PENDING"
        assert result["assigned_to"] == "UNASSIGNED"

    def test_missing_fields_log_warning(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        mock_logger = MagicMock()
        worker = _make_worker(config, mock_logger=mock_logger)
        worker._validate_routing_result({})
        assert mock_logger.warning.call_count >= 2


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
            "decisions": [{"key": "triage_routing", "category": "clinical_safety", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "evaluate_dmn", return_value={
            "next_state": "ICU",
            "assigned_to": "ICU_TEAM_A",
            "action": "PROSSEGUIR",
        }):
            result = worker.execute(ctx)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["next_state"] == "ICU"
        assert result.variables["assigned_to"] == "ICU_TEAM_A"

    def test_successful_dmn_validates_routing_fields(self):
        """Missing routing fields from DMN get defaults applied."""
        config = {
            "decisions": [{"key": "triage_routing", "category": "clinical_safety", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "evaluate_dmn", return_value={"action": "PROSSEGUIR"}):
            result = worker.execute(ctx)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["next_state"] == "PENDING"
        assert result.variables["assigned_to"] == "UNASSIGNED"

    def test_dmn_error_with_fail_closed_returns_bpmn_error(self):
        """fail_closed: DMN errors surface as BPMN error so Camunda triggers error boundary."""
        config = {
            "decisions": [{"key": "triage_routing", "category": "clinical_safety", "inputs": {}}],
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
            "decisions": [{"key": "triage_routing", "category": "clinical_safety", "inputs": {}}],
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
            "decisions": [{"key": "triage_routing", "category": "clinical_safety", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "_execute_dmn_pipeline", side_effect=RuntimeError("internal error")):
            result = worker.execute(ctx)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "DMN_ERROR_BLOCKED"
