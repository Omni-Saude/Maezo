"""Tests for VitalSignsMonitoringWorkerV2."""
import pytest
from unittest.mock import MagicMock
from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.clinical_operations.workers.vital_signs_monitoring_worker_v2 import (
    VitalSignsMonitoringWorkerV2,
)


@pytest.fixture
def worker():
    w = VitalSignsMonitoringWorkerV2.__new__(VitalSignsMonitoringWorkerV2)
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
            "vital_signs": {
                "heart_rate": 72,
                "oxygen_saturation": 98,
                "temperature_celsius": 36.5,
                "systolic_bp": 120,
                "diastolic_bp": 80,
                "respiratory_rate": 16,
            },
        },
        worker_id="clinical.vital_signs",
    )


class TestVitalSignsWorkerV2HappyPath:
    def test_prosseguir_all_normal(self, worker, context):
        worker.evaluate_dmn.return_value = {
            "action": "PROSSEGUIR",
            "severity": "INFO",
            "classification": "normal",
            "requiresImmediate": False,
            "notifyTeam": "",
        }
        result = worker.execute(context)
        assert result.status == TaskStatus.SUCCESS
        assert result.variables["action"] == "PROSSEGUIR"
        assert result.variables["vital_signs_status"] == "NORMAL"


class TestVitalSignsWorkerV2ErrorPath:
    def test_bloquear_critical_vitals(self, worker, context):
        worker.evaluate_dmn.return_value = {
            "action": "BLOQUEAR",
            "severity": "CRITICAL",
            "classification": "critical_high",
            "requiresImmediate": True,
            "notifyTeam": "rapid_response",
        }
        result = worker.execute(context)
        assert result.variables["action"] == "BLOQUEAR"
        assert result.variables["vital_signs_status"] == "CRITICAL"
        assert result.variables["requires_immediate_attention"] is True


class TestVitalSignsWorkerV2EdgeCase:
    def test_missing_action_defaults_to_revisar(self, worker, context):
        worker.evaluate_dmn.return_value = {}
        result = worker.execute(context)
        assert result.variables["action"] == "REVISAR"

    def test_empty_vital_signs_returns_bpmn_error(self, worker, context):
        context.variables["vital_signs"] = {}
        result = worker.execute(context)
        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "CLINICAL_ALERT"

    def test_exception_returns_bpmn_error(self, worker, context):
        worker.evaluate_dmn.side_effect = Exception("DMN error")
        result = worker.execute(context)
        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "CLINICAL_ALERT"
