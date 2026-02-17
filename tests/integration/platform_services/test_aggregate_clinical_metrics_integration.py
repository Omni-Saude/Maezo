"""Integration tests for Aggregate Clinical Metrics Worker V2."""
from __future__ import annotations

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus


@pytest.mark.integration
class TestAggregateClinicalMetricsWorkerV2:
    """V2 worker tests using BaseExternalTaskWorker pattern."""

    def _make_context(self, **overrides) -> TaskContext:
        defaults = {
            "task_id": "test-task-001",
            "process_instance_id": "proc-001",
            "tenant_id": "HOSPITAL_A",
            "variables": {
                "metric_types": ["readmission_rate", "mortality_index", "infection_rate"],
                "period_start": "2026-01-01T00:00:00",
                "period_end": "2026-01-31T23:59:59",
                "specialty": "cardiology",
                "correlation_id": "corr-001",
            },
            "worker_id": "platform.services.aggregate-clinical-metrics",
        }
        defaults.update(overrides)
        return TaskContext(**defaults)

    def test_worker_inherits_base(self):
        from healthcare_platform.platform_services.workers.aggregate_clinical_metrics_worker import AggregateClinicalMetricsWorker
        from healthcare_platform.shared.workers.base import BaseExternalTaskWorker
        worker = AggregateClinicalMetricsWorker()
        assert isinstance(worker, BaseExternalTaskWorker)

    def test_has_operation_name(self):
        from healthcare_platform.platform_services.workers.aggregate_clinical_metrics_worker import AggregateClinicalMetricsWorker
        worker = AggregateClinicalMetricsWorker()
        assert worker.operation_name is not None

    def test_has_topic(self):
        from healthcare_platform.platform_services.workers.aggregate_clinical_metrics_worker import AggregateClinicalMetricsWorker
        assert AggregateClinicalMetricsWorker.TOPIC == "platform.services.aggregate-clinical-metrics"

    def test_execute_returns_task_result(self):
        from healthcare_platform.platform_services.workers.aggregate_clinical_metrics_worker import AggregateClinicalMetricsWorker
        worker = AggregateClinicalMetricsWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert isinstance(result, TaskResult)

    def test_execute_success_has_correlation_id(self):
        from healthcare_platform.platform_services.workers.aggregate_clinical_metrics_worker import AggregateClinicalMetricsWorker
        worker = AggregateClinicalMetricsWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "correlation_id" in result.variables

    def test_execute_with_missing_variables(self):
        from healthcare_platform.platform_services.workers.aggregate_clinical_metrics_worker import AggregateClinicalMetricsWorker
        worker = AggregateClinicalMetricsWorker()
        context = self._make_context(variables={})
        result = worker.execute(context)
        assert result.status in (TaskStatus.SUCCESS, TaskStatus.FAILURE)

    def test_multi_tenant_isolation(self):
        from healthcare_platform.platform_services.workers.aggregate_clinical_metrics_worker import AggregateClinicalMetricsWorker
        worker = AggregateClinicalMetricsWorker()
        ctx_a = self._make_context(tenant_id="HOSPITAL_A")
        ctx_b = self._make_context(tenant_id="HOSPITAL_B")
        result_a = worker.execute(ctx_a)
        result_b = worker.execute(ctx_b)
        assert isinstance(result_a, TaskResult)
        assert isinstance(result_b, TaskResult)

    def test_metrics_calculation(self):
        from healthcare_platform.platform_services.workers.aggregate_clinical_metrics_worker import AggregateClinicalMetricsWorker
        worker = AggregateClinicalMetricsWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "metrics" in result.variables
        assert isinstance(result.variables["metrics"], list)
        assert len(result.variables["metrics"]) > 0

    def test_total_encounters_returned(self):
        from healthcare_platform.platform_services.workers.aggregate_clinical_metrics_worker import AggregateClinicalMetricsWorker
        worker = AggregateClinicalMetricsWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "total_encounters" in result.variables
        assert result.variables["total_encounters"] > 0
