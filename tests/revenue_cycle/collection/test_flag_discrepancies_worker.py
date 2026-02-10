"""Tests for FlagDiscrepanciesWorker."""
from __future__ import annotations

import pytest

from healthcare_platform.revenue_cycle.collection.workers.flag_discrepancies_worker import FlagDiscrepanciesWorker


@pytest.fixture
def worker():
    """Create worker instance."""
    return FlagDiscrepanciesWorker()


@pytest.mark.asyncio
async def test_flag_overpayment_high_severity(worker):
    """Test flagging overpayment with high severity."""
    task_vars = {
        "payment_id": "pay-001",
        "claim_id": "claim-001",
        "variance": 150.00,
        "expected_amount": 1000.00,
        "actual_amount": 1150.00,
        "duplicate_check": False,
        "currency": "BRL",
    }

    result = await worker.execute(task_vars)

    assert result["has_discrepancy"] is True
    assert result["discrepancy_type"] == "overpayment"
    assert result["severity"] == "high"
    assert result["requires_review"] is True


@pytest.mark.asyncio
async def test_flag_duplicate_critical(worker):
    """Test flagging duplicate payment."""
    task_vars = {
        "payment_id": "pay-002",
        "claim_id": "claim-002",
        "variance": 0.00,
        "expected_amount": 1000.00,
        "actual_amount": 1000.00,
        "duplicate_check": True,
        "currency": "BRL",
    }

    result = await worker.execute(task_vars)

    assert result["has_discrepancy"] is True
    assert result["discrepancy_type"] == "duplicate_payment"
    assert result["severity"] == "critical"


@pytest.mark.asyncio
async def test_no_discrepancy(worker):
    """Test when no discrepancy exists."""
    task_vars = {
        "payment_id": "pay-003",
        "claim_id": "claim-003",
        "variance": 0.00,
        "expected_amount": 1000.00,
        "actual_amount": 1000.00,
        "duplicate_check": False,
        "currency": "BRL",
    }

    result = await worker.execute(task_vars)

    assert result["has_discrepancy"] is False
    assert result["requires_review"] is False
