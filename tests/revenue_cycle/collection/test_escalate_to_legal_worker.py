from __future__ import annotations

import pytest

from healthcare_platform.revenue_cycle.collection.enums import CollectionAction, CollectionStatus
from healthcare_platform.revenue_cycle.collection.workers.escalate_to_legal_worker import (
    EscalateToLegalWorker,
)


@pytest.mark.asyncio
class TestEscalateToLegalWorker:
    """Testes para EscalateToLegalWorker."""

    async def test_escalate_for_days_over_threshold(self):
        """Testa escalação para casos com mais de 180 dias vencidos."""
        worker = EscalateToLegalWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "amount_due": 5000.0,
            "currency": "BRL",
            "days_overdue": 200,
            "patient_name": "João Silva",
            "patient_cpf": "123.456.789-00",
            "claim_id": "CLM-12345",
            "collection_attempts": 5,
        }

        result = await worker.execute(task_vars)

        assert result["escalated"] is True
        assert result["legal_case_id"].startswith("LEGAL-")
        assert result["new_status"] == CollectionStatus.LEGAL.value
        assert result["action_taken"] == CollectionAction.ESCALATE_TO_LEGAL.value
        assert "180 dias" in result["escalation_reason"]

    async def test_escalate_for_amount_over_threshold(self):
        """Testa escalação para valores acima de R$50.000."""
        worker = EscalateToLegalWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "amount_due": 75000.0,
            "currency": "BRL",
            "days_overdue": 60,
            "patient_name": "Maria Santos",
            "patient_cpf": "987.654.321-00",
            "claim_id": "CLM-67890",
            "collection_attempts": 3,
        }

        result = await worker.execute(task_vars)

        assert result["escalated"] is True
        assert "50" in result["escalation_reason"]

    async def test_no_escalation_below_thresholds(self):
        """Testa que não escalona quando abaixo dos limites."""
        worker = EscalateToLegalWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "amount_due": 10000.0,
            "currency": "BRL",
            "days_overdue": 90,
            "patient_name": "Pedro Costa",
            "patient_cpf": "111.222.333-44",
            "claim_id": "CLM-11111",
            "collection_attempts": 2,
        }

        result = await worker.execute(task_vars)

        assert result["escalated"] is False
        assert result["legal_case_id"] is None
        assert "não atende critérios" in result["escalation_reason"]

    async def test_explicit_reason_forces_escalation(self):
        """Testa que motivo explícito força escalação independente de limites."""
        worker = EscalateToLegalWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "amount_due": 2000.0,
            "currency": "BRL",
            "days_overdue": 30,
            "patient_name": "Ana Lima",
            "patient_cpf": "555.666.777-88",
            "claim_id": "CLM-22222",
            "collection_attempts": 1,
            "reason": "Paciente não responde a tentativas de contato",
        }

        result = await worker.execute(task_vars)

        assert result["escalated"] is True
        assert result["escalation_reason"] == "Paciente não responde a tentativas de contato"

    async def test_legal_case_data_complete(self):
        """Testa que dados do caso jurídico estão completos."""
        worker = EscalateToLegalWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "amount_due": 100000.0,
            "currency": "BRL",
            "days_overdue": 250,
            "patient_name": "Carlos Souza",
            "patient_cpf": "999.888.777-66",
            "claim_id": "CLM-99999",
            "collection_attempts": 10,
        }

        result = await worker.execute(task_vars)

        legal_data = result["legal_case_data"]
        assert legal_data["legal_case_id"] == result["legal_case_id"]
        assert legal_data["collection_case_id"] == "CC-12345"
        assert legal_data["patient_name"] == "Carlos Souza"
        assert legal_data["patient_cpf"] == "999.888.777-66"
        assert legal_data["claim_id"] == "CLM-99999"
        assert legal_data["amount_due"] == 100000.0
        assert legal_data["days_overdue"] == 250
        assert legal_data["collection_attempts"] == 10
        assert legal_data["status"] == "pending_review"

    async def test_threshold_constants(self):
        """Testa que constantes de threshold estão corretas."""
        worker = EscalateToLegalWorker()

        assert worker.ESCALATION_THRESHOLD_DAYS == 180
        assert worker.ESCALATION_THRESHOLD_AMOUNT == 50000.0

    async def test_exactly_at_day_threshold(self):
        """Testa escalação quando exatamente no limite de dias (180)."""
        worker = EscalateToLegalWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "amount_due": 5000.0,
            "currency": "BRL",
            "days_overdue": 180,
            "patient_name": "José Santos",
            "patient_cpf": "123.123.123-12",
            "claim_id": "CLM-33333",
            "collection_attempts": 4,
        }

        result = await worker.execute(task_vars)

        assert result["escalated"] is True

    async def test_exactly_at_amount_threshold(self):
        """Testa escalação quando exatamente no limite de valor (R$50.000)."""
        worker = EscalateToLegalWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "amount_due": 50000.0,
            "currency": "BRL",
            "days_overdue": 60,
            "patient_name": "Paula Lima",
            "patient_cpf": "321.321.321-21",
            "claim_id": "CLM-44444",
            "collection_attempts": 3,
        }

        result = await worker.execute(task_vars)

        assert result["escalated"] is True
