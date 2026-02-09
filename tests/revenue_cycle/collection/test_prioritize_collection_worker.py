from __future__ import annotations

import pytest

from platform.revenue_cycle.collection.enums import CollectionPriority
from platform.revenue_cycle.collection.workers.prioritize_collection_worker import (
    PrioritizeCollectionWorker,
)


@pytest.mark.asyncio
class TestPrioritizeCollectionWorker:
    """Testes para PrioritizeCollectionWorker."""

    async def test_critical_priority_high_amount_and_days(self):
        """Testa prioridade CRITICAL para alto valor + muitos dias vencidos."""
        worker = PrioritizeCollectionWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "amount_due": 15000.0,
            "days_overdue": 120,
            "payer_default_rate": 0.8,
            "claim_type": "emergency",
        }

        result = await worker.execute(task_vars)

        assert result["priority"] == CollectionPriority.CRITICAL.value
        assert result["priority_score"] >= 80
        assert "score_breakdown" in result
        assert result["score_breakdown"]["amount_score"] > 0

    async def test_low_priority_small_amount_few_days(self):
        """Testa prioridade LOW para baixo valor + poucos dias vencidos."""
        worker = PrioritizeCollectionWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "amount_due": 500.0,
            "days_overdue": 10,
            "payer_default_rate": 0.1,
            "claim_type": "outpatient",
        }

        result = await worker.execute(task_vars)

        assert result["priority"] == CollectionPriority.LOW.value
        assert result["priority_score"] < 40

    async def test_emergency_claim_increases_priority(self):
        """Testa que tipo 'emergency' aumenta prioridade."""
        worker = PrioritizeCollectionWorker()

        task_vars_emergency = {
            "collection_case_id": "CC-12345",
            "amount_due": 2000.0,
            "days_overdue": 30,
            "payer_default_rate": 0.3,
            "claim_type": "emergency",
        }

        task_vars_outpatient = {
            "collection_case_id": "CC-67890",
            "amount_due": 2000.0,
            "days_overdue": 30,
            "payer_default_rate": 0.3,
            "claim_type": "outpatient",
        }

        result_emergency = await worker.execute(task_vars_emergency)
        result_outpatient = await worker.execute(task_vars_outpatient)

        assert result_emergency["priority_score"] > result_outpatient["priority_score"]

    async def test_score_breakdown_contains_all_factors(self):
        """Testa que breakdown contém todos os fatores de score."""
        worker = PrioritizeCollectionWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "amount_due": 5000.0,
            "days_overdue": 60,
            "payer_default_rate": 0.5,
            "claim_type": "inpatient",
        }

        result = await worker.execute(task_vars)

        breakdown = result["score_breakdown"]
        assert "amount_score" in breakdown
        assert "days_overdue_score" in breakdown
        assert "payer_history_score" in breakdown
        assert "claim_type_score" in breakdown

    async def test_amount_score_calculation(self):
        """Testa cálculo de score por valor."""
        worker = PrioritizeCollectionWorker()

        # Valor baixo
        assert worker._calculate_amount_score(500) < 30
        # Valor médio
        assert 30 <= worker._calculate_amount_score(3000) < 60
        # Valor alto
        assert worker._calculate_amount_score(15000) >= 80

    async def test_days_overdue_score_calculation(self):
        """Testa cálculo de score por dias vencidos."""
        worker = PrioritizeCollectionWorker()

        # Poucos dias
        assert worker._calculate_days_overdue_score(15) < 25
        # Médio prazo
        assert 25 <= worker._calculate_days_overdue_score(45) < 50
        # Longo prazo
        assert worker._calculate_days_overdue_score(120) >= 75
