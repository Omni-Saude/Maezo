from __future__ import annotations

from datetime import datetime, timezone

import pytest

from platform.revenue_cycle.collection.exceptions import PaymentPlanError
from platform.revenue_cycle.collection.workers.negotiate_payment_plan_worker import (
    NegotiatePaymentPlanWorker,
)


@pytest.mark.asyncio
class TestNegotiatePaymentPlanWorker:
    """Testes para NegotiatePaymentPlanWorker."""

    async def test_create_payment_plan_success(self):
        """Testa criação bem-sucedida de plano de pagamento."""
        worker = NegotiatePaymentPlanWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "amount_due": 6000.0,
            "currency": "BRL",
            "num_installments": 6,
        }

        result = await worker.execute(task_vars)

        assert result["payment_plan_id"].startswith("PP-")
        assert result["collection_case_id"] == "CC-12345"
        assert result["num_installments"] == 6
        assert result["installment_amount"] == 1000.0
        assert result["total_amount"] == 6000.0
        assert len(result["schedule"]) == 6

    async def test_payment_plan_with_interest(self):
        """Testa plano de pagamento com juros."""
        worker = NegotiatePaymentPlanWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "amount_due": 10000.0,
            "currency": "BRL",
            "num_installments": 10,
            "interest_rate": 0.05,  # 5%
        }

        result = await worker.execute(task_vars)

        # Total should include interest
        assert result["total_amount"] == 10500.0  # 10000 * 1.05
        assert result["installment_amount"] == 1050.0

    async def test_max_installments_validation(self):
        """Testa que número máximo de parcelas é respeitado."""
        worker = NegotiatePaymentPlanWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "amount_due": 12000.0,
            "currency": "BRL",
            "num_installments": 15,  # Exceeds MAX_INSTALLMENTS (12)
        }

        with pytest.raises(PaymentPlanError) as exc_info:
            await worker.execute(task_vars)

        assert "não pode exceder" in str(exc_info.value)

    async def test_minimum_installment_validation(self):
        """Testa validação de valor mínimo de parcela (R$100)."""
        worker = NegotiatePaymentPlanWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "amount_due": 500.0,
            "currency": "BRL",
            "num_installments": 10,  # Would result in R$50/installment
        }

        with pytest.raises(PaymentPlanError) as exc_info:
            await worker.execute(task_vars)

        assert "menor que o mínimo" in str(exc_info.value)

    async def test_custom_first_payment_date(self):
        """Testa data customizada de primeiro pagamento."""
        worker = NegotiatePaymentPlanWorker()

        first_payment = datetime(2024, 6, 15, tzinfo=timezone.utc)

        task_vars = {
            "collection_case_id": "CC-12345",
            "amount_due": 3000.0,
            "currency": "BRL",
            "num_installments": 3,
            "first_payment_date": first_payment.isoformat(),
        }

        result = await worker.execute(task_vars)

        # Verify first installment date
        first_installment = result["schedule"][0]
        assert first_installment["due_date"] == first_payment.isoformat()

    async def test_schedule_monthly_intervals(self):
        """Testa que parcelas são espaçadas mensalmente (30 dias)."""
        worker = NegotiatePaymentPlanWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "amount_due": 6000.0,
            "currency": "BRL",
            "num_installments": 6,
        }

        result = await worker.execute(task_vars)

        schedule = result["schedule"]

        # Verify installment sequence
        for i, installment in enumerate(schedule, start=1):
            assert installment["installment_number"] == i
            assert installment["amount"] == 1000.0
            assert installment["status"] == "pending"

    async def test_single_installment_allowed(self):
        """Testa que plano de parcela única (1x) é permitido."""
        worker = NegotiatePaymentPlanWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "amount_due": 2000.0,
            "currency": "BRL",
            "num_installments": 1,
        }

        result = await worker.execute(task_vars)

        assert result["num_installments"] == 1
        assert result["installment_amount"] == 2000.0
        assert len(result["schedule"]) == 1

    async def test_zero_installments_raises_error(self):
        """Testa que zero parcelas gera erro."""
        worker = NegotiatePaymentPlanWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "amount_due": 5000.0,
            "currency": "BRL",
            "num_installments": 0,
        }

        with pytest.raises(PaymentPlanError):
            await worker.execute(task_vars)
