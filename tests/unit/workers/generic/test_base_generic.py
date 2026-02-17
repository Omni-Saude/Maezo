"""Unit tests for GenericWorkerBase.

Tests the core DMN wrapper logic:
- Config field storage and error strategy initialisation
- Input/output mapping
- Single DMN execution
- Pipeline execution and ordering
- Merge strategies (worst_case, best_case, append, override)
- Error handling with fail_closed / fail_safe strategies
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.shared.workers.generic.base_generic import GenericWorkerBase


# ---------------------------------------------------------------------------
# Concrete subclass for testing (GenericWorkerBase is abstract via execute())
# ---------------------------------------------------------------------------

class _ConcreteWorker(GenericWorkerBase):
    """Minimal concrete subclass that delegates execute() to a mock."""

    def execute(self, context: TaskContext) -> TaskResult:
        return TaskResult.success({"executed": True})


def _make_worker(registry_config, mock_dmn_service=None, mock_logger=None):
    """Helper to construct a _ConcreteWorker with injected mocks."""
    dmn_service = mock_dmn_service or MagicMock()
    logger = mock_logger or MagicMock()
    return _ConcreteWorker(
        topic="test.topic",
        registry_config=registry_config,
        dmn_service=dmn_service,
        logger=logger,
    )


# ---------------------------------------------------------------------------
# Initialisation tests
# ---------------------------------------------------------------------------

class TestGenericWorkerBaseInit:
    def test_init_stores_topic(self, sample_registry_config):
        worker = _make_worker(sample_registry_config)
        assert worker.topic == "test.topic"

    def test_init_stores_registry_config(self, sample_registry_config):
        worker = _make_worker(sample_registry_config)
        assert worker.registry_config is sample_registry_config

    def test_init_reads_error_strategy_fail_closed(self, sample_registry_config):
        sample_registry_config["error_strategy"] = "fail_closed"
        worker = _make_worker(sample_registry_config)
        assert worker.error_strategy == "fail_closed"

    def test_init_reads_error_strategy_fail_safe(self, sample_registry_config):
        sample_registry_config["error_strategy"] = "fail_safe"
        worker = _make_worker(sample_registry_config)
        assert worker.error_strategy == "fail_safe"

    def test_init_defaults_error_strategy_to_fail_closed(self):
        config = {"archetype": "ADMIN_ADJUDICATION", "decisions": []}
        worker = _make_worker(config)
        assert worker.error_strategy == "fail_closed"


# ---------------------------------------------------------------------------
# Input mapping
# ---------------------------------------------------------------------------

class TestMapInputs:
    def test_map_inputs_returns_context_variables(self, sample_registry_config, mock_context):
        worker = _make_worker(sample_registry_config)
        result = worker._map_inputs(mock_context)
        assert result == mock_context.variables

    def test_map_inputs_ignores_no_extra_keys(self, sample_registry_config, mock_context):
        """_map_inputs passes through only context.variables — no injection."""
        worker = _make_worker(sample_registry_config)
        result = worker._map_inputs(mock_context)
        # Should not include keys not present in context.variables
        assert "non_existent_key" not in result


# ---------------------------------------------------------------------------
# Single DMN execution
# ---------------------------------------------------------------------------

class TestExecuteSingleDmn:
    def test_execute_single_dmn_calls_evaluate_dmn(self, sample_registry_config, mock_context):
        dmn_service = MagicMock()
        worker = _make_worker(sample_registry_config, mock_dmn_service=dmn_service)

        with patch.object(worker, "evaluate_dmn", return_value={"action": "PROSSEGUIR"}) as mock_eval:
            result = worker._execute_single_dmn(mock_context, "my_decision", {}, "billing")

        mock_eval.assert_called_once_with(mock_context, "my_decision", {}, "billing")
        assert result == {"action": "PROSSEGUIR"}

    def test_execute_single_dmn_uses_default_category(self, sample_registry_config, mock_context):
        worker = _make_worker(sample_registry_config)
        with patch.object(worker, "evaluate_dmn", return_value={}) as mock_eval:
            worker._execute_single_dmn(mock_context, "decision_key", {})
        mock_eval.assert_called_once_with(mock_context, "decision_key", {}, "clinical_safety")

    def test_fail_closed_raises_on_dmn_error(self, sample_registry_config, mock_context):
        sample_registry_config["error_strategy"] = "fail_closed"
        worker = _make_worker(sample_registry_config)

        with patch.object(worker, "evaluate_dmn", side_effect=RuntimeError("DMN down")):
            with pytest.raises(RuntimeError, match="DMN down"):
                worker._execute_single_dmn(mock_context, "decision_key", {})

    def test_fail_safe_returns_empty_dict_on_dmn_error(self, sample_registry_config, mock_context, mock_logger):
        sample_registry_config["error_strategy"] = "fail_safe"
        worker = _make_worker(sample_registry_config, mock_logger=mock_logger)

        with patch.object(worker, "evaluate_dmn", side_effect=RuntimeError("DMN down")):
            result = worker._execute_single_dmn(mock_context, "decision_key", {})

        assert result == {}
        mock_logger.warning.assert_called_once()


# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------

class TestExecuteDmnPipeline:
    def test_execute_pipeline_calls_dmn_in_order(self, sample_pipeline_config, mock_context):
        worker = _make_worker(sample_pipeline_config)
        call_order = []

        def fake_single(ctx, key, inputs, category="default"):
            call_order.append(key)
            return {"step": key}

        with patch.object(worker, "_execute_single_dmn", side_effect=fake_single):
            results = worker._execute_dmn_pipeline(mock_context, sample_pipeline_config["decisions"])

        assert call_order == [
            "audit_documentation_completeness",
            "audit_rule_compliance",
            "audit_priority_classification",
        ]
        assert len(results) == 3

    def test_execute_pipeline_passes_category_per_step(self, mock_context):
        config = {
            "decisions": [
                {"key": "step_a", "category": "cat_a", "inputs": {}},
                {"key": "step_b", "category": "cat_b", "inputs": {}},
            ],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        captured = []

        def fake_single(ctx, key, inputs, category="default"):
            captured.append((key, category))
            return {}

        with patch.object(worker, "_execute_single_dmn", side_effect=fake_single):
            worker._execute_dmn_pipeline(mock_context, config["decisions"])

        assert captured[0] == ("step_a", "cat_a")
        assert captured[1] == ("step_b", "cat_b")

    def test_execute_pipeline_uses_default_category_when_absent(self, mock_context):
        """When no category key in decision config, uses _dmn_category (default: 'clinical_safety')."""
        config = {
            "decisions": [{"key": "step_x", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        captured = []

        def fake_single(ctx, key, inputs, category="clinical_safety"):
            captured.append(category)
            return {}

        with patch.object(worker, "_execute_single_dmn", side_effect=fake_single):
            worker._execute_dmn_pipeline(mock_context, config["decisions"])

        assert captured[0] == "clinical_safety"


# ---------------------------------------------------------------------------
# Merge results
# ---------------------------------------------------------------------------

class TestMergeResults:
    def test_merge_results_combines_all_dicts(self, sample_registry_config):
        worker = _make_worker(sample_registry_config)
        results = [
            {"action": "PROSSEGUIR"},
            {"score": 42},
            {"flag": True},
        ]
        merged = worker._merge_results(results)
        assert merged == {"action": "PROSSEGUIR", "score": 42, "flag": True}

    def test_merge_results_worst_case_picks_most_restrictive(self, sample_registry_config):
        """Default merge strategy is worst_case: REVISAR beats PROSSEGUIR."""
        worker = _make_worker(sample_registry_config)
        results = [{"action": "REVISAR"}, {"action": "PROSSEGUIR"}]
        merged = worker._merge_results(results)
        # worst_case: REVISAR (priority 2) > PROSSEGUIR (priority 1)
        assert merged["action"] == "REVISAR"

    def test_merge_results_skips_empty_dicts(self, sample_registry_config):
        worker = _make_worker(sample_registry_config)
        results = [{}, {"action": "BLOQUEAR"}, {}]
        merged = worker._merge_results(results)
        assert merged == {"action": "BLOQUEAR"}

    def test_merge_results_empty_list_returns_empty_dict(self, sample_registry_config):
        worker = _make_worker(sample_registry_config)
        assert worker._merge_results([]) == {}


# ---------------------------------------------------------------------------
# Output mapping
# ---------------------------------------------------------------------------

class TestMapOutputs:
    def test_map_outputs_returns_merged_unchanged(self, sample_registry_config, mock_context):
        """Default _map_outputs is identity — subclasses can override."""
        worker = _make_worker(sample_registry_config)
        merged = {"action": "PROSSEGUIR", "score": 99}
        result = worker._map_outputs(merged, mock_context)
        assert result == merged


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestHandleDmnError:
    def test_fail_closed_returns_bpmn_error(self, sample_registry_config, mock_context):
        """fail_closed: _handle_dmn_error returns TaskResult.bpmn_error with BLOQUEAR."""
        sample_registry_config["error_strategy"] = "fail_closed"
        worker = _make_worker(sample_registry_config)

        error = ValueError("table missing")
        result = worker._handle_dmn_error(error, mock_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "DMN_ERROR_BLOCKED"
        assert result.variables["resultado"] == "BLOQUEAR"
        assert "table missing" in result.error_message

    def test_fail_safe_returns_revisar_task_result(self, sample_registry_config, mock_context):
        """fail_safe: _handle_dmn_error returns TaskResult.success with REVISAR variables."""
        sample_registry_config["error_strategy"] = "fail_safe"
        worker = _make_worker(sample_registry_config)

        error = ConnectionError("timeout")
        result = worker._handle_dmn_error(error, mock_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "REVISAR"
        assert result.variables["acao"] == "Revisão manual necessária"

    def test_fail_safe_includes_error_info(self, sample_registry_config, mock_context):
        """fail_safe result variables include dmn_error and risco fields."""
        sample_registry_config["error_strategy"] = "fail_safe"
        worker = _make_worker(sample_registry_config)

        error = RuntimeError("connection refused")
        result = worker._handle_dmn_error(error, mock_context)

        assert result.status == TaskStatus.SUCCESS
        assert "dmn_error" in result.variables
        assert result.variables["risco"] == "ALTO"


# ---------------------------------------------------------------------------
# Input mapping with input_map config
# ---------------------------------------------------------------------------

class TestMapInputsWithMapping:
    def test_map_inputs_renames_keys_per_input_map(self, mock_context):
        """When input_map is configured, context keys are renamed before DMN call."""
        config = {
            "archetype": "ADMIN_ADJUDICATION",
            "decisions": [{"key": "claim_rules", "category": "billing", "inputs": {}}],
            "error_strategy": "fail_closed",
            "input_map": {
                "claimId": "claim_id",
                "payerId": "payer_id",
            },
        }
        worker = _make_worker(config)
        result = worker._map_inputs(mock_context)
        # claimId -> claim_id, payerId -> payer_id
        assert "claim_id" in result
        assert "payer_id" in result
        assert "claimId" not in result

    def test_map_inputs_passes_unmapped_keys_unchanged(self, mock_context):
        """Keys not in input_map are forwarded with their original names."""
        config = {
            "archetype": "ADMIN_ADJUDICATION",
            "decisions": [{"key": "claim_rules", "category": "billing", "inputs": {}}],
            "error_strategy": "fail_closed",
            "input_map": {"claimId": "claim_id"},  # only claimId is mapped
        }
        worker = _make_worker(config)
        result = worker._map_inputs(mock_context)
        # amount is not in input_map, passes through unchanged
        assert "amount" in result


# ---------------------------------------------------------------------------
# Output mapping with output_map config
# ---------------------------------------------------------------------------

class TestMapOutputsWithMapping:
    def test_map_outputs_renames_keys_per_output_map(self, mock_context):
        """When output_map is configured, DMN result keys are renamed."""
        config = {
            "archetype": "ADMIN_ADJUDICATION",
            "decisions": [{"key": "claim_rules", "category": "billing", "inputs": {}}],
            "error_strategy": "fail_closed",
            "output_map": {"resultado": "authorization_result", "motivo": "denial_reason"},
        }
        worker = _make_worker(config)
        merged = {"resultado": "PROSSEGUIR", "motivo": "OK"}
        result = worker._map_outputs(merged, mock_context)
        assert "authorization_result" in result
        assert "denial_reason" in result
        assert "resultado" not in result

    def test_map_outputs_passes_unmapped_keys_unchanged(self, mock_context):
        """Keys not in output_map are forwarded unchanged."""
        config = {
            "archetype": "ADMIN_ADJUDICATION",
            "decisions": [{"key": "claim_rules", "category": "billing", "inputs": {}}],
            "error_strategy": "fail_closed",
            "output_map": {"resultado": "authorization_result"},
        }
        worker = _make_worker(config)
        merged = {"resultado": "PROSSEGUIR", "extra_field": "extra_value"}
        result = worker._map_outputs(merged, mock_context)
        assert "extra_field" in result


# ---------------------------------------------------------------------------
# _build_decisions — three config formats
# ---------------------------------------------------------------------------

class TestBuildDecisions:
    def test_build_decisions_from_dmn_pipeline_key(self):
        """dmn_pipeline config format is prioritized first."""
        config = {
            "archetype": "CLINICAL_SCORE",
            "dmn_pipeline": [
                {"key": "step_a", "category": "clinical_safety"},
                {"key": "step_b", "category": "clinical_safety"},
            ],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        decisions = worker._build_decisions()
        assert len(decisions) == 2
        assert decisions[0]["key"] == "step_a"

    def test_build_decisions_from_single_dmn_key(self):
        """dmn_key config format wraps into a one-item list."""
        config = {
            "archetype": "ADMIN_ADJUDICATION",
            "dmn_key": "claim_validation_rules",
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        decisions = worker._build_decisions()
        assert len(decisions) == 1
        assert decisions[0]["key"] == "claim_validation_rules"

    def test_build_decisions_from_legacy_decisions_key(self):
        """decisions (legacy) format is used as fallback."""
        config = {
            "archetype": "ADMIN_ADJUDICATION",
            "decisions": [{"key": "legacy_rule", "category": "billing", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        decisions = worker._build_decisions()
        assert len(decisions) == 1
        assert decisions[0]["key"] == "legacy_rule"

    def test_build_decisions_empty_when_nothing_configured(self):
        config = {"archetype": "ADMIN_ADJUDICATION", "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        decisions = worker._build_decisions()
        assert decisions == []


# ---------------------------------------------------------------------------
# Base class execute() template method (GenericWorkerBase.execute)
# ---------------------------------------------------------------------------

class TestBaseExecuteTemplateMethod:
    """Tests for GenericWorkerBase.execute() — the template-method implementation.

    Uses a minimal subclass that does NOT override execute() so the base
    template method is exercised directly.
    """

    def _make_base_worker(self, config):
        """Create a worker that uses the base execute() template method."""
        # We need a subclass that does NOT override execute()
        class _BaseExecuteWorker(GenericWorkerBase):
            pass  # No execute() override — uses base class template

        return _BaseExecuteWorker(
            topic="test.base.topic",
            registry_config=config,
            logger=MagicMock(),
        )

    def test_base_execute_no_decisions_returns_bpmn_error(self):
        config = {"archetype": "ADMIN_ADJUDICATION", "error_strategy": "fail_closed"}
        worker = self._make_base_worker(config)
        ctx = TaskContext(
            task_id="t-1", process_instance_id="p-1", tenant_id="h-a",
            variables={}, worker_id="test.base.topic",
        )
        result = worker.execute(ctx)
        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "NO_DMN_CONFIGURED"

    def test_base_execute_prosseguir_returns_success(self):
        config = {
            "archetype": "ADMIN_ADJUDICATION",
            "decisions": [{"key": "rule", "category": "billing", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = self._make_base_worker(config)
        ctx = TaskContext(
            task_id="t-1", process_instance_id="p-1", tenant_id="h-a",
            variables={}, worker_id="test.base.topic",
        )
        with patch.object(worker, "evaluate_dmn", return_value={"resultado": "PROSSEGUIR"}):
            result = worker.execute(ctx)
        assert result.status == TaskStatus.SUCCESS

    def test_base_execute_bloquear_returns_bpmn_error(self):
        config = {
            "archetype": "ADMIN_ADJUDICATION",
            "decisions": [{"key": "rule", "category": "billing", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = self._make_base_worker(config)
        ctx = TaskContext(
            task_id="t-1", process_instance_id="p-1", tenant_id="h-a",
            variables={}, worker_id="test.base.topic",
        )
        with patch.object(worker, "evaluate_dmn", return_value={"resultado": "BLOQUEAR", "acao": "Blocked"}):
            result = worker.execute(ctx)
        assert result.status == TaskStatus.BPMN_ERROR


# ---------------------------------------------------------------------------
# Merge strategies: append and override
# ---------------------------------------------------------------------------

class TestApplyMergeStrategy:
    def _make_simple_worker(self):
        config = {"archetype": "ADMIN_ADJUDICATION", "error_strategy": "fail_closed"}
        return _make_worker(config)

    def test_append_strategy_creates_list_on_conflict(self):
        worker = self._make_simple_worker()
        accumulated = {"alerts": "DRUG_INTERACTION"}
        new_result = {"alerts": "ALLERGY"}
        merged = worker._apply_merge_strategy(accumulated, new_result, "append")
        assert merged["alerts"] == ["DRUG_INTERACTION", "ALLERGY"]

    def test_append_strategy_extends_existing_list(self):
        worker = self._make_simple_worker()
        accumulated = {"alerts": ["DRUG_INTERACTION"]}
        new_result = {"alerts": "ALLERGY"}
        merged = worker._apply_merge_strategy(accumulated, new_result, "append")
        assert merged["alerts"] == ["DRUG_INTERACTION", "ALLERGY"]

    def test_append_strategy_adds_new_key(self):
        worker = self._make_simple_worker()
        accumulated = {"score": 5}
        new_result = {"new_field": "value"}
        merged = worker._apply_merge_strategy(accumulated, new_result, "append")
        assert merged["score"] == 5
        assert merged["new_field"] == "value"

    def test_override_strategy_new_value_wins(self):
        worker = self._make_simple_worker()
        accumulated = {"resultado": "REVISAR", "score": 5}
        new_result = {"resultado": "PROSSEGUIR", "score": 10}
        merged = worker._apply_merge_strategy(accumulated, new_result, "override")
        assert merged["resultado"] == "PROSSEGUIR"
        assert merged["score"] == 10

    def test_override_strategy_preserves_accumulated_when_new_is_empty(self):
        worker = self._make_simple_worker()
        accumulated = {"resultado": "REVISAR"}
        merged = worker._apply_merge_strategy(accumulated, {}, "override")
        assert merged["resultado"] == "REVISAR"


# ---------------------------------------------------------------------------
# _execute_dmn_pipeline with decisions=None uses _build_decisions
# ---------------------------------------------------------------------------

class TestExecutePipelineDecisionsNone:
    def test_pipeline_uses_build_decisions_when_no_arg(self, mock_context):
        config = {
            "archetype": "ADMIN_ADJUDICATION",
            "dmn_key": "claim_validation",
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        with patch.object(worker, "evaluate_dmn", return_value={"resultado": "PROSSEGUIR"}):
            results = worker._execute_dmn_pipeline(mock_context)  # No decisions arg
        assert len(results) == 1
        assert results[0]["resultado"] == "PROSSEGUIR"


# ---------------------------------------------------------------------------
# _merge_results with per-step decisions for strategy lookup
# ---------------------------------------------------------------------------

class TestMergeResultsWithDecisions:
    def test_merge_uses_per_step_strategy_from_decisions_list(self):
        config = {"archetype": "CLINICAL_SCORE", "error_strategy": "fail_closed"}
        worker = _make_worker(config)
        decisions = [
            {"key": "step1", "merge_strategy": "append"},
            {"key": "step2", "merge_strategy": "append"},
        ]
        results = [{"alerts": "DRUG"}, {"alerts": "ALLERGY"}]
        merged = worker._merge_results(results, decisions)
        assert merged["alerts"] == ["DRUG", "ALLERGY"]

    def test_merge_falls_back_to_global_strategy_when_step_has_no_strategy(self):
        config = {
            "archetype": "ADMIN_ADJUDICATION",
            "merge_strategy": "override",
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        decisions = [
            {"key": "step1"},  # No merge_strategy key
        ]
        results = [{"resultado": "BLOQUEAR"}]
        merged = worker._merge_results(results, decisions)
        assert merged["resultado"] == "BLOQUEAR"
