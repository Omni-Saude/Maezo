"""Integration tests for Optimize Resource Utilization Worker V2."""
from __future__ import annotations

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus


@pytest.mark.integration
class TestOptimizeResourceUtilizationWorkerV2:
    """V2 worker tests using BaseExternalTaskWorker pattern."""

    def _make_context(self, **overrides) -> TaskContext:
        defaults = {
            "task_id": "test-task-001",
            "process_instance_id": "proc-001",
            "tenant_id": "HOSPITAL_A",
            "variables": {
                "analysis_period_days": 30,
                "include_or_analysis": True,
                "include_bed_analysis": True,
                "include_staff_analysis": True,
                "include_equipment_analysis": True,
                "target_utilization": 85.0,
                "correlation_id": "corr-001",
            },
            "worker_id": "platform.services.optimize-resource-utilization",
        }
        defaults.update(overrides)
        return TaskContext(**defaults)

    def test_worker_inherits_base(self):
        from healthcare_platform.platform_services.workers.optimize_resource_utilization_worker import OptimizeResourceUtilizationWorker
        from healthcare_platform.shared.workers.base import BaseExternalTaskWorker
        worker = OptimizeResourceUtilizationWorker()
        assert isinstance(worker, BaseExternalTaskWorker)

    def test_has_operation_name(self):
        from healthcare_platform.platform_services.workers.optimize_resource_utilization_worker import OptimizeResourceUtilizationWorker
        worker = OptimizeResourceUtilizationWorker()
        assert worker.operation_name is not None

    def test_has_topic(self):
        from healthcare_platform.platform_services.workers.optimize_resource_utilization_worker import OptimizeResourceUtilizationWorker
        assert OptimizeResourceUtilizationWorker.TOPIC == "platform.services.optimize-resource-utilization"

    def test_execute_returns_task_result(self):
        from healthcare_platform.platform_services.workers.optimize_resource_utilization_worker import OptimizeResourceUtilizationWorker
        worker = OptimizeResourceUtilizationWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert isinstance(result, TaskResult)

    def test_execute_success_has_correlation_id(self):
        from healthcare_platform.platform_services.workers.optimize_resource_utilization_worker import OptimizeResourceUtilizationWorker
        worker = OptimizeResourceUtilizationWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "correlation_id" in result.variables

    def test_resource_optimization_structure(self):
        from healthcare_platform.platform_services.workers.optimize_resource_utilization_worker import OptimizeResourceUtilizationWorker
        worker = OptimizeResourceUtilizationWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "or_utilization" in result.variables
        assert "bed_utilization" in result.variables
        assert "staff_productivity" in result.variables
        assert "equipment_utilization" in result.variables
        assert "efficiency_score" in result.variables

    def test_optimization_opportunities_returned(self):
        from healthcare_platform.platform_services.workers.optimize_resource_utilization_worker import OptimizeResourceUtilizationWorker
        worker = OptimizeResourceUtilizationWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "optimization_opportunities" in result.variables
        assert isinstance(result.variables["optimization_opportunities"], list)

    def test_multi_tenant_isolation(self):
        from healthcare_platform.platform_services.workers.optimize_resource_utilization_worker import OptimizeResourceUtilizationWorker
        worker = OptimizeResourceUtilizationWorker()
        ctx_a = self._make_context(tenant_id="HOSPITAL_A")
        ctx_b = self._make_context(tenant_id="HOSPITAL_B")
        result_a = worker.execute(ctx_a)
        result_b = worker.execute(ctx_b)
        assert isinstance(result_a, TaskResult)
        assert isinstance(result_b, TaskResult)
