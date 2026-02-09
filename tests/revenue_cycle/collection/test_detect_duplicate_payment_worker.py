"""Tests for DetectDuplicatePaymentWorker."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from platform.revenue_cycle.collection.workers.detect_duplicate_payment_worker import (
    DetectDuplicatePaymentWorker,
)
from platform.revenue_cycle.collection.exceptions import DuplicatePaymentError


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
async def test_detect_duplicate_no_duplicates():
    """Test duplicate check passes when no duplicates found."""
    repo = MockPaymentRepository()
    worker = DetectDuplicatePaymentWorker(repository=repo)

    task_vars = {
        "transaction_id": "TXN123",
        "nosso_numero": "NN456",
        "gross_amount": "100.00",
        "payment_date": "2024-01-15",
        "payer_document": "12345678000190",
    }

    result = await worker.execute(task_vars)

    assert result["duplicate_check_passed"] is True


@pytest.mark.asyncio
async def test_detect_duplicate_by_transaction_id():
    """Test duplicate detection by transaction_id."""
    repo = MockPaymentRepository(existing_payments={"txn_TXN123": {"id": "existing"}})
    worker = DetectDuplicatePaymentWorker(repository=repo)

    task_vars = {
        "transaction_id": "TXN123",
        "gross_amount": "100.00",
        "payment_date": "2024-01-15",
        "payer_document": "12345678000190",
    }

    with pytest.raises(DuplicatePaymentError, match="transaction_id"):
        await worker.execute(task_vars)


@pytest.mark.asyncio
async def test_detect_duplicate_by_nosso_numero():
    """Test duplicate detection by nosso_numero."""
    repo = MockPaymentRepository(existing_payments={"nosso_NN456": {"id": "existing"}})
    worker = DetectDuplicatePaymentWorker(repository=repo)

    task_vars = {
        "transaction_id": "TXN789",
        "nosso_numero": "NN456",
        "gross_amount": "100.00",
        "payment_date": "2024-01-15",
        "payer_document": "12345678000190",
    }

    with pytest.raises(DuplicatePaymentError, match="nosso_numero"):
        await worker.execute(task_vars)


@pytest.mark.asyncio
async def test_detect_duplicate_by_composite_key():
    """Test duplicate detection by composite key (amount+date+payer)."""
    composite_key = "composite_100.00_2024-01-15_12345678000190"
    repo = MockPaymentRepository(existing_payments={composite_key: {"id": "existing"}})
    worker = DetectDuplicatePaymentWorker(repository=repo)

    task_vars = {
        "transaction_id": "TXN999",
        "gross_amount": "100.00",
        "payment_date": "2024-01-15",
        "payer_document": "12345678000190",
    }

    with pytest.raises(DuplicatePaymentError, match="valor\\+data\\+pagador"):
        await worker.execute(task_vars)


@pytest.mark.asyncio
async def test_detect_duplicate_no_repository_skips_check():
    """Test duplicate check skipped when no repository configured."""
    worker = DetectDuplicatePaymentWorker(repository=None)

    task_vars = {
        "transaction_id": "TXN123",
    }

    result = await worker.execute(task_vars)

    assert result["duplicate_check_passed"] is True
