from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.enums import AgingBucket
from healthcare_platform.revenue_cycle.collection.workers.generate_collection_letter_worker import (
    GenerateCollectionLetterWorker,
)


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.generate_collection_letter_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.generate_collection_letter_worker.FederatedDMNService")
class TestGenerateCollectionLetterWorker:
    """Testes para GenerateCollectionLetterWorker."""

    @patch("healthcare_platform.revenue_cycle.collection.workers.generate_collection_letter_worker.render_letter")
    async def test_first_notice_for_early_aging(self, mock_render, mock_dmn_service_cls, mock_tenant):
        """Testa geração de primeira notificação para aging inicial (0-60 dias)."""
        mock_tenant.return_value = "tenant-1"
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {
            "letterType": "first_notice",
        }
        mock_dmn_service_cls.return_value = mock_dmn
        mock_render.return_value = "Carta de primeira cobrança..."

        worker = GenerateCollectionLetterWorker()
        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "aging_bucket": AgingBucket.DAYS_0_30.value,
            "patient_name": "João Silva",
            "amount_due": 5000.0,
            "currency": "BRL",
            "days_overdue": 20,
            "original_due_date": (datetime.now(timezone.utc) - timedelta(days=20)).isoformat(),
            "facility_name": "Hospital ABC",
            "facility_contact": "11 1234-5678",
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["letter_type"] == "first_notice"
        assert result.variables["collection_case_id"] == "CC-12345"
        assert "letter_content" in result.variables
        assert "generated_at" in result.variables
        mock_render.assert_called_once()

    @patch("healthcare_platform.revenue_cycle.collection.workers.generate_collection_letter_worker.render_letter")
    async def test_second_notice_for_medium_aging(self, mock_render, mock_dmn_service_cls, mock_tenant):
        """Testa geração de segunda notificação para aging médio (61-120 dias)."""
        mock_tenant.return_value = "tenant-1"
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {
            "letterType": "second_notice",
        }
        mock_dmn_service_cls.return_value = mock_dmn
        mock_render.return_value = "Carta de segunda cobrança..."

        worker = GenerateCollectionLetterWorker()
        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "aging_bucket": AgingBucket.DAYS_61_90.value,
            "patient_name": "Maria Santos",
            "amount_due": 3000.0,
            "currency": "BRL",
            "days_overdue": 75,
            "original_due_date": (datetime.now(timezone.utc) - timedelta(days=75)).isoformat(),
            "facility_name": "Hospital ABC",
            "facility_contact": "11 1234-5678",
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["letter_type"] == "second_notice"

    @patch("healthcare_platform.revenue_cycle.collection.workers.generate_collection_letter_worker.render_letter")
    async def test_final_notice_for_late_aging(self, mock_render, mock_dmn_service_cls, mock_tenant):
        """Testa geração de notificação final para aging avançado (121+ dias)."""
        mock_tenant.return_value = "tenant-1"
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {
            "letterType": "final_notice",
        }
        mock_dmn_service_cls.return_value = mock_dmn
        mock_render.return_value = "Carta de cobrança final..."

        worker = GenerateCollectionLetterWorker()
        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "aging_bucket": AgingBucket.DAYS_180_PLUS.value,
            "patient_name": "Pedro Costa",
            "amount_due": 10000.0,
            "currency": "BRL",
            "days_overdue": 200,
            "original_due_date": (datetime.now(timezone.utc) - timedelta(days=200)).isoformat(),
            "facility_name": "Hospital ABC",
            "facility_contact": "11 1234-5678",
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["letter_type"] == "final_notice"

    @patch("healthcare_platform.revenue_cycle.collection.workers.generate_collection_letter_worker.render_letter")
    async def test_letter_data_passed_correctly(self, mock_render, mock_dmn_service_cls, mock_tenant):
        """Testa que dados corretos são passados para template."""
        mock_tenant.return_value = "tenant-1"
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {
            "letterType": "first_notice",
        }
        mock_dmn_service_cls.return_value = mock_dmn
        mock_render.return_value = "Carta..."

        worker = GenerateCollectionLetterWorker()
        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "aging_bucket": AgingBucket.DAYS_31_60.value,
            "patient_name": "Ana Lima",
            "amount_due": 2500.0,
            "currency": "BRL",
            "days_overdue": 45,
            "original_due_date": "2024-01-01T00:00:00Z",
            "facility_name": "Hospital XYZ",
            "facility_contact": "21 9876-5432",
        }

        await worker.execute(job)

        # Verifica chamada do render_letter
        call_args = mock_render.call_args
        assert call_args[0][0] == "first_notice"
        letter_data = call_args[0][1]
        assert letter_data["patient_name"] == "Ana Lima"
        assert letter_data["amount_due"] == 2500.0
        assert letter_data["facility_name"] == "Hospital XYZ"
