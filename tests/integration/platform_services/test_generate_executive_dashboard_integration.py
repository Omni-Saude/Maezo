"""Integration tests for Generate Executive Dashboard Worker V2."""
from __future__ import annotations

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus


@pytest.mark.integration
class TestGenerateExecutiveDashboardWorkerV2:
    """V2 worker tests using BaseExternalTaskWorker pattern."""

    def _make_context(self, **overrides) -> TaskContext:
        defaults = {
            "task_id": "test-task-001",
            "process_instance_id": "proc-001",
            "tenant_id": "HOSPITAL_A",
            "variables": {
                "dashboard_type": "monthly",
                "period_start": "2026-01-01T00:00:00",
                "period_end": "2026-01-31T23:59:59",
                "correlation_id": "corr-001",
            },
            "worker_id": "platform.services.generate-executive-dashboard",
        }
        defaults.update(overrides)
        return TaskContext(**defaults)

    def test_worker_inherits_base(self):
        from healthcare_platform.platform_services.workers.generate_executive_dashboard_worker import GenerateExecutiveDashboardWorker
        from healthcare_platform.shared.workers.base import BaseExternalTaskWorker
        worker = GenerateExecutiveDashboardWorker()
        assert isinstance(worker, BaseExternalTaskWorker)

    def test_has_operation_name(self):
        from healthcare_platform.platform_services.workers.generate_executive_dashboard_worker import GenerateExecutiveDashboardWorker
        worker = GenerateExecutiveDashboardWorker()
        assert worker.operation_name is not None

    def test_has_topic(self):
        from healthcare_platform.platform_services.workers.generate_executive_dashboard_worker import GenerateExecutiveDashboardWorker
        assert GenerateExecutiveDashboardWorker.TOPIC == "platform.services.generate-executive-dashboard"

    def test_execute_returns_task_result(self):
        from healthcare_platform.platform_services.workers.generate_executive_dashboard_worker import GenerateExecutiveDashboardWorker
        worker = GenerateExecutiveDashboardWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert isinstance(result, TaskResult)

    def test_execute_success_has_correlation_id(self):
        from healthcare_platform.platform_services.workers.generate_executive_dashboard_worker import GenerateExecutiveDashboardWorker
        worker = GenerateExecutiveDashboardWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "correlation_id" in result.variables

    def test_dashboard_structure(self):
        from healthcare_platform.platform_services.workers.generate_executive_dashboard_worker import GenerateExecutiveDashboardWorker
        worker = GenerateExecutiveDashboardWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "dashboard_id" in result.variables
        assert "kpis" in result.variables
        assert "kpis_count" in result.variables
        assert "summary" in result.variables

    def test_kpis_returned(self):
        from healthcare_platform.platform_services.workers.generate_executive_dashboard_worker import GenerateExecutiveDashboardWorker
        worker = GenerateExecutiveDashboardWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert isinstance(result.variables["kpis"], list)
        assert len(result.variables["kpis"]) > 0

    def test_multi_tenant_isolation(self):
        from healthcare_platform.platform_services.workers.generate_executive_dashboard_worker import GenerateExecutiveDashboardWorker
        worker = GenerateExecutiveDashboardWorker()
        ctx_a = self._make_context(tenant_id="HOSPITAL_A")
        ctx_b = self._make_context(tenant_id="HOSPITAL_B")
        result_a = worker.execute(ctx_a)
        result_b = worker.execute(ctx_b)
        assert isinstance(result_a, TaskResult)
        assert isinstance(result_b, TaskResult)
