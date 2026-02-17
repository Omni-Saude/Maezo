"""Integration tests for Track Process Performance Worker V2."""
from __future__ import annotations

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus


@pytest.mark.integration
class TestTrackProcessPerformanceWorkerV2:
    """V2 worker tests using BaseExternalTaskWorker pattern."""

    def _make_context(self, **overrides) -> TaskContext:
        defaults = {
            "task_id": "test-task-001",
            "process_instance_id": "proc-001",
            "tenant_id": "HOSPITAL_A",
            "variables": {
                "process_definition_key": "patient-registration",
                "include_active_instances": False,
                "calculate_bottlenecks": True,
                "sla_threshold_hours": 24.0,
                "correlation_id": "corr-001",
            },
            "worker_id": "platform.services.track-process-performance",
        }
        defaults.update(overrides)
        return TaskContext(**defaults)

    def test_worker_inherits_base(self):
        from healthcare_platform.platform_services.workers.track_process_performance_worker import TrackProcessPerformanceWorker
        from healthcare_platform.shared.workers.base import BaseExternalTaskWorker
        worker = TrackProcessPerformanceWorker()
        assert isinstance(worker, BaseExternalTaskWorker)

    def test_has_operation_name(self):
        from healthcare_platform.platform_services.workers.track_process_performance_worker import TrackProcessPerformanceWorker
        worker = TrackProcessPerformanceWorker()
        assert worker.operation_name == "Track Process Performance"

    def test_has_topic(self):
        from healthcare_platform.platform_services.workers.track_process_performance_worker import TrackProcessPerformanceWorker
        assert TrackProcessPerformanceWorker.TOPIC == "platform.services.track-process-performance"

    def test_execute_returns_task_result(self):
        from healthcare_platform.platform_services.workers.track_process_performance_worker import TrackProcessPerformanceWorker
        worker = TrackProcessPerformanceWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert isinstance(result, TaskResult)

    def test_execute_success_has_correlation_id(self):
        from healthcare_platform.platform_services.workers.track_process_performance_worker import TrackProcessPerformanceWorker
        worker = TrackProcessPerformanceWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert result.status == TaskStatus.SUCCESS
        assert "correlation_id" in result.variables
        assert result.variables["correlation_id"] == "corr-001"

    def test_execute_with_missing_variables(self):
        from healthcare_platform.platform_services.workers.track_process_performance_worker import TrackProcessPerformanceWorker
        worker = TrackProcessPerformanceWorker()
        context = self._make_context(variables={"correlation_id": "corr-001"})
        result = worker.execute(context)
        # Should handle gracefully with defaults
        assert result.status == TaskStatus.SUCCESS

    def test_multi_tenant_isolation(self):
        from healthcare_platform.platform_services.workers.track_process_performance_worker import TrackProcessPerformanceWorker
        worker = TrackProcessPerformanceWorker()
        ctx_a = self._make_context(tenant_id="HOSPITAL_A")
        ctx_b = self._make_context(tenant_id="HOSPITAL_B")
        result_a = worker.execute(ctx_a)
        result_b = worker.execute(ctx_b)
        assert isinstance(result_a, TaskResult)
        assert isinstance(result_b, TaskResult)

    def test_performance_metrics_structure(self):
        from healthcare_platform.platform_services.workers.track_process_performance_worker import TrackProcessPerformanceWorker
        worker = TrackProcessPerformanceWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "process_definition_key" in result.variables
        assert "total_instances" in result.variables
        assert "completed_instances" in result.variables
        assert "avg_cycle_time_seconds" in result.variables
        assert "sla_compliance_rate" in result.variables
        assert "throughput_per_hour" in result.variables
        assert "activities_performance" in result.variables
        assert "bottlenecks" in result.variables

    def test_activities_performance_structure(self):
        from healthcare_platform.platform_services.workers.track_process_performance_worker import TrackProcessPerformanceWorker
        worker = TrackProcessPerformanceWorker()
        context = self._make_context()
        result = worker.execute(context)
        activities = result.variables["activities_performance"]
        assert isinstance(activities, list)
        if len(activities) > 0:
            assert "activity_id" in activities[0]
            assert "avg_duration_seconds" in activities[0]
            assert "is_bottleneck" in activities[0]

    def test_duration_tracking(self):
        from healthcare_platform.platform_services.workers.track_process_performance_worker import TrackProcessPerformanceWorker
        worker = TrackProcessPerformanceWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "duration_ms" in result.variables
        assert result.variables["duration_ms"] > 0

    def test_sla_compliance_calculation(self):
        from healthcare_platform.platform_services.workers.track_process_performance_worker import TrackProcessPerformanceWorker
        worker = TrackProcessPerformanceWorker()
        context = self._make_context()
        result = worker.execute(context)
        sla_rate = result.variables["sla_compliance_rate"]
        assert 0 <= sla_rate <= 100

    def test_bottleneck_detection(self):
        from healthcare_platform.platform_services.workers.track_process_performance_worker import TrackProcessPerformanceWorker
        worker = TrackProcessPerformanceWorker()
        context = self._make_context(
            variables={
                "process_definition_key": "patient-registration",
                "calculate_bottlenecks": True,
                "correlation_id": "corr-001",
            }
        )
        result = worker.execute(context)
        assert "bottlenecks" in result.variables
        bottlenecks = result.variables["bottlenecks"]
        assert isinstance(bottlenecks, list)
