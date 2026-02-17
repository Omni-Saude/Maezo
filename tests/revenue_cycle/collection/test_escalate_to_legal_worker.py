from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.enums import CollectionAction, CollectionStatus
from healthcare_platform.revenue_cycle.collection.workers.escalate_to_legal_worker import (
    EscalateToLegalWorker,
)


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.escalate_to_legal_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.escalate_to_legal_worker.FederatedDMNService")
class TestEscalateToLegalWorker:
    """Testes para EscalateToLegalWorker."""

    async def test_escalate_for_days_over_threshold(self, mock_dmn_service_cls, mock_tenant):
        """Testa escalação para casos com mais de 180 dias vencidos."""
        mock_tenant.return_value = "tenant-1"
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {
            "shouldEscalate": True,
            "escalationReason": "Mais de 180 dias vencidos",
        }
        mock_dmn_service_cls.return_value = mock_dmn

        worker = EscalateToLegalWorker()
        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "amount_due": 5000.0,
            "currency": "BRL",
            "days_overdue": 200,
            "patient_name": "João Silva",
            "patient_cpf": "123.456.789-00",
            "claim_id": "CLM-12345",
            "collection_attempts": 5,
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["escalated"] is True
        assert result.variables["legal_case_id"].startswith("LEGAL-")
        assert result.variables["new_status"] == CollectionStatus.LEGAL.value
        assert result.variables["action_taken"] == CollectionAction.LEGAL_ESCALATION.value

    async def test_escalate_for_amount_over_threshold(self, mock_dmn_service_cls, mock_tenant):
        """Testa escalação para valores acima de R$50.000."""
        mock_tenant.return_value = "tenant-1"
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {
            "shouldEscalate": True,
            "escalationReason": "Valor acima de R$ 50.000",
        }
        mock_dmn_service_cls.return_value = mock_dmn

        worker = EscalateToLegalWorker()
        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "amount_due": 75000.0,
            "currency": "BRL",
            "days_overdue": 60,
            "patient_name": "Maria Santos",
            "patient_cpf": "987.654.321-00",
            "claim_id": "CLM-67890",
            "collection_attempts": 3,
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["escalated"] is True

    async def test_no_escalation_below_thresholds(self, mock_dmn_service_cls, mock_tenant):
        """Testa que não escalona quando abaixo dos limites."""
        mock_tenant.return_value = "tenant-1"
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {
            "shouldEscalate": False,
            "escalationReason": "Não atende critérios",
        }
        mock_dmn_service_cls.return_value = mock_dmn

        worker = EscalateToLegalWorker()
        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "amount_due": 10000.0,
            "currency": "BRL",
            "days_overdue": 90,
            "patient_name": "Pedro Costa",
            "patient_cpf": "111.222.333-44",
            "claim_id": "CLM-11111",
            "collection_attempts": 2,
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["escalated"] is False
        assert result.variables["legal_case_id"] is None

    async def test_explicit_reason_forces_escalation(self, mock_dmn_service_cls, mock_tenant):
        """Testa que motivo explícito força escalação independente de limites."""
        mock_tenant.return_value = "tenant-1"
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {
            "shouldEscalate": True,
            "escalationReason": "Paciente não responde a tentativas de contato",
        }
        mock_dmn_service_cls.return_value = mock_dmn

        worker = EscalateToLegalWorker()
        job = MagicMock()
        job.variables = {
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

        result = await worker.execute(job)

        assert result.success
        assert result.variables["escalated"] is True
        assert result.variables["escalation_reason"] == "Paciente não responde a tentativas de contato"

    async def test_legal_case_data_complete(self, mock_dmn_service_cls, mock_tenant):
        """Testa que dados do caso jurídico estão completos."""
        mock_tenant.return_value = "tenant-1"
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {
            "shouldEscalate": True,
            "escalationReason": "High amount and overdue",
        }
        mock_dmn_service_cls.return_value = mock_dmn

        worker = EscalateToLegalWorker()
        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "amount_due": 100000.0,
            "currency": "BRL",
            "days_overdue": 250,
            "patient_name": "Carlos Souza",
            "patient_cpf": "999.888.777-66",
            "claim_id": "CLM-99999",
            "collection_attempts": 10,
        }

        result = await worker.execute(job)

        assert result.success
        legal_data = result.variables["legal_case_data"]
        assert legal_data["legal_case_id"] == result.variables["legal_case_id"]
        assert legal_data["collection_case_id"] == "CC-12345"
        assert legal_data["patient_name"] == "Carlos Souza"
        assert legal_data["patient_cpf"] == "999.888.777-66"
        assert legal_data["claim_id"] == "CLM-99999"
        assert legal_data["amount_due"] == 100000.0
        assert legal_data["days_overdue"] == 250
        assert legal_data["collection_attempts"] == 10
        assert legal_data["status"] == "pending_review"
