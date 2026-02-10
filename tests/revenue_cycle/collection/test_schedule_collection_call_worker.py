from __future__ import annotations

import pytest

from healthcare_platform.revenue_cycle.collection.workers.schedule_collection_call_worker import (
    ScheduleCollectionCallWorker,
)


@pytest.mark.asyncio
class TestScheduleCollectionCallWorker:
    """Testes para ScheduleCollectionCallWorker."""

    async def test_schedule_call_creates_human_task(self):
        """Testa criação de tarefa humana para ligação de cobrança."""
        worker = ScheduleCollectionCallWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "patient_name": "João Silva",
            "patient_phone": "+5511987654321",
            "amount_due": 5000.0,
            "currency": "BRL",
            "days_overdue": 30,
            "priority": "HIGH",
        }

        result = await worker.execute(task_vars)

        assert result["task_type"] == "human_task"
        assert result["status"] == "pending"
        assert result["collection_case_id"] == "CC-12345"
        assert result["task_id"].startswith("CALL-")
        assert "created_at" in result
        assert "due_by" in result

    async def test_critical_priority_shorter_sla(self):
        """Testa que prioridade CRITICAL tem SLA mais curto."""
        worker = ScheduleCollectionCallWorker()

        task_vars_critical = {
            "collection_case_id": "CC-12345",
            "patient_name": "Maria Santos",
            "patient_phone": "+5511987654321",
            "amount_due": 10000.0,
            "currency": "BRL",
            "days_overdue": 100,
            "priority": "CRITICAL",
        }

        task_vars_low = {
            "collection_case_id": "CC-67890",
            "patient_name": "Pedro Costa",
            "patient_phone": "+5511987654322",
            "amount_due": 1000.0,
            "currency": "BRL",
            "days_overdue": 10,
            "priority": "LOW",
        }

        result_critical = await worker.execute(task_vars_critical)
        result_low = await worker.execute(task_vars_low)

        # Critical should have earlier due date
        from datetime import datetime

        due_critical = datetime.fromisoformat(result_critical["due_by"])
        due_low = datetime.fromisoformat(result_low["due_by"])
        assert due_critical < due_low

    async def test_default_assignment_to_collection_team(self):
        """Testa atribuição padrão para equipe de cobrança."""
        worker = ScheduleCollectionCallWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "patient_name": "Ana Lima",
            "patient_phone": "+5511987654321",
            "amount_due": 2500.0,
            "currency": "BRL",
            "days_overdue": 20,
            "priority": "MEDIUM",
        }

        result = await worker.execute(task_vars)

        assert result["assigned_to"] == "collection_team"

    async def test_custom_assignment(self):
        """Testa atribuição customizada."""
        worker = ScheduleCollectionCallWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "patient_name": "Carlos Souza",
            "patient_phone": "+5511987654321",
            "amount_due": 7500.0,
            "currency": "BRL",
            "days_overdue": 45,
            "priority": "HIGH",
            "assigned_to": "senior_collector_001",
        }

        result = await worker.execute(task_vars)

        assert result["assigned_to"] == "senior_collector_001"

    async def test_very_overdue_accelerated_sla(self):
        """Testa que casos muito vencidos (>90 dias) têm SLA acelerado."""
        worker = ScheduleCollectionCallWorker()

        task_vars_very_overdue = {
            "collection_case_id": "CC-12345",
            "patient_name": "José Santos",
            "patient_phone": "+5511987654321",
            "amount_due": 5000.0,
            "currency": "BRL",
            "days_overdue": 120,
            "priority": "MEDIUM",
        }

        task_vars_normal = {
            "collection_case_id": "CC-67890",
            "patient_name": "Paulo Lima",
            "patient_phone": "+5511987654322",
            "amount_due": 5000.0,
            "currency": "BRL",
            "days_overdue": 20,
            "priority": "MEDIUM",
        }

        result_very_overdue = await worker.execute(task_vars_very_overdue)
        result_normal = await worker.execute(task_vars_normal)

        from datetime import datetime

        due_very_overdue = datetime.fromisoformat(result_very_overdue["due_by"])
        due_normal = datetime.fromisoformat(result_normal["due_by"])
        assert due_very_overdue < due_normal
