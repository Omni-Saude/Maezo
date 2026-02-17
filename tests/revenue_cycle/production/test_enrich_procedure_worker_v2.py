"""Tests for EnrichProcedureWorker v2 (ARCHETYPE: ADMIN_ADJUDICATION)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskStatus
from healthcare_platform.revenue_cycle.production.workers.enrich_procedure_worker_v2 import (
    EnrichProcedureWorker,
)


@pytest.fixture
def mock_dmn():
    return MagicMock()


@pytest.fixture
def context():
    return TaskContext(
        task_id="task_1",
        process_instance_id="proc_1",
        tenant_id="HOSPITAL_A",
        variables={},
        worker_id="production.enrich_procedure",
    )


@pytest.fixture
def worker(mock_dmn):
    return EnrichProcedureWorker(
        fhir_client=MagicMock(),
        dmn_service=mock_dmn,
        metrics=MagicMock(),
    )


def test_happy_path_prosseguir(worker, context, mock_dmn):
    """Enrichment succeeds with diagnosis codes present."""
    mock_dmn.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "Diagnosis validated",
        "risco": "BAIXO",
    }
    context.variables = {
        "captured_procedures": [{"code": "40101010", "procedure_id": "P1"}],
        "encounter_reference": "Encounter/123",
        "diagnosis_codes": ["J18.9"],
        "performer_references": ["Practitioner/DR1"],
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert result.variables["enriched_procedures"][0]["diagnosis_codes"] == ["J18.9"]
    assert result.variables["diagnosis_codes"] == ["J18.9"]


def test_bloquear_missing_diagnosis(worker, context, mock_dmn):
    """DMN blocks when diagnosis is required but missing."""
    mock_dmn.evaluate.return_value = {
        "resultado": "BLOQUEAR",
        "acao": "CID-10 obrigatorio para este procedimento",
        "risco": "ALTO",
    }
    context.variables = {
        "captured_procedures": [{"code": "40101010"}],
        "encounter_reference": "Encounter/123",
        "diagnosis_codes": [],
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "MISSING_DIAGNOSIS"


def test_revisar_adds_warning(worker, context, mock_dmn):
    """DMN REVISAR adds a warning but does not block."""
    mock_dmn.evaluate.return_value = {
        "resultado": "REVISAR",
        "acao": "Verify secondary diagnosis",
        "risco": "MEDIO",
    }
    context.variables = {
        "captured_procedures": [{"code": "40101010"}],
        "encounter_reference": "Encounter/123",
        "diagnosis_codes": ["J18.9"],
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert len(result.variables["enrichment_warnings"]) > 0


def test_empty_procedures_error(worker, context):
    """No procedures triggers CODING_ERROR."""
    context.variables = {"captured_procedures": []}

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "CODING_ERROR"


def test_dmn_evaluator_failure(worker, context, mock_dmn):
    """DMN service exception is caught."""
    mock_dmn.evaluate.side_effect = RuntimeError("DMN evaluation failed")
    context.variables = {
        "captured_procedures": [{"code": "40101010"}],
        "diagnosis_codes": ["J18.9"],
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR


def test_multiple_procedures_enriched(worker, context, mock_dmn):
    """All procedures get diagnosis codes and performers."""
    mock_dmn.evaluate.return_value = {
        "resultado": "PROSSEGUIR",
        "acao": "OK",
        "risco": "BAIXO",
    }
    context.variables = {
        "captured_procedures": [
            {"code": "40101010"},
            {"code": "40201010"},
        ],
        "encounter_reference": "Encounter/123",
        "diagnosis_codes": ["J18.9", "I10"],
        "performer_references": ["Practitioner/DR1"],
    }

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert len(result.variables["enriched_procedures"]) == 2
    for proc in result.variables["enriched_procedures"]:
        assert proc["diagnosis_codes"] == ["J18.9", "I10"]
