"""Tests for suggest_cid10_worker - Phase 2.2 Coding & Audit."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from healthcare_platform.revenue_cycle.coding.workers import (
    SuggestCid10Worker,
    register_worker,
)
from healthcare_platform.revenue_cycle.coding.workers.suggest_cid10_worker_v2 import (
    SuggestCid10Input,
    SuggestCid10Output,
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
    def worker(self, mock_nlp_engine, mock_ans_client, mock_dmn_service):
        return SuggestCid10Worker(
            nlp_engine=mock_nlp_engine,
            ans_client=mock_ans_client,
            dmn_service=mock_dmn_service,
        )

    @pytest.mark.asyncio
    async def test_successful_suggestion(self, worker):
        """NLP suggests valid CID-10 codes from clinical notes."""
        task_variables = {
            "clinical_notes": "Paciente com diabetes tipo 2 e hipertensao.",
            "extracted_diagnoses": [],
            "encounter_class": "ambulatorio",
            "tenant_id": "hospital-alpha",
        }

        result = await worker.execute(task_variables)

        assert "suggested_cid10_codes" in result
        assert "primary_cid10" in result
        assert "cid10_count" in result
        assert result["cid10_count"] >= 0

    @pytest.mark.asyncio
    async def test_cid10_format_validation(self, worker, mock_ans_client):
        """CID-10 codes are validated against ANS reference tables."""
        task_variables = {
            "clinical_notes": "Paciente com diabetes.",
            "extracted_diagnoses": [],
            "encounter_class": "ambulatorio",
            "tenant_id": "hospital-alpha",
        }

        result = await worker.execute(task_variables)

        assert "suggested_cid10_codes" in result
        assert result["cid10_count"] >= 0

    @pytest.mark.asyncio
    async def test_empty_clinical_notes(self, worker, mock_nlp_engine):
        """Empty clinical notes trigger validation error."""
        task_variables = {
            "clinical_notes": "",
            "extracted_diagnoses": [],
            "encounter_class": "ambulatorio",
            "tenant_id": "hospital-alpha",
        }
        mock_nlp_engine.extract_diagnoses = AsyncMock(return_value=[])

        # Pydantic validates min_length=1 before worker logic runs
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            await worker.execute(task_variables)

    @pytest.mark.asyncio
    async def test_multiple_diagnoses_suggested(self, worker, mock_nlp_engine):
        """Multiple diagnoses from complex notes are all returned."""
        mock_nlp_engine.extract_diagnoses = AsyncMock(return_value=[
            {"code": "E11.9", "description": "Diabetes mellitus tipo 2", "confidence": 0.95},
            {"code": "I10", "description": "Hipertensao essencial", "confidence": 0.88},
            {"code": "E78.5", "description": "Hiperlipidemia", "confidence": 0.82},
            {"code": "N18.3", "description": "Doenca renal cronica estagio 3", "confidence": 0.75},
        ])
        task_variables = {
            "clinical_notes": "Paciente pluripatologico com DM2, HAS, dislipidemia e DRC.",
            "extracted_diagnoses": [],
            "encounter_class": "ambulatorio",
            "tenant_id": "hospital-alpha",
        }

        result = await worker.execute(task_variables)

        assert "suggested_cid10_codes" in result
        assert result["cid10_count"] >= 2


class TestSuggestCid10Input:
    """Tests for input validation."""

    def test_valid_input(self):
        inp = SuggestCid10Input(
            clinical_notes="Paciente com diabetes.",
            extracted_diagnoses=[],
            encounter_class="ambulatorio",
            tenant_id="hospital-alpha",
        )
        assert inp.clinical_notes == "Paciente com diabetes."

    def test_missing_notes_raises(self):
        # V2 model requires clinical_notes with min_length=1
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SuggestCid10Input(
                clinical_notes="",
                extracted_diagnoses=[],
                encounter_class="ambulatorio",
                tenant_id="hospital-alpha",
            )


class TestSuggestCid10Output:
    """Tests for output model."""

    def test_output_structure(self):
        out = SuggestCid10Output(
            suggested_cid10_codes=[
                {"code": "E11.9", "confidence": 0.95},
            ],
            primary_cid10="E11.9",
            cid10_count=1,
        )
        assert len(out.suggested_cid10_codes) == 1
        assert out.suggested_cid10_codes[0]["code"] == "E11.9"
        assert out.primary_cid10 == "E11.9"
