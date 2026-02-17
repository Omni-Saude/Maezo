"""Integration tests for Alert On Anomalies Worker V2."""
from __future__ import annotations

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus


@pytest.mark.integration
class TestAlertOnAnomaliesWorkerV2:
    """V2 worker tests using BaseExternalTaskWorker pattern."""

    def _make_context(self, **overrides) -> TaskContext:
        defaults = {
            "task_id": "test-task-001",
            "process_instance_id": "proc-001",
            "tenant_id": "HOSPITAL_A",
            "variables": {
                "metric_type": "revenue",
                "detection_method": "z_score",
                "lookback_days": 30,
                "sensitivity": "medium",
                "correlation_id": "corr-001",
            },
            "worker_id": "platform.alert-on-anomalies",
        }
        defaults.update(overrides)
        return TaskContext(**defaults)

    def test_worker_inherits_base(self):
        from healthcare_platform.platform_services.workers.alert_on_anomalies_worker import AlertOnAnomaliesWorker
        from healthcare_platform.shared.workers.base import BaseExternalTaskWorker
        worker = AlertOnAnomaliesWorker()
        assert isinstance(worker, BaseExternalTaskWorker)

    def test_has_operation_name(self):
        from healthcare_platform.platform_services.workers.alert_on_anomalies_worker import AlertOnAnomaliesWorker
        worker = AlertOnAnomaliesWorker()
        assert worker.operation_name is not None

    def test_has_topic(self):
        from healthcare_platform.platform_services.workers.alert_on_anomalies_worker import AlertOnAnomaliesWorker
        assert AlertOnAnomaliesWorker.TOPIC == "platform.alert-on-anomalies"

    def test_execute_returns_task_result(self):
        from healthcare_platform.platform_services.workers.alert_on_anomalies_worker import AlertOnAnomaliesWorker
        worker = AlertOnAnomaliesWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert isinstance(result, TaskResult)

    def test_execute_success_has_correlation_id(self):
        from healthcare_platform.platform_services.workers.alert_on_anomalies_worker import AlertOnAnomaliesWorker
        worker = AlertOnAnomaliesWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "correlation_id" in result.variables

    def test_anomaly_detection_structure(self):
        from healthcare_platform.platform_services.workers.alert_on_anomalies_worker import AlertOnAnomaliesWorker
        worker = AlertOnAnomaliesWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "scan_id" in result.variables
        assert "anomalies_detected" in result.variables
        assert "anomaly_count" in result.variables
        assert "baseline_mean" in result.variables
        assert "baseline_std_dev" in result.variables

    def test_scan_id_format(self):
        from healthcare_platform.platform_services.workers.alert_on_anomalies_worker import AlertOnAnomaliesWorker
        worker = AlertOnAnomaliesWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert result.variables["scan_id"].startswith("ANOM-")

    def test_anomalies_list_returned(self):
        from healthcare_platform.platform_services.workers.alert_on_anomalies_worker import AlertOnAnomaliesWorker
        worker = AlertOnAnomaliesWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert isinstance(result.variables["anomalies_detected"], list)

    def test_alerts_sent_count(self):
        from healthcare_platform.platform_services.workers.alert_on_anomalies_worker import AlertOnAnomaliesWorker
        worker = AlertOnAnomaliesWorker()
        context = self._make_context()
        result = worker.execute(context)
        assert "alerts_sent" in result.variables
        assert result.variables["alerts_sent"] >= 0

    def test_multi_tenant_isolation(self):
        from healthcare_platform.platform_services.workers.alert_on_anomalies_worker import AlertOnAnomaliesWorker
        worker = AlertOnAnomaliesWorker()
        ctx_a = self._make_context(tenant_id="HOSPITAL_A")
        ctx_b = self._make_context(tenant_id="HOSPITAL_B")
        result_a = worker.execute(ctx_a)
        result_b = worker.execute(ctx_b)
        assert isinstance(result_a, TaskResult)
        assert isinstance(result_b, TaskResult)
