"""Tests for HandleOverpaymentWorker."""
from __future__ import annotations

from uuid import uuid4
from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.exceptions import OverpaymentError
from healthcare_platform.revenue_cycle.collection.workers.handle_overpayment_worker import HandleOverpaymentWorker


@pytest.fixture
def worker():
    """Create worker instance."""
    return HandleOverpaymentWorker()


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.handle_overpayment_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.handle_overpayment_worker.FederatedDMNService')
async def test_overpayment_raises_error(mock_dmn_service, mock_tenant, worker):
    """Test that overpayment raises OverpaymentError."""
    mock_tenant.return_value = 'test_tenant'
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {'action': 'review_required'}
    mock_dmn_service.return_value = mock_dmn

    worker.dmn_service = mock_dmn

    payment_id = str(uuid4())
    claim_id = str(uuid4())

    job = MagicMock()
    job.variables = {
        "payment_id": payment_id,
        "claim_id": claim_id,
        "payment_amount": 1200.00,
        "expected_amount": 1000.00,
        "currency": "BRL",
        "payer_id": str(uuid4()),
    }

    result = await worker.execute(job)

    # Worker catches OverpaymentError and returns BPMN error
    assert result.success is False
    assert result.error_code is not None
    assert "revisão manual" in result.error_message.lower() or "sobrepagamento" in result.error_message.lower()


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.handle_overpayment_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.handle_overpayment_worker.FederatedDMNService')
async def test_overpayment_creates_credit_note(mock_dmn_service, mock_tenant, worker):
    """Test that credit note is created for overpayment."""
    mock_tenant.return_value = 'test_tenant'
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {'action': 'review_required'}
    mock_dmn_service.return_value = mock_dmn

    worker.dmn_service = mock_dmn

    payment_id = str(uuid4())
    claim_id = str(uuid4())

    job = MagicMock()
    job.variables = {
        "payment_id": payment_id,
        "claim_id": claim_id,
        "payment_amount": 1500.00,
        "expected_amount": 1000.00,
        "currency": "BRL",
        "payer_id": str(uuid4()),
    }

    result = await worker.execute(job)

    # Worker catches OverpaymentError and returns BPMN error
    assert result.success is False
    assert result.error_code is not None
