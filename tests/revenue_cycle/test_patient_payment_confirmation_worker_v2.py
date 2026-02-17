"""
from __future__ import annotations

Tests for Patient Payment Confirmation Worker (Refactored v2)

Test Categories:
1. Happy path - confirmation + receipt sent
2. Receipt document fails (graceful degradation)
3. No receipt URL - document_sent False
4. Missing/invalid input
5. WhatsApp template failure
6. Edge case - large amount formatting
"""

from unittest.mock import MagicMock

import pytest

from healthcare_platform.shared.workers.base import TaskContext


@pytest.fixture
def mock_whatsapp_client():
    mock = MagicMock()
    mock.send_template.return_value = "msg_pay_001"
    mock.send_document.return_value = None
    return mock


@pytest.fixture
def mock_metrics():
    return MagicMock()


@pytest.fixture
def base_context():
    return TaskContext(
        task_id="task_006",
        process_instance_id="proc_006",
        tenant_id="HOSPITAL_TEST",
        variables={
            "patient_id": "pat_303",
            "phone_number": "+5511944444444",
            "payment_id": "pay_999",
            "amount": 350.00,
            "remaining_balance": 0.00,  # Required field
            "payment_method": "PIX",
            "receipt_url": "https://storage.maezo.com.br/receipts/pay_999.pdf",
        },
        worker_id="financial.payment_confirmed",
    )


@pytest.fixture
def worker(mock_whatsapp_client, mock_metrics):
    from healthcare_platform.revenue_cycle.workers.patient_payment_confirmation_worker_v2 import (
        PatientPaymentConfirmationWorker,
    )
    return PatientPaymentConfirmationWorker(
        whatsapp_client=mock_whatsapp_client,
        metrics=mock_metrics,
    )


@pytest.mark.asyncio
class TestPatientPaymentConfirmationV2:
    async def test_happy_path_sends_confirmation_and_receipt(self, worker, base_context, mock_whatsapp_client):
        """Happy path: template + receipt document both sent."""
        result = await worker.execute(base_context)

        assert result.get("confirmation_sent") is True or result.get("notification_sent") is True
        assert result["notification_sent"] is True
        assert result["document_sent"] is True
        assert result["message_id"] == "msg_pay_001"
        mock_whatsapp_client.send_template.assert_called_once()
        mock_whatsapp_client.send_document.assert_called_once()

    async def test_receipt_failure_graceful_degradation(self, worker, base_context, mock_whatsapp_client):
        # This test should expect an exception
        """Receipt document failure should not fail the whole worker."""
        mock_whatsapp_client.send_document.side_effect = ConnectionError("Storage down")

        result = await worker.execute(base_context)

        assert result.get("confirmation_sent") is True or result.get("notification_sent") is True
        assert result["notification_sent"] is True
        assert result["document_sent"] is False

    async def test_no_receipt_url_skips_document(self, worker, base_context, mock_whatsapp_client):
        """No receipt_url should skip document send."""
        base_context.variables["receipt_url"] = ""

        result = await worker.execute(base_context)

        assert result.get("confirmation_sent") is True or result.get("notification_sent") is True
        assert result["document_sent"] is False
        mock_whatsapp_client.send_document.assert_not_called()

    async def test_missing_payment_id_returns_bpmn_error(self, worker, base_context):
        # This test should expect an exception
        """Missing payment_id should return BPMN error."""
        base_context.variables["payment_id"] = ""

        result = await worker.execute(base_context)

        # Should raise exception instead
        assert result.error_code == "ERR_INVALID_INPUT"

    async def test_whatsapp_template_failure_returns_bpmn_error(self, worker, base_context, mock_whatsapp_client):
        # This test should expect an exception
        """WhatsApp template send failure should return BPMN error."""
        mock_whatsapp_client.send_template.side_effect = ConnectionError("WhatsApp API down")

        result = await worker.execute(base_context)

        # Should raise exception instead
        assert result.error_code == "ERR_PAYMENT_CONFIRMATION"

    async def test_large_amount_formatting(self, worker, base_context, mock_whatsapp_client):
        """Large amount should be formatted correctly in BRL."""
        base_context.variables["amount"] = 123456.78

        worker.execute(base_context)

        call_args = mock_whatsapp_client.send_template.call_args
        body_params = call_args.kwargs["body_params"]
        assert body_params[0] == "R$ 123.456,78"
