"""Tests for AutoMatchingWorker."""
from __future__ import annotations

import pytest

from platform.revenue_cycle.collection.workers.auto_matching_worker import AutoMatchingWorker


@pytest.fixture
def worker():
    """Create worker instance."""
    return AutoMatchingWorker()


@pytest.fixture
def available_claims():
    """Sample claims for matching."""
    return [
        {
            "claim_id": "claim-001",
            "protocol_number": "TISS-12345",
            "invoice_number": "INV-001",
            "patient_id": "patient-001",
            "total_amount": 1000.00,
        },
        {
            "claim_id": "claim-002",
            "protocol_number": "TISS-67890",
            "nosso_numero": "NN-002",
            "patient_id": "patient-002",
            "total_amount": 2000.00,
        },
        {
            "claim_id": "claim-003",
            "invoice_number": "INV-003",
            "patient_id": "patient-001",
            "total_amount": 1500.00,
        },
    ]


@pytest.mark.asyncio
async def test_match_by_protocol_success(worker, available_claims):
    """Test successful match by protocol number."""
    task_vars = {
        "payment_id": "pay-001",
        "protocol_number": "TISS-12345",
        "payment_amount": 1000.00,
        "currency": "BRL",
        "available_claims": available_claims,
    }

    result = await worker.execute(task_vars)

    assert result["matched"] is True
    assert result["claim_id"] == "claim-001"
    assert result["match_method"] == "protocol"
    assert result["confidence_score"] == 0.95
    assert result["allocation_id"] is not None


@pytest.mark.asyncio
async def test_match_by_invoice_success(worker, available_claims):
    """Test successful match by invoice number."""
    task_vars = {
        "payment_id": "pay-002",
        "invoice_number": "INV-003",
        "payment_amount": 1500.00,
        "currency": "BRL",
        "available_claims": available_claims,
    }

    result = await worker.execute(task_vars)

    assert result["matched"] is True
    assert result["claim_id"] == "claim-003"
    assert result["match_method"] == "invoice"
    assert result["confidence_score"] == 0.85


@pytest.mark.asyncio
async def test_match_by_patient_success(worker, available_claims):
    """Test successful match by patient ID and amount."""
    task_vars = {
        "payment_id": "pay-003",
        "patient_id": "patient-001",
        "payment_amount": 1020.00,  # Within 5% of 1000.00
        "currency": "BRL",
        "available_claims": available_claims,
    }

    result = await worker.execute(task_vars)

    assert result["matched"] is True
    assert result["claim_id"] == "claim-001"
    assert result["match_method"] == "patient"
    assert result["confidence_score"] >= 0.50


@pytest.mark.asyncio
async def test_no_match_found(worker, available_claims):
    """Test when no match is found."""
    task_vars = {
        "payment_id": "pay-004",
        "protocol_number": "TISS-99999",
        "payment_amount": 5000.00,
        "currency": "BRL",
        "available_claims": available_claims,
    }

    result = await worker.execute(task_vars)

    assert result["matched"] is False
    assert result["claim_id"] is None
    assert result["match_method"] == "none"
    assert result["confidence_score"] == 0.0


@pytest.mark.asyncio
async def test_empty_claims_list(worker):
    """Test with no available claims."""
    task_vars = {
        "payment_id": "pay-005",
        "protocol_number": "TISS-12345",
        "payment_amount": 1000.00,
        "currency": "BRL",
        "available_claims": [],
    }

    result = await worker.execute(task_vars)

    assert result["matched"] is False
    assert result["claim_id"] is None
