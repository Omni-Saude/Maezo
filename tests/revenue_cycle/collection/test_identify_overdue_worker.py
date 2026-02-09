from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from platform.revenue_cycle.collection.workers.identify_overdue_worker import (
    IdentifyOverdueWorker,
)


@pytest.mark.asyncio
class TestIdentifyOverdueWorker:
    """Testes para IdentifyOverdueWorker."""

    async def test_identify_overdue_claim_creates_collection_case(self):
        """Testa criação de caso de cobrança para claim vencido."""
        worker = IdentifyOverdueWorker()

        # Claim vencido há 15 dias
        due_date = datetime.now(timezone.utc) - timedelta(days=15)

        task_vars = {
            "claim_id": "CLM-12345",
            "amount_due": 5000.0,
            "currency": "BRL",
            "due_date": due_date.isoformat(),
            "payer_id": "ORG-001",
            "patient_id": "PAT-001",
            "facility_id": "FAC-001",
        }

        result = await worker.execute(task_vars)

        assert result["collection_case_id"] == "CC-CLM-12345"
        assert result["days_overdue"] == 15
        assert result["amount_due"] == 5000.0
        assert result["status"] == "overdue"
        assert "created_at" in result

    async def test_not_overdue_claim_returns_null_case(self):
        """Testa que claim não vencido não gera caso de cobrança."""
        worker = IdentifyOverdueWorker()

        # Claim vence em 10 dias
        due_date = datetime.now(timezone.utc) + timedelta(days=10)

        task_vars = {
            "claim_id": "CLM-12345",
            "amount_due": 5000.0,
            "currency": "BRL",
            "due_date": due_date.isoformat(),
            "payer_id": "ORG-001",
            "patient_id": "PAT-001",
            "facility_id": "FAC-001",
        }

        result = await worker.execute(task_vars)

        assert result["collection_case_id"] is None
        assert result["days_overdue"] == -10
        assert result["status"] == "not_overdue"

    async def test_due_today_not_overdue(self):
        """Testa que claim com vencimento hoje não é considerado vencido."""
        worker = IdentifyOverdueWorker()

        # Vence hoje
        due_date = datetime.now(timezone.utc)

        task_vars = {
            "claim_id": "CLM-12345",
            "amount_due": 5000.0,
            "currency": "BRL",
            "due_date": due_date.isoformat(),
            "payer_id": "ORG-001",
            "patient_id": "PAT-001",
            "facility_id": "FAC-001",
        }

        result = await worker.execute(task_vars)

        assert result["collection_case_id"] is None
        assert result["days_overdue"] == 0
        assert result["status"] == "not_overdue"

    async def test_handles_different_currency(self):
        """Testa suporte a diferentes moedas."""
        worker = IdentifyOverdueWorker()

        due_date = datetime.now(timezone.utc) - timedelta(days=5)

        task_vars = {
            "claim_id": "CLM-12345",
            "amount_due": 1000.0,
            "currency": "USD",
            "due_date": due_date.isoformat(),
            "payer_id": "ORG-001",
            "patient_id": "PAT-001",
            "facility_id": "FAC-001",
        }

        result = await worker.execute(task_vars)

        assert result["currency"] == "USD"
        assert result["status"] == "overdue"
