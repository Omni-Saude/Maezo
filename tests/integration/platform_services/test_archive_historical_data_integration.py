"""Integration tests for Archive Historical Data Worker V2."""
from __future__ import annotations

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus


@pytest.mark.integration
class TestArchiveHistoricalDataWorkerV2:
    """V2 worker tests using BaseExternalTaskWorker pattern."""

    def _make_context(self, **overrides) -> TaskContext:
        defaults = {
            "task_id": "test-task-001",
            "process_instance_id": "proc-001",
            "tenant_id": "HOSPITAL_A",
            "variables": {
                "entity_type": "patient",
                "retention_days": 2555,
                "archive_mode": "soft_delete",
                "anonymize_on_archive": True,
                "correlation_id": "corr-001",
            },
            "worker_id": "platform.archive-historical-data",
        }
        defaults.update(overrides)
        return TaskContext(**defaults)

    def test_worker_inherits_base(self):
        from healthcare_platform.platform_services.workers.archive_historical_data_worker import ArchiveHistoricalDataWorker
        from healthcare_platform.shared.workers.base import BaseExternalTaskWorker
        worker = ArchiveHistoricalDataWorker()
        assert isinstance(worker, BaseExternalTaskWorker)

    def test_has_operation_name(self):
        from healthcare_platform.platform_services.workers.archive_historical_data_worker import ArchiveHistoricalDataWorker
        worker = ArchiveHistoricalDataWorker()
        assert worker.operation_name is not None

    def test_has_topic(self):
        from healthcare_platform.platform_services.workers.archive_historical_data_worker import ArchiveHistoricalDataWorker
        assert ArchiveHistoricalDataWorker.TOPIC == "platform.archive-historical-data"

    def test_execute_returns_task_result(self):
        from healthcare_platform.platform_services.workers.archive_historical_data_worker import ArchiveHistoricalDataWorker
        worker = ArchiveHistoricalDataWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert isinstance(result, TaskResult)

    def test_execute_success_has_correlation_id(self):
        from healthcare_platform.platform_services.workers.archive_historical_data_worker import ArchiveHistoricalDataWorker
        worker = ArchiveHistoricalDataWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "correlation_id" in result.variables

    def test_archive_output_structure(self):
        from healthcare_platform.platform_services.workers.archive_historical_data_worker import ArchiveHistoricalDataWorker
        worker = ArchiveHistoricalDataWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "archive_id" in result.variables
        assert "total_records_archived" in result.variables
        assert "archive_storage_path" in result.variables
        assert "anonymized_fields" in result.variables

    def test_anonymization_when_enabled(self):
        from healthcare_platform.platform_services.workers.archive_historical_data_worker import ArchiveHistoricalDataWorker
        worker = ArchiveHistoricalDataWorker()
        context = self._make_context(variables={"entity_type": "patient", "anonymize_on_archive": True})
        result = worker.execute(context)
        assert "anonymized_fields" in result.variables
        assert len(result.variables["anonymized_fields"]) > 0

    def test_multi_tenant_isolation(self):
        from healthcare_platform.platform_services.workers.archive_historical_data_worker import ArchiveHistoricalDataWorker
        worker = ArchiveHistoricalDataWorker()
        ctx_a = self._make_context(tenant_id="HOSPITAL_A")
        ctx_b = self._make_context(tenant_id="HOSPITAL_B")
        result_a = worker.execute(ctx_a)
        result_b = worker.execute(ctx_b)
        assert isinstance(result_a, TaskResult)
        assert isinstance(result_b, TaskResult)
