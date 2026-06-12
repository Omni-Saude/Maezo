"""
from __future__ import annotations

Tests for Patient Bill Notification Worker (Refactored v2)

Test Categories:
1. Happy path - bill notification sent with buttons
2. No WhatsApp client - notification_sent True but no message_id
3. Correct URL generation
4. Missing/invalid input
5. WhatsApp client failure
6. Edge case - zero amount formatting
"""

from unittest.mock import MagicMock

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskStatus


@pytest.fixture
def mock_whatsapp_client():
    mock = MagicMock()
    mock.send_template.return_value = "msg_bill_001"
    return mock


@pytest.fixture
def mock_metrics():
    return MagicMock()


@pytest.fixture
def base_context():
    return TaskContext(
        task_id="task_004",
        process_instance_id="proc_004",
        tenant_id="HOSPITAL_TEST",
        variables={
            "patientId": "pat_101",
            "phoneNumber": "+5511966666666",
            "billId": "bill_555",
            "totalAmount": 2500.00,
            "dueDate": "2026-03-01",
        },
        worker_id="financial.bill_ready",
    )


@pytest.fixture
def worker(mock_whatsapp_client, mock_metrics):
    from healthcare_platform.revenue_cycle.billing.workers.patient_bill_notification_worker import (
        PatientBillNotificationWorker,
    )
    return PatientBillNotificationWorker(
        whatsapp_client=mock_whatsapp_client,
        metrics=mock_metrics,
    )


class TestPatientBillNotificationV2:
    def test_happy_path_sends_notification(self, worker, base_context, mock_whatsapp_client):
        """Happy path: bill notification sent with formatted amount."""
        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["notificationSent"] is True
        assert result.variables["messageId"] == "msg_bill_001"
        mock_whatsapp_client.send_template.assert_called_once()

    def test_no_whatsapp_client_returns_none_message_id(self, base_context, mock_metrics):
        """Without WhatsApp client, message_id should be None."""
        from healthcare_platform.revenue_cycle.billing.workers.patient_bill_notification_worker import (
            PatientBillNotificationWorker,
        )
        worker = PatientBillNotificationWorker(whatsapp_client=None, metrics=mock_metrics)

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["notificationSent"] is True
        assert result.variables["messageId"] is None

    def test_correct_urls_generated(self, worker, base_context):
        """URLs should include bill_id."""
        result = worker.execute(base_context)

        assert "bill_555" in result.variables["viewUrl"]
        assert "bill_555" in result.variables["payUrl"]

    def test_missing_bill_id_returns_bpmn_error(self, worker, base_context):
        """Missing bill_id should return BPMN error."""
        base_context.variables["billId"] = ""

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_INVALID_INPUT"

    def test_whatsapp_failure_returns_bpmn_error(self, worker, base_context, mock_whatsapp_client):
        """WhatsApp send failure should return BPMN error."""
        mock_whatsapp_client.send_template.side_effect = ConnectionError("API down")

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_BILL_NOTIFICATION"

    def test_zero_amount_formatting(self, worker, base_context, mock_whatsapp_client):
        """Zero amount should format as R$ 0,00."""
        base_context.variables["totalAmount"] = 0

        worker.execute(base_context)

        call_args = mock_whatsapp_client.send_template.call_args
        body_params = call_args.kwargs["body_params"]
        assert body_params[0] == "R$ 0,00"
