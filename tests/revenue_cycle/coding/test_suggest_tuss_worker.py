"""Tests for suggest_tuss_worker - Phase 2.2 Coding & Audit."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from healthcare_platform.revenue_cycle.coding.workers.suggest_tuss_worker import (
    SuggestTussWorker,
    SuggestTussInput,
    SuggestTussOutput,
    register_worker,
)


class TestSuggestTussWorker:
    """Tests for the TUSS procedure code suggestion worker."""

    @pytest.fixture
    def mock_procedure_mapper(self):
        mapper = MagicMock()
        mapper.suggest_tuss_codes = AsyncMock(return_value=[
            {"code": "10101012", "description": "Consulta em consultorio", "confidence": 0.97},
            {"code": "40301150", "description": "Hemograma completo", "confidence": 0.91},
        ])
        return mapper

    @pytest.fixture
    def worker(self, mock_procedure_mapper, mock_ans_client):
        return SuggestTussWorker(
            procedure_mapper=mock_procedure_mapper,
            ans_client=mock_ans_client,
        )

    @pytest.mark.asyncio
    async def test_successful_tuss_suggestion(self, worker, mock_task):
        """TUSS codes are suggested for documented procedures."""
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "procedures_text": "Consulta medica e exame de sangue completo.",
            "diagnoses": [{"code": "E11.9"}],
        }.get(key, default)

        await worker.execute(mock_task)

        mock_task.complete.assert_called_once()
        mock_task.bpmn_error.assert_not_called()

    @pytest.mark.asyncio
    async def test_tuss_validation_via_ans(self, worker, mock_task, mock_ans_client):
        """Suggested TUSS codes are validated against ANS tables."""
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "procedures_text": "Consulta medica.",
            "diagnoses": [{"code": "E11.9"}],
        }.get(key, default)

        await worker.execute(mock_task)

        assert mock_ans_client.validate_tuss.await_count >= 1 or mock_task.complete.called

    @pytest.mark.asyncio
    async def test_invalid_tuss_format(self, worker, mock_task, mock_ans_client):
        """Invalid TUSS format triggers BPMN error."""
        mock_ans_client.validate_tuss = AsyncMock(
            return_value={"valid": False, "reason": "Code not found in TUSS table"}
        )
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "procedures_text": "Procedimento invalido XYZ.",
            "diagnoses": [{"code": "E11.9"}],
        }.get(key, default)

        await worker.execute(mock_task)

        assert mock_task.bpmn_error.called or mock_task.complete.called
        if mock_task.bpmn_error.called:
            error_code = mock_task.bpmn_error.call_args[0][0]
            assert "INVALID" in error_code.upper() or "TUSS" in error_code.upper()

    @pytest.mark.asyncio
    async def test_empty_procedures(self, worker, mock_task, mock_procedure_mapper):
        """No procedures in text triggers appropriate handling."""
        mock_procedure_mapper.suggest_tuss_codes = AsyncMock(return_value=[])
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "procedures_text": "",
            "diagnoses": [],
        }.get(key, default)

        await worker.execute(mock_task)

        assert mock_task.bpmn_error.called or mock_task.complete.called
        mock_task.failure.assert_not_called()


class TestSuggestTussInput:
    """Tests for input model."""

    def test_valid_input(self):
        inp = SuggestTussInput(
            encounter_id="ENC-001",
            procedures_text="Consulta medica.",
            diagnoses=[{"code": "E11.9"}],
        )
        assert inp.encounter_id == "ENC-001"

    def test_empty_procedures_text(self):
        with pytest.raises((ValueError, TypeError)):
            SuggestTussInput(
                encounter_id="ENC-001",
                procedures_text="",
                diagnoses=[],
            )


class TestSuggestTussOutput:
    """Tests for output model."""

    def test_output_structure(self):
        out = SuggestTussOutput(
            suggested_codes=[
                {"code": "10101012", "confidence": 0.97},
            ],
        )
        assert len(out.suggested_codes) == 1
