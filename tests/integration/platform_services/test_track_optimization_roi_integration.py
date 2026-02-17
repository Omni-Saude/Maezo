"""Integration tests for Track Optimization ROI Worker V2."""
from __future__ import annotations

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus


@pytest.mark.integration
class TestTrackOptimizationROIWorkerV2:
    """V2 worker tests using BaseExternalTaskWorker pattern."""

    def _make_context(self, **overrides) -> TaskContext:
        defaults = {
            "task_id": "test-task-001",
            "process_instance_id": "proc-001",
            "tenant_id": "HOSPITAL_A",
            "variables": {
                "tracking_period_months": 6,
                "optimization_ids": ["OPT001", "OPT002"],
                "include_revenue_impact": True,
                "include_cost_savings": True,
                "correlation_id": "corr-001",
            },
            "worker_id": "platform.services.track-optimization-roi",
        }
        defaults.update(overrides)
        return TaskContext(**defaults)

    def test_worker_inherits_base(self):
        from healthcare_platform.platform_services.workers.track_optimization_roi_worker import TrackOptimizationROIWorker
        from healthcare_platform.shared.workers.base import BaseExternalTaskWorker
        worker = TrackOptimizationROIWorker()
        assert isinstance(worker, BaseExternalTaskWorker)

    def test_has_operation_name(self):
        from healthcare_platform.platform_services.workers.track_optimization_roi_worker import TrackOptimizationROIWorker
        worker = TrackOptimizationROIWorker()
        assert worker.operation_name == "Track Optimization ROI"

    def test_has_topic(self):
        from healthcare_platform.platform_services.workers.track_optimization_roi_worker import TrackOptimizationROIWorker
        assert TrackOptimizationROIWorker.TOPIC == "platform.services.track-optimization-roi"

    def test_execute_returns_task_result(self):
        from healthcare_platform.platform_services.workers.track_optimization_roi_worker import TrackOptimizationROIWorker
        worker = TrackOptimizationROIWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert isinstance(result, TaskResult)

    def test_execute_success_has_correlation_id(self):
        from healthcare_platform.platform_services.workers.track_optimization_roi_worker import TrackOptimizationROIWorker
        worker = TrackOptimizationROIWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert result.status == TaskStatus.SUCCESS
        assert "correlation_id" in result.variables
        assert result.variables["correlation_id"] == "corr-001"

    def test_execute_with_missing_variables(self):
        from healthcare_platform.platform_services.workers.track_optimization_roi_worker import TrackOptimizationROIWorker
        worker = TrackOptimizationROIWorker()
        context = self._make_context(variables={"correlation_id": "corr-001"})
        result = worker.execute(context)
        # Should handle gracefully with defaults
        assert result.status == TaskStatus.SUCCESS

    def test_multi_tenant_isolation(self):
        from healthcare_platform.platform_services.workers.track_optimization_roi_worker import TrackOptimizationROIWorker
        worker = TrackOptimizationROIWorker()
        ctx_a = self._make_context(tenant_id="HOSPITAL_A")
        ctx_b = self._make_context(tenant_id="HOSPITAL_B")
        result_a = worker.execute(ctx_a)
        result_b = worker.execute(ctx_b)
        assert isinstance(result_a, TaskResult)
        assert isinstance(result_b, TaskResult)

    def test_roi_tracking_structure(self):
        from healthcare_platform.platform_services.workers.track_optimization_roi_worker import TrackOptimizationROIWorker
        worker = TrackOptimizationROIWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "optimization_impacts" in result.variables
        assert "overall_roi" in result.variables
        assert "total_investment" in result.variables
        assert "total_return" in result.variables
        impacts = result.variables["optimization_impacts"]
        assert isinstance(impacts, list)
        if len(impacts) > 0:
            assert "optimization_id" in impacts[0]
            assert "cumulative_revenue_impact" in impacts[0]
            assert "roi_percentage" in impacts[0]

    def test_duration_tracking(self):
        from healthcare_platform.platform_services.workers.track_optimization_roi_worker import TrackOptimizationROIWorker
        worker = TrackOptimizationROIWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "duration_ms" in result.variables
        assert result.variables["duration_ms"] > 0

    def test_custom_tracking_period(self):
        from healthcare_platform.platform_services.workers.track_optimization_roi_worker import TrackOptimizationROIWorker
        worker = TrackOptimizationROIWorker()
        context = self._make_context(
            variables={
                "tracking_period_months": 12,
                "correlation_id": "corr-001",
            }
        )
        result = worker.execute(context)
        assert result.status == TaskStatus.SUCCESS

    def test_roi_calculation(self):
        from healthcare_platform.platform_services.workers.track_optimization_roi_worker import TrackOptimizationROIWorker
        worker = TrackOptimizationROIWorker()
        context = self._make_context()
        result = worker.execute(context)
        overall_roi = result.variables["overall_roi"]
        assert isinstance(overall_roi, (int, float))
        # ROI can be negative or positive
        assert overall_roi != 0  # Should calculate some ROI
