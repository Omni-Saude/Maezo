"""Tests for HandleUnderpaymentWorker."""
from __future__ import annotations

from uuid import uuid4
from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.exceptions import UnderpaymentError
from healthcare_platform.revenue_cycle.collection.workers.handle_underpayment_worker import HandleUnderpaymentWorker


@pytest.fixture
def worker():
    """Create worker instance."""
    return HandleUnderpaymentWorker()


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.handle_underpayment_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.handle_underpayment_worker.FederatedDMNService')
async def test_underpayment_is_glosa(mock_dmn_service, mock_tenant, worker):
    """Test underpayment that matches known glosa amount."""
    mock_tenant.return_value = 'test_tenant'
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {'action': 'accept_glosa'}
    mock_dmn_service.return_value = mock_dmn

    worker.dmn_service = mock_dmn

    job = MagicMock()
    job.variables = {
        "payment_id": str(uuid4()),
        "claim_id": str(uuid4()),
        "payment_amount": 900.00,
        "expected_amount": 1000.00,
        "currency": "BRL",
        "glosa_amount": 100.00,  # Matches underpayment
    }

    result = await worker.execute(job)

    assert result.success is True
    assert result.variables["underpayment_amount"] == 100.00
    assert result.variables["is_glosa"] is True
    assert result.variables["requires_collection"] is False


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.handle_underpayment_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.handle_underpayment_worker.FederatedDMNService')
async def test_underpayment_requires_collection(mock_dmn_service, mock_tenant, worker):
    """Test underpayment that requires collection action."""
    mock_tenant.return_value = 'test_tenant'
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {'action': 'collect'}
    mock_dmn_service.return_value = mock_dmn

    worker.dmn_service = mock_dmn

    job = MagicMock()
    job.variables = {
        "payment_id": str(uuid4()),
        "claim_id": str(uuid4()),
        "payment_amount": 800.00,
        "expected_amount": 1000.00,
        "currency": "BRL",
        "glosa_amount": 0.00,
    }

    result = await worker.execute(job)

    # Worker catches UnderpaymentError and returns BPMN error
    assert result.success is False
    assert result.error_code is not None


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.handle_underpayment_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.handle_underpayment_worker.FederatedDMNService')
async def test_small_underpayment_no_collection(mock_dmn_service, mock_tenant, worker):
    """Test small underpayment below collection threshold."""
    mock_tenant.return_value = 'test_tenant'
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {'action': 'write_off'}
    mock_dmn_service.return_value = mock_dmn

    worker.dmn_service = mock_dmn

    job = MagicMock()
    job.variables = {
        "payment_id": str(uuid4()),
        "claim_id": str(uuid4()),
        "payment_amount": 995.00,
        "expected_amount": 1000.00,
        "currency": "BRL",
        "glosa_amount": 0.00,
    }

    result = await worker.execute(job)

    assert result.success is True
    assert result.variables["underpayment_amount"] == 5.00
    assert result.variables["requires_collection"] is False
