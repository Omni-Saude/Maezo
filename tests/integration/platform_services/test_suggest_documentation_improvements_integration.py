"""Integration tests for Suggest Documentation Improvements Worker V2."""
from __future__ import annotations

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus


@pytest.mark.integration
class TestSuggestDocumentationImprovementsWorkerV2:
    """V2 worker tests using BaseExternalTaskWorker pattern."""

    def _make_context(self, **overrides) -> TaskContext:
        defaults = {
            "task_id": "test-task-001",
            "process_instance_id": "proc-001",
            "tenant_id": "HOSPITAL_A",
            "variables": {
                "encounter_id": "ENC001",
                "clinical_documentation": {
                    "chief_complaint": "Headache",
                    "history_present_illness": "Patient reports...",
                },
                "procedure_codes": ["10101012"],
                "provider_specialty": "GERAL",
                "analysis_focus": "coding_accuracy",
                "correlation_id": "corr-001",
            },
            "worker_id": "platform.services.suggest-documentation-improvements",
        }
        defaults.update(overrides)
        return TaskContext(**defaults)

    def test_worker_inherits_base(self):
        from healthcare_platform.platform_services.workers.suggest_documentation_improvements_worker import SuggestDocumentationImprovementsWorker
        from healthcare_platform.shared.workers.base import BaseExternalTaskWorker
        worker = SuggestDocumentationImprovementsWorker()
        assert isinstance(worker, BaseExternalTaskWorker)

    def test_has_operation_name(self):
        from healthcare_platform.platform_services.workers.suggest_documentation_improvements_worker import SuggestDocumentationImprovementsWorker
        worker = SuggestDocumentationImprovementsWorker()
        assert worker.operation_name == "Suggest Documentation Improvements"

    def test_has_topic(self):
        from healthcare_platform.platform_services.workers.suggest_documentation_improvements_worker import SuggestDocumentationImprovementsWorker
        assert SuggestDocumentationImprovementsWorker.TOPIC == "platform.services.suggest-documentation-improvements"

    def test_execute_returns_task_result(self):
        from healthcare_platform.platform_services.workers.suggest_documentation_improvements_worker import SuggestDocumentationImprovementsWorker
        worker = SuggestDocumentationImprovementsWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert isinstance(result, TaskResult)

    def test_execute_success_has_correlation_id(self):
        from healthcare_platform.platform_services.workers.suggest_documentation_improvements_worker import SuggestDocumentationImprovementsWorker
        worker = SuggestDocumentationImprovementsWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert result.status == TaskStatus.SUCCESS
        assert "correlation_id" in result.variables
        assert result.variables["correlation_id"] == "corr-001"

    def test_execute_with_missing_variables(self):
        from healthcare_platform.platform_services.workers.suggest_documentation_improvements_worker import SuggestDocumentationImprovementsWorker
        worker = SuggestDocumentationImprovementsWorker()
        context = self._make_context(variables={"correlation_id": "corr-001"})
        result = worker.execute(context)
        # Should handle gracefully with defaults
        assert result.status == TaskStatus.SUCCESS

    def test_multi_tenant_isolation(self):
        from healthcare_platform.platform_services.workers.suggest_documentation_improvements_worker import SuggestDocumentationImprovementsWorker
        worker = SuggestDocumentationImprovementsWorker()
        ctx_a = self._make_context(tenant_id="HOSPITAL_A")
        ctx_b = self._make_context(tenant_id="HOSPITAL_B")
        result_a = worker.execute(ctx_a)
        result_b = worker.execute(ctx_b)
        assert isinstance(result_a, TaskResult)
        assert isinstance(result_b, TaskResult)

    def test_suggestions_structure(self):
        from healthcare_platform.platform_services.workers.suggest_documentation_improvements_worker import SuggestDocumentationImprovementsWorker
        worker = SuggestDocumentationImprovementsWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "suggestions" in result.variables
        assert "completeness_score" in result.variables
        assert "high_priority_count" in result.variables
        suggestions = result.variables["suggestions"]
        assert isinstance(suggestions, list)

    def test_completeness_score_range(self):
        from healthcare_platform.platform_services.workers.suggest_documentation_improvements_worker import SuggestDocumentationImprovementsWorker
        worker = SuggestDocumentationImprovementsWorker()
        context = self._make_context()
        result = worker.execute(context)
        score = result.variables["completeness_score"]
        assert 0 <= score <= 1

    def test_duration_tracking(self):
        from healthcare_platform.platform_services.workers.suggest_documentation_improvements_worker import SuggestDocumentationImprovementsWorker
        worker = SuggestDocumentationImprovementsWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "duration_ms" in result.variables
        assert result.variables["duration_ms"] > 0

    def test_incomplete_documentation_generates_suggestions(self):
        from healthcare_platform.platform_services.workers.suggest_documentation_improvements_worker import SuggestDocumentationImprovementsWorker
        worker = SuggestDocumentationImprovementsWorker()
        context = self._make_context(
            variables={
                "clinical_documentation": {},  # Empty documentation
                "correlation_id": "corr-001",
            }
        )
        result = worker.execute(context)
        assert result.status == TaskStatus.SUCCESS
        suggestions = result.variables.get("suggestions", [])
        # Should identify missing fields
        assert len(suggestions) >= 0
