"""Tests for PersistPaymentWorker."""
from __future__ import annotations

from uuid import UUID, uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.persist_payment_worker import (
    PersistPaymentWorker,
)
from healthcare_platform.revenue_cycle.collection.exceptions import CollectionException


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.persist_payment_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.persist_payment_worker.FederatedDMNService')
async def test_persist_payment_success(mock_dmn_service, mock_tenant):
    """Test successful payment persistence."""
    mock_tenant.return_value = 'test_tenant'
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {'valid': True, 'payment_type': 'full'}
    mock_dmn_service.return_value = mock_dmn

    worker = PersistPaymentWorker()
    worker.dmn_service = mock_dmn

    job = MagicMock()
    job.variables = {
        "tenant_id": "hospital_a",
        "transaction_id": "TXN123",
        "bank_code": "001",
        "agency": "1234",
        "account": "567890",
        "gross_amount": 1000.00,
        "net_amount": 950.00,
        "bank_fees": 10.00,
        "tax_withholding": 40.00,
        "payment_type": "full",
        "payment_method": "bank_transfer",
        "payment_date": "2024-01-15",
        "currency": "BRL",
    }

    result = await worker.execute(job)

    assert result.success is True
    assert "payment_id" in result.variables
    assert result.variables["payment_status"] == "received"
    assert result.variables["payment_id"] == "PAY-TXN123"


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.persist_payment_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.persist_payment_worker.FederatedDMNService')
async def test_persist_payment_invalid(mock_dmn_service, mock_tenant):
    """Test persistence fails when payment is invalid."""
    mock_tenant.return_value = 'test_tenant'
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {'valid': False, 'reason': 'Invalid payment type'}
    mock_dmn_service.return_value = mock_dmn

    worker = PersistPaymentWorker()
    worker.dmn_service = mock_dmn

    job = MagicMock()
    job.variables = {
        "transaction_id": "TXN123",
        "gross_amount": 1000.00,
        "net_amount": 1000.00,
    }

    result = await worker.execute(job)

    # Worker catches CollectionException and returns BPMN error
    assert result.success is False
    assert result.error_code == "PAYMENT_INVALID"
    assert "Pagamento inválido" in result.error_message


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.persist_payment_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.persist_payment_worker.FederatedDMNService')
async def test_persist_payment_minimal_data(mock_dmn_service, mock_tenant):
    """Test persistence with minimal required data."""
    mock_tenant.return_value = 'test_tenant'
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {'valid': True, 'payment_type': 'advance'}
    mock_dmn_service.return_value = mock_dmn

    worker = PersistPaymentWorker()
    worker.dmn_service = mock_dmn

    job = MagicMock()
    job.variables = {
        "tenant_id": "hospital_b",
        "transaction_id": "TXN456",
        "gross_amount": 500.00,
        "net_amount": 500.00,
        "bank_code": "237",
        "payment_type": "advance",
        "payment_method": "pix",
    }

    result = await worker.execute(job)

    assert result.success is True
    assert "payment_id" in result.variables
    assert result.variables["payment_id"] == "PAY-TXN456"
    assert result.variables["payment_status"] == "received"
