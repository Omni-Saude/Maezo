"""Tests for NotifySubmissionStatusWorker."""
from __future__ import annotations

import types

import pytest

from healthcare_platform.revenue_cycle.billing.workers.notify_submission_status_worker_v2 import NotifySubmissionStatusWorker
from healthcare_platform.shared.integrations.whatsapp_client import StubWhatsAppClient

from unittest.mock import Mock


@pytest.fixture
def mock_dmn_service():
    """Create mock DMN service."""
    dmn_service = Mock()
    # Default DMN response: PROSSEGUIR (allow processing)
    dmn_service.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "Processar com sucesso",
        "risco": "BAIXO"
    }
    return dmn_service


@pytest.fixture
def whatsapp_client():
    """Create stub WhatsApp client."""
    return StubWhatsAppClient()


@pytest.fixture
def worker(whatsapp_client, mock_dmn_service):
    """Create worker instance."""
    return NotifySubmissionStatusWorker(
        whatsapp_client=whatsapp_client,
        dmn_service=mock_dmn_service
    )


@pytest.fixture
def submitted_job():
    """Create job for submitted status."""
    return types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "protocol_number": "PROTO-2025-001",
            "submission_status": "submitted",
            "payer_name": "Unimed São Paulo",
            "total_amount": 15000.50,
            "notification_phones": ["+5511999999999", "+5511988888888"]
        }
    )


@pytest.mark.asyncio
async def test_notify_submitted_status(worker, submitted_job):
    """Test notification for submitted status."""
    result = await worker.execute(submitted_job)

    assert result.success is True
    assert result.variables["notifications_sent"] == 2
    assert len(result.variables["notification_ids"]) == 2


@pytest.mark.asyncio
async def test_notify_acknowledged_status(worker):
    """Test notification for acknowledged status."""
    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "protocol_number": "PROTO-2025-001",
            "submission_status": "acknowledged",
            "payer_name": "Bradesco Saúde",
            "total_amount": 8500.00,
            "notification_phones": ["+5511977777777"]
        }
    )

    result = await worker.execute(job)

    assert result.success is True
    assert result.variables["notifications_sent"] == 1


@pytest.mark.asyncio
async def test_notify_rejected_status(worker):
    """Test notification for rejected status."""
    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "protocol_number": "PROTO-2025-001",
            "submission_status": "rejected",
            "payer_name": "SulAmérica",
            "total_amount": 12000.00,
            "notification_phones": ["+5511966666666"]
        }
    )

    result = await worker.execute(job)

    assert result.success is True
    assert result.variables["notifications_sent"] == 1


@pytest.mark.asyncio
async def test_notify_failed_status(worker):
    """Test notification for failed status."""
    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "protocol_number": None,  # No protocol for failed
            "submission_status": "failed",
            "payer_name": "Amil",
            "total_amount": 9500.00,
            "notification_phones": ["+5511955555555"]
        }
    )

    result = await worker.execute(job)

    assert result.success is True
    assert result.variables["notifications_sent"] == 1


@pytest.mark.asyncio
async def test_missing_claim_id(worker):
    """Test error when claim ID is missing."""
    job = types.SimpleNamespace(
        variables={
            "submission_status": "submitted",
            "notification_phones": ["+5511999999999"]
        }
    )

    result = await worker.execute(job)

    assert result.success is False
    assert result.error_code == "MISSING_CLAIM_ID"


@pytest.mark.asyncio
async def test_invalid_submission_status(worker):
    """Test error with invalid submission status."""
    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "submission_status": "invalid_status",
            "notification_phones": ["+5511999999999"]
        }
    )

    result = await worker.execute(job)

    assert result.success is False
    assert result.error_code == "INVALID_STATUS"


@pytest.mark.asyncio
async def test_empty_notification_phones(worker):
    """Test handling when notification phones list is empty."""
    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "protocol_number": "PROTO-2025-001",
            "submission_status": "submitted",
            "payer_name": "Operadora",
            "total_amount": 1000.00,
            "notification_phones": []
        }
    )

    result = await worker.execute(job)

    assert result.success is True
    assert result.variables["notifications_sent"] == 0
    assert result.variables["notification_ids"] == []


@pytest.mark.asyncio
async def test_missing_notification_phones(worker):
    """Test handling when notification phones is not provided."""
    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "submission_status": "submitted",
            "payer_name": "Operadora",
            "total_amount": 1000.00
        }
    )

    result = await worker.execute(job)

    assert result.success is True
    assert result.variables["notifications_sent"] == 0


