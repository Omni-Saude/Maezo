"""Tests for DetectDuplicatePaymentWorker."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.detect_duplicate_payment_worker import (
    DetectDuplicatePaymentWorker,
)
from healthcare_platform.revenue_cycle.collection.exceptions import DuplicatePaymentError


class MockPaymentRepository:
    """Mock payment repository for testing."""

    def __init__(self, existing_payments: dict[str, Any] | None = None):
        self.existing_payments = existing_payments or {}

    async def find_by_transaction_id(self, transaction_id: str) -> Any | None:
        return self.existing_payments.get(f"txn_{transaction_id}")

    async def find_by_nosso_numero(self, nosso_numero: str) -> Any | None:
        return self.existing_payments.get(f"nosso_{nosso_numero}")

    async def find_by_composite_key(
        self, amount: str, payment_date: str, payer_document: str
    ) -> Any | None:
        key = f"composite_{amount}_{payment_date}_{payer_document}"
        return self.existing_payments.get(key)


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.detect_duplicate_payment_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.detect_duplicate_payment_worker.FederatedDMNService")
async def test_detect_duplicate_no_duplicates(mock_dmn_service_cls, mock_tenant):
    """Test duplicate check passes when no duplicates found."""
    mock_tenant.return_value = "tenant-1"
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {}
    mock_dmn_service_cls.return_value = mock_dmn

    repo = MockPaymentRepository()
    worker = DetectDuplicatePaymentWorker(repository=repo)
    job = MagicMock()
    job.variables = {
        "transaction_id": "TXN123",
        "nosso_numero": "NN456",
        "gross_amount": "100.00",
        "payment_date": "2024-01-15",
        "payer_document": "12345678000190",
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["duplicate_check_passed"] is True


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.detect_duplicate_payment_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.detect_duplicate_payment_worker.FederatedDMNService")
async def test_detect_duplicate_by_transaction_id(mock_dmn_service_cls, mock_tenant):
    """Test duplicate detection by transaction_id."""
    mock_tenant.return_value = "tenant-1"
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {}
    mock_dmn_service_cls.return_value = mock_dmn

    repo = MockPaymentRepository(existing_payments={"txn_TXN123": {"id": "existing"}})
    worker = DetectDuplicatePaymentWorker(repository=repo)
    job = MagicMock()
    job.variables = {
        "transaction_id": "TXN123",
        "gross_amount": "100.00",
        "payment_date": "2024-01-15",
        "payer_document": "12345678000190",
    }

    result = await worker.execute(job)

    assert result.success is False
    assert result.error_code == "DUPLICATE_PAYMENT"
    assert "transaction_id" in result.error_message


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.detect_duplicate_payment_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.detect_duplicate_payment_worker.FederatedDMNService")
async def test_detect_duplicate_by_nosso_numero(mock_dmn_service_cls, mock_tenant):
    """Test duplicate detection by nosso_numero."""
    mock_tenant.return_value = "tenant-1"
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {}
    mock_dmn_service_cls.return_value = mock_dmn

    repo = MockPaymentRepository(existing_payments={"nosso_NN456": {"id": "existing"}})
    worker = DetectDuplicatePaymentWorker(repository=repo)
    job = MagicMock()
    job.variables = {
        "transaction_id": "TXN789",
        "nosso_numero": "NN456",
        "gross_amount": "100.00",
        "payment_date": "2024-01-15",
        "payer_document": "12345678000190",
    }

    result = await worker.execute(job)

    assert result.success is False
    assert result.error_code == "DUPLICATE_PAYMENT"
    assert "nosso_numero" in result.error_message


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.detect_duplicate_payment_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.detect_duplicate_payment_worker.FederatedDMNService")
async def test_detect_duplicate_by_composite_key(mock_dmn_service_cls, mock_tenant):
    """Test duplicate detection by composite key (amount+date+payer)."""
    mock_tenant.return_value = "tenant-1"
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {}
    mock_dmn_service_cls.return_value = mock_dmn

    composite_key = "composite_100.00_2024-01-15_12345678000190"
    repo = MockPaymentRepository(existing_payments={composite_key: {"id": "existing"}})
    worker = DetectDuplicatePaymentWorker(repository=repo)
    job = MagicMock()
    job.variables = {
        "transaction_id": "TXN999",
        "gross_amount": "100.00",
        "payment_date": "2024-01-15",
        "payer_document": "12345678000190",
    }

    result = await worker.execute(job)

    assert result.success is False
    assert result.error_code == "DUPLICATE_PAYMENT"


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.detect_duplicate_payment_worker.get_required_tenant")
async def test_detect_duplicate_no_repository_skips_check(mock_tenant):
    """Test duplicate check skipped when no repository configured."""
    mock_tenant.return_value = "tenant-1"

    worker = DetectDuplicatePaymentWorker(repository=None)
    job = MagicMock()
    job.variables = {
        "transaction_id": "TXN123",
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["duplicate_check_passed"] is True
