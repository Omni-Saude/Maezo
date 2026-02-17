from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.write_off_bad_debt_worker import (
    WriteOffBadDebtWorker,
)


@pytest.mark.asyncio
class TestWriteOffBadDebtWorker:
    """Testes para WriteOffBadDebtWorker."""

    @patch('healthcare_platform.revenue_cycle.collection.workers.write_off_bad_debt_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.write_off_bad_debt_worker.FederatedDMNService')
    async def test_write_off_below_approval_threshold(self, mock_dmn_class, mock_tenant):
        """Testa baixa de valor abaixo do limite (R$10.000) sem necessidade de aprovação."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn
        mock_dmn.evaluate.return_value = {
            'requiresApproval': False,
            'writeOffAllowed': True
        }

        worker = WriteOffBadDebtWorker()

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "amount_due": 5000.0,
            "currency": "BRL",
            "reason": "Paciente falecido sem herdeiros",
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["amount_written_off"] == 5000.0
        assert result.variables["requires_approval"] is False
        assert result.variables["approved"] is False
        assert "written_off_at" in result.variables

    @patch('healthcare_platform.revenue_cycle.collection.workers.write_off_bad_debt_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.write_off_bad_debt_worker.FederatedDMNService')
    async def test_write_off_above_threshold_with_approval(self, mock_dmn_class, mock_tenant):
        """Testa baixa de valor acima do limite com aprovação gerencial."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn
        mock_dmn.evaluate.return_value = {
            'requiresApproval': True,
            'writeOffAllowed': True
        }

        worker = WriteOffBadDebtWorker()

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "amount_due": 25000.0,
            "currency": "BRL",
            "reason": "Devedor em recuperação judicial",
            "approved_by": "manager-001",
            "approval_reference": "APPR-2024-001",
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["amount_written_off"] == 25000.0
        assert result.variables["requires_approval"] is True
        assert result.variables["approved"] is True

    @patch('healthcare_platform.revenue_cycle.collection.workers.write_off_bad_debt_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.write_off_bad_debt_worker.FederatedDMNService')
    async def test_write_off_above_threshold_without_approval_raises_error(self, mock_dmn_class, mock_tenant):
        """Testa que valores acima do limite sem aprovação geram erro."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn
        mock_dmn.evaluate.return_value = {
            'requiresApproval': True,
            'writeOffAllowed': True
        }

        worker = WriteOffBadDebtWorker()

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "amount_due": 15000.0,
            "currency": "BRL",
            "reason": "Dívida incobrável",
        }

        result = await worker.execute(job)

        assert not result.success
        assert result.error_code == 'APPROVAL_REQUIRED'

    @patch('healthcare_platform.revenue_cycle.collection.workers.write_off_bad_debt_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.write_off_bad_debt_worker.FederatedDMNService')
    async def test_write_off_not_allowed(self, mock_dmn_class, mock_tenant):
        """Testa que baixa não permitida gera erro."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn
        mock_dmn.evaluate.return_value = {
            'requiresApproval': False,
            'writeOffAllowed': False
        }

        worker = WriteOffBadDebtWorker()

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "amount_due": 3000.0,
            "currency": "BRL",
            "reason": "Cliente ativo",
        }

        result = await worker.execute(job)

        assert not result.success
        assert result.error_code == 'WRITE_OFF_NOT_ALLOWED'

    @patch('healthcare_platform.revenue_cycle.collection.workers.write_off_bad_debt_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.write_off_bad_debt_worker.FederatedDMNService')
    async def test_write_off_reason_included(self, mock_dmn_class, mock_tenant):
        """Testa que motivo da baixa está incluído no resultado."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn
        mock_dmn.evaluate.return_value = {
            'requiresApproval': False,
            'writeOffAllowed': True
        }

        worker = WriteOffBadDebtWorker()

        reason = "Cliente desaparecido após múltiplas tentativas de contato"

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "amount_due": 2000.0,
            "currency": "BRL",
            "reason": reason,
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["write_off_reason"] == reason

    @patch('healthcare_platform.revenue_cycle.collection.workers.write_off_bad_debt_worker.get_required_tenant')
    @patch('healthcare_platform.revenue_cycle.collection.workers.write_off_bad_debt_worker.FederatedDMNService')
    async def test_large_amount_with_approval(self, mock_dmn_class, mock_tenant):
        """Testa baixa de valor muito alto com aprovação."""
        mock_tenant.return_value = 'test-tenant'
        mock_dmn = MagicMock()
        mock_dmn_class.return_value = mock_dmn
        mock_dmn.evaluate.return_value = {
            'requiresApproval': True,
            'writeOffAllowed': True
        }

        worker = WriteOffBadDebtWorker()

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "amount_due": 100000.0,
            "currency": "BRL",
            "reason": "Falência decretada - sem ativos",
            "approved_by": "cfo-001",
            "approval_reference": "BOARD-DECISION-2024-05",
        }

        result = await worker.execute(job)

        assert result.success
        assert result.variables["approved"] is True
        assert result.variables["amount_written_off"] == 100000.0
