"""Tests for ClassifyPaymentTypeWorker."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.classify_payment_type_worker import (
    ClassifyPaymentTypeWorker,
)


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.classify_payment_type_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.classify_payment_type_worker.FederatedDMNService")
async def test_classify_payment_full(mock_dmn_service_cls, mock_tenant):
    """Test classification as full payment."""
    mock_tenant.return_value = "tenant-1"
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {
        "paymentType": "full",
        "classificationReason": "ratio_1.00",
    }
    mock_dmn_service_cls.return_value = mock_dmn

    worker = ClassifyPaymentTypeWorker()
    job = MagicMock()
    job.variables = {
        "net_amount": "1000.00",
        "expected_amount": "1000.00",
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["payment_type"] == "full"
    assert "ratio" in result.variables["classification_reason"]


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.classify_payment_type_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.classify_payment_type_worker.FederatedDMNService")
async def test_classify_payment_partial(mock_dmn_service_cls, mock_tenant):
    """Test classification as partial payment."""
    mock_tenant.return_value = "tenant-1"
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {
        "paymentType": "partial",
        "classificationReason": "ratio_0.50",
    }
    mock_dmn_service_cls.return_value = mock_dmn

    worker = ClassifyPaymentTypeWorker()
    job = MagicMock()
    job.variables = {
        "net_amount": "500.00",
        "expected_amount": "1000.00",
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["payment_type"] == "partial"
    assert "0.5" in result.variables["payment_ratio"]


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.classify_payment_type_worker.get_required_tenant")
async def test_classify_payment_advance_no_expected(mock_tenant):
    """Test classification as advance when no expected amount."""
    mock_tenant.return_value = "tenant-1"

    worker = ClassifyPaymentTypeWorker()
    job = MagicMock()
    job.variables = {
        "net_amount": "1000.00",
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["payment_type"] == "advance"
    assert result.variables["classification_reason"] == "no_expected_amount"


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.classify_payment_type_worker.get_required_tenant")
async def test_classify_payment_advance_zero_expected(mock_tenant):
    """Test classification as advance when expected is zero."""
    mock_tenant.return_value = "tenant-1"

    worker = ClassifyPaymentTypeWorker()
    job = MagicMock()
    job.variables = {
        "net_amount": "500.00",
        "expected_amount": "0",
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["payment_type"] == "advance"


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.classify_payment_type_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.classify_payment_type_worker.FederatedDMNService")
async def test_classify_payment_overpayment(mock_dmn_service_cls, mock_tenant):
    """Test classification when payment exceeds expected."""
    mock_tenant.return_value = "tenant-1"
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {
        "paymentType": "full",
        "classificationReason": "ratio_1.20",
    }
    mock_dmn_service_cls.return_value = mock_dmn

    worker = ClassifyPaymentTypeWorker()
    job = MagicMock()
    job.variables = {
        "net_amount": "1200.00",
        "expected_amount": "1000.00",
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["payment_type"] == "full"
    assert "1.2" in result.variables["payment_ratio"]
