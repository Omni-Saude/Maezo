"""Tests for PersistPaymentWorker."""
from __future__ import annotations

from uuid import UUID, uuid4
from unittest.mock import AsyncMock

import pytest

from healthcare_platform.revenue_cycle.collection.workers.persist_payment_worker import (
    PersistPaymentWorker,
)
from healthcare_platform.revenue_cycle.collection.entities import Payment
from healthcare_platform.revenue_cycle.collection.exceptions import CollectionException


class MockPaymentRepository:
    """Mock payment repository for testing."""

    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.saved_payments: list[Payment] = []

    async def save(self, payment: Payment) -> UUID:
        if self.should_fail:
            raise Exception("Database error")
        self.saved_payments.append(payment)
        return payment.id


@pytest.mark.asyncio
async def test_persist_payment_success():
    """Test successful payment persistence."""
    repo = MockPaymentRepository()
    worker = PersistPaymentWorker(repository=repo)

    task_vars = {
        "tenant_id": "hospital_a",
        "transaction_id": "TXN123",
        "bank_code": "001",
        "agency": "1234",
        "account": "567890",
        "gross_amount": "1000.00",
        "net_amount": "950.00",
        "bank_fees": "10.00",
        "tax_withholding": "40.00",
        "payment_type": "full",
        "payment_method": "bank_transfer",
        "payment_date": "2024-01-15",
        "currency": "BRL",
    }

    result = await worker.execute(task_vars)

    assert "payment_id" in result
    assert result["payment_status"] == "received"
    assert len(repo.saved_payments) == 1
    assert repo.saved_payments[0].transaction_id == "TXN123"


@pytest.mark.asyncio
async def test_persist_payment_no_repository():
    """Test persistence fails when no repository configured."""
    worker = PersistPaymentWorker(repository=None)

    task_vars = {
        "transaction_id": "TXN123",
        "gross_amount": "1000.00",
        "net_amount": "1000.00",
    }

    with pytest.raises(CollectionException, match="não configurado"):
        await worker.execute(task_vars)


@pytest.mark.asyncio
async def test_persist_payment_database_error():
    """Test persistence handles database errors."""
    repo = MockPaymentRepository(should_fail=True)
    worker = PersistPaymentWorker(repository=repo)

    task_vars = {
        "tenant_id": "hospital_a",
        "transaction_id": "TXN123",
        "bank_code": "001",
        "agency": "1234",
        "account": "567890",
        "gross_amount": "1000.00",
        "net_amount": "950.00",
        "payment_type": "full",
        "payment_method": "bank_transfer",
    }

    with pytest.raises(CollectionException, match="persistir pagamento"):
        await worker.execute(task_vars)


@pytest.mark.asyncio
async def test_persist_payment_minimal_data():
    """Test persistence with minimal required data."""
    repo = MockPaymentRepository()
    worker = PersistPaymentWorker(repository=repo)

    task_vars = {
        "tenant_id": "hospital_b",
        "transaction_id": "TXN456",
        "gross_amount": "500.00",
        "net_amount": "500.00",
        "bank_code": "237",
        "payment_type": "advance",
        "payment_method": "pix",
    }

    result = await worker.execute(task_vars)

    assert "payment_id" in result
    assert len(repo.saved_payments) == 1
    payment = repo.saved_payments[0]
    assert payment.transaction_id == "TXN456"
    assert str(payment.net_amount.amount) == "500.00"
