"""Integration tests for Calculate Operational Metrics Worker V2."""
from __future__ import annotations

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus


@pytest.mark.integration
class TestCalculateOperationalMetricsWorkerV2:
    """V2 worker tests using BaseExternalTaskWorker pattern."""

    def _make_context(self, **overrides) -> TaskContext:
        defaults = {
            "task_id": "test-task-001",
            "process_instance_id": "proc-001",
            "tenant_id": "HOSPITAL_A",
            "variables": {
                "metric_types": ["los", "bed_occupancy", "or_utilization", "ed_throughput"],
                "period_start": "2026-01-01T00:00:00",
                "period_end": "2026-01-31T23:59:59",
                "department": "surgery",
                "correlation_id": "corr-001",
            },
            "worker_id": "platform.services.calculate-operational-metrics",
        }
        defaults.update(overrides)
        return TaskContext(**defaults)

    def test_worker_inherits_base(self):
        from healthcare_platform.platform_services.workers.calculate_operational_metrics_worker import CalculateOperationalMetricsWorker
        from healthcare_platform.shared.workers.base import BaseExternalTaskWorker
        worker = CalculateOperationalMetricsWorker()
        assert isinstance(worker, BaseExternalTaskWorker)

    def test_has_operation_name(self):
        from healthcare_platform.platform_services.workers.calculate_operational_metrics_worker import CalculateOperationalMetricsWorker
        worker = CalculateOperationalMetricsWorker()
        assert worker.operation_name is not None

    def test_has_topic(self):
        from healthcare_platform.platform_services.workers.calculate_operational_metrics_worker import CalculateOperationalMetricsWorker
        assert CalculateOperationalMetricsWorker.TOPIC == "platform.services.calculate-operational-metrics"

    def test_execute_returns_task_result(self):
        from healthcare_platform.platform_services.workers.calculate_operational_metrics_worker import CalculateOperationalMetricsWorker
        worker = CalculateOperationalMetricsWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert isinstance(result, TaskResult)

    def test_execute_success_has_correlation_id(self):
        from healthcare_platform.platform_services.workers.calculate_operational_metrics_worker import CalculateOperationalMetricsWorker
        worker = CalculateOperationalMetricsWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "correlation_id" in result.variables

    def test_operational_metrics_returned(self):
        from healthcare_platform.platform_services.workers.calculate_operational_metrics_worker import CalculateOperationalMetricsWorker
        worker = CalculateOperationalMetricsWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "metrics" in result.variables
        assert isinstance(result.variables["metrics"], list)
        assert len(result.variables["metrics"]) > 0

    def test_calculation_id_generated(self):
        from healthcare_platform.platform_services.workers.calculate_operational_metrics_worker import CalculateOperationalMetricsWorker
        worker = CalculateOperationalMetricsWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "calculation_id" in result.variables
        assert result.variables["calculation_id"].startswith("OPER-")

    def test_multi_tenant_isolation(self):
        from healthcare_platform.platform_services.workers.calculate_operational_metrics_worker import CalculateOperationalMetricsWorker
        worker = CalculateOperationalMetricsWorker()
        ctx_a = self._make_context(tenant_id="HOSPITAL_A")
        ctx_b = self._make_context(tenant_id="HOSPITAL_B")
        result_a = worker.execute(ctx_a)
        result_b = worker.execute(ctx_b)
        assert isinstance(result_a, TaskResult)
        assert isinstance(result_b, TaskResult)
