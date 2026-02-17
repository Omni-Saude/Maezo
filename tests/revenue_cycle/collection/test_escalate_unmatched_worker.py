"""Tests for EscalateUnmatchedWorker."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.exceptions import UnmatchedPaymentError
from healthcare_platform.revenue_cycle.collection.workers.escalate_unmatched_worker import EscalateUnmatchedWorker


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.escalate_unmatched_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.escalate_unmatched_worker.FederatedDMNService")
async def test_escalate_unmatched_raises_error(mock_dmn_service_cls, mock_tenant):
    """Test that unmatched payment raises error for manual review."""
    mock_tenant.return_value = "tenant-1"
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {}
    mock_dmn_service_cls.return_value = mock_dmn

    worker = EscalateUnmatchedWorker()
    job = MagicMock()
    job.variables = {
        "payment_id": "pay-001",
        "payment_amount": 1500.00,
        "currency": "BRL",
        "payer_id": "payer-001",
        "attempted_strategies": ["protocol", "invoice", "patient"],
        "payment_date": "2024-01-15",
        "transaction_id": "TXN-12345",
        "notes": "Unable to match automatically",
    }

    result = await worker.execute(job)

    assert result.success is False
    assert result.error_code == "UNMATCHED_PAYMENT"
    assert "revisão manual" in result.error_message.lower()


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.escalate_unmatched_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.escalate_unmatched_worker.FederatedDMNService")
async def test_escalation_includes_context(mock_dmn_service_cls, mock_tenant):
    """Test that escalation includes full context."""
    mock_tenant.return_value = "tenant-1"
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {}
    mock_dmn_service_cls.return_value = mock_dmn

    worker = EscalateUnmatchedWorker()
    job = MagicMock()
    job.variables = {
        "payment_id": "pay-002",
        "payment_amount": 2000.00,
        "currency": "BRL",
        "payer_id": "payer-002",
        "attempted_strategies": ["protocol", "invoice"],
        "transaction_id": "TXN-67890",
    }

    result = await worker.execute(job)

    assert result.success is False
    assert result.error_code == "UNMATCHED_PAYMENT"
