from __future__ import annotations

import pytest

from platform.revenue_cycle.collection.enums import CollectionStatus
from platform.revenue_cycle.collection.exceptions import WriteOffError
from platform.revenue_cycle.collection.workers.write_off_bad_debt_worker import (
    WriteOffBadDebtWorker,
)


@pytest.mark.asyncio
class TestWriteOffBadDebtWorker:
    """Testes para WriteOffBadDebtWorker."""

    async def test_write_off_below_approval_threshold(self):
        """Testa baixa de valor abaixo do limite (R$10.000) sem necessidade de aprovação."""
        worker = WriteOffBadDebtWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "amount_due": 5000.0,
            "currency": "BRL",
            "reason": "Paciente falecido sem herdeiros",
        }

        result = await worker.execute(task_vars)

        assert result["amount_written_off"] == 5000.0
        assert result["requires_approval"] is False
        assert result["approved"] is False
        assert result["new_status"] == CollectionStatus.WRITTEN_OFF.value
        assert "written_off_at" in result

    async def test_write_off_above_threshold_with_approval(self):
        """Testa baixa de valor acima do limite com aprovação gerencial."""
        worker = WriteOffBadDebtWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "amount_due": 25000.0,
            "currency": "BRL",
            "reason": "Devedor em recuperação judicial",
            "approved_by": "manager-001",
            "approval_reference": "APPR-2024-001",
        }

        result = await worker.execute(task_vars)

        assert result["amount_written_off"] == 25000.0
        assert result["requires_approval"] is True
        assert result["approved"] is True
        assert result["approved_by"] == "manager-001"
        assert result["approval_reference"] == "APPR-2024-001"

    async def test_write_off_above_threshold_without_approval_raises_error(self):
        """Testa que valores acima do limite sem aprovação geram erro."""
        worker = WriteOffBadDebtWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "amount_due": 15000.0,
            "currency": "BRL",
            "reason": "Dívida incobrável",
        }

        with pytest.raises(WriteOffError) as exc_info:
            await worker.execute(task_vars)

        assert "requer aprovação gerencial" in str(exc_info.value)
        assert "10,000" in str(exc_info.value) or "10.000" in str(exc_info.value)

    async def test_exactly_at_approval_threshold_requires_approval(self):
        """Testa que valor exatamente no limite (R$10.000) requer aprovação."""
        worker = WriteOffBadDebtWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "amount_due": 10000.0,
            "currency": "BRL",
            "reason": "Prescrição da dívida",
        }

        with pytest.raises(WriteOffError):
            await worker.execute(task_vars)

    async def test_custom_write_off_date(self):
        """Testa data customizada de baixa."""
        from datetime import datetime, timezone

        worker = WriteOffBadDebtWorker()

        custom_date = datetime(2024, 12, 31, tzinfo=timezone.utc)

        task_vars = {
            "collection_case_id": "CC-12345",
            "amount_due": 3000.0,
            "currency": "BRL",
            "reason": "Insolvência declarada",
            "write_off_date": custom_date.isoformat(),
        }

        result = await worker.execute(task_vars)

        assert result["written_off_at"] == custom_date.isoformat()

    async def test_write_off_reason_included(self):
        """Testa que motivo da baixa está incluído no resultado."""
        worker = WriteOffBadDebtWorker()

        reason = "Cliente desaparecido após múltiplas tentativas de contato"

        task_vars = {
            "collection_case_id": "CC-12345",
            "amount_due": 2000.0,
            "currency": "BRL",
            "reason": reason,
        }

        result = await worker.execute(task_vars)

        assert result["write_off_reason"] == reason

    async def test_approval_threshold_constant(self):
        """Testa que constante de aprovação está correta."""
        worker = WriteOffBadDebtWorker()

        assert worker.APPROVAL_THRESHOLD == 10000.0

    async def test_write_off_different_currency(self):
        """Testa baixa com moeda diferente."""
        worker = WriteOffBadDebtWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "amount_due": 5000.0,
            "currency": "USD",
            "reason": "International patient - uncollectible",
        }

        result = await worker.execute(task_vars)

        assert result["currency"] == "USD"
        assert result["amount_written_off"] == 5000.0

    async def test_large_amount_with_approval(self):
        """Testa baixa de valor muito alto com aprovação."""
        worker = WriteOffBadDebtWorker()

        task_vars = {
            "collection_case_id": "CC-12345",
            "amount_due": 100000.0,
            "currency": "BRL",
            "reason": "Falência decretada - sem ativos",
            "approved_by": "cfo-001",
            "approval_reference": "BOARD-DECISION-2024-05",
        }

        result = await worker.execute(task_vars)

        assert result["approved"] is True
        assert result["amount_written_off"] == 100000.0
