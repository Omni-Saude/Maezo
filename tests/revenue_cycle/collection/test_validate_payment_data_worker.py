"""Tests for ValidatePaymentDataWorker."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.validate_payment_data_worker import (
    ValidatePaymentDataWorker,
)


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.validate_payment_data_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.validate_payment_data_worker.FederatedDMNService')
async def test_validate_payment_data_success(mock_dmn_class, mock_tenant):
    """Test successful payment data validation."""
    mock_tenant.return_value = 'test-tenant'
    mock_dmn = MagicMock()
    mock_dmn_class.return_value = mock_dmn
    mock_dmn.evaluate.return_value = {
        'validationStatus': 'valid'
    }

    worker = ValidatePaymentDataWorker()

    job = MagicMock()
    job.variables = {
        "transaction_id": "TXN123",
        "gross_amount": "1000.50",
        "currency": "BRL",
        "payment_date": "2024-01-15",
        "payer_name": "Hospital XYZ",
        "payer_document": "12345678000190",
        "bank_code": "001",
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["validation_status"] == "valid"
    assert "validated_at" in result.variables
    assert result.variables["transaction_id"] == "TXN123"


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.validate_payment_data_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.validate_payment_data_worker.FederatedDMNService')
async def test_validate_payment_data_invalid_amount(mock_dmn_class, mock_tenant):
    """Test validation fails with zero/negative amount."""
    mock_tenant.return_value = 'test-tenant'
    mock_dmn = MagicMock()
    mock_dmn_class.return_value = mock_dmn

    worker = ValidatePaymentDataWorker()

    job = MagicMock()
    job.variables = {
        "transaction_id": "TXN123",
        "gross_amount": "0",
        "currency": "BRL",
        "payer_name": "Hospital",
        "payer_document": "12345678000190",
        "bank_code": "001",
    }

    result = await worker.execute(job)

    assert not result.success
    assert result.error_code == 'INVALID_PAYMENT_AMOUNT'


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.validate_payment_data_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.validate_payment_data_worker.FederatedDMNService')
async def test_validate_payment_data_negative_amount(mock_dmn_class, mock_tenant):
    """Test validation fails with negative amount."""
    mock_tenant.return_value = 'test-tenant'
    mock_dmn = MagicMock()
    mock_dmn_class.return_value = mock_dmn

    worker = ValidatePaymentDataWorker()

    job = MagicMock()
    job.variables = {
        "transaction_id": "TXN456",
        "gross_amount": "-100.00",
        "currency": "BRL",
    }

    result = await worker.execute(job)

    assert not result.success
    assert result.error_code == 'INVALID_PAYMENT_AMOUNT'
