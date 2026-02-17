"""Tests for SendDailySummaryWorker."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.send_daily_summary_worker import (
    SendDailySummaryWorker,
)


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.send_daily_summary_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.send_daily_summary_worker.FederatedDMNService')
async def test_send_daily_summary_success(mock_dmn_class, mock_tenant):
    """Test successful daily summary sending."""
    mock_tenant.return_value = 'test-tenant'
    mock_dmn = MagicMock()
    mock_dmn_class.return_value = mock_dmn
    mock_dmn.evaluate.return_value = {
        'deliveryMethod': 'whatsapp'
    }

    worker = SendDailySummaryWorker()

    job = MagicMock()
    job.variables = {
        "date": "2024-01-31",
        "collection_rate": 85.5,
        "dso": 45.2,
        "amount_collected_today": 50000.0,
        "amount_billed_today": 58000.0,
        "overdue_count": 25,
        "overdue_amount": 75000.0,
        "recipients": ["+5511999999999", "+5511888888888"],
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["messages_sent"] == 2
    assert result.variables["status"] == "success"
    assert len(result.variables["failed_recipients"]) == 0


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.send_daily_summary_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.send_daily_summary_worker.FederatedDMNService')
async def test_send_daily_summary_no_recipients(mock_dmn_class, mock_tenant):
    """Test summary with no recipients."""
    mock_tenant.return_value = 'test-tenant'
    mock_dmn = MagicMock()
    mock_dmn_class.return_value = mock_dmn
    mock_dmn.evaluate.return_value = {
        'deliveryMethod': 'email'
    }

    worker = SendDailySummaryWorker()

    job = MagicMock()
    job.variables = {
        "date": "2024-01-31",
        "collection_rate": 85.5,
        "dso": 45.2,
        "overdue_count": 25,
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["messages_sent"] == 0
    assert result.variables["status"] == "success"
