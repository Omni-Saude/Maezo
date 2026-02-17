"""Integration tests for Recommend Procedure Bundles Worker V2."""
from __future__ import annotations

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus


@pytest.mark.integration
class TestRecommendProcedureBundlesWorkerV2:
    """V2 worker tests using BaseExternalTaskWorker pattern."""

    def _make_context(self, **overrides) -> TaskContext:
        defaults = {
            "task_id": "test-task-001",
            "process_instance_id": "proc-001",
            "tenant_id": "HOSPITAL_A",
            "variables": {
                "payer_id": "PYR001",
                "analysis_period_days": 180,
                "min_co_occurrence_count": 10,
                "target_discount_percentage": 10.0,
                "correlation_id": "corr-001",
            },
            "worker_id": "platform.services.recommend-procedure-bundles",
        }
        defaults.update(overrides)
        return TaskContext(**defaults)

    def test_worker_inherits_base(self):
        from healthcare_platform.platform_services.workers.recommend_procedure_bundles_worker import RecommendProcedureBundlesWorker
        from healthcare_platform.shared.workers.base import BaseExternalTaskWorker
        worker = RecommendProcedureBundlesWorker()
        assert isinstance(worker, BaseExternalTaskWorker)

    def test_has_operation_name(self):
        from healthcare_platform.platform_services.workers.recommend_procedure_bundles_worker import RecommendProcedureBundlesWorker
        worker = RecommendProcedureBundlesWorker()
        assert worker.operation_name == "Recommend Procedure Bundles"

    def test_has_topic(self):
        from healthcare_platform.platform_services.workers.recommend_procedure_bundles_worker import RecommendProcedureBundlesWorker
        assert RecommendProcedureBundlesWorker.TOPIC == "platform.services.recommend-procedure-bundles"

    def test_execute_returns_task_result(self):
        from healthcare_platform.platform_services.workers.recommend_procedure_bundles_worker import RecommendProcedureBundlesWorker
        worker = RecommendProcedureBundlesWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert isinstance(result, TaskResult)

    def test_execute_success_has_correlation_id(self):
        from healthcare_platform.platform_services.workers.recommend_procedure_bundles_worker import RecommendProcedureBundlesWorker
        worker = RecommendProcedureBundlesWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert result.status == TaskStatus.SUCCESS
        assert "correlation_id" in result.variables
        assert result.variables["correlation_id"] == "corr-001"

    def test_execute_with_missing_variables(self):
        from healthcare_platform.platform_services.workers.recommend_procedure_bundles_worker import RecommendProcedureBundlesWorker
        worker = RecommendProcedureBundlesWorker()
        context = self._make_context(variables={"correlation_id": "corr-001"})
        result = worker.execute(context)
        # Should handle gracefully with defaults
        assert result.status == TaskStatus.SUCCESS

    def test_multi_tenant_isolation(self):
        from healthcare_platform.platform_services.workers.recommend_procedure_bundles_worker import RecommendProcedureBundlesWorker
        worker = RecommendProcedureBundlesWorker()
        ctx_a = self._make_context(tenant_id="HOSPITAL_A")
        ctx_b = self._make_context(tenant_id="HOSPITAL_B")
        result_a = worker.execute(ctx_a)
        result_b = worker.execute(ctx_b)
        assert isinstance(result_a, TaskResult)
        assert isinstance(result_b, TaskResult)

    def test_bundle_recommendations_structure(self):
        from healthcare_platform.platform_services.workers.recommend_procedure_bundles_worker import RecommendProcedureBundlesWorker
        worker = RecommendProcedureBundlesWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "recommended_bundles" in result.variables
        assert "total_projected_savings" in result.variables
        bundles = result.variables["recommended_bundles"]
        assert isinstance(bundles, list)
        if len(bundles) > 0:
            assert "bundle_id" in bundles[0]
            assert "procedure_codes" in bundles[0]
            assert "projected_annual_savings" in bundles[0]

    def test_duration_tracking(self):
        from healthcare_platform.platform_services.workers.recommend_procedure_bundles_worker import RecommendProcedureBundlesWorker
        worker = RecommendProcedureBundlesWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "duration_ms" in result.variables
        assert result.variables["duration_ms"] > 0

    def test_custom_target_discount(self):
        from healthcare_platform.platform_services.workers.recommend_procedure_bundles_worker import RecommendProcedureBundlesWorker
        worker = RecommendProcedureBundlesWorker()
        context = self._make_context(
            variables={
                "target_discount_percentage": 15.0,
                "correlation_id": "corr-001",
            }
        )
        result = worker.execute(context)
        assert result.status == TaskStatus.SUCCESS
        bundles = result.variables.get("recommended_bundles", [])
        if len(bundles) > 0:
            assert bundles[0]["discount_percentage"] == 15.0
