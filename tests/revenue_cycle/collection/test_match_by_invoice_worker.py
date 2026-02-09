"""Tests for MatchByInvoiceWorker."""
from __future__ import annotations

import pytest

from platform.revenue_cycle.collection.workers.match_by_invoice_worker import MatchByInvoiceWorker


@pytest.fixture
def worker():
    """Create worker instance."""
    return MatchByInvoiceWorker()


@pytest.mark.asyncio
async def test_match_by_invoice_number(worker):
    """Test match by invoice number."""
    task_vars = {
        "payment_id": "pay-001",
        "invoice_number": "INV-001",
        "payment_amount": 1000.00,
        "currency": "BRL",
        "available_claims": [
            {"claim_id": "claim-001", "invoice_number": "INV-001"}
        ],
    }

    result = await worker.execute(task_vars)

    assert result["matched"] is True
    assert result["claim_id"] == "claim-001"


@pytest.mark.asyncio
async def test_match_by_nosso_numero(worker):
    """Test match by nosso_numero from CNAB."""
    task_vars = {
        "payment_id": "pay-002",
        "invoice_number": "INV-002",
        "nosso_numero": "NN-123",
        "payment_amount": 2000.00,
        "currency": "BRL",
        "available_claims": [
            {"claim_id": "claim-002", "nosso_numero": "NN-123"}
        ],
    }

    result = await worker.execute(task_vars)

    assert result["matched"] is True
    assert result["claim_id"] == "claim-002"


@pytest.mark.asyncio
async def test_invoice_not_found(worker):
    """Test when invoice is not found."""
    task_vars = {
        "payment_id": "pay-003",
        "invoice_number": "INV-999",
        "payment_amount": 1000.00,
        "currency": "BRL",
        "available_claims": [
            {"claim_id": "claim-001", "invoice_number": "INV-001"}
        ],
    }

    result = await worker.execute(task_vars)

    assert result["matched"] is False
    assert result["claim_id"] is None
