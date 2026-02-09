"""Tests for ReceivePaymentNotificationWorker."""
from __future__ import annotations

import json

import pytest

from platform.revenue_cycle.collection.workers.receive_payment_notification_worker import (
    ReceivePaymentNotificationWorker,
)
from platform.revenue_cycle.collection.exceptions import PaymentValidationError


@pytest.mark.asyncio
async def test_receive_payment_notification_success():
    """Test successful webhook notification reception."""
    worker = ReceivePaymentNotificationWorker(webhook_secret="test_secret")

    payload = {
        "transaction_id": "TXN123456",
        "bank_code": "001",
        "agency": "1234",
        "account": "567890",
        "amount": "1500.50",
        "currency": "BRL",
        "payment_date": "2024-01-15",
        "payer_name": "Hospital ABC",
        "payer_document": "12345678000190",
        "payment_method": "pix",
        "signature": "dummy",
    }
    raw_payload = json.dumps(payload)

    # Calculate correct signature
    import hmac
    import hashlib
    signature = hmac.new(
        "test_secret".encode(),
        raw_payload.encode(),
        hashlib.sha256,
    ).hexdigest()

    task_vars = {
        "webhook_payload": raw_payload,
        "signature": signature,
    }

    result = await worker.execute(task_vars)

    assert result["transaction_id"] == "TXN123456"
    assert result["bank_code"] == "001"
    assert result["gross_amount"] == "1500.50"
    assert result["currency"] == "BRL"
    assert result["payment_method"] == "pix"
    assert result["source"] == "webhook"
    assert "received_at" in result


@pytest.mark.asyncio
async def test_receive_payment_notification_invalid_signature():
    """Test webhook with invalid signature fails."""
    worker = ReceivePaymentNotificationWorker(webhook_secret="test_secret")

    payload = {
        "transaction_id": "TXN123",
        "amount": "100.00",
        "signature": "invalid",
    }
    raw_payload = json.dumps(payload)

    task_vars = {
        "webhook_payload": raw_payload,
        "signature": "invalid_signature_xyz",
    }

    with pytest.raises(PaymentValidationError, match="Assinatura do webhook inválida"):
        await worker.execute(task_vars)


@pytest.mark.asyncio
async def test_receive_payment_notification_missing_payload():
    """Test webhook with missing payload fails."""
    worker = ReceivePaymentNotificationWorker()

    task_vars = {"signature": "some_signature"}

    with pytest.raises(PaymentValidationError, match="Payload ou assinatura"):
        await worker.execute(task_vars)


@pytest.mark.asyncio
async def test_receive_payment_notification_malformed_json():
    """Test webhook with malformed JSON fails."""
    worker = ReceivePaymentNotificationWorker(webhook_secret="test_secret")

    raw_payload = "{not valid json"
    import hmac
    import hashlib
    signature = hmac.new(
        "test_secret".encode(),
        raw_payload.encode(),
        hashlib.sha256,
    ).hexdigest()

    task_vars = {
        "webhook_payload": raw_payload,
        "signature": signature,
    }

    with pytest.raises(PaymentValidationError, match="parsear payload"):
        await worker.execute(task_vars)
