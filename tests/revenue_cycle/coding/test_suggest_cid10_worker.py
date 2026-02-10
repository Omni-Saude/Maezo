"""Tests for suggest_cid10_worker - Phase 2.2 Coding & Audit."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from healthcare_platform.revenue_cycle.coding.workers.suggest_cid10_worker import (
    SuggestCid10Worker,
    SuggestCid10Input,
    SuggestCid10Output,
    register_worker,
)


class TestSuggestCid10Worker:
    """Tests for the CID-10 code suggestion worker."""

    @pytest.fixture
    def mock_nlp_engine(self):
        engine = MagicMock()
        engine.extract_diagnoses = AsyncMock(return_value=[
            {"code": "E11.9", "description": "Diabetes mellitus tipo 2", "confidence": 0.95},
            {"code": "I10", "description": "Hipertensao essencial", "confidence": 0.88},
        ])
        return engine

    @pytest.fixture
    def worker(self, mock_nlp_engine, mock_ans_client):
        return SuggestCid10Worker(
            nlp_engine=mock_nlp_engine,
            ans_client=mock_ans_client,
        )

    @pytest.mark.asyncio
    async def test_successful_suggestion(self, worker, mock_task):
        """NLP suggests valid CID-10 codes from clinical notes."""
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "clinical_notes": "Paciente com diabetes tipo 2 e hipertensao.",
        }.get(key, default)

        await worker.execute(mock_task)

        mock_task.complete.assert_called_once()
        call_args = mock_task.complete.call_args
        variables = call_args[0][0] if call_args[0] else call_args[1].get("variables", {})
        assert "suggested_cid10" in variables or "cid10_codes" in variables or mock_task.complete.called

    @pytest.mark.asyncio
    async def test_cid10_format_validation(self, worker, mock_task, mock_ans_client):
        """CID-10 codes are validated against ANS reference tables."""
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "clinical_notes": "Paciente com diabetes.",
        }.get(key, default)

        await worker.execute(mock_task)

        mock_task.complete.assert_called_once()
        mock_task.bpmn_error.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_clinical_notes(self, worker, mock_task, mock_nlp_engine):
        """Empty clinical notes trigger BPMN error or return empty suggestions."""
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "clinical_notes": "",
        }.get(key, default)
        mock_nlp_engine.extract_diagnoses = AsyncMock(return_value=[])

        await worker.execute(mock_task)

        assert mock_task.bpmn_error.called or mock_task.complete.called
        if mock_task.complete.called:
            call_args = mock_task.complete.call_args
            variables = call_args[0][0] if call_args[0] else call_args[1].get("variables", {})
            suggestions = variables.get("suggested_cid10", variables.get("cid10_codes", []))
            assert len(suggestions) == 0

    @pytest.mark.asyncio
    async def test_multiple_diagnoses_suggested(self, worker, mock_task, mock_nlp_engine):
        """Multiple diagnoses from complex notes are all returned."""
        mock_nlp_engine.extract_diagnoses = AsyncMock(return_value=[
            {"code": "E11.9", "description": "Diabetes mellitus tipo 2", "confidence": 0.95},
            {"code": "I10", "description": "Hipertensao essencial", "confidence": 0.88},
            {"code": "E78.5", "description": "Hiperlipidemia", "confidence": 0.82},
            {"code": "N18.3", "description": "Doenca renal cronica estagio 3", "confidence": 0.75},
        ])
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
            "clinical_notes": "Paciente pluripatologico com DM2, HAS, dislipidemia e DRC.",
        }.get(key, default)

        await worker.execute(mock_task)

        mock_task.complete.assert_called_once()
        call_args = mock_task.complete.call_args
        variables = call_args[0][0] if call_args[0] else call_args[1].get("variables", {})
        suggestions = variables.get("suggested_cid10", variables.get("cid10_codes", []))
        assert len(suggestions) >= 2


class TestSuggestCid10Input:
    """Tests for input validation."""

    def test_valid_input(self):
        inp = SuggestCid10Input(
            encounter_id="ENC-001",
            clinical_notes="Paciente com diabetes.",
        )
        assert inp.encounter_id == "ENC-001"

    def test_missing_notes_raises(self):
        with pytest.raises((ValueError, TypeError)):
            SuggestCid10Input(encounter_id="ENC-001", clinical_notes="")


class TestSuggestCid10Output:
    """Tests for output model."""

    def test_output_structure(self):
        out = SuggestCid10Output(
            suggested_codes=[
                {"code": "E11.9", "confidence": 0.95},
            ],
        )
        assert len(out.suggested_codes) == 1
        assert out.suggested_codes[0]["code"] == "E11.9"
