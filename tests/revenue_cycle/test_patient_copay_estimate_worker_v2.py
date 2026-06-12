"""
from __future__ import annotations

Tests for Patient Copay Estimate Worker (Refactored v2)

Test Categories:
1. Happy path - PROSSEGUIR sends notification
2. BLOQUEAR - invalid phone format
3. REVISAR - needs manual review
4. Missing/invalid input
5. DMN evaluator failure
6. Edge case - invalid coverage percentage blocked by DMN
"""

from unittest.mock import MagicMock

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskStatus


@pytest.fixture
def mock_dmn_service():
    mock = MagicMock()
    mock.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "Copay estimate valid",
        "risco": "BAIXO",
    }
    return mock


@pytest.fixture
def mock_whatsapp_client():
    mock = MagicMock()
    mock.send_template.return_value = "msg_copay_001"
    return mock


@pytest.fixture
def mock_metrics():
    return MagicMock()


@pytest.fixture
def base_context():
    return TaskContext(
        task_id="task_005",
        process_instance_id="proc_005",
        tenant_id="HOSPITAL_TEST",
        variables={
            "patientId": "pat_202",
            "phoneNumber": "+5511955555555",
            "appointmentId": "appt_789",
            "estimatedCopay": 150.00,
            "insuranceCoverage": 80.0,
            "appointmentDate": "2026-03-15",
        },
        worker_id="financial.copay_estimate",
    )


@pytest.fixture
def worker(mock_dmn_service, mock_whatsapp_client, mock_metrics):
    from healthcare_platform.revenue_cycle.billing.workers.patient_copay_estimate_worker import (
        PatientCopayEstimateWorker,
    )
    return PatientCopayEstimateWorker(
        whatsapp_client=mock_whatsapp_client,
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
    )


class TestPatientCopayEstimateV2:
    def test_happy_path_prosseguir_sends_notification(self, worker, base_context, mock_whatsapp_client):
        """PROSSEGUIR: copay estimate sent via WhatsApp."""
        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["notificationSent"] is True
        assert result.variables["resultado"] == "PROSSEGUIR"
        assert result.variables["formattedCopay"] == "R$ 150,00"
        mock_whatsapp_client.send_template.assert_called_once()

    def test_bloquear_invalid_phone(self, worker, base_context, mock_dmn_service):
        """BLOQUEAR: invalid phone format returns BPMN error."""
        base_context.variables["phoneNumber"] = "11999999999"  # missing +
        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Invalid phone format",
            "risco": "MEDIO",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_COPAY_VALIDATION"
        assert result.error_message == "Invalid phone format"

    def test_revisar_needs_manual_review(self, worker, base_context, mock_dmn_service):
        """REVISAR: needs manual review, no notification sent."""
        mock_dmn_service.evaluate.return_value = {
            "resultado": "REVISAR",
            "acao": "Coverage edge case needs review",
            "risco": "MEDIO",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["notificationSent"] is False
        assert result.variables["requiresReview"] is True

    def test_missing_appointment_id_returns_bpmn_error(self, worker, base_context):
        """Missing appointment_id should return BPMN error."""
        base_context.variables["appointmentId"] = ""

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_INVALID_INPUT"

    def test_dmn_failure_returns_bpmn_error(self, worker, base_context, mock_dmn_service):
        """DMN evaluation failure should return BPMN error."""
        mock_dmn_service.evaluate.side_effect = RuntimeError("DMN service down")

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_COPAY_ESTIMATE"

    def test_invalid_coverage_blocked_by_dmn(self, worker, base_context, mock_dmn_service):
        """Coverage > 100 should be blocked by DMN."""
        base_context.variables["insuranceCoverage"] = 150.0
        mock_dmn_service.evaluate.return_value = {
            "resultado": "BLOQUEAR",
            "acao": "Invalid coverage percentage",
            "risco": "MEDIO",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_COPAY_VALIDATION"
        assert "Invalid coverage" in result.error_message
