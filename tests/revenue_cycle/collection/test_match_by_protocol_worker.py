"""Tests for MatchByProtocolWorker."""
from __future__ import annotations

from uuid import uuid4
from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.match_by_protocol_worker import MatchByProtocolWorker


@pytest.fixture
def worker():
    """Create worker instance."""
    return MatchByProtocolWorker()


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.match_by_protocol_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.match_by_protocol_worker.FederatedDMNService')
async def test_match_by_protocol_success(mock_dmn_service, mock_tenant, worker):
    """Test successful protocol match."""
    mock_tenant.return_value = 'test_tenant'
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {'match_quality': 'exact', 'confidence': 1.0}
    mock_dmn_service.return_value = mock_dmn

    worker.dmn_service = mock_dmn

    claim_id = str(uuid4())
    job = MagicMock()
    job.variables = {
        "payment_id": str(uuid4()),
        "protocol_number": "TISS-12345",
        "payment_amount": 1000.00,
        "currency": "BRL",
        "available_claims": [
            {
                "claim_id": claim_id,
                "protocol_number": "TISS-12345",
                "total_amount": 1000.00,
            }
        ],
    }

    result = await worker.execute(job)

    assert result.success is True
    assert result.variables["matched"] is True
    assert result.variables["claim_id"] == claim_id
    assert result.variables["protocol_number"] == "TISS-12345"


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.match_by_protocol_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.match_by_protocol_worker.FederatedDMNService')
async def test_protocol_not_found(mock_dmn_service, mock_tenant, worker):
    """Test when protocol is not found."""
    mock_tenant.return_value = 'test_tenant'
    mock_dmn = MagicMock()
    mock_dmn_service.return_value = mock_dmn

    worker.dmn_service = mock_dmn

    job = MagicMock()
    job.variables = {
        "payment_id": str(uuid4()),
        "protocol_number": "TISS-99999",
        "payment_amount": 1000.00,
        "currency": "BRL",
        "available_claims": [
            {
                "claim_id": str(uuid4()),
                "protocol_number": "TISS-12345",
                "total_amount": 1000.00,
            }
        ],
    }

    result = await worker.execute(job)

    assert result.success is True
    assert result.variables["matched"] is False
    assert result.variables["claim_id"] is None
