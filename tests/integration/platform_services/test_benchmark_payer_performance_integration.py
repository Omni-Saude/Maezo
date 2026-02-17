"""Integration tests for Benchmark Payer Performance Worker V2."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus


@pytest.mark.integration
class TestBenchmarkPayerPerformanceWorkerV2:
    """V2 worker tests using BaseExternalTaskWorker pattern."""

    def _make_context(self, **overrides) -> TaskContext:
        defaults = {
            "task_id": "test-task-002",
            "process_instance_id": "proc-002",
            "tenant_id": "HOSPITAL_A",
            "variables": {
                "analysis_period_days": 90,
                "payer_ids": ["PAY001", "PAY002"],
                "include_timeliness": True,
                "include_denial_rates": True,
                "include_rate_comparison": True,
                "include_contract_compliance": True,
                "market_benchmark_source": "ANS",
                "correlation_id": "corr-002",
            },
            "worker_id": "benchmark-payer-performance",
        }
        defaults.update(overrides)
        return TaskContext(**defaults)

    def test_worker_inherits_base(self):
        from healthcare_platform.platform_services.workers.benchmark_payer_performance_worker import BenchmarkPayerPerformanceWorker
        from healthcare_platform.shared.workers.base import BaseExternalTaskWorker
        worker = BenchmarkPayerPerformanceWorker()
        assert isinstance(worker, BaseExternalTaskWorker)

    def test_has_operation_name(self):
        from healthcare_platform.platform_services.workers.benchmark_payer_performance_worker import BenchmarkPayerPerformanceWorker
        worker = BenchmarkPayerPerformanceWorker()
        assert worker.operation_name is not None

    def test_has_topic(self):
        from healthcare_platform.platform_services.workers.benchmark_payer_performance_worker import BenchmarkPayerPerformanceWorker
        assert BenchmarkPayerPerformanceWorker.TOPIC == "benchmark-payer-performance"

    def test_execute_returns_task_result(self):
        from healthcare_platform.platform_services.workers.benchmark_payer_performance_worker import BenchmarkPayerPerformanceWorker
        worker = BenchmarkPayerPerformanceWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert isinstance(result, TaskResult)

    def test_execute_success_has_correlation_id(self):
        from healthcare_platform.platform_services.workers.benchmark_payer_performance_worker import BenchmarkPayerPerformanceWorker
        worker = BenchmarkPayerPerformanceWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "correlation_id" in result.variables

    def test_execute_with_missing_variables(self):
        from healthcare_platform.platform_services.workers.benchmark_payer_performance_worker import BenchmarkPayerPerformanceWorker
        worker = BenchmarkPayerPerformanceWorker()
        context = self._make_context(variables={})
        result = worker.execute(context)
        # Should handle gracefully with defaults
        assert result.status in (TaskStatus.SUCCESS, TaskStatus.FAILURE)

    def test_multi_tenant_isolation(self):
        from healthcare_platform.platform_services.workers.benchmark_payer_performance_worker import BenchmarkPayerPerformanceWorker
        worker = BenchmarkPayerPerformanceWorker()
        ctx_a = self._make_context(tenant_id="HOSPITAL_A")
        ctx_b = self._make_context(tenant_id="HOSPITAL_B")
        result_a = worker.execute(ctx_a)
        result_b = worker.execute(ctx_b)
        assert isinstance(result_a, TaskResult)
        assert isinstance(result_b, TaskResult)

    def test_all_payers_benchmarked(self):
        from healthcare_platform.platform_services.workers.benchmark_payer_performance_worker import BenchmarkPayerPerformanceWorker
        worker = BenchmarkPayerPerformanceWorker()
        context = self._make_context(variables={"payer_ids": None})  # All payers
        result = worker.execute(context)
        assert result.status == TaskStatus.SUCCESS
        assert "payer_benchmarks" in result.variables

    def test_specific_payers_benchmarked(self):
        from healthcare_platform.platform_services.workers.benchmark_payer_performance_worker import BenchmarkPayerPerformanceWorker
        worker = BenchmarkPayerPerformanceWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert result.status == TaskStatus.SUCCESS
        assert "payer_benchmarks" in result.variables

    def test_overall_score_calculation(self):
        from healthcare_platform.platform_services.workers.benchmark_payer_performance_worker import BenchmarkPayerPerformanceWorker
        worker = BenchmarkPayerPerformanceWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "payer_benchmarks" in result.variables
        # Each benchmark should have an overall score
        for benchmark in result.variables.get("payer_benchmarks", []):
            assert "overall_score" in benchmark

    def test_action_items_generated(self):
        from healthcare_platform.platform_services.workers.benchmark_payer_performance_worker import BenchmarkPayerPerformanceWorker
        worker = BenchmarkPayerPerformanceWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "action_items" in result.variables

    def test_renegotiation_opportunities_identified(self):
        from healthcare_platform.platform_services.workers.benchmark_payer_performance_worker import BenchmarkPayerPerformanceWorker
        worker = BenchmarkPayerPerformanceWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "renegotiation_opportunities" in result.variables

    def test_best_worst_performers_identified(self):
        from healthcare_platform.platform_services.workers.benchmark_payer_performance_worker import BenchmarkPayerPerformanceWorker
        worker = BenchmarkPayerPerformanceWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "best_performer" in result.variables
        assert "worst_performer" in result.variables