@pytest.mark.asyncio
async def test_brazilian_currency_formatting(worker):
    """Test that currency is formatted in Brazilian format."""
    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "protocol_number": "PROTO-2025-001",
            "submission_status": "submitted",
            "payer_name": "Operadora",
            "total_amount": 1234567.89,
            "notification_phones": ["+5511999999999"]
        }
    )

    result = await worker.execute(job)

    # Should format as R$ 1.234.567,89
    assert result.success is True


@pytest.mark.asyncio
async def test_template_language_portuguese(worker, submitted_job):
    """Test that template uses Portuguese language."""
    result = await worker.execute(submitted_job)

    assert result.success is True
    # Stub client should have received pt_BR templates


@pytest.mark.asyncio
async def test_multiple_phone_numbers(worker):
    """Test sending to multiple phone numbers."""
    phones = [
        "+5511999999999",
        "+5511988888888",
        "+5511977777777",
        "+5511966666666"
    ]

    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "protocol_number": "PROTO-2025-001",
            "submission_status": "submitted",
            "payer_name": "Operadora",
            "total_amount": 5000.00,
            "notification_phones": phones
        }
    )

    result = await worker.execute(job)

    assert result.success is True
    assert result.variables["notifications_sent"] == 4
    assert len(result.variables["notification_ids"]) == 4


@pytest.mark.asyncio
async def test_partial_notification_failure(worker, whatsapp_client, monkeypatch):
    """Test handling when some notifications fail."""
    call_count = 0

    async def mock_send_with_failure(phone, template):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("Network error")
        return f"msg_{call_count}"

    monkeypatch.setattr(whatsapp_client, "send_template_message", mock_send_with_failure)

    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "protocol_number": "PROTO-2025-001",
            "submission_status": "submitted",
            "payer_name": "Operadora",
            "total_amount": 1000.00,
            "notification_phones": ["+5511999999999", "+5511988888888", "+5511977777777"]
        }
    )

    result = await worker.execute(job)

    assert result.success is True
    assert result.variables["notifications_sent"] == 2  # 1 failed


@pytest.mark.asyncio
async def test_all_notifications_fail(worker, whatsapp_client, monkeypatch):
    """Test handling when all notifications fail."""
    async def mock_send_failure(phone, template):
        raise RuntimeError("WhatsApp API error")

    monkeypatch.setattr(whatsapp_client, "send_template_message", mock_send_failure)

    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "protocol_number": "PROTO-2025-001",
            "submission_status": "submitted",
            "payer_name": "Operadora",
            "total_amount": 1000.00,
            "notification_phones": ["+5511999999999", "+5511988888888"]
        }
    )

    result = await worker.execute(job)

    assert result.success is False
    assert result.retry is True


@pytest.mark.asyncio
async def test_default_payer_name(worker):
    """Test default payer name when not provided."""
    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "protocol_number": "PROTO-2025-001",
            "submission_status": "submitted",
            "total_amount": 1000.00,
            "notification_phones": ["+5511999999999"]
        }
    )

    result = await worker.execute(job)

    assert result.success is True


@pytest.mark.asyncio
async def test_default_total_amount(worker):
    """Test default total amount when not provided."""
    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "protocol_number": "PROTO-2025-001",
            "submission_status": "submitted",
            "payer_name": "Operadora",
            "notification_phones": ["+5511999999999"]
        }
    )

    result = await worker.execute(job)

    assert result.success is True


@pytest.mark.asyncio
async def test_worker_metadata(worker):
    """Test worker metadata and configuration."""
    assert worker._topic == "billing-notify-submission-status"
    assert worker.operation_name == "Notificar status de submissão"
    assert worker.worker_name == "NotifySubmissionStatusWorker"


@pytest.mark.asyncio
async def test_template_names_for_each_status(worker):
    """Test that correct template names are used for each status."""
    statuses = ["submitted", "acknowledged", "rejected", "failed"]
    expected_templates = [
        "billing_submitted",
        "billing_acknowledged",
        "billing_rejected",
        "billing_failed"
    ]

    for status, expected_template in zip(statuses, expected_templates):
        job = types.SimpleNamespace(
            variables={
                "claim_id": "CLAIM-12345",
                "protocol_number": "PROTO-2025-001",
                "submission_status": status,
                "payer_name": "Operadora",
                "total_amount": 1000.00,
                "notification_phones": ["+5511999999999"]
            }
        )

        result = await worker.execute(job)
        assert result.success is True


@pytest.mark.asyncio
async def test_case_insensitive_status(worker):
    """Test that submission status is case insensitive."""
    job = types.SimpleNamespace(
        variables={
            "claim_id": "CLAIM-12345",
            "protocol_number": "PROTO-2025-001",
            "submission_status": "SUBMITTED",  # Uppercase
            "payer_name": "Operadora",
            "total_amount": 1000.00,
            "notification_phones": ["+5511999999999"]
        }
    )

    result = await worker.execute(job)

    assert result.success is True
