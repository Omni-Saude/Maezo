"""Tests for FlagDiscrepanciesWorker."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from healthcare_platform.revenue_cycle.collection.workers.flag_discrepancies_worker import FlagDiscrepanciesWorker


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.flag_discrepancies_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.flag_discrepancies_worker.FederatedDMNService")
async def test_flag_overpayment_high_severity(mock_dmn_service_cls, mock_tenant):
    """Test flagging overpayment with high severity."""
    mock_tenant.return_value = "tenant-1"
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {
        "hasDiscrepancy": True,
        "discrepancyType": "overpayment",
        "severity": "high",
    }
    mock_dmn_service_cls.return_value = mock_dmn

    worker = FlagDiscrepanciesWorker()
    job = MagicMock()
    job.variables = {
        "payment_id": str(uuid4()),
        "claim_id": str(uuid4()),
        "variance": 150.00,
        "expected_amount": 1000.00,
        "actual_amount": 1150.00,
        "duplicate_check": False,
        "currency": "BRL",
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["has_discrepancy"] is True
    assert result.variables["discrepancy_type"] == "overpayment"
    assert result.variables["severity"] == "high"
    assert result.variables["requires_review"] is True


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.flag_discrepancies_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.flag_discrepancies_worker.FederatedDMNService")
async def test_flag_duplicate_critical(mock_dmn_service_cls, mock_tenant):
    """Test flagging duplicate payment."""
    mock_tenant.return_value = "tenant-1"
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {
        "hasDiscrepancy": True,
        "discrepancyType": "duplicate_payment",
        "severity": "critical",
    }
    mock_dmn_service_cls.return_value = mock_dmn

    worker = FlagDiscrepanciesWorker()
    job = MagicMock()
    job.variables = {
        "payment_id": str(uuid4()),
        "claim_id": str(uuid4()),
        "variance": 0.00,
        "expected_amount": 1000.00,
        "actual_amount": 1000.00,
        "duplicate_check": True,
        "currency": "BRL",
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["has_discrepancy"] is True
    assert result.variables["discrepancy_type"] == "duplicate_payment"
    assert result.variables["severity"] == "critical"


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.flag_discrepancies_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.flag_discrepancies_worker.FederatedDMNService")
async def test_no_discrepancy(mock_dmn_service_cls, mock_tenant):
    """Test when no discrepancy exists."""
    mock_tenant.return_value = "tenant-1"
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {
        "hasDiscrepancy": False,
        "discrepancyType": None,
        "severity": "low",
    }
    mock_dmn_service_cls.return_value = mock_dmn

    worker = FlagDiscrepanciesWorker()
    job = MagicMock()
    job.variables = {
        "payment_id": str(uuid4()),
        "claim_id": str(uuid4()),
        "variance": 0.00,
        "expected_amount": 1000.00,
        "actual_amount": 1000.00,
        "duplicate_check": False,
        "currency": "BRL",
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["has_discrepancy"] is False
    assert result.variables["requires_review"] is False
