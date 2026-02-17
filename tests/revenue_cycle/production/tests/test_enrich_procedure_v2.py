"""Tests for EnrichProcedureWorker (v2)."""
from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.revenue_cycle.production.workers.enrich_procedure_worker_v2 import (
    EnrichProcedureWorker,
)


def make_context(variables: dict, tenant_id: str = "test-tenant") -> TaskContext:
    """Create a test TaskContext."""
    return TaskContext(
        task_id="task-001",
        process_instance_id="proc-001",
        tenant_id=tenant_id,
        variables=variables,
        worker_id="test-worker",
    )


@pytest.fixture
def worker():
    """Create EnrichProcedureWorker with mocked dependencies."""
    fhir_client = MagicMock()
    worker = EnrichProcedureWorker(fhir_client=fhir_client)
    worker.logger = MagicMock()
    return worker


def test_enrich_procedure_happy_path(worker):
    """Test successful procedure enrichment."""
    # Mock service response - service.enrich returns dict with enriched_procedures
    worker.service.enrich = MagicMock(
        return_value={
            "enriched_procedures": [
                {
                    "code": "40301010",
                    "description": "Consulta médica",
                    "diagnosis_codes": ["I10", "E11"],
                    "performer_references": ["Practitioner/dr-123"],
                    "encounter_reference": "Encounter/enc-123",
                }
            ],
        }
    )

    # Mock DMN evaluation
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "PROSSEGUIR",
            "acao": "",
        }
    )

    context = make_context(
        {
            "captured_procedures": [
                {
                    "code": "40301010",
                    "description": "Consulta médica",
                }
            ],
            "encounter_reference": "Encounter/enc-123",
            "diagnosis_codes": ["I10", "E11"],
            "performer_references": ["Practitioner/dr-123"],
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert "enriched_procedures" in result.variables
    assert len(result.variables["enriched_procedures"]) == 1
    assert "diagnosis_codes" in result.variables
    worker.service.enrich.assert_called_once()


def test_enrich_procedure_no_procedures_error(worker):
    """Test error when no procedures provided."""
    worker.evaluate_dmn = MagicMock()

    context = make_context(
        {
            "captured_procedures": [],
            "encounter_reference": "Encounter/enc-123",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "CODING_ERROR"
    assert "no procedures" in result.error_message.lower()


def test_enrich_procedure_missing_diagnosis_block(worker):
    """Test DMN blocking due to missing diagnosis."""
    worker.service = MagicMock()
    worker.service.enrich_procedures.return_value = {
        "enriched_procedures": [
            {
                "code": "40301010",
                "description": "Consulta médica",
                "diagnosis_codes": [],
            }
        ],
    }

    # DMN blocks due to missing required diagnosis
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "BLOQUEAR",
            "acao": "Diagnosis required for billing",
            "diagnosis_required": True,
            "diagnosis_count_sufficient": False,
        }
    )

    context = make_context(
        {
            "captured_procedures": [{"code": "40301010"}],
            "encounter_reference": "Encounter/enc-123",
            "diagnosis_codes": [],
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "MISSING_DIAGNOSIS"
    assert "diagnosis required" in result.error_message.lower()


def test_enrich_procedure_review_warning(worker):
    """Test DMN review returns success with warning."""
    worker.service.enrich = MagicMock(
        return_value={
            "enriched_procedures": [
                {
                    "code": "40301010",
                    "description": "Consulta médica",
                    "diagnosis_codes": ["Z00"],
                }
            ],
        }
    )

    # DMN suggests review but doesn't block
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "REVISAR",
            "acao": "Diagnosis code requires additional documentation",
        }
    )

    context = make_context(
        {
            "captured_procedures": [{"code": "40301010"}],
            "encounter_reference": "Encounter/enc-123",
            "diagnosis_codes": ["Z00"],
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert "enriched_procedures" in result.variables
    assert "enrichment_warnings" in result.variables
    assert len(result.variables["enrichment_warnings"]) > 0


def test_enrich_procedure_service_exception(worker):
    """Test handling of service exceptions."""
    worker.service.enrich = MagicMock(side_effect=Exception("FHIR server unavailable"))

    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "PROSSEGUIR",
            "acao": "",
        }
    )

    context = make_context(
        {
            "captured_procedures": [{"code": "40301010"}],
            "encounter_reference": "Encounter/enc-123",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "CODING_ERROR"
    assert "fhir server unavailable" in result.error_message.lower()


def test_enrich_procedure_multiple_diagnoses(worker):
    """Test enrichment with multiple diagnosis codes."""
    worker.service.enrich = MagicMock(
        return_value={
            "enriched_procedures": [
                {
                    "code": "40301010",
                    "description": "Consulta médica",
                    "diagnosis_codes": ["I10", "E11", "E78.5"],
                }
            ],
        }
    )

    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "PROSSEGUIR",
            "acao": "",
        }
    )

    context = make_context(
        {
            "captured_procedures": [{"code": "40301010"}],
            "encounter_reference": "Encounter/enc-123",
            "diagnosis_codes": ["I10", "E11", "E78.5"],
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    # diagnosis_codes is in result.variables, not in enriched_procedures[0]
    assert len(result.variables["diagnosis_codes"]) == 3


def test_enrich_procedure_missing_performer(worker):
    """Test enrichment when performer is missing."""
    worker.service.enrich = MagicMock(
        return_value={
            "enriched_procedures": [
                {
                    "code": "40301010",
                    "description": "Consulta médica",
                    "diagnosis_codes": ["I10"],
                    "performer_references": [],
                }
            ],
        }
    )

    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "REVISAR",
            "acao": "Performer information missing",
        }
    )

    context = make_context(
        {
            "captured_procedures": [{"code": "40301010"}],
            "encounter_reference": "Encounter/enc-123",
            "diagnosis_codes": ["I10"],
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert "enrichment_warnings" in result.variables
    assert any("performer" in w.lower() for w in result.variables["enrichment_warnings"])
