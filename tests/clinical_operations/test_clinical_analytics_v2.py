"""Tests for ClinicalAnalyticsWorkerV2."""
import pytest
from unittest.mock import MagicMock
from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.clinical_operations.workers.clinical_analytics_worker_v2 import (
    ClinicalAnalyticsWorkerV2,
)


@pytest.fixture
def worker():
    w = ClinicalAnalyticsWorkerV2.__new__(ClinicalAnalyticsWorkerV2)
    w.dmn_service = MagicMock()
    w.tenant_resolver = MagicMock()
    w.lgpd_hasher = MagicMock()
    w.metrics = MagicMock()
    w.logger = MagicMock()
    w.evaluate_dmn = MagicMock()
    return w


@pytest.fixture
def context():
    return TaskContext(
        task_id="test-123",
        process_instance_id="proc-456",
        tenant_id="hospital-A",
        variables={
            "analytics_type": "kpi",
            "metric_name": "readmission_rate",
            "metric_value": 3.5,
            "granularity": "daily",
        },
        worker_id="clinical.analytics",
    )


class TestAnalyticsWorkerV2HappyPath:
    def test_prosseguir_action(self, worker, context):
        worker.evaluate_dmn.return_value = {
            "action": "PROSSEGUIR",
            "nivelAlerta": "OK",
            "kpiStatus": "within_target",
            "kpiScore": 95.0,
            "threshold": 5.0,
            "variance": -1.5,
            "qualityScore": 90.0,
            "qualityLevel": "excellent",
        }
        result = worker.execute(context)
        assert result.status == TaskStatus.SUCCESS
        assert result.variables["action"] == "PROSSEGUIR"
        assert result.variables["analyticsType"] == "kpi"


class TestAnalyticsWorkerV2ErrorPath:
    def test_bloquear_action(self, worker, context):
        worker.evaluate_dmn.return_value = {
            "action": "BLOQUEAR",
            "nivelAlerta": "Critico",
            "kpiStatus": "critical",
            "kpiScore": 20.0,
        }
        result = worker.execute(context)
        assert result.variables["action"] == "BLOQUEAR"


class TestAnalyticsWorkerV2EdgeCase:
    def test_missing_action_defaults_to_revisar(self, worker, context):
        worker.evaluate_dmn.return_value = {}
        result = worker.execute(context)
        assert result.variables["action"] == "REVISAR"

    def test_exception_returns_bpmn_error(self, worker, context):
        worker.evaluate_dmn.side_effect = Exception("Service down")
        result = worker.execute(context)
        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_CLINICAL_ANALYTICS"
