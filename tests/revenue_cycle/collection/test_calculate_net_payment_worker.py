"""Tests for CalculateNetPaymentWorker."""
from __future__ import annotations

import pytest

from healthcare_platform.revenue_cycle.collection.workers.calculate_net_payment_worker import (
    CalculateNetPaymentWorker,
)
from healthcare_platform.revenue_cycle.collection.exceptions import PaymentValidationError


@pytest.mark.asyncio
async def test_calculate_net_payment_success():
    """Test successful net payment calculation."""
    worker = CalculateNetPaymentWorker()

    task_vars = {
        "gross_amount": "1000.00",
        "bank_fees": "10.00",
        "tax_withholding": "40.00",
    }

    result = await worker.execute(task_vars)

    assert result["net_amount"] == "950.00"
    assert result["bank_fees"] == "10.00"
    assert result["tax_withholding"] == "40.00"
    assert result["currency"] == "BRL"


@pytest.mark.asyncio
async def test_calculate_net_payment_no_fees():
    """Test calculation with no fees or taxes."""
    worker = CalculateNetPaymentWorker()

    task_vars = {
        "gross_amount": "500.00",
    }

    result = await worker.execute(task_vars)

    assert result["net_amount"] == "500.00"
    assert result["bank_fees"] == "0.00"
    assert result["tax_withholding"] == "0.00"


@pytest.mark.asyncio
async def test_calculate_net_payment_negative_result():
    """Test calculation fails when net amount would be negative."""
    worker = CalculateNetPaymentWorker()

    task_vars = {
        "gross_amount": "100.00",
        "bank_fees": "50.00",
        "tax_withholding": "60.00",  # Total deductions exceed gross
    }

    with pytest.raises(PaymentValidationError, match="não pode ser negativo"):
        await worker.execute(task_vars)


@pytest.mark.asyncio
async def test_calculate_net_payment_zero_gross():
    """Test calculation with zero gross amount."""
    worker = CalculateNetPaymentWorker()

    task_vars = {
        "gross_amount": "0.00",
        "bank_fees": "0.00",
        "tax_withholding": "0.00",
    }

    result = await worker.execute(task_vars)

    assert result["net_amount"] == "0.00"


@pytest.mark.asyncio
async def test_calculate_net_payment_invalid_amount_format():
    """Test calculation fails with invalid amount format."""
    worker = CalculateNetPaymentWorker()

    task_vars = {
        "gross_amount": "invalid",
    }

    with pytest.raises(PaymentValidationError, match="parsear valores monetários"):
        await worker.execute(task_vars)
