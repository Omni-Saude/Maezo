"""Tests for finalize_coding_worker - Phase 2.2 Coding & Audit."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from healthcare_platform.revenue_cycle.coding.workers import (
    FinalizeCodingWorker,
    FinalizeCodingInput,
    FinalizeCodingOutput,
    register_worker,
)


class TestFinalizeCodingWorker:
    """Tests for the coding finalization worker."""

    @pytest.fixture
    def mock_encounter_service(self):
        svc = MagicMock()
        svc.lock_coding = AsyncMock(return_value={"locked": True, "lock_id": "LOCK-001"})
        svc.save_final_coding = AsyncMock(return_value={"saved": True, "version": 1})
        return svc

    @pytest.fixture
    def worker(self, mock_encounter_service, mock_dmn_service):
        return FinalizeCodingWorker(
            encounter_service=mock_encounter_service,
            dmn_service=mock_dmn_service
        )

    def _make_task_vars(self, overrides=None):
        base = {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "cid10_codes": [{"code": "E11.9"}, {"code": "I10"}],
            "tuss_codes": [{"code": "10101012"}],
            "audit_status": "approved",
            "audit_score": 0.95,
            "fraud_risk": 0.05,
            "fraud_risk_level": "low",
            "complexity_score": 0.42,
        }
        if overrides:
            base.update(overrides)
        return base

    @pytest.mark.asyncio
    async def test_successful_finalization(self, worker, mock_task, mock_encounter_service):
        """Approved coding is finalized and encounter is locked."""
        vars_ = self._make_task_vars()
        mock_task.get_variable.side_effect = lambda key, default=None: vars_.get(key, default)

        await worker.execute(mock_task)

        mock_task.complete.assert_called_once()
        mock_encounter_service.lock_coding.assert_awaited_once()
        mock_encounter_service.save_final_coding.assert_awaited_once()
        mock_task.bpmn_error.assert_not_called()

    @pytest.mark.asyncio
    async def test_coding_not_approved_bpmn_error(self, worker, mock_task):
        """Unapproved coding triggers BPMN error."""
        vars_ = self._make_task_vars({"audit_status": "failed", "audit_score": 0.50})
        mock_task.get_variable.side_effect = lambda key, default=None: vars_.get(key, default)

        await worker.execute(mock_task)

        mock_task.bpmn_error.assert_called_once()
        error_code = mock_task.bpmn_error.call_args[0][0]
        assert "APPROVED" in error_code.upper() or "AUDIT" in error_code.upper() or "CODING" in error_code.upper()
        mock_task.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_fraud_block_bpmn_error(self, worker, mock_task):
        """High fraud risk blocks finalization with BPMN error."""
        vars_ = self._make_task_vars({
            "fraud_risk": 0.92,
            "fraud_risk_level": "critical",
        })
        mock_task.get_variable.side_effect = lambda key, default=None: vars_.get(key, default)

        await worker.execute(mock_task)

        mock_task.bpmn_error.assert_called_once()
        error_code = mock_task.bpmn_error.call_args[0][0]
        assert "FRAUD" in error_code.upper() or "BLOCK" in error_code.upper()
        mock_task.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_encounter_lock(self, worker, mock_task, mock_encounter_service):
        """Encounter coding is locked after finalization to prevent edits."""
        vars_ = self._make_task_vars()
        mock_task.get_variable.side_effect = lambda key, default=None: vars_.get(key, default)

        await worker.execute(mock_task)

        mock_encounter_service.lock_coding.assert_awaited_once_with("ENC-001")
        mock_task.complete.assert_called_once()
        call_args = mock_task.complete.call_args
        variables = call_args[0][0] if call_args[0] else call_args[1].get("variables", {})
        assert variables.get("coding_locked", False) is True or "lock" in str(variables).lower()

    @pytest.mark.asyncio
    async def test_lock_failure_retries(self, worker, mock_task, mock_encounter_service):
        """Lock service failure triggers task failure for retry."""
        mock_encounter_service.lock_coding = AsyncMock(
            side_effect=ConnectionError("Lock service unavailable")
        )
        vars_ = self._make_task_vars()
        mock_task.get_variable.side_effect = lambda key, default=None: vars_.get(key, default)

        await worker.execute(mock_task)

        mock_task.failure.assert_called_once()
        mock_task.complete.assert_not_called()


class TestFinalizeCodingInput:
    """Tests for input model."""

    def test_valid_input(self):
        inp = FinalizeCodingInput(
            encounter_id="ENC-001",
            cid10_codes=[{"code": "E11.9"}],
            tuss_codes=[{"code": "10101012"}],
            audit_status="approved",
            fraud_risk_level="low",
        )
        assert inp.audit_status == "approved"

    def test_missing_audit_status_raises(self):
        with pytest.raises((ValueError, TypeError)):
            FinalizeCodingInput(
                encounter_id="ENC-001",
                cid10_codes=[{"code": "E11.9"}],
                tuss_codes=[{"code": "10101012"}],
                audit_status="",
                fraud_risk_level="low",
            )


class TestFinalizeCodingOutput:
    """Tests for output model."""

    def test_finalized_output(self):
        out = FinalizeCodingOutput(
            encounter_id="ENC-001",
            coding_locked=True,
            version=1,
            status="finalized",
        )
        assert out.coding_locked is True
        assert out.status == "finalized"


class TestRegisterWorker:
    """Tests for worker registration."""

    def test_register_returns_topic(self):
        result = register_worker()
        assert result is not None
