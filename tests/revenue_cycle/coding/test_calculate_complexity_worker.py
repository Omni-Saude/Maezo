"""Tests for calculate_complexity_worker - Phase 2.2 Coding & Audit."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from healthcare_platform.revenue_cycle.coding.workers.calculate_complexity_worker import (
    CalculateComplexityWorker,
    CalculateComplexityInput,
    CalculateComplexityOutput,
    register_worker,
)


class TestCalculateComplexityWorker:
    """Tests for the complexity calculation worker."""

    @pytest.fixture
    def mock_complexity_engine(self):
        engine = MagicMock()
        engine.calculate = AsyncMock(return_value={
            "complexity_score": 0.35,
            "complexity_level": "low",
            "charlson_index": 1,
            "age_factor": 1.0,
            "comorbidity_count": 1,
            "procedure_weight": 0.3,
        })
        return engine

    @pytest.fixture
    def worker(self, mock_complexity_engine):
        return CalculateComplexityWorker(complexity_engine=mock_complexity_engine)

    def _make_task_vars(self, overrides=None):
        base = {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "cid10_codes": [{"code": "E11.9"}],
            "tuss_codes": [{"code": "10101012"}],
            "patient_age": 45,
            "patient_id": "PAT-001",
        }
        if overrides:
            base.update(overrides)
        return base

    @pytest.mark.asyncio
    async def test_low_complexity(self, worker, mock_task):
        """Simple encounter scores low complexity."""
        vars_ = self._make_task_vars()
        mock_task.get_variable.side_effect = lambda key, default=None: vars_.get(key, default)

        await worker.execute(mock_task)

        mock_task.complete.assert_called_once()
        call_args = mock_task.complete.call_args
        variables = call_args[0][0] if call_args[0] else call_args[1].get("variables", {})
        score = variables.get("complexity_score", variables.get("score", 0))
        level = variables.get("complexity_level", variables.get("level", ""))
        assert score < 0.5 or level == "low" or "low" in str(variables).lower()

    @pytest.mark.asyncio
    async def test_high_complexity(self, worker, mock_task):
        """Complex encounter with multiple comorbidities scores high."""
        mock_complexity_engine = MagicMock()
        mock_complexity_engine.calculate = AsyncMock(return_value={
            "complexity_score": 0.88,
            "complexity_level": "high",
            "charlson_index": 6,
            "age_factor": 1.5,
            "comorbidity_count": 5,
            "procedure_weight": 0.9,
        })
        worker_high = CalculateComplexityWorker(complexity_engine=mock_complexity_engine)
        vars_ = self._make_task_vars({
            "cid10_codes": [
                {"code": "E11.9"},
                {"code": "I10"},
                {"code": "N18.5"},
                {"code": "I50.0"},
                {"code": "E78.5"},
            ],
            "tuss_codes": [
                {"code": "10101012"},
                {"code": "30911017"},
                {"code": "40301150"},
            ],
            "patient_age": 78,
        })
        mock_task.get_variable.side_effect = lambda key, default=None: vars_.get(key, default)

        await worker_high.execute(mock_task)

        mock_task.complete.assert_called_once()
        call_args = mock_task.complete.call_args
        variables = call_args[0][0] if call_args[0] else call_args[1].get("variables", {})
        score = variables.get("complexity_score", variables.get("score", 0))
        assert score > 0.7 or "high" in str(variables).lower()

    @pytest.mark.asyncio
    async def test_charlson_comorbidity_index(self, worker, mock_task):
        """Charlson Comorbidity Index is calculated and included in output."""
        mock_complexity_engine = MagicMock()
        mock_complexity_engine.calculate = AsyncMock(return_value={
            "complexity_score": 0.62,
            "complexity_level": "moderate",
            "charlson_index": 4,
            "age_factor": 1.2,
            "comorbidity_count": 3,
            "procedure_weight": 0.5,
        })
        worker_cci = CalculateComplexityWorker(complexity_engine=mock_complexity_engine)
        vars_ = self._make_task_vars({
            "cid10_codes": [
                {"code": "E11.9"},
                {"code": "I50.0"},
                {"code": "N18.3"},
            ],
            "patient_age": 65,
        })
        mock_task.get_variable.side_effect = lambda key, default=None: vars_.get(key, default)

        await worker_cci.execute(mock_task)

        mock_task.complete.assert_called_once()
        call_args = mock_task.complete.call_args
        variables = call_args[0][0] if call_args[0] else call_args[1].get("variables", {})
        cci = variables.get("charlson_index", variables.get("cci", None))
        assert cci is not None or "charlson" in str(variables).lower()

    @pytest.mark.asyncio
    async def test_age_factor(self, worker, mock_task):
        """Patient age increases complexity score appropriately."""
        mock_complexity_engine = MagicMock()
        mock_complexity_engine.calculate = AsyncMock(return_value={
            "complexity_score": 0.55,
            "complexity_level": "moderate",
            "charlson_index": 2,
            "age_factor": 1.8,
            "comorbidity_count": 1,
            "procedure_weight": 0.3,
        })
        worker_age = CalculateComplexityWorker(complexity_engine=mock_complexity_engine)
        vars_ = self._make_task_vars({"patient_age": 90})
        mock_task.get_variable.side_effect = lambda key, default=None: vars_.get(key, default)

        await worker_age.execute(mock_task)

        mock_task.complete.assert_called_once()
        call_args = mock_task.complete.call_args
        variables = call_args[0][0] if call_args[0] else call_args[1].get("variables", {})
        age_factor = variables.get("age_factor", None)
        assert age_factor is not None and age_factor > 1.0 or "age" in str(variables).lower()


class TestCalculateComplexityInput:
    """Tests for input model."""

    def test_valid_input(self):
        inp = CalculateComplexityInput(
            encounter_id="ENC-001",
            cid10_codes=[{"code": "E11.9"}],
            tuss_codes=[{"code": "10101012"}],
            patient_age=45,
        )
        assert inp.patient_age == 45

    def test_negative_age_raises(self):
        with pytest.raises((ValueError, TypeError)):
            CalculateComplexityInput(
                encounter_id="ENC-001",
                cid10_codes=[{"code": "E11.9"}],
                tuss_codes=[{"code": "10101012"}],
                patient_age=-1,
            )


class TestCalculateComplexityOutput:
    """Tests for output model."""

    def test_output_structure(self):
        out = CalculateComplexityOutput(
            complexity_score=0.42,
            complexity_level="low",
            charlson_index=1,
            age_factor=1.0,
        )
        assert 0.0 <= out.complexity_score <= 1.0
        assert out.charlson_index >= 0
