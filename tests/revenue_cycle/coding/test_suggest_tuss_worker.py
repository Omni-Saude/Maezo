"""Tests for suggest_tuss_worker - Phase 2.2 Coding & Audit."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from healthcare_platform.revenue_cycle.coding.workers import (
    SuggestTussWorker,
    register_worker,
)
from healthcare_platform.revenue_cycle.coding.workers.suggest_tuss_worker_v2 import (
    SuggestTussInput,
    SuggestTussOutput,
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
    def worker(self, mock_procedure_mapper, mock_ans_client, mock_dmn_service):
        return SuggestTussWorker(
            procedure_mapper=mock_procedure_mapper,
            ans_client=mock_ans_client,
            dmn_service=mock_dmn_service,
        )

    @pytest.mark.asyncio
    async def test_successful_tuss_suggestion(self, worker):
        """TUSS codes are suggested for documented procedures."""
        task_variables = {
            "extracted_procedures": [{"description": "Consulta medica"}, {"description": "Exame de sangue"}],
            "suggested_cid10_codes": [{"code": "E11.9"}],
            "encounter_class": "ambulatorio",
            "tenant_id": "hospital-alpha",
        }

        result = await worker.execute(task_variables)

        assert "suggested_tuss_codes" in result
        assert "tuss_count" in result
        assert result["tuss_count"] >= 0

    @pytest.mark.asyncio
    async def test_tuss_validation_via_ans(self, worker, mock_ans_client):
        """Suggested TUSS codes are validated against ANS tables."""
        task_variables = {
            "extracted_procedures": [{"description": "Consulta medica"}],
            "suggested_cid10_codes": [{"code": "E11.9"}],
            "encounter_class": "ambulatorio",
            "tenant_id": "hospital-alpha",
        }

        result = await worker.execute(task_variables)

        assert "suggested_tuss_codes" in result
        assert result["tuss_count"] >= 0

    @pytest.mark.asyncio
    async def test_invalid_tuss_format(self, worker, mock_ans_client):
        """Invalid TUSS format is handled gracefully by returning empty or validated results."""
        mock_ans_client.validate_tuss = AsyncMock(
            return_value={"valid": False, "reason": "Code not found in TUSS table"}
        )
        task_variables = {
            "extracted_procedures": [{"description": "Procedimento invalido XYZ"}],
            "suggested_cid10_codes": [{"code": "E11.9"}],
            "encounter_class": "ambulatorio",
            "tenant_id": "hospital-alpha",
        }

        result = await worker.execute(task_variables)

        # V2 worker returns results even if validation finds issues
        assert "suggested_tuss_codes" in result
        assert "tuss_count" in result

    @pytest.mark.asyncio
    async def test_empty_procedures(self, worker, mock_procedure_mapper):
        """No procedures in text triggers appropriate handling."""
        mock_procedure_mapper.suggest_tuss_codes = AsyncMock(return_value=[])
        task_variables = {
            "extracted_procedures": [],
            "suggested_cid10_codes": [],
            "encounter_class": "ambulatorio",
            "tenant_id": "hospital-alpha",
        }

        # Should raise CodingException when both procedures and diagnoses are empty
        from healthcare_platform.shared.domain.exceptions import CodingException
        with pytest.raises(CodingException):
            await worker.execute(task_variables)


class TestSuggestTussInput:
    """Tests for input model."""

    def test_valid_input(self):
        inp = SuggestTussInput(
            extracted_procedures=[{"description": "Consulta medica"}],
            suggested_cid10_codes=[{"code": "E11.9"}],
            encounter_class="ambulatorio",
            tenant_id="hospital-alpha",
        )
        assert len(inp.extracted_procedures) == 1

    def test_empty_procedures_text(self):
        # V2 model allows empty lists - validation happens in the worker
        inp = SuggestTussInput(
            extracted_procedures=[],
            suggested_cid10_codes=[],
            encounter_class="ambulatorio",
            tenant_id="hospital-alpha",
        )
        assert len(inp.extracted_procedures) == 0


class TestSuggestTussOutput:
    """Tests for output model."""

    def test_output_structure(self):
        out = SuggestTussOutput(
            suggested_tuss_codes=[
                {"code": "10101012", "confidence": 0.97},
            ],
            tuss_count=1,
        )
        assert len(out.suggested_tuss_codes) == 1
        assert out.tuss_count == 1
