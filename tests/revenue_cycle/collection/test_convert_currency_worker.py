"""Tests for ConvertCurrencyWorker."""
from __future__ import annotations

from decimal import Decimal

import pytest

from healthcare_platform.revenue_cycle.collection.workers.convert_currency_worker import (
    ConvertCurrencyWorker,
)


@pytest.mark.asyncio
async def test_convert_currency_brl_passthrough():
    """Test BRL payments pass through without conversion."""
    worker = ConvertCurrencyWorker()

    task_vars = {
        "gross_amount": "1000.00",
        "currency": "BRL",
    }

    result = await worker.execute(task_vars)

    assert result["gross_amount_brl"] == "1000.00"
    assert result["exchange_rate"] == "1.0"
    assert result["original_currency"] == "BRL"


@pytest.mark.asyncio
async def test_convert_currency_usd_to_brl():
    """Test USD to BRL conversion."""
    worker = ConvertCurrencyWorker(exchange_rates={"USD": Decimal("5.00")})

    task_vars = {
        "gross_amount": "100.00",
        "currency": "USD",
    }

    result = await worker.execute(task_vars)

    assert result["gross_amount_brl"] == "500.00"
    assert result["exchange_rate"] == "5.00"
    assert result["original_currency"] == "USD"
    assert result["original_gross_amount"] == "100.00"
    assert result["currency"] == "BRL"


@pytest.mark.asyncio
async def test_convert_currency_with_net_amount():
    """Test conversion includes net amount."""
    worker = ConvertCurrencyWorker(exchange_rates={"EUR": Decimal("6.00")})

    task_vars = {
        "gross_amount": "200.00",
        "net_amount": "180.00",
        "currency": "EUR",
    }

    result = await worker.execute(task_vars)

    assert result["gross_amount_brl"] == "1200.00"
    assert result["net_amount_brl"] == "1080.00"
    assert result["exchange_rate"] == "6.00"


@pytest.mark.asyncio
async def test_convert_currency_unknown_currency_default():
    """Test unknown currency defaults to 1:1 rate."""
    worker = ConvertCurrencyWorker(exchange_rates={})

    task_vars = {
        "gross_amount": "100.00",
        "currency": "XYZ",
    }

    result = await worker.execute(task_vars)

    assert result["gross_amount_brl"] == "100.00"
    assert result["exchange_rate"] == "1.0"
    assert result["original_currency"] == "XYZ"
