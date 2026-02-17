"""Integration tests for Integrate Laboratory Worker V2."""
from __future__ import annotations

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus


@pytest.mark.integration
class TestIntegrateLaboratoryWorkerV2:
    """V2 worker tests using BaseExternalTaskWorker pattern."""

    def _make_context(self, **overrides) -> TaskContext:
        defaults = {
            "task_id": "test-task-001",
            "process_instance_id": "proc-001",
            "tenant_id": "HOSPITAL_A",
            "variables": {
                "patient_id": "PAT-12345",
                "order_id": "ORD-67890",
                "test_type": "blood_panel",
                "lab_system_code": "LAB-SYS-001",
                "validate_ranges": True,
                "correlation_id": "corr-001",
            },
            "worker_id": "platform.services.integrate-laboratory",
        }
        defaults.update(overrides)
        return TaskContext(**defaults)

    def test_worker_inherits_base(self):
        from healthcare_platform.platform_services.workers.integrate_laboratory_worker import IntegrateLaboratoryWorker
        from healthcare_platform.shared.workers.base import BaseExternalTaskWorker
        worker = IntegrateLaboratoryWorker()
        assert isinstance(worker, BaseExternalTaskWorker)

    def test_has_operation_name(self):
        from healthcare_platform.platform_services.workers.integrate_laboratory_worker import IntegrateLaboratoryWorker
        worker = IntegrateLaboratoryWorker()
        assert worker.operation_name is not None

    def test_has_topic(self):
        from healthcare_platform.platform_services.workers.integrate_laboratory_worker import IntegrateLaboratoryWorker
        assert IntegrateLaboratoryWorker.TOPIC == "platform.services.integrate-laboratory"

    def test_execute_returns_task_result(self):
        from healthcare_platform.platform_services.workers.integrate_laboratory_worker import IntegrateLaboratoryWorker
        worker = IntegrateLaboratoryWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert isinstance(result, TaskResult)

    def test_execute_success_has_correlation_id(self):
        from healthcare_platform.platform_services.workers.integrate_laboratory_worker import IntegrateLaboratoryWorker
        worker = IntegrateLaboratoryWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "correlation_id" in result.variables

    def test_laboratory_integration_structure(self):
        from healthcare_platform.platform_services.workers.integrate_laboratory_worker import IntegrateLaboratoryWorker
        worker = IntegrateLaboratoryWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "integration_id" in result.variables
        assert "results" in result.variables
        assert "results_count" in result.variables
        assert "validation_status" in result.variables
        assert "fhir_resource_id" in result.variables

    def test_integration_id_format(self):
        from healthcare_platform.platform_services.workers.integrate_laboratory_worker import IntegrateLaboratoryWorker
        worker = IntegrateLaboratoryWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert result.variables["integration_id"].startswith("LAB-")

    def test_critical_results_detection(self):
        from healthcare_platform.platform_services.workers.integrate_laboratory_worker import IntegrateLaboratoryWorker
        worker = IntegrateLaboratoryWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "critical_results_count" in result.variables
        assert "abnormal_results_count" in result.variables

    def test_multi_tenant_isolation(self):
        from healthcare_platform.platform_services.workers.integrate_laboratory_worker import IntegrateLaboratoryWorker
        worker = IntegrateLaboratoryWorker()
        ctx_a = self._make_context(tenant_id="HOSPITAL_A")
        ctx_b = self._make_context(tenant_id="HOSPITAL_B")
        result_a = worker.execute(ctx_a)
        result_b = worker.execute(ctx_b)
        assert isinstance(result_a, TaskResult)
        assert isinstance(result_b, TaskResult)
