"""
from __future__ import annotations

Tests for Doctor Procedure Auth Status Worker (Refactored v2)

Test Categories:
1. Happy path - notification sent with DMN routing
2. Skip routing - DMN says skip (no pending)
3. Urgent routing - overdue authorizations
4. Missing/invalid input
5. DMN evaluator failure
6. Edge case - empty authorizations list
"""

from unittest.mock import MagicMock

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskStatus


@pytest.fixture
def mock_dmn_service():
    mock = MagicMock()
    mock.evaluate.return_value = {
        "destino": "whatsapp",
        "prioridade": 3,
        "restricao": "Standard notification",
    }
    return mock


@pytest.fixture
def mock_whatsapp_client():
    mock = MagicMock()
    mock.send_template.return_value = "msg_auth_001"
    return mock


@pytest.fixture
def mock_metrics():
    return MagicMock()


@pytest.fixture
def base_context():
    return TaskContext(
        task_id="task_001",
        process_instance_id="proc_001",
        tenant_id="HOSPITAL_TEST",
        variables={
            "doctor_id": "doc_123",
            "phone_number": "+5511999999999",
            "pending_authorizations": [
                {"patient_name": "Joao", "procedure": "RMN", "days_pending": 5, "payer": "Unimed"},
                {"patient_name": "Maria", "procedure": "TC", "days_pending": 10, "payer": "Amil"},
            ],
        },
        worker_id="financial.auth_pending",
    )


@pytest.fixture
def worker(mock_dmn_service, mock_whatsapp_client, mock_metrics):
    from healthcare_platform.revenue_cycle.workers.doctor_procedure_auth_status_worker_v2 import (
        DoctorProcedureAuthStatusWorker,
    )
    return DoctorProcedureAuthStatusWorker(
        whatsapp_client=mock_whatsapp_client,
        dmn_service=mock_dmn_service,
        metrics=mock_metrics,
    )


class TestDoctorProcedureAuthStatusV2:
    def test_happy_path_sends_notification(self, worker, base_context, mock_whatsapp_client):
        """Happy path: DMN routes to whatsapp, notification sent."""
        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["notification_sent"] is True
        assert result.variables["message_id"] == "msg_auth_001"
        assert result.variables["total_pending"] == 2
        mock_whatsapp_client.send_template.assert_called_once()

    def test_skip_routing_no_pending(self, worker, base_context, mock_dmn_service):
        """DMN returns skip when no pending authorizations."""
        base_context.variables["pending_authorizations"] = []
        mock_dmn_service.evaluate.return_value = {
            "destino": "skip",
            "prioridade": 5,
            "restricao": "No pending authorizations",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["notification_sent"] is False
        assert result.variables["destino"] == "skip"

    def test_urgent_routing_overdue(self, worker, base_context, mock_dmn_service):
        """DMN returns urgent priority for overdue authorizations."""
        base_context.variables["pending_authorizations"][1]["days_pending"] = 15
        mock_dmn_service.evaluate.return_value = {
            "destino": "whatsapp",
            "prioridade": 1,
            "restricao": "Urgent: overdue authorizations",
        }

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["prioridade"] == 1
        assert result.variables["restricao"] == "Urgent: overdue authorizations"

    def test_missing_doctor_id_returns_bpmn_error(self, worker, base_context):
        """Missing doctor_id should return BPMN error."""
        base_context.variables["doctor_id"] = ""

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_INVALID_INPUT"

    def test_dmn_failure_returns_bpmn_error(self, worker, base_context, mock_dmn_service):
        """DMN evaluation failure should return BPMN error."""
        mock_dmn_service.evaluate.side_effect = RuntimeError("DMN evaluation failed")

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_AUTH_STATUS_NOTIFICATION"
        assert "DMN evaluation failed" in result.error_message

    def test_summary_shows_top_3_sorted_by_days(self, worker, base_context, mock_whatsapp_client):
        """Summary should include top 3 authorizations sorted by days_pending desc."""
        base_context.variables["pending_authorizations"] = [
            {"patient_name": "A", "procedure": "P1", "days_pending": 1, "payer": "X"},
            {"patient_name": "B", "procedure": "P2", "days_pending": 20, "payer": "Y"},
            {"patient_name": "C", "procedure": "P3", "days_pending": 10, "payer": "Z"},
            {"patient_name": "D", "procedure": "P4", "days_pending": 5, "payer": "W"},
        ]

        worker.execute(base_context)

        call_args = mock_whatsapp_client.send_template.call_args
        body_params = call_args.kwargs["body_params"]
        # Summary text is 3rd param, should contain B (20d), C (10d), D (5d)
        # Top 3 sorted by days_pending DESC: B=20, C=10, D=5
        assert "B" in body_params[2]
        assert "C" in body_params[2]
        assert "D" in body_params[2]
        assert "A" not in body_params[2]  # A has 1 day, not in top 3
