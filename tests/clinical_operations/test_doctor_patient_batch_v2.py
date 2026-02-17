"""
Tests for Doctor/Patient LOW Complexity Workers (Refactored V2)

Purpose: Validate 21 LOW workers using pytest fixtures (no Stubs)

Test Categories:
1. Happy path - DMN returns PROSSEGUIR → TaskStatus.SUCCESS
2. BLOQUEAR path - DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR
3. Error handling - DMN raises Exception → TaskStatus.BPMN_ERROR

ADR Compliance:
- ADR-003: Pytest fixtures instead of Stub classes
- ADR-007: DMN federation mocking
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_dmn_service():
    """Mock FederatedDMNService with default PROSSEGUIR response."""
    mock = MagicMock()
    mock.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "Processar normalmente",
        "risco": "BAIXO",
    }
    return mock


@pytest.fixture
def mock_metrics():
    """Mock WorkerMetrics."""
    return MagicMock()


@pytest.fixture
def base_context():
    """Base task context for testing."""
    return TaskContext(
        task_id="task-001",
        process_instance_id="proc-001",
        tenant_id="HOSPITAL_TEST",
        variables={},
        worker_id="test-worker",
        retries=3,
    )


# ============================================================================
# DOCTOR BED AVAILABILITY WORKER TESTS
# ============================================================================

class TestDoctorBedAvailabilityWorker:
    """Tests for DoctorBedAvailabilityWorker."""

    def test_happy_path_prosseguir(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns PROSSEGUIR → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.doctor_bed_availability_worker import (
            DoctorBedAvailabilityWorker,
        )

        worker = DoctorBedAvailabilityWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "bed_id": "BED-101",
            "unit": "ICU",
            "bed_type": "critical_care",
            "patient_id": "Patient/p-123",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "PROSSEGUIR"
        assert result.variables["notification_sent"] is True
        mock_dmn_service.evaluate.assert_called_once()

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.doctor_bed_availability_worker import (
            DoctorBedAvailabilityWorker,
        )

        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Bed unavailable - maintenance",
            "risco": "MEDIO",
        }
        worker = DoctorBedAvailabilityWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"bed_id": "BED-101", "unit": "ICU", "bed_type": "critical_care", "patient_id": "Patient/p-123"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_BED_UNAVAILABLE"

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.doctor_bed_availability_worker import (
            DoctorBedAvailabilityWorker,
        )

        mock_dmn_service.evaluate.side_effect = ValueError("DMN evaluation failed")
        worker = DoctorBedAvailabilityWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"bed_id": "BED-101", "unit": "ICU"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_BED_AVAILABILITY"


# ============================================================================
# DOCTOR CME REMINDER WORKER TESTS
# ============================================================================

class TestDoctorCmeReminderWorker:
    """Tests for DoctorCmeReminderWorker."""

    def test_happy_path_prosseguir(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns PROSSEGUIR → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.doctor_cme_reminder_worker import (
            DoctorCmeReminderWorker,
        )

        worker = DoctorCmeReminderWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "doctor_id": "Practitioner/d-456",
            "credits_due": 12,
            "deadline_days": 30,
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "PROSSEGUIR"
        mock_dmn_service.evaluate.assert_called_once()

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.doctor_cme_reminder_worker import (
            DoctorCmeReminderWorker,
        )

        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "CME expired - restrict privileges",
            "risco": "ALTO",
        }
        worker = DoctorCmeReminderWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"doctor_id": "Practitioner/d-456", "credits_due": 50}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.doctor_cme_reminder_worker import (
            DoctorCmeReminderWorker,
        )

        mock_dmn_service.evaluate.side_effect = RuntimeError("DMN failure")
        worker = DoctorCmeReminderWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"doctor_id": "Practitioner/d-456"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR


# ============================================================================
# DOCTOR CRITICAL VALUE WORKER TESTS
# ============================================================================

class TestDoctorCriticalValueWorker:
    """Tests for DoctorCriticalValueWorker."""

    def test_happy_path_prosseguir(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns PROSSEGUIR → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.doctor_critical_value_worker import (
            DoctorCriticalValueWorker,
        )

        worker = DoctorCriticalValueWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "observation_reference": "Observation/o-789",
            "test_name": "Potassium",
            "critical_value": 6.5,
            "patient_reference": "Patient/p-123",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "PROSSEGUIR"

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.doctor_critical_value_worker import (
            DoctorCriticalValueWorker,
        )

        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Life-threatening value - immediate intervention",
            "risco": "CRITICO",
        }
        worker = DoctorCriticalValueWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"observation_reference": "Observation/o-789", "critical_value": 8.5}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.doctor_critical_value_worker import (
            DoctorCriticalValueWorker,
        )

        mock_dmn_service.evaluate.side_effect = Exception("Critical value processing failed")
        worker = DoctorCriticalValueWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"observation_reference": "Observation/o-789"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR


# ============================================================================
# DOCTOR DISCHARGE READINESS WORKER TESTS
# ============================================================================

class TestDoctorDischargeReadinessWorker:
    """Tests for DoctorDischargeReadinessWorker."""

    def test_happy_path_prosseguir(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns PROSSEGUIR → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.doctor_discharge_readiness_worker import (
            DoctorDischargeReadinessWorker,
        )

        worker = DoctorDischargeReadinessWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "encounter_reference": "Encounter/e-001",
            "criteria_met": 8,
            "criteria_total": 10,
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "PROSSEGUIR"

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.doctor_discharge_readiness_worker import (
            DoctorDischargeReadinessWorker,
        )

        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Not ready - pending tests",
            "risco": "MEDIO",
        }
        worker = DoctorDischargeReadinessWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"encounter_reference": "Encounter/e-001", "criteria_met": 3}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.doctor_discharge_readiness_worker import (
            DoctorDischargeReadinessWorker,
        )

        mock_dmn_service.evaluate.side_effect = ValueError("Readiness check failed")
        worker = DoctorDischargeReadinessWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"encounter_reference": "Encounter/e-001"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR


# ============================================================================
# DOCTOR FOLLOWUP COMPLETION WORKER TESTS
# ============================================================================

class TestDoctorFollowupCompletionWorker:
    """Tests for DoctorFollowupCompletionWorker."""

    def test_happy_path_prosseguir(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns PROSSEGUIR → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.doctor_followup_completion_worker import (
            DoctorFollowupCompletionWorker,
        )

        worker = DoctorFollowupCompletionWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "appointment_reference": "Appointment/a-567",
            "followup_completed": True,
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "PROSSEGUIR"

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.doctor_followup_completion_worker import (
            DoctorFollowupCompletionWorker,
        )

        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Followup overdue - escalate",
            "risco": "MEDIO",
        }
        worker = DoctorFollowupCompletionWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"appointment_reference": "Appointment/a-567", "followup_completed": False}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.doctor_followup_completion_worker import (
            DoctorFollowupCompletionWorker,
        )

        mock_dmn_service.evaluate.side_effect = RuntimeError("Followup check failed")
        worker = DoctorFollowupCompletionWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"appointment_reference": "Appointment/a-567"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR


# ============================================================================
# DOCTOR PATIENT FEEDBACK WORKER TESTS
# ============================================================================

class TestDoctorPatientFeedbackWorker:
    """Tests for DoctorPatientFeedbackWorker."""

    def test_happy_path_prosseguir(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns PROSSEGUIR → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.doctor_patient_feedback_worker import (
            DoctorPatientFeedbackWorker,
        )

        worker = DoctorPatientFeedbackWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "feedback_score": 4.5,
            "doctor_id": "Practitioner/d-789",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "PROSSEGUIR"

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.doctor_patient_feedback_worker import (
            DoctorPatientFeedbackWorker,
        )

        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Low satisfaction - requires review",
            "risco": "ALTO",
        }
        worker = DoctorPatientFeedbackWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"feedback_score": 1.5, "doctor_id": "Practitioner/d-789"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.doctor_patient_feedback_worker import (
            DoctorPatientFeedbackWorker,
        )

        mock_dmn_service.evaluate.side_effect = Exception("Feedback processing failed")
        worker = DoctorPatientFeedbackWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"feedback_score": 3.0}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR


# ============================================================================
# DOCTOR PATIENT RECOVERY ALERT WORKER TESTS
# ============================================================================

class TestDoctorPatientRecoveryAlertWorker:
    """Tests for DoctorPatientRecoveryAlertWorker."""

    def test_happy_path_prosseguir(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns PROSSEGUIR → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.doctor_patient_recovery_alert_worker import (
            DoctorPatientRecoveryAlertWorker,
        )

        worker = DoctorPatientRecoveryAlertWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "patient_id": "Patient/p-999",
            "recovery_status": "on_track",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "PROSSEGUIR"

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.doctor_patient_recovery_alert_worker import (
            DoctorPatientRecoveryAlertWorker,
        )

        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Recovery delayed - alert team",
            "risco": "MEDIO",
        }
        worker = DoctorPatientRecoveryAlertWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"patient_id": "Patient/p-999", "recovery_status": "delayed"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.doctor_patient_recovery_alert_worker import (
            DoctorPatientRecoveryAlertWorker,
        )

        mock_dmn_service.evaluate.side_effect = ValueError("Recovery check failed")
        worker = DoctorPatientRecoveryAlertWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"patient_id": "Patient/p-999"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR


# ============================================================================
# DOCTOR PERFORMANCE SUMMARY WORKER TESTS
# ============================================================================

class TestDoctorPerformanceSummaryWorker:
    """Tests for DoctorPerformanceSummaryWorker."""

    def test_happy_path_prosseguir(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns PROSSEGUIR → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.doctor_performance_summary_worker import (
            DoctorPerformanceSummaryWorker,
        )

        worker = DoctorPerformanceSummaryWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "doctor_id": "Practitioner/d-111",
            "performance_score": 85,
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "PROSSEGUIR"

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.doctor_performance_summary_worker import (
            DoctorPerformanceSummaryWorker,
        )

        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Performance below threshold",
            "risco": "ALTO",
        }
        worker = DoctorPerformanceSummaryWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"doctor_id": "Practitioner/d-111", "performance_score": 45}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.doctor_performance_summary_worker import (
            DoctorPerformanceSummaryWorker,
        )

        mock_dmn_service.evaluate.side_effect = RuntimeError("Performance calculation failed")
        worker = DoctorPerformanceSummaryWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"doctor_id": "Practitioner/d-111"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR


# ============================================================================
# DOCTOR READMISSION RISK WORKER TESTS
# ============================================================================

class TestDoctorReadmissionRiskWorker:
    """Tests for DoctorReadmissionRiskWorker."""

    def test_happy_path_prosseguir(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns PROSSEGUIR → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.doctor_readmission_risk_worker import (
            DoctorReadmissionRiskWorker,
        )

        worker = DoctorReadmissionRiskWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "patient_id": "Patient/p-222",
            "risk_score": 0.25,
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "PROSSEGUIR"

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.doctor_readmission_risk_worker import (
            DoctorReadmissionRiskWorker,
        )

        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "High readmission risk - intervention needed",
            "risco": "ALTO",
        }
        worker = DoctorReadmissionRiskWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"patient_id": "Patient/p-222", "risk_score": 0.85}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.doctor_readmission_risk_worker import (
            DoctorReadmissionRiskWorker,
        )

        mock_dmn_service.evaluate.side_effect = Exception("Risk calculation failed")
        worker = DoctorReadmissionRiskWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"patient_id": "Patient/p-222"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR


# ============================================================================
# DOCTOR REFERRAL STATUS WORKER TESTS
# ============================================================================

class TestDoctorReferralStatusWorker:
    """Tests for DoctorReferralStatusWorker."""

    def test_happy_path_prosseguir(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns PROSSEGUIR → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.doctor_referral_status_worker import (
            DoctorReferralStatusWorker,
        )

        worker = DoctorReferralStatusWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "referral_id": "ServiceRequest/r-333",
            "referral_status": "accepted",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "PROSSEGUIR"

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.doctor_referral_status_worker import (
            DoctorReferralStatusWorker,
        )

        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Referral rejected - alternate required",
            "risco": "MEDIO",
        }
        worker = DoctorReferralStatusWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"referral_id": "ServiceRequest/r-333", "referral_status": "rejected"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.doctor_referral_status_worker import (
            DoctorReferralStatusWorker,
        )

        mock_dmn_service.evaluate.side_effect = ValueError("Referral processing failed")
        worker = DoctorReferralStatusWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"referral_id": "ServiceRequest/r-333"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR


# ============================================================================
# DOCTOR ROUNDS SUMMARY WORKER TESTS
# ============================================================================

class TestDoctorRoundsSummaryWorker:
    """Tests for DoctorRoundsSummaryWorker."""

    def test_happy_path_prosseguir(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns PROSSEGUIR → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.doctor_rounds_summary_worker import (
            DoctorRoundsSummaryWorker,
        )

        worker = DoctorRoundsSummaryWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "doctor_id": "Practitioner/d-444",
            "rounds_completed": 10,
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "PROSSEGUIR"

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.doctor_rounds_summary_worker import (
            DoctorRoundsSummaryWorker,
        )

        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Rounds incomplete - escalate",
            "risco": "MEDIO",
        }
        worker = DoctorRoundsSummaryWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"doctor_id": "Practitioner/d-444", "rounds_completed": 2}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.doctor_rounds_summary_worker import (
            DoctorRoundsSummaryWorker,
        )

        mock_dmn_service.evaluate.side_effect = RuntimeError("Rounds summary failed")
        worker = DoctorRoundsSummaryWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"doctor_id": "Practitioner/d-444"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR


# ============================================================================
# DOCTOR SPECIALIST CONSULT WORKER TESTS
# ============================================================================

class TestDoctorSpecialistConsultWorker:
    """Tests for DoctorSpecialistConsultWorker."""

    def test_happy_path_prosseguir(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns PROSSEGUIR → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.doctor_specialist_consult_worker import (
            DoctorSpecialistConsultWorker,
        )

        worker = DoctorSpecialistConsultWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "consult_request": "ServiceRequest/c-555",
            "specialty": "cardiology",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "PROSSEGUIR"

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.doctor_specialist_consult_worker import (
            DoctorSpecialistConsultWorker,
        )

        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "No specialist available",
            "risco": "ALTO",
        }
        worker = DoctorSpecialistConsultWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"consult_request": "ServiceRequest/c-555", "specialty": "neurology"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.doctor_specialist_consult_worker import (
            DoctorSpecialistConsultWorker,
        )

        mock_dmn_service.evaluate.side_effect = Exception("Consult request failed")
        worker = DoctorSpecialistConsultWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"consult_request": "ServiceRequest/c-555"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR


# ============================================================================
# DOCTOR TRIAGE ESCALATION WORKER TESTS
# ============================================================================

class TestDoctorTriageEscalationWorker:
    """Tests for DoctorTriageEscalationWorker."""

    def test_happy_path_prosseguir(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns PROSSEGUIR → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.doctor_triage_escalation_worker import (
            DoctorTriageEscalationWorker,
        )

        worker = DoctorTriageEscalationWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "triage_score": 3,
            "patient_id": "Patient/p-666",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "PROSSEGUIR"

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.doctor_triage_escalation_worker import (
            DoctorTriageEscalationWorker,
        )

        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Critical triage - immediate escalation",
            "risco": "CRITICO",
        }
        worker = DoctorTriageEscalationWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"triage_score": 1, "patient_id": "Patient/p-666"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.doctor_triage_escalation_worker import (
            DoctorTriageEscalationWorker,
        )

        mock_dmn_service.evaluate.side_effect = ValueError("Triage escalation failed")
        worker = DoctorTriageEscalationWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"triage_score": 1}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR


# ============================================================================
# PATIENT CARE TEAM INTRO WORKER TESTS
# ============================================================================

class TestPatientCareTeamIntroWorker:
    """Tests for PatientCareTeamIntroWorker."""

    def test_happy_path_prosseguir(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns PROSSEGUIR → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.patient_care_team_intro_worker import (
            PatientCareTeamIntroWorker,
        )

        worker = PatientCareTeamIntroWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "patient_id": "Patient/p-777",
            "care_team": ["Dr. Smith", "Nurse Jones"],
            "unit_info": {"name": "Cardiology"},
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "PROSSEGUIR"
        assert result.variables["notification_sent"] is True

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.patient_care_team_intro_worker import (
            PatientCareTeamIntroWorker,
        )

        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Care team incomplete",
            "risco": "MEDIO",
        }
        worker = PatientCareTeamIntroWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"patient_id": "Patient/p-777", "care_team": []}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_CARE_TEAM_INTRO_BLOCKED"

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.patient_care_team_intro_worker import (
            PatientCareTeamIntroWorker,
        )

        mock_dmn_service.evaluate.side_effect = RuntimeError("Care team intro failed")
        worker = PatientCareTeamIntroWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"patient_id": "Patient/p-777"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_CARE_TEAM_INTRO"


# ============================================================================
# PATIENT DAILY CARE PLAN WORKER TESTS
# ============================================================================

class TestPatientDailyCarePlanWorker:
    """Tests for PatientDailyCarePlanWorker."""

    def test_happy_path_prosseguir(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns PROSSEGUIR → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.patient_daily_care_plan_worker import (
            PatientDailyCarePlanWorker,
        )

        worker = PatientDailyCarePlanWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "patient_id": "Patient/p-888",
            "care_plan_id": "CarePlan/cp-001",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "PROSSEGUIR"

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.patient_daily_care_plan_worker import (
            PatientDailyCarePlanWorker,
        )

        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Care plan outdated",
            "risco": "MEDIO",
        }
        worker = PatientDailyCarePlanWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"patient_id": "Patient/p-888"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.patient_daily_care_plan_worker import (
            PatientDailyCarePlanWorker,
        )

        mock_dmn_service.evaluate.side_effect = Exception("Daily care plan failed")
        worker = PatientDailyCarePlanWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"patient_id": "Patient/p-888"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR


# ============================================================================
# PATIENT FOLLOWUP REMINDER WORKER TESTS
# ============================================================================

class TestPatientFollowupReminderWorker:
    """Tests for PatientFollowupReminderWorker."""

    def test_happy_path_prosseguir(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns PROSSEGUIR → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.patient_followup_reminder_worker import (
            PatientFollowupReminderWorker,
        )

        worker = PatientFollowupReminderWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "patient_id": "Patient/p-999",
            "appointment_date": "2026-03-01",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "PROSSEGUIR"

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.patient_followup_reminder_worker import (
            PatientFollowupReminderWorker,
        )

        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "No contact information",
            "risco": "BAIXO",
        }
        worker = PatientFollowupReminderWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"patient_id": "Patient/p-999"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.patient_followup_reminder_worker import (
            PatientFollowupReminderWorker,
        )

        mock_dmn_service.evaluate.side_effect = ValueError("Reminder processing failed")
        worker = PatientFollowupReminderWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"patient_id": "Patient/p-999"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR


# ============================================================================
# PATIENT MEAL PREFERENCE WORKER TESTS
# ============================================================================

class TestPatientMealPreferenceWorker:
    """Tests for PatientMealPreferenceWorker."""

    def test_happy_path_prosseguir(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns PROSSEGUIR → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.patient_meal_preference_worker import (
            PatientMealPreferenceWorker,
        )

        worker = PatientMealPreferenceWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "patient_id": "Patient/p-1010",
            "dietary_restrictions": ["vegetarian"],
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "PROSSEGUIR"

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.patient_meal_preference_worker import (
            PatientMealPreferenceWorker,
        )

        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Conflicting dietary restrictions",
            "risco": "MEDIO",
        }
        worker = PatientMealPreferenceWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"patient_id": "Patient/p-1010", "dietary_restrictions": ["kosher", "vegan", "diabetic"]}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.patient_meal_preference_worker import (
            PatientMealPreferenceWorker,
        )

        mock_dmn_service.evaluate.side_effect = RuntimeError("Meal preference failed")
        worker = PatientMealPreferenceWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"patient_id": "Patient/p-1010"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR


# ============================================================================
# PATIENT MEDICATION ADHERENCE WORKER TESTS
# ============================================================================

class TestPatientMedicationAdherenceWorker:
    """Tests for PatientMedicationAdherenceWorker."""

    def test_happy_path_prosseguir(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns PROSSEGUIR → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.patient_medication_adherence_worker import (
            PatientMedicationAdherenceWorker,
        )

        worker = PatientMedicationAdherenceWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "patient_id": "Patient/p-1111",
            "adherence_rate": 0.95,
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "PROSSEGUIR"

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.patient_medication_adherence_worker import (
            PatientMedicationAdherenceWorker,
        )

        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Low adherence - intervention required",
            "risco": "ALTO",
        }
        worker = PatientMedicationAdherenceWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"patient_id": "Patient/p-1111", "adherence_rate": 0.35}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.patient_medication_adherence_worker import (
            PatientMedicationAdherenceWorker,
        )

        mock_dmn_service.evaluate.side_effect = Exception("Adherence calculation failed")
        worker = PatientMedicationAdherenceWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"patient_id": "Patient/p-1111"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR


# ============================================================================
# PATIENT MEDICATION REMINDER WORKER TESTS
# ============================================================================

class TestPatientMedicationReminderWorker:
    """Tests for PatientMedicationReminderWorker."""

    def test_happy_path_prosseguir(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns PROSSEGUIR → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.patient_medication_reminder_worker import (
            PatientMedicationReminderWorker,
        )

        worker = PatientMedicationReminderWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "patient_id": "Patient/p-1212",
            "medication_name": "Aspirin",
            "scheduled_time": "08:00",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "PROSSEGUIR"

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.patient_medication_reminder_worker import (
            PatientMedicationReminderWorker,
        )

        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Medication discontinued",
            "risco": "BAIXO",
        }
        worker = PatientMedicationReminderWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"patient_id": "Patient/p-1212", "medication_name": "Discontinued Med"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.patient_medication_reminder_worker import (
            PatientMedicationReminderWorker,
        )

        mock_dmn_service.evaluate.side_effect = ValueError("Reminder failed")
        worker = PatientMedicationReminderWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"patient_id": "Patient/p-1212"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR


# ============================================================================
# PATIENT RECOVERY CHECKIN WORKER TESTS
# ============================================================================

class TestPatientRecoveryCheckinWorker:
    """Tests for PatientRecoveryCheckinWorker."""

    def test_happy_path_prosseguir(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns PROSSEGUIR → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.patient_recovery_checkin_worker import (
            PatientRecoveryCheckinWorker,
        )

        worker = PatientRecoveryCheckinWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "patient_id": "Patient/p-1313",
            "recovery_status": "improving",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "PROSSEGUIR"

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.patient_recovery_checkin_worker import (
            PatientRecoveryCheckinWorker,
        )

        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Recovery setback detected",
            "risco": "ALTO",
        }
        worker = PatientRecoveryCheckinWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"patient_id": "Patient/p-1313", "recovery_status": "deteriorating"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.patient_recovery_checkin_worker import (
            PatientRecoveryCheckinWorker,
        )

        mock_dmn_service.evaluate.side_effect = RuntimeError("Recovery check failed")
        worker = PatientRecoveryCheckinWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"patient_id": "Patient/p-1313"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR


# ============================================================================
# PATIENT TEST RESULTS WORKER TESTS
# ============================================================================

class TestPatientTestResultsWorker:
    """Tests for PatientTestResultsWorker."""

    def test_happy_path_prosseguir(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns PROSSEGUIR → TaskStatus.SUCCESS."""
        from healthcare_platform.clinical_operations.workers.patient_test_results_worker import (
            PatientTestResultsWorker,
        )

        worker = PatientTestResultsWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {
            "patient_id": "Patient/p-1414",
            "test_type": "blood_work",
            "results_available": True,
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["resultado"] == "PROSSEGUIR"

    def test_bloquear_path(self, mock_dmn_service, mock_metrics, base_context):
        """DMN returns BLOQUEAR → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.patient_test_results_worker import (
            PatientTestResultsWorker,
        )

        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Abnormal results - urgent review",
            "risco": "CRITICO",
        }
        worker = PatientTestResultsWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"patient_id": "Patient/p-1414", "test_type": "cardiac_enzymes", "results_abnormal": True}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR

    def test_error_handling(self, mock_dmn_service, mock_metrics, base_context):
        """DMN raises Exception → TaskStatus.BPMN_ERROR."""
        from healthcare_platform.clinical_operations.workers.patient_test_results_worker import (
            PatientTestResultsWorker,
        )

        mock_dmn_service.evaluate.side_effect = Exception("Test results processing failed")
        worker = PatientTestResultsWorker(dmn_service=mock_dmn_service, metrics=mock_metrics)
        base_context.variables = {"patient_id": "Patient/p-1414"}

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
