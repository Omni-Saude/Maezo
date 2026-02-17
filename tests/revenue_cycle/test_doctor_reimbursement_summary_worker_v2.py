"""
from __future__ import annotations

Tests for Doctor Reimbursement Summary Worker (Refactored v2)

Test Categories:
1. Happy path - summary sent
2. Zero billed amount (receipt rate = 0)
3. High receipt rate
4. Missing/invalid input
5. WhatsApp client failure
6. Edge case - currency formatting
"""

from unittest.mock import MagicMock

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskStatus


@pytest.fixture
def mock_whatsapp_client():
    mock = MagicMock()
    mock.send_template.return_value = "msg_reimb_001"
    return mock


@pytest.fixture
def mock_metrics():
    return MagicMock()


@pytest.fixture
def base_context():
    return TaskContext(
        task_id="task_002",
        process_instance_id="proc_002",
        tenant_id="HOSPITAL_TEST",
        variables={
            "doctor_id": "doc_456",
            "phone_number": "+5511988888888",
            "period": "Jan/2026",
            "total_billed": 50000.00,
            "total_received": 35000.00,
            "total_pending": 10000.00,
            "top_denials": ["Procedimento nao coberto", "Prazo expirado"],
        },
        worker_id="financial.reimbursement_summary",
    )


@pytest.fixture
def worker(mock_whatsapp_client, mock_metrics):
    from healthcare_platform.revenue_cycle.workers.doctor_reimbursement_summary_worker_v2 import (
        DoctorReimbursementSummaryWorker,
    )
    return DoctorReimbursementSummaryWorker(
        whatsapp_client=mock_whatsapp_client,
        metrics=mock_metrics,
    )


class TestDoctorReimbursementSummaryV2:
    def test_happy_path_sends_summary(self, worker, base_context, mock_whatsapp_client):
        """Happy path: summary sent with receipt rate."""
        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["notification_sent"] is True
        assert result.variables["receipt_rate"] == 70.0
        mock_whatsapp_client.send_template.assert_called_once()

    def test_zero_billed_receipt_rate_zero(self, worker, base_context):
        """Zero billed amount should yield 0% receipt rate."""
        base_context.variables["total_billed"] = 0
        base_context.variables["total_received"] = 0

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["receipt_rate"] == 0

    def test_high_receipt_rate(self, worker, base_context):
        """Full payment should yield 100% receipt rate."""
        base_context.variables["total_received"] = 50000.00

        result = worker.execute(base_context)

        assert result.status == TaskStatus.SUCCESS
        assert result.variables["receipt_rate"] == 100.0

    def test_missing_period_returns_bpmn_error(self, worker, base_context):
        """Missing period should return BPMN error."""
        base_context.variables["period"] = ""

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_INVALID_INPUT"

    def test_whatsapp_failure_returns_bpmn_error(self, worker, base_context, mock_whatsapp_client):
        """WhatsApp send failure should return BPMN error."""
        mock_whatsapp_client.send_template.side_effect = ConnectionError("WhatsApp unavailable")

        result = worker.execute(base_context)

        assert result.status == TaskStatus.BPMN_ERROR
        assert result.error_code == "ERR_REIMBURSEMENT_SUMMARY"

    def test_currency_formatting_in_body_params(self, worker, base_context, mock_whatsapp_client):
        """Body params should contain BRL formatted amounts."""
        base_context.variables["total_billed"] = 1234.56

        worker.execute(base_context)

        call_args = mock_whatsapp_client.send_template.call_args
        body_params = call_args.kwargs["body_params"]
        assert body_params[1] == "R$ 1.234,56"
