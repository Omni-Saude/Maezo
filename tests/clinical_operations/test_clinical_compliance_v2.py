"""Tests for ClinicalComplianceWorkerV2."""
import pytest
from unittest.mock import MagicMock
from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.clinical_operations.workers.clinical_compliance_worker_v2 import (
    ClinicalComplianceWorkerV2,
)


@pytest.fixture
def worker():
    w = ClinicalComplianceWorkerV2.__new__(ClinicalComplianceWorkerV2)
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
            "compliance_domain": "regulatory",
            "encounter_reference": "ENC-001",
            "rule_reference": "ANVISA-RDC-222",
            "severity": "major",
            "verification_items": ["item1", "item2"],
        },
        worker_id="clinical.compliance",
    )


class TestComplianceWorkerV2HappyPath:
    def test_prosseguir_action(self, worker, context):
        worker.evaluate_dmn.return_value = {
            "action": "PROSSEGUIR",
            "violationsCount": 0,
            "criticalCount": 0,
            "complianceScore": 100.0,
            "complianceStatus": "compliant",
            "nivelAlerta": "OK",
            "justificativa": "Full compliance",
        }
        result = worker.execute(context)
        assert result.status == TaskStatus.SUCCESS
        assert result.variables["action"] == "PROSSEGUIR"
        assert result.variables["complianceStatus"] == "compliant"


class TestComplianceWorkerV2ErrorPath:
    def test_bloquear_triggers_escalation(self, worker, context):
        worker.evaluate_dmn.return_value = {
            "action": "BLOQUEAR",
            "violationsCount": 3,
            "criticalCount": 2,
            "violationSeverity": "critical",
            "complianceScore": 30.0,
            "complianceStatus": "non_compliant",
            "escalationLevel": "director",
            "escalationTarget": "compliance_officer",
            "nextVerificationDays": 7,
        }
        result = worker.execute(context)
        assert result.variables["action"] == "BLOQUEAR"
        assert result.variables["escalationLevel"] == "director"


class TestComplianceWorkerV2EdgeCase:
    def test_missing_action_defaults_to_revisar(self, worker, context):
        worker.evaluate_dmn.return_value = {}
        result = worker.execute(context)
        assert result.variables["action"] == "REVISAR"

    def test_exception_returns_bpmn_error(self, worker, context):
        worker.evaluate_dmn.side_effect = Exception("Timeout")
        result = worker.execute(context)
        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_CLINICAL_COMPLIANCE"
