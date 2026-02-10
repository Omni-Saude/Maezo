from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from healthcare_platform.revenue_cycle.collection.workers.send_whatsapp_reminder_worker import (
    SendWhatsAppReminderWorker,
)


@pytest.mark.asyncio
class TestSendWhatsAppReminderWorker:
    """Testes para SendWhatsAppReminderWorker."""

    async def test_send_gentle_reminder_early_overdue(self):
        """Testa envio de lembrete gentil para vencimento recente (≤7 dias)."""
        mock_client = Mock()
        mock_client.send_template_message = AsyncMock(
            return_value={"message_id": "MSG-12345", "status": "sent"}
        )

        worker = SendWhatsAppReminderWorker(whatsapp_client=mock_client)

        task_vars = {
            "collection_case_id": "CC-12345",
            "patient_phone": "+5511987654321",
            "patient_first_name": "João",
            "amount_due": 1000.0,
            "currency": "BRL",
            "days_overdue": 5,
        }

        result = await worker.execute(task_vars)

        assert result["message_id"] == "MSG-12345"
        assert result["status"] == "sent"
        assert result["template_name"] == "payment_reminder_gentle"
        mock_client.send_template_message.assert_called_once()

    async def test_send_urgent_reminder_medium_overdue(self):
        """Testa envio de lembrete urgente para vencimento médio (8-30 dias)."""
        mock_client = Mock()
        mock_client.send_template_message = AsyncMock(
            return_value={"message_id": "MSG-67890", "status": "sent"}
        )

        worker = SendWhatsAppReminderWorker(whatsapp_client=mock_client)

        task_vars = {
            "collection_case_id": "CC-12345",
            "patient_phone": "+5511987654321",
            "patient_first_name": "Maria",
            "amount_due": 2500.0,
            "currency": "BRL",
            "days_overdue": 20,
        }

        result = await worker.execute(task_vars)

        assert result["template_name"] == "payment_reminder_urgent"

    async def test_send_final_reminder_late_overdue(self):
        """Testa envio de lembrete final para vencimento tardio (>30 dias)."""
        mock_client = Mock()
        mock_client.send_template_message = AsyncMock(
            return_value={"message_id": "MSG-99999", "status": "sent"}
        )

        worker = SendWhatsAppReminderWorker(whatsapp_client=mock_client)

        task_vars = {
            "collection_case_id": "CC-12345",
            "patient_phone": "+5511987654321",
            "patient_first_name": "Pedro",
            "amount_due": 5000.0,
            "currency": "BRL",
            "days_overdue": 60,
        }

        result = await worker.execute(task_vars)

        assert result["template_name"] == "payment_reminder_final"

    async def test_includes_payment_link_when_provided(self):
        """Testa inclusão de link de pagamento quando fornecido."""
        mock_client = Mock()
        mock_client.send_template_message = AsyncMock(
            return_value={"message_id": "MSG-12345", "status": "sent"}
        )

        worker = SendWhatsAppReminderWorker(whatsapp_client=mock_client)

        task_vars = {
            "collection_case_id": "CC-12345",
            "patient_phone": "+5511987654321",
            "patient_first_name": "Ana",
            "amount_due": 1500.0,
            "currency": "BRL",
            "days_overdue": 10,
            "payment_link": "https://pay.hospital.com/ABC123",
        }

        result = await worker.execute(task_vars)

        # Verify template parameters include payment link
        call_args = mock_client.send_template_message.call_args
        template = call_args.kwargs["template"]
        assert "payment_link" in template.parameters

    async def test_lgpd_no_pii_in_result(self):
        """Testa conformidade LGPD: sem PII nos resultados."""
        mock_client = Mock()
        mock_client.send_template_message = AsyncMock(
            return_value={"message_id": "MSG-12345", "status": "sent"}
        )

        worker = SendWhatsAppReminderWorker(whatsapp_client=mock_client)

        task_vars = {
            "collection_case_id": "CC-12345",
            "patient_phone": "+5511987654321",
            "patient_first_name": "Carlos",
            "amount_due": 3000.0,
            "currency": "BRL",
            "days_overdue": 15,
        }

        result = await worker.execute(task_vars)

        # Result should NOT contain patient phone or name
        assert "patient_phone" not in result
        assert "patient_first_name" not in result
        assert result["collection_case_id"] == "CC-12345"
