"""Tests for SendDailySummaryWorker."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from healthcare_platform.revenue_cycle.collection.workers.send_daily_summary_worker import (
    SendDailySummaryWorker,
)


@pytest.mark.asyncio
async def test_send_daily_summary_success():
    """Test successful daily summary sending."""
    # Mock WhatsApp client
    mock_whatsapp = MagicMock()
    mock_whatsapp.send_message = AsyncMock()

    worker = SendDailySummaryWorker(whatsapp_client=mock_whatsapp)

    task_variables = {
        "date": "2024-01-31",
        "collection_rate": 85.5,
        "dso": 45.2,
        "amount_collected_today": 50000.0,
        "amount_billed_today": 58000.0,
        "overdue_count": 25,
        "overdue_amount": 75000.0,
        "recipients": ["+5511999999999", "+5511888888888"],
    }

    result = await worker.execute(task_variables)

    assert result["messages_sent"] == 2
    assert result["status"] == "success"
    assert len(result["failed_recipients"]) == 0

    # Verify WhatsApp client was called
    assert mock_whatsapp.send_message.call_count == 2


@pytest.mark.asyncio
async def test_send_daily_summary_partial_failure():
    """Test handling of partial send failures."""
    # Mock WhatsApp client with one failure
    mock_whatsapp = MagicMock()

    call_count = 0

    async def mock_send(to: str, message: str):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise Exception("Network error")

    mock_whatsapp.send_message = AsyncMock(side_effect=mock_send)

    worker = SendDailySummaryWorker(whatsapp_client=mock_whatsapp)

    task_variables = {
        "date": "2024-01-31",
        "collection_rate": 85.5,
        "dso": 45.2,
        "amount_collected_today": 50000.0,
        "amount_billed_today": 58000.0,
        "overdue_count": 25,
        "overdue_amount": 75000.0,
        "recipients": ["+5511999999999", "+5511888888888"],
    }

    result = await worker.execute(task_variables)

    assert result["messages_sent"] == 1
    assert result["status"] == "success"
    assert len(result["failed_recipients"]) == 1


@pytest.mark.asyncio
async def test_send_daily_summary_all_failures():
    """Test handling when all sends fail."""
    # Mock WhatsApp client with all failures
    mock_whatsapp = MagicMock()
    mock_whatsapp.send_message = AsyncMock(side_effect=Exception("Network error"))

    worker = SendDailySummaryWorker(whatsapp_client=mock_whatsapp)

    task_variables = {
        "date": "2024-01-31",
        "collection_rate": 85.5,
        "dso": 45.2,
        "amount_collected_today": 50000.0,
        "amount_billed_today": 58000.0,
        "overdue_count": 25,
        "overdue_amount": 75000.0,
        "recipients": ["+5511999999999"],
    }

    result = await worker.execute(task_variables)

    assert result["messages_sent"] == 0
    assert result["status"] == "failed"
    assert len(result["failed_recipients"]) == 1


@pytest.mark.asyncio
async def test_send_daily_summary_message_format():
    """Test that message is properly formatted in Portuguese."""
    mock_whatsapp = MagicMock()
    messages_sent = []

    async def capture_message(to: str, message: str):
        messages_sent.append(message)

    mock_whatsapp.send_message = AsyncMock(side_effect=capture_message)

    worker = SendDailySummaryWorker(whatsapp_client=mock_whatsapp)

    task_variables = {
        "date": "2024-01-31",
        "collection_rate": 85.5,
        "dso": 45.2,
        "amount_collected_today": 50000.0,
        "amount_billed_today": 58000.0,
        "overdue_count": 25,
        "overdue_amount": 75000.0,
        "recipients": ["+5511999999999"],
    }

    await worker.execute(task_variables)

    message = messages_sent[0]
    assert "Resumo de Cobrança" in message
    assert "R$" in message
    assert "50,000.00" in message or "50000" in message
    assert "85.5%" in message or "85.5" in message
