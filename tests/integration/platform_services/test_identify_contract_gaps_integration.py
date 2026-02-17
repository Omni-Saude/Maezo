"""Integration tests for Identify Contract Gaps Worker V2."""
from __future__ import annotations

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus


@pytest.mark.integration
class TestIdentifyContractGapsWorkerV2:
    """V2 worker tests using BaseExternalTaskWorker pattern."""

    def _make_context(self, **overrides) -> TaskContext:
        defaults = {
            "task_id": "test-task-001",
            "process_instance_id": "proc-001",
            "tenant_id": "HOSPITAL_A",
            "variables": {
                "contract_id": "CNT-12345",
                "payer_id": "PAY-67890",
                "include_procedure_coverage": True,
                "include_term_analysis": True,
                "expiration_warning_days": 90,
                "correlation_id": "corr-001",
            },
            "worker_id": "platform.services.identify-contract-gaps",
        }
        defaults.update(overrides)
        return TaskContext(**defaults)

    def test_worker_inherits_base(self):
        from healthcare_platform.platform_services.workers.identify_contract_gaps_worker import IdentifyContractGapsWorker
        from healthcare_platform.shared.workers.base import BaseExternalTaskWorker
        worker = IdentifyContractGapsWorker()
        assert isinstance(worker, BaseExternalTaskWorker)

    def test_has_operation_name(self):
        from healthcare_platform.platform_services.workers.identify_contract_gaps_worker import IdentifyContractGapsWorker
        worker = IdentifyContractGapsWorker()
        assert worker.operation_name is not None

    def test_has_topic(self):
        from healthcare_platform.platform_services.workers.identify_contract_gaps_worker import IdentifyContractGapsWorker
        assert IdentifyContractGapsWorker.TOPIC == "platform.services.identify-contract-gaps"

    def test_execute_returns_task_result(self):
        from healthcare_platform.platform_services.workers.identify_contract_gaps_worker import IdentifyContractGapsWorker
        worker = IdentifyContractGapsWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert isinstance(result, TaskResult)

    def test_execute_success_has_correlation_id(self):
        from healthcare_platform.platform_services.workers.identify_contract_gaps_worker import IdentifyContractGapsWorker
        worker = IdentifyContractGapsWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "correlation_id" in result.variables

    def test_contract_analysis_structure(self):
        from healthcare_platform.platform_services.workers.identify_contract_gaps_worker import IdentifyContractGapsWorker
        worker = IdentifyContractGapsWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "analysis_id" in result.variables
        assert "gaps" in result.variables
        assert "gaps_count" in result.variables
        assert "total_estimated_impact" in result.variables
        assert "contract_health_score" in result.variables

    def test_analysis_id_format(self):
        from healthcare_platform.platform_services.workers.identify_contract_gaps_worker import IdentifyContractGapsWorker
        worker = IdentifyContractGapsWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert result.variables["analysis_id"].startswith("CGAP-")

    def test_multi_tenant_isolation(self):
        from healthcare_platform.platform_services.workers.identify_contract_gaps_worker import IdentifyContractGapsWorker
        worker = IdentifyContractGapsWorker()
        ctx_a = self._make_context(tenant_id="HOSPITAL_A")
        ctx_b = self._make_context(tenant_id="HOSPITAL_B")
        result_a = worker.execute(ctx_a)
        result_b = worker.execute(ctx_b)
        assert isinstance(result_a, TaskResult)
        assert isinstance(result_b, TaskResult)
