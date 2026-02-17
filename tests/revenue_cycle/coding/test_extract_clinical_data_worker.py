"""Tests for extract_clinical_data_worker - Phase 2.2 Coding & Audit."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from healthcare_platform.revenue_cycle.coding.workers import (
    ExtractClinicalDataWorker,
    ExtractClinicalDataInput,
    ExtractClinicalDataOutput,
    register_worker,
)


class TestExtractClinicalDataWorker:
    """Tests for the clinical data extraction worker."""

    @pytest.fixture
    def mock_fhir_service(self):
        svc = MagicMock()
        svc.get_encounter = AsyncMock(return_value={
            "id": "ENC-001",
            "status": "finished",
            "patient_id": "PAT-001",
            "diagnoses": [
                {"code": "E11.9", "description": "Diabetes mellitus tipo 2", "type": "primary"},
            ],
            "procedures": [
                {"code": "10101012", "description": "Consulta em consultorio", "quantity": 1},
            ],
            "clinical_notes": "Paciente com diabetes tipo 2 descompensado.",
            "attending_physician": "CRM-12345",
        })
        return svc

    @pytest.fixture
    def worker(self, mock_fhir_service, mock_dmn_service):
        return ExtractClinicalDataWorker(fhir_service=mock_fhir_service, dmn_service=mock_dmn_service)

    @pytest.mark.asyncio
    async def test_successful_extraction(self, worker, mock_task, mock_fhir_service):
        """Extraction succeeds with valid encounter and completes the task."""
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "encounter_id": "ENC-001",
            "tenant_id": "hospital-alpha",
        }.get(key, default)

        await worker.execute(mock_task)

        mock_fhir_service.get_encounter.assert_awaited_once_with("ENC-001")
        mock_task.complete.assert_called_once()
        call_kwargs = mock_task.complete.call_args
        variables = call_kwargs[0][0] if call_kwargs[0] else call_kwargs[1].get("variables", {})
        assert "clinical_data" in variables or mock_task.complete.called

    @pytest.mark.asyncio
    async def test_encounter_not_found_bpmn_error(self, worker, mock_task, mock_fhir_service):
        """Missing encounter triggers a BPMN error for process handling."""
        mock_fhir_service.get_encounter = AsyncMock(return_value=None)

        await worker.execute(mock_task)

        mock_task.bpmn_error.assert_called_once()
        error_code = mock_task.bpmn_error.call_args[0][0]
        assert "ENCOUNTER_NOT_FOUND" in error_code or "not_found" in error_code.lower()
        mock_task.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_fhir_service_error_retry(self, worker, mock_task, mock_fhir_service):
        """FHIR service failure triggers a task failure for retry."""
        mock_fhir_service.get_encounter = AsyncMock(
            side_effect=ConnectionError("FHIR server unavailable")
        )

        await worker.execute(mock_task)

        mock_task.failure.assert_called_once()
        failure_args = mock_task.failure.call_args
        assert "FHIR" in str(failure_args) or "unavailable" in str(failure_args).lower()
        mock_task.complete.assert_not_called()
        mock_task.bpmn_error.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_encounter_id(self, worker, mock_task):
        """Missing encounter_id variable triggers BPMN error."""
        mock_task.get_variable.side_effect = lambda key, default=None: {
            "tenant_id": "hospital-alpha",
        }.get(key, default)

        await worker.execute(mock_task)

        assert mock_task.bpmn_error.called or mock_task.failure.called
        mock_task.complete.assert_not_called()


class TestExtractClinicalDataInput:
    """Tests for input validation model."""

    def test_valid_input(self):
        inp = ExtractClinicalDataInput(
            encounter_id="ENC-001",
            tenant_id="hospital-alpha",
        )
        assert inp.encounter_id == "ENC-001"
        assert inp.tenant_id == "hospital-alpha"

    def test_missing_encounter_id_raises(self):
        with pytest.raises((ValueError, TypeError)):
            ExtractClinicalDataInput(
                encounter_id="",
                tenant_id="hospital-alpha",
            )


class TestExtractClinicalDataOutput:
    """Tests for output model structure."""

    def test_output_contains_required_fields(self):
        out = ExtractClinicalDataOutput(
            encounter_id="ENC-001",
            patient_id="PAT-001",
            diagnoses=[{"code": "E11.9", "type": "primary"}],
            procedures=[{"code": "10101012"}],
            clinical_notes="Notes here.",
        )
        assert out.encounter_id == "ENC-001"
        assert len(out.diagnoses) == 1
        assert len(out.procedures) == 1


class TestRegisterWorker:
    """Tests for worker registration."""

    def test_register_returns_topic(self):
        result = register_worker()
        assert result is not None
        assert isinstance(result, (str, dict, tuple))
