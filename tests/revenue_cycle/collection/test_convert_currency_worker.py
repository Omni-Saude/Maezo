"""Tests for ConvertCurrencyWorker."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.convert_currency_worker import (
    ConvertCurrencyWorker,
)


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.convert_currency_worker.get_required_tenant")
async def test_convert_currency_brl_passthrough(mock_tenant):
    """Test BRL payments pass through without conversion."""
    mock_tenant.return_value = "tenant-1"

    worker = ConvertCurrencyWorker()
    job = MagicMock()
    job.variables = {
        "gross_amount": "1000.00",
        "currency": "BRL",
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["gross_amount_brl"] == "1000.00"
    assert result.variables["exchange_rate"] == "1.0"
    assert result.variables["original_currency"] == "BRL"


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.convert_currency_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.convert_currency_worker.FederatedDMNService")
async def test_convert_currency_usd_to_brl(mock_dmn_service_cls, mock_tenant):
    """Test USD to BRL conversion."""
    mock_tenant.return_value = "tenant-1"
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {
        "exchangeRate": "5.00",
    }
    mock_dmn_service_cls.return_value = mock_dmn

    worker = ConvertCurrencyWorker()
    job = MagicMock()
    job.variables = {
        "gross_amount": "100.00",
        "currency": "USD",
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["gross_amount_brl"] == "500.0000"
    assert result.variables["exchange_rate"] == "5.00"
    assert result.variables["original_currency"] == "USD"
    assert result.variables["original_gross_amount"] == "100.00"
    assert result.variables["currency"] == "BRL"


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.convert_currency_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.convert_currency_worker.FederatedDMNService")
async def test_convert_currency_with_net_amount(mock_dmn_service_cls, mock_tenant):
    """Test conversion includes net amount."""
    mock_tenant.return_value = "tenant-1"
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {
        "exchangeRate": "6.00",
    }
    mock_dmn_service_cls.return_value = mock_dmn

    worker = ConvertCurrencyWorker()
    job = MagicMock()
    job.variables = {
        "gross_amount": "200.00",
        "net_amount": "180.00",
        "currency": "EUR",
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["gross_amount_brl"] == "1200.0000"
    assert result.variables["net_amount_brl"] == "1080.0000"
    assert result.variables["exchange_rate"] == "6.00"


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.convert_currency_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.convert_currency_worker.FederatedDMNService")
async def test_convert_currency_unknown_currency_default(mock_dmn_service_cls, mock_tenant):
    """Test unknown currency defaults to 1:1 rate."""
    mock_tenant.return_value = "tenant-1"
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {
        "exchangeRate": "1.0",
    }
    mock_dmn_service_cls.return_value = mock_dmn

    worker = ConvertCurrencyWorker()
    job = MagicMock()
    job.variables = {
        "gross_amount": "100.00",
        "currency": "XYZ",
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["gross_amount_brl"] == "100.000"
    assert result.variables["exchange_rate"] == "1.0"
    assert result.variables["original_currency"] == "XYZ"
