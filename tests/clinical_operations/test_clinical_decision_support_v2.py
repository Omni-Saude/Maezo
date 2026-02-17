"""Tests for ClinicalDecisionSupportWorkerV2."""
import pytest
from unittest.mock import MagicMock
from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.clinical_operations.workers.clinical_decision_support_worker_v2 import (
    ClinicalDecisionSupportWorkerV2,
)


@pytest.fixture
def worker():
    w = ClinicalDecisionSupportWorkerV2.__new__(ClinicalDecisionSupportWorkerV2)
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
            "decision_type": "all",
            "encounter_reference": "ENC-001",
            "medications": ["med1"],
            "allergies": [],
            "diagnosis_codes": [],
            "lab_results": [],
            "age_years": 45,
            "renal_function": "normal",
            "hepatic_function": "normal",
            "pregnancy_status": False,
        },
        worker_id="clinical.decision_support",
    )


class TestCDSWorkerV2HappyPath:
    def test_prosseguir_action(self, worker, context):
        worker.evaluate_dmn.return_value = {
            "resultado": "PROSSEGUIR",
            "action": "PROSSEGUIR",
            "requiresPhysicianReview": False,
            "pathway": "standard",
            "severity": "low",
            "priority": 5,
            "displayOrder": "inline_info",
            "requiresOverride": False,
            "dismissible": True,
        }
        result = worker.execute(context)
        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "PROSSEGUIR"

    def test_output_contains_session_id(self, worker, context):
        worker.evaluate_dmn.return_value = {
            "resultado": "PROSSEGUIR",
            "action": "PROSSEGUIR",
            "requiresPhysicianReview": False,
            "pathway": "standard",
            "severity": "low",
            "priority": 5,
            "displayOrder": "inline_info",
            "requiresOverride": False,
            "dismissible": True,
        }
        result = worker.execute(context)
        assert "supportSessionId" in result.variables
        assert result.variables["supportSessionId"].startswith("CDS-")


class TestCDSWorkerV2ErrorPath:
    def test_bloquear_action(self, worker, context):
        worker.evaluate_dmn.return_value = {
            "resultado": "BLOQUEAR",
            "action": "BLOQUEAR",
            "requiresPhysicianReview": True,
            "pathway": "critical",
            "severity": "critical",
            "priority": 1,
            "displayOrder": "modal",
            "requiresOverride": True,
            "dismissible": False,
        }
        result = worker.execute(context)
        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "CDS_CRITICAL_BLOCK"


class TestCDSWorkerV2EdgeCase:
    def test_missing_action_defaults_to_revisar(self, worker, context):
        worker.evaluate_dmn.return_value = {}
        result = worker.execute(context)
        # With empty DMN, resultado defaults to _FAIL_SAFE="REVISAR"
        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "REVISAR"

    def test_exception_returns_failsafe(self, worker, context):
        worker.evaluate_dmn.side_effect = Exception("DMN unavailable")
        result = worker.execute(context)
        assert result.status == TaskStatus.BPMN_ERROR
        assert result.variables.get("resultado") == "REVISAR"
