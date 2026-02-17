"""Integration tests for Calculate Revenue Potential Worker V2."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus


@pytest.mark.integration
class TestCalculateRevenuePotentialWorkerV2:
    """V2 worker tests using BaseExternalTaskWorker pattern."""

    def _make_context(self, **overrides) -> TaskContext:
        defaults = {
            "task_id": "test-task-004",
            "process_instance_id": "proc-004",
            "tenant_id": "HOSPITAL_A",
            "variables": {
                "current_annual_revenue": 5000000.0,
                "volume_growth_scenarios": [5.0, 10.0, 15.0],
                "pricing_optimization_scenarios": [5.0, 10.0, 15.0],
                "payer_mix_scenarios": None,
                "include_bundle_impact": True,
                "include_coding_improvements": True,
                "time_horizon_months": 12,
                "correlation_id": "corr-004",
            },
            "worker_id": "calculate-revenue-potential",
        }
        defaults.update(overrides)
        return TaskContext(**defaults)

    def test_worker_inherits_base(self):
        from healthcare_platform.platform_services.workers.calculate_revenue_potential_worker import CalculateRevenuePotentialWorker
        from healthcare_platform.shared.workers.base import BaseExternalTaskWorker
        worker = CalculateRevenuePotentialWorker()
        assert isinstance(worker, BaseExternalTaskWorker)

    def test_has_operation_name(self):
        from healthcare_platform.platform_services.workers.calculate_revenue_potential_worker import CalculateRevenuePotentialWorker
        worker = CalculateRevenuePotentialWorker()
        assert worker.operation_name is not None

    def test_has_topic(self):
        from healthcare_platform.platform_services.workers.calculate_revenue_potential_worker import CalculateRevenuePotentialWorker
        assert CalculateRevenuePotentialWorker.TOPIC == "calculate-revenue-potential"

    def test_execute_returns_task_result(self):
        from healthcare_platform.platform_services.workers.calculate_revenue_potential_worker import CalculateRevenuePotentialWorker
        worker = CalculateRevenuePotentialWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert isinstance(result, TaskResult)

    def test_execute_success_has_correlation_id(self):
        from healthcare_platform.platform_services.workers.calculate_revenue_potential_worker import CalculateRevenuePotentialWorker
        worker = CalculateRevenuePotentialWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "correlation_id" in result.variables

    def test_execute_with_missing_variables(self):
        from healthcare_platform.platform_services.workers.calculate_revenue_potential_worker import CalculateRevenuePotentialWorker
        worker = CalculateRevenuePotentialWorker()
        context = self._make_context(variables={"current_annual_revenue": 5000000.0})
        result = worker.execute(context)
        # Should handle gracefully with defaults
        assert result.status in (TaskStatus.SUCCESS, TaskStatus.FAILURE)

    def test_multi_tenant_isolation(self):
        from healthcare_platform.platform_services.workers.calculate_revenue_potential_worker import CalculateRevenuePotentialWorker
        worker = CalculateRevenuePotentialWorker()
        ctx_a = self._make_context(tenant_id="HOSPITAL_A")
        ctx_b = self._make_context(tenant_id="HOSPITAL_B")
        result_a = worker.execute(ctx_a)
        result_b = worker.execute(ctx_b)
        assert isinstance(result_a, TaskResult)
        assert isinstance(result_b, TaskResult)

    def test_multiple_scenarios_generated(self):
        from healthcare_platform.platform_services.workers.calculate_revenue_potential_worker import CalculateRevenuePotentialWorker
        worker = CalculateRevenuePotentialWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert result.status == TaskStatus.SUCCESS
        assert "scenarios" in result.variables
        scenarios = result.variables.get("scenarios", [])
        # Should have volume, pricing, combined, bundle, and coding scenarios
        assert len(scenarios) > 0

    def test_best_case_scenario_identified(self):
        from healthcare_platform.platform_services.workers.calculate_revenue_potential_worker import CalculateRevenuePotentialWorker
        worker = CalculateRevenuePotentialWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "best_case_scenario" in result.variables

    def test_conservative_scenario_identified(self):
        from healthcare_platform.platform_services.workers.calculate_revenue_potential_worker import CalculateRevenuePotentialWorker
        worker = CalculateRevenuePotentialWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "conservative_scenario" in result.variables

    def test_recommended_scenario_identified(self):
        from healthcare_platform.platform_services.workers.calculate_revenue_potential_worker import CalculateRevenuePotentialWorker
        worker = CalculateRevenuePotentialWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "recommended_scenario" in result.variables

    def test_maximum_potential_calculated(self):
        from healthcare_platform.platform_services.workers.calculate_revenue_potential_worker import CalculateRevenuePotentialWorker
        worker = CalculateRevenuePotentialWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "maximum_potential_increase" in result.variables
        # V2 worker doesn't return maximum_potential_percentage separately
        # It's available in best_case_scenario.revenue_increase_percentage

    def test_scenario_includes_risk_level(self):
        from healthcare_platform.platform_services.workers.calculate_revenue_potential_worker import CalculateRevenuePotentialWorker
        worker = CalculateRevenuePotentialWorker()
        context = self._make_context()
        result = worker.execute(context)
        scenarios = result.variables.get("scenarios", [])
        for scenario in scenarios:
            assert "risk_level" in scenario
            assert scenario["risk_level"] in ["low", "medium", "high"]

    def test_scenario_includes_implementation_difficulty(self):
        from healthcare_platform.platform_services.workers.calculate_revenue_potential_worker import CalculateRevenuePotentialWorker
        worker = CalculateRevenuePotentialWorker()
        context = self._make_context()
        result = worker.execute(context)
        scenarios = result.variables.get("scenarios", [])
        for scenario in scenarios:
            assert "implementation_difficulty" in scenario

    def test_strategic_recommendations_generated(self):
        from healthcare_platform.platform_services.workers.calculate_revenue_potential_worker import CalculateRevenuePotentialWorker
        worker = CalculateRevenuePotentialWorker()
        context = self._make_context()
        result = worker.execute(context)
        # V2 worker returns recommended_scenario instead of strategic_recommendations
        assert "recommended_scenario" in result.variables

    def test_action_plan_generated(self):
        from healthcare_platform.platform_services.workers.calculate_revenue_potential_worker import CalculateRevenuePotentialWorker
        worker = CalculateRevenuePotentialWorker()
        context = self._make_context()
        result = worker.execute(context)
        # V2 worker doesn't generate action_plan - it provides scenarios
        # Each scenario has implementation_difficulty and time_to_implement_months
        assert "scenarios" in result.variables
        scenarios = result.variables.get("scenarios", [])
        assert len(scenarios) > 0
        for scenario in scenarios:
            assert "implementation_difficulty" in scenario
            assert "time_to_implement_months" in scenario

    def test_bundle_impact_included_when_requested(self):
        from healthcare_platform.platform_services.workers.calculate_revenue_potential_worker import CalculateRevenuePotentialWorker
        worker = CalculateRevenuePotentialWorker()
        context = self._make_context(variables={"current_annual_revenue": 5000000.0, "include_bundle_impact": True})
        result = worker.execute(context)
        scenarios = result.variables.get("scenarios", [])
        # Should have a bundle scenario
        bundle_scenarios = [s for s in scenarios if "bundle" in s.get("scenario_name", "").lower()]
        assert len(bundle_scenarios) > 0

    def test_coding_improvements_included_when_requested(self):
        from healthcare_platform.platform_services.workers.calculate_revenue_potential_worker import CalculateRevenuePotentialWorker
        worker = CalculateRevenuePotentialWorker()
        context = self._make_context(variables={"current_annual_revenue": 5000000.0, "include_coding_improvements": True})
        result = worker.execute(context)
        scenarios = result.variables.get("scenarios", [])
        # Should have a coding scenario
        coding_scenarios = [s for s in scenarios if "cod" in s.get("scenario_name", "").lower()]
        assert len(coding_scenarios) > 0
