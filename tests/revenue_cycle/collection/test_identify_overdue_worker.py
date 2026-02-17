from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.identify_overdue_worker import (
    IdentifyOverdueWorker,
)


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.identify_overdue_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.identify_overdue_worker.FederatedDMNService')
class TestIdentifyOverdueWorker:
    """Testes para IdentifyOverdueWorker."""

    async def test_identify_overdue_claim_creates_collection_case(self, mock_dmn_service, mock_tenant):
        """Testa criação de caso de cobrança para claim vencido."""
        mock_tenant.return_value = 'test_tenant'
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {'bucket': '15-30_days', 'priority': 'medium'}
        mock_dmn_service.return_value = mock_dmn

        worker = IdentifyOverdueWorker()
        worker.dmn_service = mock_dmn

        # Claim vencido há 15 dias
        due_date = datetime.now(timezone.utc) - timedelta(days=15)

        job = MagicMock()
        job.variables = {
            "claim_id": "CLM-12345",
            "amount_due": 5000.0,
            "currency": "BRL",
            "due_date": due_date.isoformat(),
            "payer_id": "ORG-001",
            "patient_id": "PAT-001",
            "facility_id": "FAC-001",
        }

        result = await worker.execute(job)

        assert result.success is True
        assert result.variables["collection_case_id"] == "CC-CLM-12345"
        assert result.variables["days_overdue"] == 15
        assert result.variables["amount_due"] == 5000.0
        assert result.variables["status"] == "overdue"

    async def test_not_overdue_claim_returns_null_case(self, mock_dmn_service, mock_tenant):
        """Testa que claim não vencido não gera caso de cobrança."""
        mock_tenant.return_value = 'test_tenant'
        mock_dmn = MagicMock()
        mock_dmn_service.return_value = mock_dmn

        worker = IdentifyOverdueWorker()
        worker.dmn_service = mock_dmn

        # Claim vence em 10 dias
        due_date = datetime.now(timezone.utc) + timedelta(days=10)

        job = MagicMock()
        job.variables = {
            "claim_id": "CLM-12345",
            "amount_due": 5000.0,
            "currency": "BRL",
            "due_date": due_date.isoformat(),
            "payer_id": "ORG-001",
            "patient_id": "PAT-001",
            "facility_id": "FAC-001",
        }

        result = await worker.execute(job)

        assert result.success is True
        assert result.variables["collection_case_id"] is None
        assert result.variables["days_overdue"] == -10
        assert result.variables["status"] == "not_overdue"

    async def test_due_today_not_overdue(self, mock_dmn_service, mock_tenant):
        """Testa que claim com vencimento hoje não é considerado vencido."""
        mock_tenant.return_value = 'test_tenant'
        mock_dmn = MagicMock()
        mock_dmn_service.return_value = mock_dmn

        worker = IdentifyOverdueWorker()
        worker.dmn_service = mock_dmn

        # Vence hoje
        due_date = datetime.now(timezone.utc)

        job = MagicMock()
        job.variables = {
            "claim_id": "CLM-12345",
            "amount_due": 5000.0,
            "currency": "BRL",
            "due_date": due_date.isoformat(),
            "payer_id": "ORG-001",
            "patient_id": "PAT-001",
            "facility_id": "FAC-001",
        }

        result = await worker.execute(job)

        assert result.success is True
        assert result.variables["collection_case_id"] is None
        assert result.variables["days_overdue"] == 0
        assert result.variables["status"] == "not_overdue"

    async def test_handles_different_currency(self, mock_dmn_service, mock_tenant):
        """Testa suporte a diferentes moedas."""
        mock_tenant.return_value = 'test_tenant'
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {'bucket': '0-15_days', 'priority': 'low'}
        mock_dmn_service.return_value = mock_dmn

        worker = IdentifyOverdueWorker()
        worker.dmn_service = mock_dmn

        due_date = datetime.now(timezone.utc) - timedelta(days=5)

        job = MagicMock()
        job.variables = {
            "claim_id": "CLM-12345",
            "amount_due": 1000.0,
            "currency": "USD",
            "due_date": due_date.isoformat(),
            "payer_id": "ORG-001",
            "patient_id": "PAT-001",
            "facility_id": "FAC-001",
        }

        result = await worker.execute(job)

        assert result.success is True
        assert result.variables["status"] == "overdue"
