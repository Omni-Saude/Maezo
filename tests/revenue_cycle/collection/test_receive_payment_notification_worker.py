"""Tests for ReceivePaymentNotificationWorker."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.receive_payment_notification_worker import (
    ReceivePaymentNotificationWorker,
)


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.receive_payment_notification_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.receive_payment_notification_worker.FederatedDMNService')
async def test_receive_payment_notification_success(mock_dmn_class, mock_tenant):
    """Test successful webhook notification reception."""
    mock_tenant.return_value = 'test-tenant'
    mock_dmn = MagicMock()
    mock_dmn_class.return_value = mock_dmn
    mock_dmn.evaluate.return_value = {
        'paymentType': 'pix'
    }

    worker = ReceivePaymentNotificationWorker()

    job = MagicMock()
    job.variables = {
        "transaction_id": "TXN123456",
        "bank_code": "001",
        "amount": 1500.50,
        "payment_method": "pix",
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["transaction_id"] == "TXN123456"
    assert result.variables["bank_code"] == "001"
    assert result.variables["gross_amount"] == "1500.5"
    assert result.variables["payment_method"] == "pix"
    assert result.variables["payment_type"] == "pix"
    assert result.variables["source"] == "webhook"
    assert "received_at" in result.variables


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.receive_payment_notification_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.receive_payment_notification_worker.FederatedDMNService')
async def test_receive_payment_notification_standard_type(mock_dmn_class, mock_tenant):
    """Test webhook notification with standard payment type."""
    mock_tenant.return_value = 'test-tenant'
    mock_dmn = MagicMock()
    mock_dmn_class.return_value = mock_dmn
    mock_dmn.evaluate.return_value = {
        'paymentType': 'standard'
    }

    worker = ReceivePaymentNotificationWorker()

    job = MagicMock()
    job.variables = {
        "transaction_id": "TXN789",
        "bank_code": "237",
        "amount": 2500.0,
        "payment_method": "bank_transfer",
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["payment_type"] == "standard"
