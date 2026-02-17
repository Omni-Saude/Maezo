"""Tests for MatchByPatientWorker."""
from __future__ import annotations

from uuid import uuid4
from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.match_by_patient_worker import MatchByPatientWorker


@pytest.fixture
def worker():
    """Create worker instance."""
    return MatchByPatientWorker()


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.match_by_patient_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.match_by_patient_worker.FederatedDMNService')
async def test_match_by_patient_within_tolerance(mock_dmn_service, mock_tenant, worker):
    """Test patient match with amount within tolerance."""
    mock_tenant.return_value = 'test_tenant'
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {'match_quality': 'good', 'tolerance_ok': True}
    mock_dmn_service.return_value = mock_dmn

    worker.dmn_service = mock_dmn

    claim_id = str(uuid4())
    job = MagicMock()
    job.variables = {
        "payment_id": str(uuid4()),
        "patient_id": "patient-001",
        "payment_amount": 1020.00,  # Within 5% of 1000.00
        "currency": "BRL",
        "tolerance_percent": 5.0,
        "available_claims": [
            {"claim_id": claim_id, "patient_id": "patient-001", "total_amount": 1000.00}
        ],
    }

    result = await worker.execute(job)

    assert result.success is True
    assert result.variables["matched"] is True
    assert result.variables["claim_id"] == claim_id
    assert result.variables["confidence_score"] > 0.3
    assert result.variables["amount_difference"] == 20.0


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.match_by_patient_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.match_by_patient_worker.FederatedDMNService')
async def test_patient_not_found(mock_dmn_service, mock_tenant, worker):
    """Test when patient has no claims."""
    mock_tenant.return_value = 'test_tenant'
    mock_dmn = MagicMock()
    mock_dmn_service.return_value = mock_dmn

    worker.dmn_service = mock_dmn

    job = MagicMock()
    job.variables = {
        "payment_id": str(uuid4()),
        "patient_id": "patient-999",
        "payment_amount": 1000.00,
        "currency": "BRL",
        "available_claims": [
            {"claim_id": str(uuid4()), "patient_id": "patient-001", "total_amount": 1000.00}
        ],
    }

    result = await worker.execute(job)

    assert result.success is True
    assert result.variables["matched"] is False
    assert result.variables["claim_id"] is None
