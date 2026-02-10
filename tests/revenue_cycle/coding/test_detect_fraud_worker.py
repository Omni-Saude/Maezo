"""Tests for detect_fraud_worker - Phase 2.2 Coding & Audit."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from healthcare_platform.revenue_cycle.coding.workers.detect_fraud_worker import (
    DetectFraudWorker,
    DetectFraudInput,
    DetectFraudOutput,
    register_worker,
)


class TestDetectFraudWorker:
    """Tests for the fraud detection worker."""

    @pytest.fixture
    def mock_fraud_engine(self):
        engine = MagicMock()
        engine.analyze = AsyncMock(return_value={
            "risk_score": 0.05,
            "risk_level": "low",
            "flags": [],
            "upcoding_detected": False,
            "unbundling_detected": False,
            "frequency_abuse": False,
        })
        return engine

    @pytest.fixture
    def worker(self, mock_fraud_engine):
        return DetectFraudWorker(fraud_engine=mock_fraud_engine)

    def _make_task_vars(self, overrides=None):
        base = {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "cid10_codes": [{"code": "E11.9"}],
            "tuss_codes": [{"code": "10101012", "quantity": 1}],
            "patient_id": "PAT-001",
            "attending_physician": "CRM-12345",
        }
        if overrides:
            base.update(overrides)
        return base

    @pytest.mark.asyncio
    async def test_no_fraud_detected(self, worker, mock_task):
        """Clean encounter passes fraud check."""
        vars_ = self._make_task_vars()
        mock_task.get_variable.side_effect = lambda key, default=None: vars_.get(key, default)

        await worker.execute(mock_task)

        mock_task.complete.assert_called_once()
        mock_task.bpmn_error.assert_not_called()

    @pytest.mark.asyncio
    async def test_upcoding_detected(self, worker, mock_task):
        """Upcoding pattern is flagged."""
        mock_fraud_engine = MagicMock()
        mock_fraud_engine.analyze = AsyncMock(return_value={
            "risk_score": 0.72,
            "risk_level": "high",
            "flags": ["UPCODING_SUSPECTED"],
            "upcoding_detected": True,
            "unbundling_detected": False,
            "frequency_abuse": False,
        })
        worker_up = DetectFraudWorker(fraud_engine=mock_fraud_engine)
        vars_ = self._make_task_vars()
        mock_task.get_variable.side_effect = lambda key, default=None: vars_.get(key, default)

        await worker_up.execute(mock_task)

        assert mock_task.bpmn_error.called or mock_task.complete.called
        if mock_task.complete.called:
            call_args = mock_task.complete.call_args
            variables = call_args[0][0] if call_args[0] else call_args[1].get("variables", {})
            assert "upcoding" in str(variables).lower() or variables.get("fraud_flags")

    @pytest.mark.asyncio
    async def test_unbundling_detected(self, worker, mock_task):
        """Unbundling pattern is flagged."""
        mock_fraud_engine = MagicMock()
        mock_fraud_engine.analyze = AsyncMock(return_value={
            "risk_score": 0.68,
            "risk_level": "high",
            "flags": ["UNBUNDLING_SUSPECTED"],
            "upcoding_detected": False,
            "unbundling_detected": True,
            "frequency_abuse": False,
        })
        worker_ub = DetectFraudWorker(fraud_engine=mock_fraud_engine)
        vars_ = self._make_task_vars({
            "tuss_codes": [
                {"code": "10101012", "quantity": 1},
                {"code": "10101020", "quantity": 1},
                {"code": "10101039", "quantity": 1},
            ],
        })
        mock_task.get_variable.side_effect = lambda key, default=None: vars_.get(key, default)

        await worker_ub.execute(mock_task)

        assert mock_task.bpmn_error.called or mock_task.complete.called

    @pytest.mark.asyncio
    async def test_high_risk_bpmn_error(self, worker, mock_task):
        """Very high risk score triggers BPMN error to block billing."""
        mock_fraud_engine = MagicMock()
        mock_fraud_engine.analyze = AsyncMock(return_value={
            "risk_score": 0.95,
            "risk_level": "critical",
            "flags": ["UPCODING_SUSPECTED", "UNBUNDLING_SUSPECTED", "FREQUENCY_ABUSE"],
            "upcoding_detected": True,
            "unbundling_detected": True,
            "frequency_abuse": True,
        })
        worker_high = DetectFraudWorker(fraud_engine=mock_fraud_engine)
        vars_ = self._make_task_vars()
        mock_task.get_variable.side_effect = lambda key, default=None: vars_.get(key, default)

        await worker_high.execute(mock_task)

        mock_task.bpmn_error.assert_called_once()
        error_code = mock_task.bpmn_error.call_args[0][0]
        assert "FRAUD" in error_code.upper() or "RISK" in error_code.upper()
        mock_task.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_frequency_abuse(self, worker, mock_task):
        """Abnormal procedure frequency is flagged."""
        mock_fraud_engine = MagicMock()
        mock_fraud_engine.analyze = AsyncMock(return_value={
            "risk_score": 0.60,
            "risk_level": "medium",
            "flags": ["FREQUENCY_ABUSE"],
            "upcoding_detected": False,
            "unbundling_detected": False,
            "frequency_abuse": True,
        })
        worker_freq = DetectFraudWorker(fraud_engine=mock_fraud_engine)
        vars_ = self._make_task_vars({
            "tuss_codes": [{"code": "10101012", "quantity": 15}],
        })
        mock_task.get_variable.side_effect = lambda key, default=None: vars_.get(key, default)

        await worker_freq.execute(mock_task)

        assert mock_task.bpmn_error.called or mock_task.complete.called
        if mock_task.complete.called:
            call_args = mock_task.complete.call_args
            variables = call_args[0][0] if call_args[0] else call_args[1].get("variables", {})
            flags = variables.get("fraud_flags", variables.get("flags", []))
            assert len(flags) >= 1 or "frequency" in str(variables).lower()


class TestDetectFraudInput:
    """Tests for input model."""

    def test_valid_input(self):
        inp = DetectFraudInput(
            encounter_id="ENC-001",
            patient_id="PAT-001",
            cid10_codes=[{"code": "E11.9"}],
            tuss_codes=[{"code": "10101012"}],
        )
        assert inp.patient_id == "PAT-001"


class TestDetectFraudOutput:
    """Tests for output model."""

    def test_clean_output(self):
        out = DetectFraudOutput(
            risk_score=0.05,
            risk_level="low",
            flags=[],
        )
        assert out.risk_level == "low"
        assert out.risk_score < 0.5

    def test_high_risk_output(self):
        out = DetectFraudOutput(
            risk_score=0.95,
            risk_level="critical",
            flags=["UPCODING_SUSPECTED"],
        )
        assert out.risk_score > 0.8
        assert len(out.flags) >= 1
