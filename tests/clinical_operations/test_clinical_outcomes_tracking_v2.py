"""Tests for ClinicalOutcomesTrackingWorkerV2."""
import pytest
from unittest.mock import MagicMock
from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.clinical_operations.workers.clinical_outcomes_tracking_worker_v2 import (
    ClinicalOutcomesTrackingWorkerV2,
)


@pytest.fixture
def worker():
    w = ClinicalOutcomesTrackingWorkerV2.__new__(ClinicalOutcomesTrackingWorkerV2)
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
            "outcome_measures": [{"value": 80}, {"value": 90}],
            "assessment_type": "interim",
            "patient_reference": "PAT-001",
            "encounter_reference": "ENC-001",
            "outcome_goals": [{"target_value": 100, "current_value": 85}],
            "improvement_trend": "improving",
            "statistical_significance": True,
            "clinical_significance": "improvement",
            "benchmark_percentile": 75.0,
        },
        worker_id="clinical.outcomes",
    )


class TestOutcomesWorkerV2HappyPath:
    def test_prosseguir_action(self, worker, context):
        worker.evaluate_dmn.return_value = {
            "action": "PROSSEGUIR",
            "outcomeCategory": "good",
            "trajectory": "improving",
            "riskLevel": "low",
            "complicationGrade": "none",
            "qualityTier": "tier1",
            "nextAssessmentDays": 14,
            "justificativa": "On track",
        }
        result = worker.execute(context)
        assert result.status == TaskStatus.SUCCESS
        assert result.variables["action"] == "PROSSEGUIR"
        assert result.variables["outcomeScore"] == 85.0


class TestOutcomesWorkerV2ErrorPath:
    def test_bloquear_action(self, worker, context):
        worker.evaluate_dmn.return_value = {
            "action": "BLOQUEAR",
            "outcomeCategory": "critical",
            "trajectory": "declining",
            "riskLevel": "high",
            "complicationGrade": "severe",
            "qualityTier": "tier4",
            "nextAssessmentDays": 1,
            "justificativa": "Critical decline",
        }
        result = worker.execute(context)
        assert result.status == TaskStatus.SUCCESS
        assert result.variables["action"] == "BLOQUEAR"


class TestOutcomesWorkerV2EdgeCase:
    def test_missing_action_defaults_to_revisar(self, worker, context):
        worker.evaluate_dmn.return_value = {}
        result = worker.execute(context)
        # _worst_action with all "REVISAR" defaults returns "REVISAR"
        assert result.variables["action"] == "REVISAR"

    def test_empty_measures_score_zero(self, worker, context):
        context.variables["outcome_measures"] = []
        worker.evaluate_dmn.return_value = {"action": "PROSSEGUIR"}
        result = worker.execute(context)
        assert result.variables["outcomeScore"] == 0.0

    def test_exception_returns_bpmn_error(self, worker, context):
        worker.evaluate_dmn.side_effect = Exception("DMN down")
        result = worker.execute(context)
        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_OUTCOMES_TRACKING"
