from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.apply_penalties_worker import (
    ApplyPenaltiesWorker,
)


@pytest.mark.asyncio
class TestApplyPenaltiesWorker:
    """Testes para ApplyPenaltiesWorker."""

    @patch('healthcare_platform.revenue_cycle.collection.workers.apply_penalties_worker.get_required_tenant', return_value='test-tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.apply_penalties_worker.FederatedDMNService')
    async def test_apply_penalties_success(self, MockDMNService, mock_tenant):
        """Testa aplicação bem-sucedida de multas e juros."""
        mock_dmn = MockDMNService.return_value
        mock_dmn.evaluate.return_value = {
            'penaltyAmount': 100.0,
            'interestAmount': 50.0,
            'totalAmount': 5150.0,
            'breakdown': {
                'days_overdue': 30,
                'penalty_rate': 0.02,
                'interest_rate_per_month': 0.01,
                'interest_days': 30
            }
        }

        worker = ApplyPenaltiesWorker()
        due_date = datetime.now(timezone.utc) - timedelta(days=30)

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "principal_amount": 5000.0,
            "currency": "BRL",
            "days_overdue": 30,
            "original_due_date": due_date.isoformat(),
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["collection_case_id"] == "CC-12345"
        assert result.variables["principal_amount"] == 5000.0
        assert result.variables["penalty_amount"] == 100.0
        assert result.variables["interest_amount"] == 50.0
        assert result.variables["total_amount"] == 5150.0
        assert "penalty_breakdown" in result.variables

    @patch('healthcare_platform.revenue_cycle.collection.workers.apply_penalties_worker.get_required_tenant', return_value='test-tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.apply_penalties_worker.FederatedDMNService')
    async def test_penalty_breakdown_included(self, MockDMNService, mock_tenant):
        """Testa inclusão de breakdown detalhado de multas."""
        mock_dmn = MockDMNService.return_value
        mock_dmn.evaluate.return_value = {
            'penaltyAmount': 200.0,
            'interestAmount': 150.0,
            'totalAmount': 10350.0,
            'breakdown': {
                'days_overdue': 60,
                'penalty_rate': 0.02,
                'interest_rate_per_month': 0.01,
                'interest_days': 60
            }
        }

        worker = ApplyPenaltiesWorker()
        due_date = datetime.now(timezone.utc) - timedelta(days=60)

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "principal_amount": 10000.0,
            "currency": "BRL",
            "days_overdue": 60,
            "original_due_date": due_date.isoformat(),
        }

        result = await worker.execute(job)

        assert result.success
        breakdown = result.variables["penalty_breakdown"]
        assert "days_overdue" in breakdown
        assert "penalty_rate" in breakdown
        assert "interest_rate_per_month" in breakdown
        assert "interest_days" in breakdown
        assert breakdown["days_overdue"] == 60

    @patch('healthcare_platform.revenue_cycle.collection.workers.apply_penalties_worker.get_required_tenant', return_value='test-tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.apply_penalties_worker.FederatedDMNService')
    async def test_custom_penalty_rate(self, MockDMNService, mock_tenant):
        """Testa aplicação de taxa de multa customizada."""
        mock_dmn = MockDMNService.return_value
        mock_dmn.evaluate.return_value = {
            'penaltyAmount': 500.0,
            'interestAmount': 100.0,
            'totalAmount': 10600.0,
            'breakdown': {
                'days_overdue': 30,
                'penalty_rate': 0.05,
                'interest_rate_per_month': 0.015,
                'interest_days': 30
            }
        }

        worker = ApplyPenaltiesWorker()
        due_date = datetime.now(timezone.utc) - timedelta(days=30)

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "principal_amount": 10000.0,
            "currency": "BRL",
            "days_overdue": 30,
            "original_due_date": due_date.isoformat(),
            "penalty_rate": 0.05,
            "interest_rate_per_month": 0.015,
        }

        result = await worker.execute(job)

        assert result.success
        # Verify DMN was called with custom rates
        assert mock_dmn.evaluate.called

    @patch('healthcare_platform.revenue_cycle.collection.workers.apply_penalties_worker.get_required_tenant', return_value='test-tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.apply_penalties_worker.FederatedDMNService')
    async def test_zero_penalties_for_same_day(self, MockDMNService, mock_tenant):
        """Testa que não há multas para pagamento no dia do vencimento."""
        mock_dmn = MockDMNService.return_value
        mock_dmn.evaluate.return_value = {
            'penaltyAmount': 0.0,
            'interestAmount': 0.0,
            'totalAmount': 5000.0,
            'breakdown': {
                'days_overdue': 0,
                'penalty_rate': 0.02,
                'interest_rate_per_month': 0.01,
                'interest_days': 0
            }
        }

        worker = ApplyPenaltiesWorker()
        due_date = datetime.now(timezone.utc)

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "principal_amount": 5000.0,
            "currency": "BRL",
            "days_overdue": 0,
            "original_due_date": due_date.isoformat(),
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["penalty_amount"] == 0.0
        assert result.variables["interest_amount"] == 0.0
        assert result.variables["total_amount"] == 5000.0

    @patch('healthcare_platform.revenue_cycle.collection.workers.apply_penalties_worker.get_required_tenant', return_value='test-tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.apply_penalties_worker.FederatedDMNService')
    async def test_different_currency(self, MockDMNService, mock_tenant):
        """Testa suporte a diferentes moedas."""
        mock_dmn = MockDMNService.return_value
        mock_dmn.evaluate.return_value = {
            'penaltyAmount': 20.0,
            'interestAmount': 10.0,
            'totalAmount': 1030.0,
            'breakdown': {
                'days_overdue': 15,
                'penalty_rate': 0.02,
                'interest_rate_per_month': 0.01,
                'interest_days': 15
            }
        }

        worker = ApplyPenaltiesWorker()
        due_date = datetime.now(timezone.utc) - timedelta(days=15)

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "principal_amount": 1000.0,
            "currency": "USD",
            "days_overdue": 15,
            "original_due_date": due_date.isoformat(),
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["currency"] == "USD"
