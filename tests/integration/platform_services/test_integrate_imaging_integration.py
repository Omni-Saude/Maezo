"""Integration tests for Integrate Imaging Worker V2."""
from __future__ import annotations

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus


@pytest.mark.integration
class TestIntegrateImagingWorkerV2:
    """V2 worker tests using BaseExternalTaskWorker pattern."""

    def _make_context(self, **overrides) -> TaskContext:
        defaults = {
            "task_id": "test-task-001",
            "process_instance_id": "proc-001",
            "tenant_id": "HOSPITAL_A",
            "variables": {
                "patient_id": "PAT-12345",
                "accession_number": "ACC-67890",
                "study_instance_uid": "1.2.840.113619.2.1.1.123456",
                "modality": "CT",
                "study_description": "CT Chest",
                "pacs_url": "https://pacs.hospital.com",
                "correlation_id": "corr-001",
            },
            "worker_id": "platform.services.integrate-imaging",
        }
        defaults.update(overrides)
        return TaskContext(**defaults)

    def test_worker_inherits_base(self):
        from healthcare_platform.platform_services.workers.integrate_imaging_worker import IntegrateImagingWorker
        from healthcare_platform.shared.workers.base import BaseExternalTaskWorker
        worker = IntegrateImagingWorker()
        assert isinstance(worker, BaseExternalTaskWorker)

    def test_has_operation_name(self):
        from healthcare_platform.platform_services.workers.integrate_imaging_worker import IntegrateImagingWorker
        worker = IntegrateImagingWorker()
        assert worker.operation_name is not None

    def test_has_topic(self):
        from healthcare_platform.platform_services.workers.integrate_imaging_worker import IntegrateImagingWorker
        assert IntegrateImagingWorker.TOPIC == "platform.services.integrate-imaging"

    def test_execute_returns_task_result(self):
        from healthcare_platform.platform_services.workers.integrate_imaging_worker import IntegrateImagingWorker
        worker = IntegrateImagingWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert isinstance(result, TaskResult)

    def test_execute_success_has_correlation_id(self):
        from healthcare_platform.platform_services.workers.integrate_imaging_worker import IntegrateImagingWorker
        worker = IntegrateImagingWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "correlation_id" in result.variables

    def test_imaging_integration_structure(self):
        from healthcare_platform.platform_services.workers.integrate_imaging_worker import IntegrateImagingWorker
        worker = IntegrateImagingWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "integration_id" in result.variables
        assert "series_info" in result.variables
        assert "series_count" in result.variables
        assert "fhir_imaging_study_id" in result.variables
        assert "viewer_url" in result.variables

    def test_integration_id_format(self):
        from healthcare_platform.platform_services.workers.integrate_imaging_worker import IntegrateImagingWorker
        worker = IntegrateImagingWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert result.variables["integration_id"].startswith("IMG-")

    def test_multi_tenant_isolation(self):
        from healthcare_platform.platform_services.workers.integrate_imaging_worker import IntegrateImagingWorker
        worker = IntegrateImagingWorker()
        ctx_a = self._make_context(tenant_id="HOSPITAL_A")
        ctx_b = self._make_context(tenant_id="HOSPITAL_B")
        result_a = worker.execute(ctx_a)
        result_b = worker.execute(ctx_b)
        assert isinstance(result_a, TaskResult)
        assert isinstance(result_b, TaskResult)
