"""Unit tests for GenericDataEnrichmentWorker.

Verifies:
- Default error_strategy is always fail_safe (enrichment failures must not block)
- _tag_enriched_fields() identifies and tags new fields added by DMN
- _tag_enriched_fields() sets _enriched to empty list when no new fields added
- _tag_enriched_fields() logs debug message when fields are tagged
- ARCHETYPE constant is correct
- No-decisions path returns BPMN error
- DMN errors with fail_safe return success (pipeline continues without enrichment)
- DMN errors with fail_closed re-raise
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.shared.workers.generic.data_enrichment import GenericDataEnrichmentWorker


def _make_worker(registry_config, mock_logger=None):
    """Helper: construct worker with mocked dependencies."""
    return GenericDataEnrichmentWorker(
        topic="clinical.patient_enrichment",
        registry_config=registry_config,
        logger=mock_logger or MagicMock(),
    )


def _make_context(**var_overrides):
    """Helper: create a TaskContext with patient data variables."""
    variables = {
        "patientId": "PAT-005",
        "encounterId": "ENC-001",
        "timestamp": "2026-02-17T14:00:00Z",
    }
    variables.update(var_overrides)
    return TaskContext(
        task_id="t-enrichment-001",
        process_instance_id="p-enrichment-001",
        tenant_id="hospital-a",
        variables=variables,
        worker_id="clinical.patient_enrichment",
    )


# ---------------------------------------------------------------------------
# Archetype constant
# ---------------------------------------------------------------------------

class TestArchetypeConstant:
    def test_archetype_constant(self):
        assert GenericDataEnrichmentWorker.ARCHETYPE == "DATA_ENRICHMENT"


# ---------------------------------------------------------------------------
# Default error strategy
# ---------------------------------------------------------------------------

class TestDefaultErrorStrategy:
    def test_default_error_strategy_is_fail_safe_when_not_set(self):
        config = {"decisions": [{"key": "patient_lookup", "category": "clinical_safety", "inputs": {}}]}
        worker = _make_worker(config)
        assert worker.error_strategy == "fail_safe"

    def test_explicit_fail_closed_is_respected(self):
        config = {
            "decisions": [{"key": "patient_lookup", "category": "clinical_safety", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        assert worker.error_strategy == "fail_closed"

    def test_fail_safe_preserved_when_already_set(self):
        config = {
            "decisions": [{"key": "patient_lookup", "category": "clinical_safety", "inputs": {}}],
            "error_strategy": "fail_safe",
        }
        worker = _make_worker(config)
        assert worker.error_strategy == "fail_safe"


# ---------------------------------------------------------------------------
# _tag_enriched_fields
# ---------------------------------------------------------------------------

class TestTagEnrichedFields:
    def test_new_fields_are_tagged_in_enriched_list(self):
        config = {"decisions": [], "error_strategy": "fail_safe"}
        worker = _make_worker(config)
        original_keys = {"patientId", "encounterId"}
        result = {"patientId": "PAT-005", "encounterId": "ENC-001", "riskLevel": "LOW"}
        output = worker._tag_enriched_fields(result, original_keys)
        assert "riskLevel" in output["_enriched"]

    def test_original_fields_not_in_enriched_list(self):
        config = {"decisions": [], "error_strategy": "fail_safe"}
        worker = _make_worker(config)
        original_keys = {"patientId", "encounterId"}
        result = {"patientId": "PAT-005", "encounterId": "ENC-001", "riskLevel": "LOW"}
        output = worker._tag_enriched_fields(result, original_keys)
        assert "patientId" not in output["_enriched"]
        assert "encounterId" not in output["_enriched"]

    def test_no_new_fields_sets_enriched_to_empty_list(self):
        config = {"decisions": [], "error_strategy": "fail_safe"}
        worker = _make_worker(config)
        original_keys = {"patientId", "encounterId"}
        result = {"patientId": "PAT-005", "encounterId": "ENC-001"}
        output = worker._tag_enriched_fields(result, original_keys)
        assert output["_enriched"] == []

    def test_multiple_enriched_fields_all_tagged(self):
        config = {"decisions": [], "error_strategy": "fail_safe"}
        worker = _make_worker(config)
        original_keys = {"patientId"}
        result = {
            "patientId": "PAT-005",
            "riskLevel": "MEDIUM",
            "insurancePlan": "PLAN-ABC",
            "preferredDoctor": "DR-001",
        }
        output = worker._tag_enriched_fields(result, original_keys)
        assert set(output["_enriched"]) == {"riskLevel", "insurancePlan", "preferredDoctor"}

    def test_tag_enriched_fields_returns_modified_result(self):
        config = {"decisions": [], "error_strategy": "fail_safe"}
        worker = _make_worker(config)
        original_keys = {"patientId"}
        result = {"patientId": "PAT-005", "newField": "value"}
        output = worker._tag_enriched_fields(result, original_keys)
        assert "_enriched" in output
        assert output["newField"] == "value"

    def test_tag_enriched_fields_logs_debug_when_fields_added(self):
        config = {"decisions": [], "error_strategy": "fail_safe"}
        mock_logger = MagicMock()
        worker = _make_worker(config, mock_logger=mock_logger)
        original_keys = {"patientId"}
        result = {"patientId": "PAT-005", "riskLevel": "LOW"}
        worker._tag_enriched_fields(result, original_keys)
        mock_logger.debug.assert_called()

    def test_empty_original_keys_all_result_fields_are_enriched(self):
        config = {"decisions": [], "error_strategy": "fail_safe"}
        worker = _make_worker(config)
        result = {"field1": "val1", "field2": "val2"}
        output = worker._tag_enriched_fields(result, set())
        # All fields are new (original_keys is empty), but _enriched itself shouldn't count
        # since it's added after the comparison
        enriched_without_meta = [f for f in output["_enriched"] if f != "_enriched"]
        assert "field1" in enriched_without_meta
        assert "field2" in enriched_without_meta


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
            "decisions": [{"key": "patient_lookup", "category": "clinical_safety", "inputs": {}}],
            "error_strategy": "fail_safe",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "evaluate_dmn", return_value={
            "riskLevel": "LOW",
            "insurancePlan": "PLAN-XYZ",
            "action": "PROSSEGUIR",
        }):
            result = worker.execute(ctx)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["riskLevel"] == "LOW"

    def test_successful_dmn_tags_enriched_fields(self):
        """New fields from DMN are tagged in _enriched metadata."""
        config = {
            "decisions": [{"key": "patient_lookup", "category": "clinical_safety", "inputs": {}}],
            "error_strategy": "fail_safe",
        }
        worker = _make_worker(config)
        ctx = _make_context()  # original keys: patientId, encounterId, timestamp

        with patch.object(worker, "evaluate_dmn", return_value={
            "riskLevel": "HIGH",
            "preferredDoctor": "DR-007",
        }):
            result = worker.execute(ctx)

        assert result.status == TaskStatus.SUCCESS
        assert "_enriched" in result.variables
        assert isinstance(result.variables["_enriched"], list)

    def test_dmn_error_with_fail_safe_returns_success(self):
        """fail_safe: DMN error is handled, pipeline continues without enrichment."""
        config = {
            "decisions": [{"key": "patient_lookup", "category": "clinical_safety", "inputs": {}}],
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
            "decisions": [{"key": "patient_lookup", "category": "clinical_safety", "inputs": {}}],
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
            "decisions": [{"key": "patient_lookup", "category": "clinical_safety", "inputs": {}}],
            "error_strategy": "fail_closed",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "_execute_dmn_pipeline", side_effect=RuntimeError("internal error")):
            result = worker.execute(ctx)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "DMN_ERROR_BLOCKED"

    def test_enriched_metadata_is_list_type(self):
        """_enriched field in output is always a list."""
        config = {
            "decisions": [{"key": "patient_lookup", "category": "clinical_safety", "inputs": {}}],
            "error_strategy": "fail_safe",
        }
        worker = _make_worker(config)
        ctx = _make_context()

        with patch.object(worker, "evaluate_dmn", return_value={}):
            result = worker.execute(ctx)

        assert result.status == TaskStatus.SUCCESS
        assert isinstance(result.variables["_enriched"], list)
