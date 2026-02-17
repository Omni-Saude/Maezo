"""Unit tests for GenericComplianceValidationWorker.

Verifies:
- Default error_strategy is always fail_closed (compliance must block on failure)
- _ensure_compliance_fields() defaults compliant to False when missing
- _ensure_compliance_fields() defaults violations to list type
- _ensure_compliance_fields() adds explanatory violation when compliant=False and violations empty
- Valid compliance fields pass through unchanged
- ARCHETYPE constant is correct
- No-decisions path returns BPMN error
- DMN errors with fail_closed re-raise (regulatory violations must not be ignored)
- DMN errors with fail_safe return success
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.shared.workers.generic.compliance_validation import GenericComplianceValidationWorker


def _make_worker(registry_config, mock_logger=None):
    """Helper: construct worker with mocked dependencies."""
    return GenericComplianceValidationWorker(
        topic="compliance.ans_validation",
        registry_config=registry_config,
        logger=mock_logger or MagicMock(),
    )


def _make_context(**var_overrides):
    """Helper: create a TaskContext with compliance-relevant variables."""
    variables = {
        "claimId": "CLM-456",
        "payerId": "ANS-001",
        "procedureCode": "10.01.08-0",
        "patientId": "PAT-003",
        "timestamp": "2026-02-17T12:00:00Z",
    }
    variables.update(var_overrides)
    return TaskContext(
        task_id="t-compliance-001",
        process_instance_id="p-compliance-001",
        tenant_id="hospital-a",
        variables=variables,
        worker_id="compliance.ans_validation",
    )


# ---------------------------------------------------------------------------
# Archetype constant
# ---------------------------------------------------------------------------

class TestArchetypeConstant:
    def test_archetype_constant(self):
        assert GenericComplianceValidationWorker.ARCHETYPE == "COMPLIANCE_VALIDATION"


# ---------------------------------------------------------------------------
# Default error strategy
# ---------------------------------------------------------------------------

class TestDefaultErrorStrategy:
    def test_default_error_strategy_is_fail_closed_when_not_set(self):
        config = {"decisions": [{"key": "ans_rules", "category": "billing", "inputs": {}}]}
        worker = _make_worker(config)
        assert worker.error_strategy == "fail_closed"

    def test_explicit_fail_safe_is_respected(self):
        config = {
            "decisions": [{"key": "ans_rules", "category": "billing", "inputs": {}}],
            "error_strategy": "fail_safe",
        }
        worker = _make_worker(config)
        assert worker.error_strategy == "fail_safe"

    def test_fail_closed_preserved_when_already_set(self):
        config = {
            "decisions": [{"key": "ans_rules", "category": "billing", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        assert worker.error_strategy == "fail_closed"


# ---------------------------------------------------------------------------
# _ensure_compliance_fields
# ---------------------------------------------------------------------------

class TestEnsureComplianceFields:
    def test_missing_compliant_defaults_to_false(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._ensure_compliance_fields({})
        assert result["compliant"] is False

    def test_existing_compliant_true_is_preserved(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._ensure_compliance_fields({"compliant": True})
        assert result["compliant"] is True

    def test_existing_compliant_false_is_preserved(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._ensure_compliance_fields({"compliant": False, "violations": ["missing_auth"]})
        assert result["compliant"] is False

    def test_missing_violations_defaults_to_empty_list_when_compliant(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._ensure_compliance_fields({"compliant": True})
        assert isinstance(result["violations"], list)
        assert result["violations"] == []

    def test_non_compliant_without_violations_gets_explanatory_entry(self):
        """When compliant=False and no violations given, adds explanatory violation."""
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._ensure_compliance_fields({"compliant": False})
        assert isinstance(result["violations"], list)
        assert len(result["violations"]) >= 1
        assert "unclear" in result["violations"][0].lower() or "compliance" in result["violations"][0].lower()

    def test_existing_violations_list_is_preserved(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        violations = ["ANS_AUTH_MISSING", "PROCEDURE_NOT_COVERED"]
        result = worker._ensure_compliance_fields({"compliant": False, "violations": violations})
        assert result["violations"] == violations

    def test_scalar_violations_wrapped_in_list(self):
        """When violations is a string (scalar), it must be converted to a list."""
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        result = worker._ensure_compliance_fields({"compliant": False, "violations": "MISSING_DOCS"})
        assert isinstance(result["violations"], list)

    def test_missing_compliant_logs_warning(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        mock_logger = MagicMock()
        worker = _make_worker(config, mock_logger=mock_logger)
        worker._ensure_compliance_fields({})
        mock_logger.warning.assert_called()


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
            "decisions": [{"key": "ans_rules", "category": "billing", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "evaluate_dmn", return_value={
            "compliant": True,
            "violations": [],
            "action": "PROSSEGUIR",
        }):
            result = worker.execute(ctx)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["compliant"] is True
        assert result.variables["violations"] == []

    def test_successful_dmn_ensures_compliance_fields_present(self):
        """DMN output without compliance fields gets defaults applied."""
        config = {
            "decisions": [{"key": "ans_rules", "category": "billing", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "evaluate_dmn", return_value={"action": "PROSSEGUIR"}):
            result = worker.execute(ctx)

        assert result.status == TaskStatus.SUCCESS
        assert "compliant" in result.variables
        assert "violations" in result.variables

    def test_non_compliant_result_still_returns_success(self):
        """A non-compliant verdict is a valid business outcome — not an error."""
        config = {
            "decisions": [{"key": "ans_rules", "category": "billing", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "evaluate_dmn", return_value={
            "compliant": False,
            "violations": ["ANS_AUTH_MISSING"],
            "action": "BLOQUEAR",
        }):
            result = worker.execute(ctx)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["compliant"] is False

    def test_dmn_error_with_fail_closed_returns_bpmn_error(self):
        """fail_closed: DMN errors surface as BPMN error so Camunda triggers error boundary."""
        config = {
            "decisions": [{"key": "ans_rules", "category": "billing", "inputs": {}}],
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
            "decisions": [{"key": "ans_rules", "category": "billing", "inputs": {}}],
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
            "decisions": [{"key": "ans_rules", "category": "billing", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "_execute_dmn_pipeline", side_effect=RuntimeError("internal error")):
            result = worker.execute(ctx)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "DMN_ERROR_BLOCKED"
