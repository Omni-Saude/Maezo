"""Tests for ValidatePaymentDataWorker."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from healthcare_platform.revenue_cycle.collection.workers.validate_payment_data_worker import (
    ValidatePaymentDataWorker,
)
from healthcare_platform.revenue_cycle.collection.exceptions import PaymentValidationError


@pytest.mark.asyncio
async def test_validate_payment_data_success():
    """Test successful payment data validation."""
    worker = ValidatePaymentDataWorker()

    task_vars = {
        "transaction_id": "TXN123",
        "gross_amount": "1000.50",
        "currency": "BRL",
        "payment_date": "2024-01-15",
        "payer_name": "Hospital XYZ",
        "payer_document": "12345678000190",
        "bank_code": "001",
    }

    result = await worker.execute(task_vars)

    assert result["validation_status"] == "valid"
    assert "validated_at" in result
    assert result["transaction_id"] == "TXN123"


@pytest.mark.asyncio
async def test_validate_payment_data_missing_required_fields():
    """Test validation fails with missing required fields."""
    worker = ValidatePaymentDataWorker()

    task_vars = {
        "transaction_id": "TXN123",
        "gross_amount": "1000.00",
        # Missing currency, payer_name, payer_document, bank_code
    }

    with pytest.raises(PaymentValidationError, match="Campos obrigatórios ausentes"):
        await worker.execute(task_vars)


@pytest.mark.asyncio
async def test_validate_payment_data_invalid_amount():
    """Test validation fails with zero/negative amount."""
    worker = ValidatePaymentDataWorker()

    task_vars = {
        "transaction_id": "TXN123",
        "gross_amount": "0",
        "currency": "BRL",
        "payer_name": "Hospital",
        "payer_document": "12345678000190",
        "bank_code": "001",
    }

    with pytest.raises(PaymentValidationError, match="maior que zero"):
        await worker.execute(task_vars)


@pytest.mark.asyncio
async def test_validate_payment_data_future_date():
    """Test validation fails with future payment date."""
    worker = ValidatePaymentDataWorker()

    future_date = (date.today() + timedelta(days=10)).isoformat()

    task_vars = {
        "transaction_id": "TXN123",
        "gross_amount": "100.00",
        "currency": "BRL",
        "payment_date": future_date,
        "payer_name": "Hospital",
        "payer_document": "12345678000190",
        "bank_code": "001",
    }

    with pytest.raises(PaymentValidationError, match="Validação de dados"):
        await worker.execute(task_vars)


@pytest.mark.asyncio
async def test_validate_payment_data_invalid_currency():
    """Test validation fails with invalid currency code."""
    worker = ValidatePaymentDataWorker()

    task_vars = {
        "transaction_id": "TXN123",
        "gross_amount": "100.00",
        "currency": "INVALID",  # Invalid currency
        "payer_name": "Hospital",
        "payer_document": "12345678000190",
        "bank_code": "001",
    }

    with pytest.raises(PaymentValidationError, match="Validação de dados"):
        await worker.execute(task_vars)
