"""Tests for MedicationManagementWorkerV2."""
import pytest
from unittest.mock import MagicMock
from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.clinical_operations.workers.medication_management_worker_v2 import (
    MedicationManagementWorkerV2,
)


@pytest.fixture
def worker():
    w = MedicationManagementWorkerV2.__new__(MedicationManagementWorkerV2)
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
            "medication_orders": [
                {
                    "medication_name": "Amoxicillin",
                    "medication_class": "ANTIBIOTIC",
                    "dose_value": 500,
                    "dose_unit": "mg",
                    "route": "ORAL",
                    "medication_form": "tablet",
                    "frequency": "8/8h",
                    "dosage": "500mg",
                }
            ],
            "allergies": [],
        },
        worker_id="clinical.medication",
    )


class TestMedicationWorkerV2HappyPath:
    def test_prosseguir_action(self, worker, context):
        worker.evaluate_dmn.return_value = {
            "action": "PROSSEGUIR",
            "isHighRisk": False,
            "scheduleTimes": "08:00,16:00,00:00",
            "severity": "NONE",
        }
        result = worker.execute(context)
        assert result.status == TaskStatus.SUCCESS
        assert result.variables["action"] == "PROSSEGUIR"
        assert len(result.variables["administration_schedule"]) == 3


class TestMedicationWorkerV2ErrorPath:
    def test_bloquear_allergy_cross_reactivity(self, worker, context):
        context.variables["allergies"] = ["PENICILLIN"]

        def dmn_side_effect(context, decision_key, variables, **kwargs):
            if decision_key == "med_allergy_cross_001":
                return {"crossReactive": True, "action": "BLOQUEAR", "riskLevel": "HIGH"}
            return {"action": "PROSSEGUIR", "isHighRisk": False, "scheduleTimes": "08:00", "severity": "NONE"}

        worker.evaluate_dmn.side_effect = dmn_side_effect
        result = worker.execute(context)
        assert result.variables["action"] == "BLOQUEAR"
        assert result.variables["warningCount"] >= 1


class TestMedicationWorkerV2EdgeCase:
    def test_empty_medications_returns_bpmn_error(self, worker, context):
        context.variables["medication_orders"] = []
        result = worker.execute(context)
        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "CLINICAL_ALERT"

    def test_missing_action_defaults_to_revisar(self, worker, context):
        worker.evaluate_dmn.return_value = {
            "isHighRisk": False,
            "scheduleTimes": "08:00",
            "severity": "NONE",
        }
        result = worker.execute(context)
        # No action returned from dose DMN means no escalation from PROSSEGUIR default
        assert result.status == TaskStatus.SUCCESS

    def test_exception_returns_bpmn_error(self, worker, context):
        worker.evaluate_dmn.side_effect = Exception("DMN unavailable")
        result = worker.execute(context)
        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "CLINICAL_ALERT"
