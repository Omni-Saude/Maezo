"""Unit tests for GenericClinicalScoreWorker.

Verifies:
- Default error_strategy is always fail_safe
- _normalize_scores() clamps values to [0, 100]
- _normalize_scores() replaces non-numeric values with 0.0
- Score fields not in result are left unchanged
- ARCHETYPE constant is correct
- No-decisions path returns BPMN error
- DMN errors with fail_safe return success (pipeline continues)
- DMN errors with fail_closed re-raise
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.shared.workers.generic.clinical_score import GenericClinicalScoreWorker


def _make_worker(registry_config, mock_logger=None):
    """Helper: construct worker with mocked dependencies."""
    return GenericClinicalScoreWorker(
        topic="clinical.audit_score",
        registry_config=registry_config,
        logger=mock_logger or MagicMock(),
    )


def _make_context(**var_overrides):
    """Helper: create a minimal TaskContext with clinical scoring variables."""
    variables = {
        "patientId": "PAT-001",
        "auditId": "AUD-123",
        "documentationCompleteness": 0.85,
        "timestamp": "2026-02-17T10:00:00Z",
    }
    variables.update(var_overrides)
    return TaskContext(
        task_id="t-score-001",
        process_instance_id="p-score-001",
        tenant_id="hospital-a",
        variables=variables,
        worker_id="clinical.audit_score",
    )


# ---------------------------------------------------------------------------
# Archetype constant
# ---------------------------------------------------------------------------

class TestArchetypeConstant:
    def test_archetype_constant(self):
        assert GenericClinicalScoreWorker.ARCHETYPE == "CLINICAL_SCORE"


# ---------------------------------------------------------------------------
# Default error strategy
# ---------------------------------------------------------------------------

class TestDefaultErrorStrategy:
    def test_default_error_strategy_is_fail_safe_when_not_set(self):
        config = {"decisions": [{"key": "audit_score_rules", "category": "clinical_safety", "inputs": {}}]}
        worker = _make_worker(config)
        assert worker.error_strategy == "fail_safe"

    def test_explicit_fail_closed_is_respected(self):
        config = {
            "decisions": [{"key": "audit_score_rules", "category": "clinical_safety", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        assert worker.error_strategy == "fail_closed"

    def test_fail_safe_preserved_when_already_set(self):
        config = {
            "decisions": [{"key": "audit_score_rules", "category": "clinical_safety", "inputs": {}}],
            "error_strategy": "fail_safe",
        }
        worker = _make_worker(config)
        assert worker.error_strategy == "fail_safe"


# ---------------------------------------------------------------------------
# _normalize_scores
# ---------------------------------------------------------------------------

class TestNormalizeScores:
    def test_score_within_range_is_unchanged(self):
        config = {"decisions": [], "error_strategy": "fail_safe"}
        worker = _make_worker(config)
        result = worker._normalize_scores({"score": 75.0})
        assert result["score"] == 75.0

    def test_score_above_100_is_clamped_to_100(self):
        config = {"decisions": [], "error_strategy": "fail_safe"}
        worker = _make_worker(config)
        result = worker._normalize_scores({"score": 150.0})
        assert result["score"] == 100.0

    def test_score_below_0_is_clamped_to_0(self):
        config = {"decisions": [], "error_strategy": "fail_safe"}
        worker = _make_worker(config)
        result = worker._normalize_scores({"score": -10.0})
        assert result["score"] == 0.0

    def test_audit_score_field_is_normalized(self):
        config = {"decisions": [], "error_strategy": "fail_safe"}
        worker = _make_worker(config)
        result = worker._normalize_scores({"audit_score": 120.0})
        assert result["audit_score"] == 100.0

    def test_compliance_score_field_is_normalized(self):
        config = {"decisions": [], "error_strategy": "fail_safe"}
        worker = _make_worker(config)
        result = worker._normalize_scores({"compliance_score": -5.0})
        assert result["compliance_score"] == 0.0

    def test_risk_score_field_is_normalized(self):
        config = {"decisions": [], "error_strategy": "fail_safe"}
        worker = _make_worker(config)
        result = worker._normalize_scores({"risk_score": 50.0})
        assert result["risk_score"] == 50.0

    def test_non_numeric_score_replaced_with_zero(self):
        config = {"decisions": [], "error_strategy": "fail_safe"}
        mock_logger = MagicMock()
        worker = _make_worker(config, mock_logger=mock_logger)
        result = worker._normalize_scores({"score": "HIGH"})
        assert result["score"] == 0.0

    def test_none_score_replaced_with_zero(self):
        config = {"decisions": [], "error_strategy": "fail_safe"}
        worker = _make_worker(config)
        result = worker._normalize_scores({"score": None})
        assert result["score"] == 0.0

    def test_non_score_fields_left_unchanged(self):
        config = {"decisions": [], "error_strategy": "fail_safe"}
        worker = _make_worker(config)
        result = worker._normalize_scores({"action": "PROSSEGUIR", "reason": "OK"})
        assert result["action"] == "PROSSEGUIR"
        assert result["reason"] == "OK"

    def test_multiple_score_fields_normalized_together(self):
        config = {"decisions": [], "error_strategy": "fail_safe"}
        worker = _make_worker(config)
        result = worker._normalize_scores({
            "score": 110.0,
            "audit_score": 90.0,
            "compliance_score": -1.0,
        })
        assert result["score"] == 100.0
        assert result["audit_score"] == 90.0
        assert result["compliance_score"] == 0.0


# ---------------------------------------------------------------------------
# execute() integration-level unit tests
# ---------------------------------------------------------------------------

class TestExecute:
    def test_no_decisions_returns_bpmn_error(self):
        config = {"decisions": [], "error_strategy": "fail_safe"}
        worker = _make_worker(config)
        ctx = _make_context()
        result = worker.execute(ctx)
        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "NO_DECISIONS_CONFIGURED"

    def test_successful_dmn_returns_success(self):
        config = {
            "decisions": [{"key": "audit_score_rules", "category": "clinical_safety", "inputs": {}}],
            "error_strategy": "fail_safe",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "evaluate_dmn", return_value={"score": 85.0, "action": "PROSSEGUIR"}):
            result = worker.execute(ctx)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["score"] == 85.0

    def test_successful_dmn_normalizes_score_in_output(self):
        config = {
            "decisions": [{"key": "audit_score_rules", "category": "clinical_safety", "inputs": {}}],
            "error_strategy": "fail_safe",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "evaluate_dmn", return_value={"score": 150.0}):
            result = worker.execute(ctx)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["score"] == 100.0

    def test_dmn_error_with_fail_safe_continues_pipeline(self):
        """fail_safe: DMN evaluation failure returns empty dict; pipeline continues."""
        config = {
            "decisions": [{"key": "audit_score_rules", "category": "clinical_safety", "inputs": {}}],
            "error_strategy": "fail_safe",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "evaluate_dmn", side_effect=RuntimeError("DMN unreachable")):
            result = worker.execute(ctx)

        # fail_safe: pipeline continues — no exception raised
        assert result.status == TaskStatus.SUCCESS

    def test_dmn_error_with_fail_closed_returns_bpmn_error(self):
        """fail_closed: DMN errors surface as BPMN error so Camunda triggers error boundary."""
        config = {
            "decisions": [{"key": "audit_score_rules", "category": "clinical_safety", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "evaluate_dmn", side_effect=RuntimeError("connection lost")):
            result = worker.execute(ctx)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "DMN_ERROR_BLOCKED"
        assert result.variables["resultado"] == "BLOQUEAR"

    def test_exception_outside_dmn_eval_returns_bpmn_error_for_fail_closed(self):
        """Non-DMN exceptions in execute() surface as BPMN error for fail_closed."""
        config = {
            "decisions": [{"key": "audit_score_rules", "category": "clinical_safety", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "_execute_dmn_pipeline", side_effect=RuntimeError("internal error")):
            result = worker.execute(ctx)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "DMN_ERROR_BLOCKED"
