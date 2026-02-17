from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.exceptions import PaymentPlanError
from healthcare_platform.revenue_cycle.collection.workers.negotiate_payment_plan_worker import (
    NegotiatePaymentPlanWorker,
)


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.negotiate_payment_plan_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.negotiate_payment_plan_worker.FederatedDMNService')
class TestNegotiatePaymentPlanWorker:
    """Testes para NegotiatePaymentPlanWorker."""

    async def test_create_payment_plan_success(self, mock_dmn_service, mock_tenant):
        """Testa criação bem-sucedida de plano de pagamento."""
        mock_tenant.return_value = 'test_tenant'
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {'eligible': True, 'reason': 'approved'}
        mock_dmn_service.return_value = mock_dmn

        worker = NegotiatePaymentPlanWorker()
        worker.dmn_service = mock_dmn

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "amount_due": 6000.0,
            "currency": "BRL",
            "num_installments": 6,
        }

        result = await worker.execute(job)

        assert result.success is True
        assert result.variables["payment_plan_id"].startswith("PP-")
        assert result.variables["num_installments"] == 6
        assert result.variables["installment_amount"] == 1000.0
        assert result.variables["total_amount"] == 6000.0
        assert len(result.variables["schedule"]) == 6

    async def test_payment_plan_with_interest(self, mock_dmn_service, mock_tenant):
        """Testa plano de pagamento com juros."""
        mock_tenant.return_value = 'test_tenant'
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {'eligible': True, 'reason': 'approved'}
        mock_dmn_service.return_value = mock_dmn

        worker = NegotiatePaymentPlanWorker()
        worker.dmn_service = mock_dmn

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "amount_due": 10000.0,
            "currency": "BRL",
            "num_installments": 10,
            "interest_rate": 0.05,  # 5%
        }

        result = await worker.execute(job)

        assert result.success is True
        # Total should include interest
        assert result.variables["total_amount"] == 10500.0  # 10000 * 1.05
        assert result.variables["installment_amount"] == 1050.0

    async def test_max_installments_validation(self, mock_dmn_service, mock_tenant):
        """Testa que número máximo de parcelas é respeitado."""
        mock_tenant.return_value = 'test_tenant'
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {
            'eligible': False,
            'reason': 'Número de parcelas não pode exceder 12'
        }
        mock_dmn_service.return_value = mock_dmn

        worker = NegotiatePaymentPlanWorker()
        worker.dmn_service = mock_dmn

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "amount_due": 12000.0,
            "currency": "BRL",
            "num_installments": 15,  # Exceeds MAX_INSTALLMENTS (12)
        }

        result = await worker.execute(job)

        # Worker catches PaymentPlanError and returns BPMN error
        assert result.success is False
        assert result.error_code is not None
        assert "não pode exceder" in result.error_message

    async def test_minimum_installment_validation(self, mock_dmn_service, mock_tenant):
        """Testa validação de valor mínimo de parcela (R$100)."""
        mock_tenant.return_value = 'test_tenant'
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {
            'eligible': False,
            'reason': 'Valor da parcela menor que o mínimo permitido (R$100)'
        }
        mock_dmn_service.return_value = mock_dmn

        worker = NegotiatePaymentPlanWorker()
        worker.dmn_service = mock_dmn

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "amount_due": 500.0,
            "currency": "BRL",
            "num_installments": 10,  # Would result in R$50/installment
        }

        result = await worker.execute(job)

        # Worker catches PaymentPlanError and returns BPMN error
        assert result.success is False
        assert result.error_code is not None
        assert "menor que o mínimo" in result.error_message

    async def test_schedule_monthly_intervals(self, mock_dmn_service, mock_tenant):
        """Testa que parcelas são espaçadas mensalmente (30 dias)."""
        mock_tenant.return_value = 'test_tenant'
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {'eligible': True}
        mock_dmn_service.return_value = mock_dmn

        worker = NegotiatePaymentPlanWorker()
        worker.dmn_service = mock_dmn

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "amount_due": 6000.0,
            "currency": "BRL",
            "num_installments": 6,
        }

        result = await worker.execute(job)

        assert result.success is True
        schedule = result.variables["schedule"]

        # Verify installment sequence
        for i, installment in enumerate(schedule, start=1):
            assert installment["installment_number"] == i
            assert installment["amount"] == 1000.0
            assert installment["status"] == "pending"

    async def test_single_installment_allowed(self, mock_dmn_service, mock_tenant):
        """Testa que plano de parcela única (1x) é permitido."""
        mock_tenant.return_value = 'test_tenant'
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {'eligible': True}
        mock_dmn_service.return_value = mock_dmn

        worker = NegotiatePaymentPlanWorker()
        worker.dmn_service = mock_dmn

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "amount_due": 2000.0,
            "currency": "BRL",
            "num_installments": 1,
        }

        result = await worker.execute(job)

        assert result.success is True
        assert result.variables["num_installments"] == 1
        assert result.variables["installment_amount"] == 2000.0
        assert len(result.variables["schedule"]) == 1

    async def test_zero_installments_raises_error(self, mock_dmn_service, mock_tenant):
        """Testa que zero parcelas gera erro."""
        mock_tenant.return_value = 'test_tenant'
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {'eligible': False, 'reason': 'Invalid installment count'}
        mock_dmn_service.return_value = mock_dmn

        worker = NegotiatePaymentPlanWorker()
        worker.dmn_service = mock_dmn

        job = MagicMock()
        job.variables = {
            "collection_case_id": "CC-12345",
            "amount_due": 5000.0,
            "currency": "BRL",
            "num_installments": 0,
        }

        result = await worker.execute(job)

        # Worker catches PaymentPlanError and returns BPMN error
        assert result.success is False
        assert result.error_code is not None
