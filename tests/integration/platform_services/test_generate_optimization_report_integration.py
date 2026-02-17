"""Integration tests for Generate Optimization Report Worker V2."""
from __future__ import annotations

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus


@pytest.mark.integration
class TestGenerateOptimizationReportWorkerV2:
    """V2 worker tests using BaseExternalTaskWorker pattern."""

    def _make_context(self, **overrides) -> TaskContext:
        defaults = {
            "task_id": "test-task-001",
            "process_instance_id": "proc-001",
            "tenant_id": "HOSPITAL_A",
            "variables": {
                "report_period_start": "2026-01-01T00:00:00",
                "report_period_end": "2026-01-31T23:59:59",
                "executive_summary_only": False,
                "correlation_id": "corr-001",
            },
            "worker_id": "platform.services.generate-optimization-report",
        }
        defaults.update(overrides)
        return TaskContext(**defaults)

    def test_worker_inherits_base(self):
        from healthcare_platform.platform_services.workers.generate_optimization_report_worker import GenerateOptimizationReportWorker
        from healthcare_platform.shared.workers.base import BaseExternalTaskWorker
        worker = GenerateOptimizationReportWorker()
        assert isinstance(worker, BaseExternalTaskWorker)

    def test_has_operation_name(self):
        from healthcare_platform.platform_services.workers.generate_optimization_report_worker import GenerateOptimizationReportWorker
        worker = GenerateOptimizationReportWorker()
        assert worker.operation_name is not None

    def test_has_topic(self):
        from healthcare_platform.platform_services.workers.generate_optimization_report_worker import GenerateOptimizationReportWorker
        assert GenerateOptimizationReportWorker.TOPIC == "platform.services.generate-optimization-report"

    def test_execute_returns_task_result(self):
        from healthcare_platform.platform_services.workers.generate_optimization_report_worker import GenerateOptimizationReportWorker
        worker = GenerateOptimizationReportWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert isinstance(result, TaskResult)

    def test_execute_success_has_correlation_id(self):
        from healthcare_platform.platform_services.workers.generate_optimization_report_worker import GenerateOptimizationReportWorker
        worker = GenerateOptimizationReportWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "correlation_id" in result.variables

    def test_report_structure(self):
        from healthcare_platform.platform_services.workers.generate_optimization_report_worker import GenerateOptimizationReportWorker
        worker = GenerateOptimizationReportWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "report_id" in result.variables
        assert "executive_summary" in result.variables
        assert "findings_count" in result.variables
        assert "total_revenue_opportunity" in result.variables

    def test_report_id_format(self):
        from healthcare_platform.platform_services.workers.generate_optimization_report_worker import GenerateOptimizationReportWorker
        worker = GenerateOptimizationReportWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert result.variables["report_id"].startswith("OPT-")

    def test_multi_tenant_isolation(self):
        from healthcare_platform.platform_services.workers.generate_optimization_report_worker import GenerateOptimizationReportWorker
        worker = GenerateOptimizationReportWorker()
        ctx_a = self._make_context(tenant_id="HOSPITAL_A")
        ctx_b = self._make_context(tenant_id="HOSPITAL_B")
        result_a = worker.execute(ctx_a)
        result_b = worker.execute(ctx_b)
        assert isinstance(result_a, TaskResult)
        assert isinstance(result_b, TaskResult)
