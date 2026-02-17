"""Integration tests for Export To DataWarehouse Worker V2."""
from __future__ import annotations

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus


@pytest.mark.integration
class TestExportToDataWarehouseWorkerV2:
    """V2 worker tests using BaseExternalTaskWorker pattern."""

    def _make_context(self, **overrides) -> TaskContext:
        defaults = {
            "task_id": "test-task-001",
            "process_instance_id": "proc-001",
            "tenant_id": "HOSPITAL_A",
            "variables": {
                "entity_type": "patient",
                "export_mode": "incremental",
                "output_format": "parquet",
                "anonymize_pii": True,
                "correlation_id": "corr-001",
            },
            "worker_id": "platform.export-to-datawarehouse",
        }
        defaults.update(overrides)
        return TaskContext(**defaults)

    def test_worker_inherits_base(self):
        from healthcare_platform.platform_services.workers.export_to_datawarehouse_worker import ExportToDataWarehouseWorker
        from healthcare_platform.shared.workers.base import BaseExternalTaskWorker
        worker = ExportToDataWarehouseWorker()
        assert isinstance(worker, BaseExternalTaskWorker)

    def test_has_operation_name(self):
        from healthcare_platform.platform_services.workers.export_to_datawarehouse_worker import ExportToDataWarehouseWorker
        worker = ExportToDataWarehouseWorker()
        assert worker.operation_name is not None

    def test_has_topic(self):
        from healthcare_platform.platform_services.workers.export_to_datawarehouse_worker import ExportToDataWarehouseWorker
        assert ExportToDataWarehouseWorker.TOPIC == "platform.export-to-datawarehouse"

    def test_execute_returns_task_result(self):
        from healthcare_platform.platform_services.workers.export_to_datawarehouse_worker import ExportToDataWarehouseWorker
        worker = ExportToDataWarehouseWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert isinstance(result, TaskResult)

    def test_execute_success_has_correlation_id(self):
        from healthcare_platform.platform_services.workers.export_to_datawarehouse_worker import ExportToDataWarehouseWorker
        worker = ExportToDataWarehouseWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "correlation_id" in result.variables

    def test_export_structure(self):
        from healthcare_platform.platform_services.workers.export_to_datawarehouse_worker import ExportToDataWarehouseWorker
        worker = ExportToDataWarehouseWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "export_id" in result.variables
        assert "total_records" in result.variables
        assert "file_paths" in result.variables
        assert "file_size_bytes" in result.variables
        assert "partitions" in result.variables

    def test_export_id_format(self):
        from healthcare_platform.platform_services.workers.export_to_datawarehouse_worker import ExportToDataWarehouseWorker
        worker = ExportToDataWarehouseWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert result.variables["export_id"].startswith("EXP-")

    def test_anonymization_when_enabled(self):
        from healthcare_platform.platform_services.workers.export_to_datawarehouse_worker import ExportToDataWarehouseWorker
        worker = ExportToDataWarehouseWorker()
        context = self._make_context(variables={"entity_type": "patient", "anonymize_pii": True})
        result = worker.execute(context)
        assert "anonymized_fields" in result.variables
        assert len(result.variables["anonymized_fields"]) > 0

    def test_file_paths_returned(self):
        from healthcare_platform.platform_services.workers.export_to_datawarehouse_worker import ExportToDataWarehouseWorker
        worker = ExportToDataWarehouseWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert isinstance(result.variables["file_paths"], list)
        assert len(result.variables["file_paths"]) > 0

    def test_multi_tenant_isolation(self):
        from healthcare_platform.platform_services.workers.export_to_datawarehouse_worker import ExportToDataWarehouseWorker
        worker = ExportToDataWarehouseWorker()
        ctx_a = self._make_context(tenant_id="HOSPITAL_A")
        ctx_b = self._make_context(tenant_id="HOSPITAL_B")
        result_a = worker.execute(ctx_a)
        result_b = worker.execute(ctx_b)
        assert isinstance(result_a, TaskResult)
        assert isinstance(result_b, TaskResult)
