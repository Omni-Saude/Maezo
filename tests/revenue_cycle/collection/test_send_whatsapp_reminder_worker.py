from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.send_whatsapp_reminder_worker import (
    SendWhatsAppReminderWorker,
)


@pytest.mark.asyncio
class TestSendWhatsAppReminderWorker:
    """Testes para SendWhatsAppReminderWorker."""

    @patch('healthcare_platform.revenue_cycle.collection.workers.send_whatsapp_reminder_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.send_whatsapp_reminder_worker.FederatedDMNService')
    async def test_send_gentle_reminder_early_overdue(self, mock_dmn_class, mock_tenant):
        """Testa envio de lembrete gentil para vencimento recente (≤7 dias)."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn
        mock_dmn.evaluate.return_value = {
            'templateName': 'payment_reminder_gentle'
        }

        worker = SendWhatsAppReminderWorker()

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "patient_phone": "+5511987654321",
            "patient_first_name": "João",
            "amount_due": 1000.0,
            "currency": "BRL",
            "days_overdue": 5,
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["message_id"] == "WA-CC-12345"
        assert result.variables["status"] == "sent"
        assert result.variables["template_name"] == "payment_reminder_gentle"

    @patch('healthcare_platform.revenue_cycle.collection.workers.send_whatsapp_reminder_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.send_whatsapp_reminder_worker.FederatedDMNService')
    async def test_send_urgent_reminder_medium_overdue(self, mock_dmn_class, mock_tenant):
        """Testa envio de lembrete urgente para vencimento médio (8-30 dias)."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn
        mock_dmn.evaluate.return_value = {
            'templateName': 'payment_reminder_urgent'
        }

        worker = SendWhatsAppReminderWorker()

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "patient_phone": "+5511987654321",
            "patient_first_name": "Maria",
            "amount_due": 2500.0,
            "currency": "BRL",
            "days_overdue": 20,
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["template_name"] == "payment_reminder_urgent"

    @patch('healthcare_platform.revenue_cycle.collection.workers.send_whatsapp_reminder_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.send_whatsapp_reminder_worker.FederatedDMNService')
    async def test_send_final_reminder_late_overdue(self, mock_dmn_class, mock_tenant):
        """Testa envio de lembrete final para vencimento tardio (>30 dias)."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn
        mock_dmn.evaluate.return_value = {
            'templateName': 'payment_reminder_final'
        }

        worker = SendWhatsAppReminderWorker()

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "patient_phone": "+5511987654321",
            "patient_first_name": "Pedro",
            "amount_due": 5000.0,
            "currency": "BRL",
            "days_overdue": 60,
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["template_name"] == "payment_reminder_final"

    @patch('healthcare_platform.revenue_cycle.collection.workers.send_whatsapp_reminder_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.send_whatsapp_reminder_worker.FederatedDMNService')
    async def test_lgpd_no_pii_in_result(self, mock_dmn_class, mock_tenant):
        """Testa conformidade LGPD: sem PII nos resultados."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn
        mock_dmn.evaluate.return_value = {
            'templateName': 'payment_reminder_gentle'
        }

        worker = SendWhatsAppReminderWorker()

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "patient_phone": "+5511987654321",
            "patient_first_name": "Carlos",
            "amount_due": 3000.0,
            "currency": "BRL",
            "days_overdue": 15,
        }

        result = await worker.execute(job)

        assert result.success
        # Result should NOT contain patient phone or name
        assert "patient_phone" not in result.variables
        assert "patient_first_name" not in result.variables
        assert result.variables["collection_case_id"] == "CC-12345"
