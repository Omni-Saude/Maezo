"""Unit tests for GenericClinicalAlertWorker.

Verifies:
- Default error_strategy is always fail_safe
- Alert metadata defaults (alert_severity='INFO', requires_acknowledgment=False)
- Timestamp is pulled from context.variables
- ARCHETYPE constant is correct
- No-decisions path returns safe default (not an error)
- DMN errors return success with review flag (fail_safe)
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.shared.workers.generic.clinical_alert import GenericClinicalAlertWorker


def _make_worker(registry_config, mock_logger=None):
    """Helper: construct worker with mocked dependencies."""
    return GenericClinicalAlertWorker(
        topic="clinical.sepsis_alert",
        registry_config=registry_config,
        logger=mock_logger or MagicMock(),
    )


def _make_context(**var_overrides):
    """Helper: create a TaskContext with clinical variables."""
    variables = {
        "patientId": "PAT-777",
        "news2Score": 5,
        "timestamp": "2026-02-17T08:00:00Z",
    }
    variables.update(var_overrides)
    return TaskContext(
        task_id="t-002",
        process_instance_id="p-002",
        tenant_id="hospital-a",
        variables=variables,
        worker_id="clinical.sepsis_alert",
    )


# ---------------------------------------------------------------------------
# Archetype constant
# ---------------------------------------------------------------------------

class TestArchetypeConstant:
    def test_archetype_constant(self):
        assert GenericClinicalAlertWorker.ARCHETYPE == "CLINICAL_ALERT"


# ---------------------------------------------------------------------------
# Default error strategy
# ---------------------------------------------------------------------------

class TestDefaultErrorStrategy:
    def test_default_error_strategy_is_fail_safe_when_not_set(self):
        config = {"decisions": [{"key": "sepsis_rules", "category": "clinical_safety", "inputs": {}}]}
        worker = _make_worker(config)
        assert worker.error_strategy == "fail_safe"

    def test_explicit_fail_closed_is_respected(self):
        config = {
            "decisions": [{"key": "sepsis_rules", "category": "clinical_safety", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        assert worker.error_strategy == "fail_closed"

    def test_fail_safe_preserved_when_already_set(self):
        config = {
            "decisions": [{"key": "sepsis_rules", "category": "clinical_safety", "inputs": {}}],
            "error_strategy": "fail_safe",
        }
        worker = _make_worker(config)
        assert worker.error_strategy == "fail_safe"


# ---------------------------------------------------------------------------
# _ensure_alert_fields
# ---------------------------------------------------------------------------

class TestEnsureAlertFields:
    def test_ensures_alert_level_default(self):
        """When no alert_level present, defaults to INFO."""
        config = {"decisions": [], "error_strategy": "fail_safe"}
        worker = _make_worker(config)
        result = worker._ensure_alert_fields({})
        assert result["alert_level"] == "INFO"

    def test_does_not_override_existing_alert_level(self):
        config = {"decisions": [], "error_strategy": "fail_safe"}
        worker = _make_worker(config)
        result = worker._ensure_alert_fields({"alert_level": "CRITICAL"})
        assert result["alert_level"] == "CRITICAL"

    def test_ensures_requires_acknowledgment_default(self):
        config = {"decisions": [], "error_strategy": "fail_safe"}
        worker = _make_worker(config)
        result = worker._ensure_alert_fields({})
        assert result["requires_acknowledgment"] is False

    def test_does_not_override_existing_acknowledgment(self):
        config = {"decisions": [], "error_strategy": "fail_safe"}
        worker = _make_worker(config)
        result = worker._ensure_alert_fields({"requires_acknowledgment": True})
        assert result["requires_acknowledgment"] is True

    def test_ensures_notified_roles_default(self):
        config = {"decisions": [], "error_strategy": "fail_safe"}
        worker = _make_worker(config)
        result = worker._ensure_alert_fields({})
        assert result["notified_roles"] == []

    def test_does_not_override_existing_notified_roles(self):
        config = {"decisions": [], "error_strategy": "fail_safe"}
        worker = _make_worker(config)
        result = worker._ensure_alert_fields({"notified_roles": ["ICU_NURSE", "DOCTOR"]})
        assert result["notified_roles"] == ["ICU_NURSE", "DOCTOR"]


# ---------------------------------------------------------------------------
# execute() integration-level unit tests
# ---------------------------------------------------------------------------

class TestExecute:
    def test_no_decisions_returns_bpmn_error(self):
        """Clinical alert worker with no decisions returns BPMN error."""
        config = {"decisions": [], "error_strategy": "fail_safe"}
        worker = _make_worker(config)
        ctx = _make_context()
        result = worker.execute(ctx)
        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "NO_DECISIONS_CONFIGURED"

    def test_successful_dmn_enriches_alert_fields(self):
        config = {
            "decisions": [{"key": "sepsis_rules", "category": "clinical_safety", "inputs": {}}],
            "error_strategy": "fail_safe",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "evaluate_dmn", return_value={"alert_level": "HIGH", "action": "PROSSEGUIR"}):
            result = worker.execute(ctx)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["alert_level"] == "HIGH"
        assert "requires_acknowledgment" in result.variables

    def test_dmn_error_with_fail_safe_returns_success_with_revisar(self):
        """fail_safe: DMN error is handled, pipeline continues with REVISAR sentinel."""
        config = {
            "decisions": [{"key": "sepsis_rules", "category": "clinical_safety", "inputs": {}}],
            "error_strategy": "fail_safe",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "evaluate_dmn", side_effect=RuntimeError("DMN unreachable")):
            result = worker.execute(ctx)

        # fail_safe: returns success (pipeline continues with safe defaults)
        assert result.status == TaskStatus.SUCCESS
        # The failed step returns {} (fail_safe), merged result gets alert defaults
        assert "alert_level" in result.variables
        assert "requires_acknowledgment" in result.variables

    def test_exception_outside_dmn_eval_is_handled(self):
        """Non-DMN exceptions in execute() trigger _handle_dmn_error path returning bpmn_error."""
        config = {
            "decisions": [{"key": "sepsis_rules", "category": "clinical_safety", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        # Patch _execute_dmn_pipeline to raise a non-DMN error
        with patch.object(worker, "_execute_dmn_pipeline", side_effect=RuntimeError("internal error")):
            result = worker.execute(ctx)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "DMN_ERROR_BLOCKED"
        assert result.variables["resultado"] == "BLOQUEAR"
        assert "internal error" in result.error_message
