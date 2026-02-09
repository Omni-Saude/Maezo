"""Tests for MatchByPatientWorker."""
from __future__ import annotations

import pytest

from platform.revenue_cycle.collection.workers.match_by_patient_worker import MatchByPatientWorker


@pytest.fixture
def worker():
    """Create worker instance."""
    return MatchByPatientWorker()


@pytest.mark.asyncio
async def test_match_by_patient_within_tolerance(worker):
    """Test patient match with amount within tolerance."""
    task_vars = {
        "payment_id": "pay-001",
        "patient_id": "patient-001",
        "payment_amount": 1020.00,  # Within 5% of 1000.00
        "currency": "BRL",
        "tolerance_percent": 5.0,
        "available_claims": [
            {"claim_id": "claim-001", "patient_id": "patient-001", "total_amount": 1000.00}
        ],
    }

    result = await worker.execute(task_vars)

    assert result["matched"] is True
    assert result["claim_id"] == "claim-001"
    assert result["confidence_score"] > 0.3
    assert result["amount_difference"] == 20.0


@pytest.mark.asyncio
async def test_match_exceeds_tolerance(worker):
    """Test patient match where amount exceeds tolerance."""
    task_vars = {
        "payment_id": "pay-002",
        "patient_id": "patient-001",
        "payment_amount": 1100.00,  # 10% difference - exceeds 5% tolerance
        "currency": "BRL",
        "tolerance_percent": 5.0,
        "available_claims": [
            {"claim_id": "claim-001", "patient_id": "patient-001", "total_amount": 1000.00}
        ],
    }

    result = await worker.execute(task_vars)

    assert result["matched"] is False
    assert result["claim_id"] is None


@pytest.mark.asyncio
async def test_patient_not_found(worker):
    """Test when patient has no claims."""
    task_vars = {
        "payment_id": "pay-003",
        "patient_id": "patient-999",
        "payment_amount": 1000.00,
        "currency": "BRL",
        "available_claims": [
            {"claim_id": "claim-001", "patient_id": "patient-001", "total_amount": 1000.00}
        ],
    }

    result = await worker.execute(task_vars)

    assert result["matched"] is False
    assert result["claim_id"] is None
