from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.enums import CollectionPriority
from healthcare_platform.revenue_cycle.collection.workers.prioritize_collection_worker import (
    PrioritizeCollectionWorker,
)


@pytest.mark.asyncio
class TestPrioritizeCollectionWorker:
    """Testes para PrioritizeCollectionWorker."""

    @patch('healthcare_platform.revenue_cycle.collection.workers.prioritize_collection_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.prioritize_collection_worker.FederatedDMNService')
    async def test_critical_priority_high_amount_and_days(self, mock_dmn_class, mock_tenant):
        """Testa prioridade CRITICAL para alto valor + muitos dias vencidos."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn
        mock_dmn.evaluate.return_value = {
            'priority': CollectionPriority.CRITICAL.value,
            'priorityScore': 90.0,
            'breakdown': {
                'amount_score': 85.0,
                'days_overdue_score': 90.0,
                'payer_history_score': 80.0,
                'claim_type_score': 95.0
            }
        }

        worker = PrioritizeCollectionWorker()

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "amount_due": 15000.0,
            "days_overdue": 120,
            "payer_default_rate": 0.8,
            "claim_type": "emergency",
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["priority"] == CollectionPriority.CRITICAL.value
        assert result.variables["priority_score"] >= 80
        assert "score_breakdown" in result.variables
        assert result.variables["score_breakdown"]["amount_score"] > 0

    @patch('healthcare_platform.revenue_cycle.collection.workers.prioritize_collection_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.prioritize_collection_worker.FederatedDMNService')
    async def test_low_priority_small_amount_few_days(self, mock_dmn_class, mock_tenant):
        """Testa prioridade LOW para baixo valor + poucos dias vencidos."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn
        mock_dmn.evaluate.return_value = {
            'priority': CollectionPriority.LOW.value,
            'priorityScore': 30.0,
            'breakdown': {}
        }

        worker = PrioritizeCollectionWorker()

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "amount_due": 500.0,
            "days_overdue": 10,
            "payer_default_rate": 0.1,
            "claim_type": "outpatient",
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["priority"] == CollectionPriority.LOW.value
        assert result.variables["priority_score"] < 40

    @patch('healthcare_platform.revenue_cycle.collection.workers.prioritize_collection_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.prioritize_collection_worker.FederatedDMNService')
    async def test_emergency_claim_increases_priority(self, mock_dmn_class, mock_tenant):
        """Testa que tipo 'emergency' aumenta prioridade."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn

        worker = PrioritizeCollectionWorker()

        # Emergency claim
        mock_dmn.evaluate.return_value = {
            'priority': 'HIGH',
            'priorityScore': 75.0,
            'breakdown': {}
        }

        job_emergency = MagicMock()
        job_emergency.variables = {
            "collection_case_id": "CC-12345",
            "amount_due": 2000.0,
            "days_overdue": 30,
            "payer_default_rate": 0.3,
            "claim_type": "emergency",
        }

        result_emergency = await worker.execute(job_emergency)

        # Outpatient claim
        mock_dmn.evaluate.return_value = {
            'priority': 'MEDIUM',
            'priorityScore': 50.0,
            'breakdown': {}
        }

        job_outpatient = MagicMock()
        job_outpatient.variables = {
            "collection_case_id": "CC-67890",
            "amount_due": 2000.0,
            "days_overdue": 30,
            "payer_default_rate": 0.3,
            "claim_type": "outpatient",
        }

        result_outpatient = await worker.execute(job_outpatient)

        assert result_emergency.variables["priority_score"] > result_outpatient.variables["priority_score"]

    @patch('healthcare_platform.revenue_cycle.collection.workers.prioritize_collection_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.prioritize_collection_worker.FederatedDMNService')
    async def test_score_breakdown_contains_all_factors(self, mock_dmn_class, mock_tenant):
        """Testa que breakdown contém todos os fatores de score."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn
        mock_dmn.evaluate.return_value = {
            'priority': 'MEDIUM',
            'priorityScore': 60.0,
            'breakdown': {
                'amount_score': 50.0,
                'days_overdue_score': 60.0,
                'payer_history_score': 55.0,
                'claim_type_score': 65.0
            }
        }

        worker = PrioritizeCollectionWorker()

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "amount_due": 5000.0,
            "days_overdue": 60,
            "payer_default_rate": 0.5,
            "claim_type": "inpatient",
        }

        result = await worker.execute(job)

        breakdown = result.variables["score_breakdown"]
        assert "amount_score" in breakdown
        assert "days_overdue_score" in breakdown
        assert "payer_history_score" in breakdown
        assert "claim_type_score" in breakdown
