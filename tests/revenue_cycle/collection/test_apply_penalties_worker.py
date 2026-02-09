from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from platform.revenue_cycle.collection.workers.apply_penalties_worker import (
    ApplyPenaltiesWorker,
)


@pytest.mark.asyncio
class TestApplyPenaltiesWorker:
    """Testes para ApplyPenaltiesWorker."""

    @patch("platform.revenue_cycle.collection.workers.apply_penalties_worker.calculate_penalty")
    async def test_apply_penalties_success(self, mock_calculate_penalty):
        """Testa aplicação bem-sucedida de multas e juros."""
        mock_calculate_penalty.return_value = {
            "penalty": 100.0,
            "interest": 50.0,
            "penalty_rate": 0.02,
            "interest_rate_per_month": 0.01,
            "interest_days": 30,
        }

        worker = ApplyPenaltiesWorker()

        due_date = datetime.now(timezone.utc) - timedelta(days=30)

        task_vars = {
            "collection_case_id": "CC-12345",
            "principal_amount": 5000.0,
            "currency": "BRL",
            "days_overdue": 30,
            "original_due_date": due_date.isoformat(),
        }

        result = await worker.execute(task_vars)

        assert result["collection_case_id"] == "CC-12345"
        assert result["principal_amount"] == 5000.0
        assert result["penalty_amount"] == 100.0
        assert result["interest_amount"] == 50.0
        assert result["total_amount"] == 5150.0
        assert "penalty_breakdown" in result

    @patch("platform.revenue_cycle.collection.workers.apply_penalties_worker.calculate_penalty")
    async def test_penalty_breakdown_included(self, mock_calculate_penalty):
        """Testa inclusão de breakdown detalhado de multas."""
        mock_calculate_penalty.return_value = {
            "penalty": 200.0,
            "interest": 150.0,
            "penalty_rate": 0.02,
            "interest_rate_per_month": 0.01,
            "interest_days": 60,
        }

        worker = ApplyPenaltiesWorker()

        due_date = datetime.now(timezone.utc) - timedelta(days=60)

        task_vars = {
            "collection_case_id": "CC-12345",
            "principal_amount": 10000.0,
            "currency": "BRL",
            "days_overdue": 60,
            "original_due_date": due_date.isoformat(),
        }

        result = await worker.execute(task_vars)

        breakdown = result["penalty_breakdown"]
        assert "days_overdue" in breakdown
        assert "penalty_rate" in breakdown
        assert "interest_rate_per_month" in breakdown
        assert "interest_days" in breakdown
        assert breakdown["days_overdue"] == 60

    @patch("platform.revenue_cycle.collection.workers.apply_penalties_worker.calculate_penalty")
    async def test_custom_penalty_rate(self, mock_calculate_penalty):
        """Testa aplicação de taxa de multa customizada."""
        mock_calculate_penalty.return_value = {
            "penalty": 500.0,
            "interest": 100.0,
            "penalty_rate": 0.05,
            "interest_rate_per_month": 0.015,
            "interest_days": 30,
        }

        worker = ApplyPenaltiesWorker()

        due_date = datetime.now(timezone.utc) - timedelta(days=30)

        task_vars = {
            "collection_case_id": "CC-12345",
            "principal_amount": 10000.0,
            "currency": "BRL",
            "days_overdue": 30,
            "original_due_date": due_date.isoformat(),
            "penalty_rate": 0.05,
            "interest_rate_per_month": 0.015,
        }

        result = await worker.execute(task_vars)

        # Verify calculate_penalty was called with custom rates
        call_kwargs = mock_calculate_penalty.call_args.kwargs
        assert call_kwargs["penalty_rate"] == 0.05
        assert call_kwargs["interest_rate_per_month"] == 0.015

    @patch("platform.revenue_cycle.collection.workers.apply_penalties_worker.calculate_penalty")
    async def test_zero_penalties_for_same_day(self, mock_calculate_penalty):
        """Testa que não há multas para pagamento no dia do vencimento."""
        mock_calculate_penalty.return_value = {
            "penalty": 0.0,
            "interest": 0.0,
            "penalty_rate": 0.02,
            "interest_rate_per_month": 0.01,
            "interest_days": 0,
        }

        worker = ApplyPenaltiesWorker()

        due_date = datetime.now(timezone.utc)

        task_vars = {
            "collection_case_id": "CC-12345",
            "principal_amount": 5000.0,
            "currency": "BRL",
            "days_overdue": 0,
            "original_due_date": due_date.isoformat(),
        }

        result = await worker.execute(task_vars)

        assert result["penalty_amount"] == 0.0
        assert result["interest_amount"] == 0.0
        assert result["total_amount"] == 5000.0

    @patch("platform.revenue_cycle.collection.workers.apply_penalties_worker.calculate_penalty")
    async def test_different_currency(self, mock_calculate_penalty):
        """Testa suporte a diferentes moedas."""
        mock_calculate_penalty.return_value = {
            "penalty": 20.0,
            "interest": 10.0,
            "penalty_rate": 0.02,
            "interest_rate_per_month": 0.01,
            "interest_days": 15,
        }

        worker = ApplyPenaltiesWorker()

        due_date = datetime.now(timezone.utc) - timedelta(days=15)

        task_vars = {
            "collection_case_id": "CC-12345",
            "principal_amount": 1000.0,
            "currency": "USD",
            "days_overdue": 15,
            "original_due_date": due_date.isoformat(),
        }

        result = await worker.execute(task_vars)

        assert result["currency"] == "USD"
        # Verify Money object was created with correct currency
        call_args = mock_calculate_penalty.call_args
        money_arg = call_args.kwargs["principal_amount"]
        assert money_arg.currency == "USD"
