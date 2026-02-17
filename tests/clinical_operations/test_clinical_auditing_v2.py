"""Tests for ClinicalAuditingWorkerV2."""
import pytest
from unittest.mock import MagicMock
from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.clinical_operations.workers.clinical_auditing_worker_v2 import (
    ClinicalAuditingWorkerV2,
)


@pytest.fixture
def worker():
    w = ClinicalAuditingWorkerV2.__new__(ClinicalAuditingWorkerV2)
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
            "audit_type": "documentation",
            "encounter_reference": "ENC-001",
            "compliance_score": 95.0,
            "critical_findings_count": 0,
            "finding_severity": "low",
        },
        worker_id="clinical.auditing",
    )


class TestAuditingWorkerV2HappyPath:
    def test_prosseguir_action(self, worker, context):
        worker.evaluate_dmn.return_value = {
            "action": "PROSSEGUIR",
            "overallStatus": "compliant",
            "nextAuditDays": 90,
            "justificativa": "All clear",
            "complianceStatus": "compliant",
            "priority": "low",
            "dueDays": 30,
        }
        result = worker.execute(context)
        assert result.status == TaskStatus.SUCCESS
        assert result.variables["action"] == "PROSSEGUIR"
        assert "auditId" in result.variables


class TestAuditingWorkerV2ErrorPath:
    def test_bloquear_action(self, worker, context):
        context.variables["critical_findings_count"] = 5
        worker.evaluate_dmn.return_value = {
            "action": "BLOQUEAR",
            "overallStatus": "non_compliant",
            "nextAuditDays": 7,
            "justificativa": "Critical findings",
            "complianceStatus": "non_compliant",
            "priority": "critical",
            "dueDays": 1,
        }
        result = worker.execute(context)
        assert result.variables["action"] == "BLOQUEAR"


class TestAuditingWorkerV2EdgeCase:
    def test_missing_action_defaults_to_revisar(self, worker, context):
        worker.evaluate_dmn.return_value = {}
        result = worker.execute(context)
        assert result.variables["action"] == "REVISAR"

    def test_exception_returns_bpmn_error(self, worker, context):
        worker.evaluate_dmn.side_effect = Exception("DMN timeout")
        result = worker.execute(context)
        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_CLINICAL_AUDIT"
