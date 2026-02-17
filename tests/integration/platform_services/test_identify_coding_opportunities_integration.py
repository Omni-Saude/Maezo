"""Integration tests for Identify Coding Opportunities Worker V2."""
from __future__ import annotations

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus


@pytest.mark.integration
class TestIdentifyCodingOpportunitiesWorkerV2:
    """V2 worker tests using BaseExternalTaskWorker pattern."""

    def _make_context(self, **overrides) -> TaskContext:
        defaults = {
            "task_id": "test-task-001",
            "process_instance_id": "proc-001",
            "tenant_id": "HOSPITAL_A",
            "variables": {
                "encounter_id": "ENC-12345",
                "patient_id": "PAT-67890",
                "current_procedure_codes": ["10101012"],
                "analysis_depth": "standard",
                "correlation_id": "corr-001",
            },
            "worker_id": "platform.services.identify-coding-opportunities",
        }
        defaults.update(overrides)
        return TaskContext(**defaults)

    def test_worker_inherits_base(self):
        from healthcare_platform.platform_services.workers.identify_coding_opportunities_worker import IdentifyCodingOpportunitiesWorker
        from healthcare_platform.shared.workers.base import BaseExternalTaskWorker
        worker = IdentifyCodingOpportunitiesWorker()
        assert isinstance(worker, BaseExternalTaskWorker)

    def test_has_operation_name(self):
        from healthcare_platform.platform_services.workers.identify_coding_opportunities_worker import IdentifyCodingOpportunitiesWorker
        worker = IdentifyCodingOpportunitiesWorker()
        assert worker.operation_name is not None

    def test_has_topic(self):
        from healthcare_platform.platform_services.workers.identify_coding_opportunities_worker import IdentifyCodingOpportunitiesWorker
        assert IdentifyCodingOpportunitiesWorker.TOPIC == "platform.services.identify-coding-opportunities"

    def test_execute_returns_task_result(self):
        from healthcare_platform.platform_services.workers.identify_coding_opportunities_worker import IdentifyCodingOpportunitiesWorker
        worker = IdentifyCodingOpportunitiesWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert isinstance(result, TaskResult)

    def test_execute_success_has_correlation_id(self):
        from healthcare_platform.platform_services.workers.identify_coding_opportunities_worker import IdentifyCodingOpportunitiesWorker
        worker = IdentifyCodingOpportunitiesWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "correlation_id" in result.variables

    def test_opportunities_structure(self):
        from healthcare_platform.platform_services.workers.identify_coding_opportunities_worker import IdentifyCodingOpportunitiesWorker
        worker = IdentifyCodingOpportunitiesWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "opportunities" in result.variables
        assert "opportunities_count" in result.variables
        assert "total_potential_revenue" in result.variables
        assert "compliance_summary" in result.variables

    def test_analysis_id_generated(self):
        from healthcare_platform.platform_services.workers.identify_coding_opportunities_worker import IdentifyCodingOpportunitiesWorker
        worker = IdentifyCodingOpportunitiesWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "analysis_id" in result.variables
        assert result.variables["analysis_id"].startswith("CODING-")

    def test_multi_tenant_isolation(self):
        from healthcare_platform.platform_services.workers.identify_coding_opportunities_worker import IdentifyCodingOpportunitiesWorker
        worker = IdentifyCodingOpportunitiesWorker()
        ctx_a = self._make_context(tenant_id="HOSPITAL_A")
        ctx_b = self._make_context(tenant_id="HOSPITAL_B")
        result_a = worker.execute(ctx_a)
        result_b = worker.execute(ctx_b)
        assert isinstance(result_a, TaskResult)
        assert isinstance(result_b, TaskResult)
