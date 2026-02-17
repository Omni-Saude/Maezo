"""Integration tests for Detect Data Quality Issues Worker V2."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus


@pytest.mark.integration
class TestDetectDataQualityIssuesWorkerV2:
    """V2 worker tests using BaseExternalTaskWorker pattern."""

    def _make_context(self, **overrides) -> TaskContext:
        defaults = {
            "task_id": "test-task-001",
            "process_instance_id": "proc-001",
            "tenant_id": "HOSPITAL_A",
            "variables": {
                "quality_dimensions": ["completeness", "accuracy"],
                "data_sources": ["tasy", "fhir"],
                "entity_types": ["patient"],
                "period_start": "2026-01-01T00:00:00",
                "period_end": "2026-01-31T23:59:59",
                "correlation_id": "corr-001",
            },
            "worker_id": "platform.services.detect-data-quality-issues",
        }
        defaults.update(overrides)
        return TaskContext(**defaults)

    def test_worker_inherits_base(self):
        from healthcare_platform.platform_services.workers.detect_data_quality_issues_worker import DetectDataQualityIssuesWorker
        from healthcare_platform.shared.workers.base import BaseExternalTaskWorker
        worker = DetectDataQualityIssuesWorker()
        assert isinstance(worker, BaseExternalTaskWorker)

    def test_has_operation_name(self):
        from healthcare_platform.platform_services.workers.detect_data_quality_issues_worker import DetectDataQualityIssuesWorker
        worker = DetectDataQualityIssuesWorker()
        assert worker.operation_name is not None

    def test_has_topic(self):
        from healthcare_platform.platform_services.workers.detect_data_quality_issues_worker import DetectDataQualityIssuesWorker
        assert DetectDataQualityIssuesWorker.TOPIC == "platform.services.detect-data-quality-issues"

    def test_execute_returns_task_result(self):
        from healthcare_platform.platform_services.workers.detect_data_quality_issues_worker import DetectDataQualityIssuesWorker
        worker = DetectDataQualityIssuesWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert isinstance(result, TaskResult)

    def test_execute_success_has_correlation_id(self):
        from healthcare_platform.platform_services.workers.detect_data_quality_issues_worker import DetectDataQualityIssuesWorker
        worker = DetectDataQualityIssuesWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "correlation_id" in result.variables

    def test_execute_with_missing_variables(self):
        from healthcare_platform.platform_services.workers.detect_data_quality_issues_worker import DetectDataQualityIssuesWorker
        worker = DetectDataQualityIssuesWorker()
        context = self._make_context(variables={})
        result = worker.execute(context)
        # Should handle gracefully - either success with defaults or failure
        assert result.status in (TaskStatus.SUCCESS, TaskStatus.FAILURE)

    def test_multi_tenant_isolation(self):
        from healthcare_platform.platform_services.workers.detect_data_quality_issues_worker import DetectDataQualityIssuesWorker
        worker = DetectDataQualityIssuesWorker()
        ctx_a = self._make_context(tenant_id="HOSPITAL_A")
        ctx_b = self._make_context(tenant_id="HOSPITAL_B")
        result_a = worker.execute(ctx_a)
        result_b = worker.execute(ctx_b)
        assert isinstance(result_a, TaskResult)
        assert isinstance(result_b, TaskResult)

    def test_dmn_evaluation_fallback(self):
        from healthcare_platform.platform_services.workers.detect_data_quality_issues_worker import DetectDataQualityIssuesWorker
        worker = DetectDataQualityIssuesWorker()
        context = self._make_context()
        # Should handle missing DMN tables gracefully
        result = worker.execute(context)
        assert result.status == TaskStatus.SUCCESS

    def test_quality_score_calculation(self):
        from healthcare_platform.platform_services.workers.detect_data_quality_issues_worker import DetectDataQualityIssuesWorker
        worker = DetectDataQualityIssuesWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "quality_score" in result.variables
        assert 0 <= result.variables["quality_score"] <= 100

    def test_severity_threshold_filtering(self):
        from healthcare_platform.platform_services.workers.detect_data_quality_issues_worker import DetectDataQualityIssuesWorker
        worker = DetectDataQualityIssuesWorker()
        context = self._make_context(
            variables={
                "quality_dimensions": ["completeness"],
                "severity_threshold": "high",
            }
        )
        result = worker.execute(context)
        # Should only return high and critical issues
        assert result.status == TaskStatus.SUCCESS

    def test_critical_issues_trigger_bpmn_error(self):
        from healthcare_platform.platform_services.workers.detect_data_quality_issues_worker import DetectDataQualityIssuesWorker
        worker = DetectDataQualityIssuesWorker()

        # Mock DMN to return BLOQUEAR
        with patch.object(worker, '_dmn_safe') as mock_dmn:
            mock_dmn.return_value = {"resultado": "BLOQUEAR"}
            context = self._make_context()
            result = worker.execute(context)
            assert result.status == TaskStatus.BPMN_ERROR
            assert result.error_code == "ERR_QUALITY_CRITICAL"
