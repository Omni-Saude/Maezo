"""
Unit tests for pipeline execution patterns and merge strategies in GenericWorkerBase.

Tests cover the behaviour of _execute_dmn_pipeline with various combinations:
- fail_closed vs fail_safe error handling per step
- Partial failures in multi-step pipelines
- Empty pipelines
- Single-step pipelines
- _merge_results as the de-facto "override/append" strategy
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.shared.workers.generic.base_generic import GenericWorkerBase


# ---------------------------------------------------------------------------
# Minimal concrete subclass
# ---------------------------------------------------------------------------

class _PipelineWorker(GenericWorkerBase):
    def execute(self, context: TaskContext) -> TaskResult:  # pragma: no cover
        return TaskResult.success({})


def _make_worker(registry_config, mock_logger=None):
    return _PipelineWorker(
        topic="test.pipeline.worker",
        registry_config=registry_config,
        dmn_service=MagicMock(),
        logger=mock_logger or MagicMock(),
    )


def _make_context(**overrides):
    variables = {"patientId": "PAT-TEST-001", "amount": 100.0}
    variables.update(overrides)
    return TaskContext(
        task_id="t-pipeline-001",
        process_instance_id="p-pipeline-001",
        tenant_id="HOSPITAL_A",
        variables=variables,
        worker_id="test.pipeline.worker",
    )


# ---------------------------------------------------------------------------
# Pipeline with all successes
# ---------------------------------------------------------------------------

class TestPipelineAllSuccess:

    def test_all_steps_return_results(self):
        config = {
            "decisions": [
                {"key": "step1", "category": "default", "inputs": {}},
                {"key": "step2", "category": "default", "inputs": {}},
            ],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "evaluate_dmn", side_effect=[
            {"action": "PROSSEGUIR"},
            {"score": 5},
        ]):
            results = worker._execute_dmn_pipeline(ctx, config["decisions"])

        assert len(results) == 2
        assert results[0] == {"action": "PROSSEGUIR"}
        assert results[1] == {"score": 5}

    def test_merge_of_all_success_results(self):
        config = {
            "decisions": [
                {"key": "step1", "category": "default", "inputs": {}},
                {"key": "step2", "category": "default", "inputs": {}},
            ],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "evaluate_dmn", side_effect=[
            {"action": "PROSSEGUIR"},
            {"score": 5},
        ]):
            results = worker._execute_dmn_pipeline(ctx, config["decisions"])

        merged = worker._merge_results(results)
        assert merged == {"action": "PROSSEGUIR", "score": 5}

    def test_pipeline_single_step_returns_single_result(self):
        config = {
            "decisions": [{"key": "only_step", "category": "default", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "evaluate_dmn", return_value={"decision": "OK"}):
            results = worker._execute_dmn_pipeline(ctx, config["decisions"])

        assert len(results) == 1
        assert results[0] == {"decision": "OK"}

    def test_empty_pipeline_returns_empty_list(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        ctx = _make_context()

        results = worker._execute_dmn_pipeline(ctx, [])
        assert results == []


# ---------------------------------------------------------------------------
# "Worst case" merge semantics (last writer wins with specific keys)
# ---------------------------------------------------------------------------

class TestWorstCaseMerge:
    """
    GenericWorkerBase._merge_results is override (last-wins).
    Worst-case semantics for adjudication outcomes (BLOQUEAR > REVISAR > PROSSEGUIR)
    must be implemented at the execute() level by subclasses, not in the base merge.
    These tests verify the base merge behaviour so subclasses can build on top of it.
    """

    def test_worst_case_explicit_bloquear_key_wins_via_override(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        # Simulate two steps: second step with BLOQUEAR overrides first
        results = [
            {"resultado": "PROSSEGUIR"},
            {"resultado": "BLOQUEAR"},
        ]
        merged = worker._merge_results(results)
        assert merged["resultado"] == "BLOQUEAR"

    def test_worst_case_revisar_overrides_prosseguir(self):
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        results = [
            {"resultado": "PROSSEGUIR"},
            {"resultado": "REVISAR"},
        ]
        merged = worker._merge_results(results)
        assert merged["resultado"] == "REVISAR"

    def test_prosseguir_does_not_override_bloquear_when_earlier(self):
        """worst_case strategy keeps BLOQUEAR even when PROSSEGUIR comes later."""
        config = {"decisions": [], "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        # Default merge_strategy is worst_case: BLOQUEAR (priority 3) beats PROSSEGUIR (1)
        results = [
            {"resultado": "BLOQUEAR"},
            {"resultado": "PROSSEGUIR"},
        ]
        merged = worker._merge_results(results)
        # worst_case: BLOQUEAR is most restrictive and wins regardless of order
        assert merged["resultado"] == "BLOQUEAR"


# ---------------------------------------------------------------------------
# "Best case" / accumulate merge semantics
# ---------------------------------------------------------------------------

class TestBestCaseMerge:

    def test_best_case_prosseguir_wins_over_revisar(self):
        """best_case strategy keeps least restrictive: PROSSEGUIR (priority 1) beats REVISAR (2)."""
        config = {"decisions": [], "error_strategy": "fail_safe", "merge_strategy": "best_case"}
        worker = _make_worker(config)
        results = [{"resultado": "REVISAR"}, {"resultado": "PROSSEGUIR"}]
        merged = worker._merge_results(results)
        # best_case: PROSSEGUIR has lower priority (1 < 2) so it wins
        assert merged["resultado"] == "PROSSEGUIR"

    def test_non_conflicting_keys_accumulate(self):
        config = {"decisions": [], "error_strategy": "fail_safe"}
        worker = _make_worker(config)
        results = [{"score": 3}, {"alert_level": "LOW"}, {"route": "BED_01"}]
        merged = worker._merge_results(results)
        assert merged["score"] == 3
        assert merged["alert_level"] == "LOW"
        assert merged["route"] == "BED_01"

    def test_empty_results_from_fail_safe_skipped(self):
        """Empty dicts (from fail_safe) are skipped in merge."""
        config = {"decisions": [], "error_strategy": "fail_safe"}
        worker = _make_worker(config)
        results = [{}, {"good_key": "value"}, {}]
        merged = worker._merge_results(results)
        assert merged == {"good_key": "value"}


# ---------------------------------------------------------------------------
# Pipeline failure handling
# ---------------------------------------------------------------------------

class TestPipelineErrorHandling:

    def test_pipeline_error_fail_closed_raises(self):
        config = {
            "decisions": [{"key": "step1", "category": "default", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "evaluate_dmn", side_effect=RuntimeError("DMN timeout")):
            with pytest.raises(RuntimeError, match="DMN timeout"):
                worker._execute_dmn_pipeline(ctx, config["decisions"])

    def test_pipeline_error_fail_safe_returns_empty_for_failed_step(self):
        config = {
            "decisions": [{"key": "step1", "category": "default", "inputs": {}}],
            "error_strategy": "fail_safe",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "evaluate_dmn", side_effect=RuntimeError("timeout")):
            results = worker._execute_dmn_pipeline(ctx, config["decisions"])

        assert results == [{}]  # fail_safe returns empty dict for failed step

    def test_partial_pipeline_failure_fail_safe_succeeds_for_good_steps(self):
        config = {
            "decisions": [
                {"key": "step_ok", "category": "default", "inputs": {}},
                {"key": "step_fail", "category": "default", "inputs": {}},
                {"key": "step_ok2", "category": "default", "inputs": {}},
            ],
            "error_strategy": "fail_safe",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        def fake_eval(ctx, key, inputs, category="default"):
            if key == "step_fail":
                raise RuntimeError("step failure")
            return {"from": key}

        with patch.object(worker, "evaluate_dmn", side_effect=fake_eval):
            results = worker._execute_dmn_pipeline(ctx, config["decisions"])

        # step_ok succeeds, step_fail returns {}, step_ok2 succeeds
        assert len(results) == 3
        assert results[0] == {"from": "step_ok"}
        assert results[1] == {}  # failed step -> empty
        assert results[2] == {"from": "step_ok2"}

    def test_partial_pipeline_failure_fail_closed_stops_at_first_error(self):
        config = {
            "decisions": [
                {"key": "step_ok", "category": "default", "inputs": {}},
                {"key": "step_fail", "category": "default", "inputs": {}},
            ],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        def fake_eval(ctx, key, inputs, category="default"):
            if key == "step_fail":
                raise RuntimeError("hard failure")
            return {"from": key}

        with patch.object(worker, "evaluate_dmn", side_effect=fake_eval):
            with pytest.raises(RuntimeError, match="hard failure"):
                worker._execute_dmn_pipeline(ctx, config["decisions"])

    def test_pipeline_with_mixed_results_and_fail_safe(self):
        """Combination of successful and failed steps (fail_safe) merges correctly."""
        config = {
            "decisions": [
                {"key": "s1", "category": "default", "inputs": {}},
                {"key": "s2", "category": "default", "inputs": {}},
            ],
            "error_strategy": "fail_safe",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        def fake_eval(ctx, key, inputs, category="default"):
            if key == "s2":
                raise RuntimeError("transient")
            return {"result_from": key}

        with patch.object(worker, "evaluate_dmn", side_effect=fake_eval):
            results = worker._execute_dmn_pipeline(ctx, config["decisions"])

        merged = worker._merge_results(results)
        assert merged == {"result_from": "s1"}  # s2 was {}, skipped in merge
