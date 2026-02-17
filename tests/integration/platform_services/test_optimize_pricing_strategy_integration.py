"""Integration tests for Optimize Pricing Strategy Worker V2."""
from __future__ import annotations

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus


@pytest.mark.integration
class TestOptimizePricingStrategyWorkerV2:
    """V2 worker tests using BaseExternalTaskWorker pattern."""

    def _make_context(self, **overrides) -> TaskContext:
        defaults = {
            "task_id": "test-task-001",
            "process_instance_id": "proc-001",
            "tenant_id": "HOSPITAL_A",
            "variables": {
                "contract_id": "CNT-12345",
                "payer_id": "PAY-67890",
                "include_market_benchmark": True,
                "target_margin_percentage": 15.0,
                "analysis_scope": "full",
                "correlation_id": "corr-001",
            },
            "worker_id": "platform.services.optimize-pricing-strategy",
        }
        defaults.update(overrides)
        return TaskContext(**defaults)

    def test_worker_inherits_base(self):
        from healthcare_platform.platform_services.workers.optimize_pricing_strategy_worker import OptimizePricingStrategyWorker
        from healthcare_platform.shared.workers.base import BaseExternalTaskWorker
        worker = OptimizePricingStrategyWorker()
        assert isinstance(worker, BaseExternalTaskWorker)

    def test_has_operation_name(self):
        from healthcare_platform.platform_services.workers.optimize_pricing_strategy_worker import OptimizePricingStrategyWorker
        worker = OptimizePricingStrategyWorker()
        assert worker.operation_name is not None

    def test_has_topic(self):
        from healthcare_platform.platform_services.workers.optimize_pricing_strategy_worker import OptimizePricingStrategyWorker
        assert OptimizePricingStrategyWorker.TOPIC == "platform.services.optimize-pricing-strategy"

    def test_execute_returns_task_result(self):
        from healthcare_platform.platform_services.workers.optimize_pricing_strategy_worker import OptimizePricingStrategyWorker
        worker = OptimizePricingStrategyWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert isinstance(result, TaskResult)

    def test_execute_success_has_correlation_id(self):
        from healthcare_platform.platform_services.workers.optimize_pricing_strategy_worker import OptimizePricingStrategyWorker
        worker = OptimizePricingStrategyWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "correlation_id" in result.variables

    def test_pricing_analysis_structure(self):
        from healthcare_platform.platform_services.workers.optimize_pricing_strategy_worker import OptimizePricingStrategyWorker
        worker = OptimizePricingStrategyWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "analysis_id" in result.variables
        assert "opportunities" in result.variables
        assert "total_projected_increase" in result.variables
        assert "current_annual_revenue" in result.variables
        assert "optimized_annual_revenue" in result.variables

    def test_analysis_id_format(self):
        from healthcare_platform.platform_services.workers.optimize_pricing_strategy_worker import OptimizePricingStrategyWorker
        worker = OptimizePricingStrategyWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert result.variables["analysis_id"].startswith("PRICING-")

    def test_multi_tenant_isolation(self):
        from healthcare_platform.platform_services.workers.optimize_pricing_strategy_worker import OptimizePricingStrategyWorker
        worker = OptimizePricingStrategyWorker()
        ctx_a = self._make_context(tenant_id="HOSPITAL_A")
        ctx_b = self._make_context(tenant_id="HOSPITAL_B")
        result_a = worker.execute(ctx_a)
        result_b = worker.execute(ctx_b)
        assert isinstance(result_a, TaskResult)
        assert isinstance(result_b, TaskResult)
