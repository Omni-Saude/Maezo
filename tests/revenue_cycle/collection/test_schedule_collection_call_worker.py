from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.schedule_collection_call_worker import (
    ScheduleCollectionCallWorker,
)


@pytest.mark.asyncio
class TestScheduleCollectionCallWorker:
    """Testes para ScheduleCollectionCallWorker."""

    @patch('healthcare_platform.revenue_cycle.collection.workers.schedule_collection_call_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.schedule_collection_call_worker.FederatedDMNService')
    async def test_schedule_call_creates_human_task(self, mock_dmn_class, mock_tenant):
        """Testa criação de tarefa humana para ligação de cobrança."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn
        mock_dmn.evaluate.return_value = {
            'strategy': 'phone_call'
        }

        worker = ScheduleCollectionCallWorker()

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "patient_name": "João Silva",
            "patient_phone": "+5511987654321",
            "amount_due": 5000.0,
            "currency": "BRL",
            "days_overdue": 30,
            "priority": "HIGH",
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["task_type"] == "human_task"
        assert result.variables["status"] == "pending"
        assert result.variables["collection_case_id"] == "CC-12345"
        assert result.variables["task_id"].startswith("CALL-")
        assert "created_at" in result.variables

    @patch('healthcare_platform.revenue_cycle.collection.workers.schedule_collection_call_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.schedule_collection_call_worker.FederatedDMNService')
    async def test_default_assignment_to_collection_team(self, mock_dmn_class, mock_tenant):
        """Testa atribuição padrão para equipe de cobrança."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn
        mock_dmn.evaluate.return_value = {
            'strategy': 'phone_call'
        }

        worker = ScheduleCollectionCallWorker()

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "patient_name": "Ana Lima",
            "patient_phone": "+5511987654321",
            "amount_due": 2500.0,
            "currency": "BRL",
            "days_overdue": 20,
            "priority": "MEDIUM",
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["assigned_to"] == "collection_team"

    @patch('healthcare_platform.revenue_cycle.collection.workers.schedule_collection_call_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.schedule_collection_call_worker.FederatedDMNService')
    async def test_custom_assignment(self, mock_dmn_class, mock_tenant):
        """Testa atribuição customizada."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn
        mock_dmn.evaluate.return_value = {
            'strategy': 'phone_call'
        }

        worker = ScheduleCollectionCallWorker()

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "patient_name": "Carlos Souza",
            "patient_phone": "+5511987654321",
            "amount_due": 7500.0,
            "currency": "BRL",
            "days_overdue": 45,
            "priority": "HIGH",
            "assigned_to": "senior_collector_001",
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["assigned_to"] == "senior_collector_001"
