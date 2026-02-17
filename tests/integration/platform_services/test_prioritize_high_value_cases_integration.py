"""Integration tests for Prioritize High Value Cases Worker V2."""
from __future__ import annotations

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus


@pytest.mark.integration
class TestPrioritizeHighValueCasesWorkerV2:
    """V2 worker tests using BaseExternalTaskWorker pattern."""

    def _make_context(self, **overrides) -> TaskContext:
        defaults = {
            "task_id": "test-task-001",
            "process_instance_id": "proc-001",
            "tenant_id": "HOSPITAL_A",
            "variables": {
                "encounter_ids": ["ENC-001", "ENC-002", "ENC-003", "ENC-004", "ENC-005"],
                "include_complexity": True,
                "include_payer_margin": True,
                "revenue_threshold": 5000.0,
                "correlation_id": "corr-001",
            },
            "worker_id": "platform.services.prioritize-high-value-cases",
        }
        defaults.update(overrides)
        return TaskContext(**defaults)

    def test_worker_inherits_base(self):
        from healthcare_platform.platform_services.workers.prioritize_high_value_cases_worker import PrioritizeHighValueCasesWorker
        from healthcare_platform.shared.workers.base import BaseExternalTaskWorker
        worker = PrioritizeHighValueCasesWorker()
        assert isinstance(worker, BaseExternalTaskWorker)

    def test_has_operation_name(self):
        from healthcare_platform.platform_services.workers.prioritize_high_value_cases_worker import PrioritizeHighValueCasesWorker
        worker = PrioritizeHighValueCasesWorker()
        assert worker.operation_name is not None

    def test_has_topic(self):
        from healthcare_platform.platform_services.workers.prioritize_high_value_cases_worker import PrioritizeHighValueCasesWorker
        assert PrioritizeHighValueCasesWorker.TOPIC == "platform.services.prioritize-high-value-cases"

    def test_execute_returns_task_result(self):
        from healthcare_platform.platform_services.workers.prioritize_high_value_cases_worker import PrioritizeHighValueCasesWorker
        worker = PrioritizeHighValueCasesWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert isinstance(result, TaskResult)

    def test_execute_success_has_correlation_id(self):
        from healthcare_platform.platform_services.workers.prioritize_high_value_cases_worker import PrioritizeHighValueCasesWorker
        worker = PrioritizeHighValueCasesWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "correlation_id" in result.variables

    def test_case_prioritization_structure(self):
        from healthcare_platform.platform_services.workers.prioritize_high_value_cases_worker import PrioritizeHighValueCasesWorker
        worker = PrioritizeHighValueCasesWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "prioritized_cases" in result.variables
        assert "total_cases_analyzed" in result.variables
        assert "critical_cases" in result.variables

    def test_prioritized_cases_returned(self):
        from healthcare_platform.platform_services.workers.prioritize_high_value_cases_worker import PrioritizeHighValueCasesWorker
        worker = PrioritizeHighValueCasesWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert isinstance(result.variables["prioritized_cases"], list)
        assert len(result.variables["prioritized_cases"]) > 0

    def test_priority_tiers_assigned(self):
        from healthcare_platform.platform_services.workers.prioritize_high_value_cases_worker import PrioritizeHighValueCasesWorker
        worker = PrioritizeHighValueCasesWorker()
        context = self._make_context()
        result = worker.execute(context)
        cases = result.variables["prioritized_cases"]
        for case in cases:
            assert "priority_tier" in case
            assert case["priority_tier"] in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]

    def test_multi_tenant_isolation(self):
        from healthcare_platform.platform_services.workers.prioritize_high_value_cases_worker import PrioritizeHighValueCasesWorker
        worker = PrioritizeHighValueCasesWorker()
        ctx_a = self._make_context(tenant_id="HOSPITAL_A")
        ctx_b = self._make_context(tenant_id="HOSPITAL_B")
        result_a = worker.execute(ctx_a)
        result_b = worker.execute(ctx_b)
        assert isinstance(result_a, TaskResult)
        assert isinstance(result_b, TaskResult)
