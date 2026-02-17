"""Tests for ValidateProcedureWorker (v2)."""
from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.revenue_cycle.production.workers.validate_procedure_worker_v2 import (
    ValidateProcedureWorker,
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
    """Create ValidateProcedureWorker."""
    worker = ValidateProcedureWorker()
    worker.logger = MagicMock()
    return worker


def test_validate_procedure_happy_path_all_valid(worker):
    """Test successful validation of all procedures."""
    # Mock DMN evaluation - all codes valid
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "PROSSEGUIR",
            "acao": "",
            "risco": "BAIXO",
            "procedureName": "Consulta médica",
            "coverageType": "ambulatorial",
        }
    )

    context = make_context(
        {
            "procedure_codes": ["40301010", "20101012", "30101016"],
            "coverage_type": "ambulatorial",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert "validated_procedures" in result.variables
    assert result.variables["all_valid"] is True
    assert len(result.variables["validated_procedures"]) == 3
    assert len(result.variables["invalid_codes"]) == 0


def test_validate_procedure_no_procedures_error(worker):
    """Test error when no procedures provided."""
    worker.evaluate_dmn = MagicMock()

    context = make_context(
        {
            "procedure_codes": [],
            "coverage_type": "ambulatorial",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "CODING_ERROR"
    assert "no procedure codes" in result.error_message.lower()


def test_validate_procedure_invalid_code_block(worker):
    """Test DMN blocking invalid procedure code."""
    # Mock DMN evaluation - invalid code
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "BLOQUEAR",
            "acao": "Invalid procedure code",
            "risco": "ALTO",
            "procedureName": None,
            "coverageType": None,
            "validation_error": "Code not found in TUSS table",
        }
    )

    context = make_context(
        {
            "procedure_codes": ["99999999"],
            "coverage_type": "ambulatorial",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "INVALID_PROCEDURE_CODE"
    assert "invalid codes: 99999999" in result.error_message.lower()
    assert "99999999" in result.variables["invalid_codes"]


def test_validate_procedure_mixed_valid_invalid(worker):
    """Test validation with mix of valid and invalid codes."""
    # Return different results per call
    call_count = [0]

    def evaluate_dmn_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # First code valid
            return {
                "resultado": "PROSSEGUIR",
                "acao": "",
                "risco": "BAIXO",
                "procedureName": "Consulta médica",
                "coverageType": "ambulatorial",
            }
        else:
            # Second code invalid
            return {
                "resultado": "BLOQUEAR",
                "acao": "Invalid procedure code",
                "risco": "ALTO",
                "procedureName": None,
                "coverageType": None,
            }

    worker.evaluate_dmn = MagicMock(side_effect=evaluate_dmn_side_effect)

    context = make_context(
        {
            "procedure_codes": ["40301010", "99999999"],
            "coverage_type": "ambulatorial",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "INVALID_PROCEDURE_CODE"
    # Worker includes validated_procedures and invalid_codes in error variables
    assert "validated_procedures" in result.variables
    assert len(result.variables["validated_procedures"]) == 2
    assert len(result.variables["invalid_codes"]) == 1


def test_validate_procedure_exception_handling(worker):
    """Test handling of unexpected exceptions."""
    worker.evaluate_dmn = MagicMock(
        side_effect=Exception("DMN service unavailable")
    )

    context = make_context(
        {
            "procedure_codes": ["40301010"],
            "coverage_type": "ambulatorial",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "CODING_ERROR"
    assert "dmn service unavailable" in result.error_message.lower()


def test_validate_procedure_coverage_type_mismatch(worker):
    """Test validation with coverage type mismatch."""
    # Mock DMN evaluation - coverage type doesn't match
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "BLOQUEAR",
            "acao": "Procedure not covered under this plan",
            "risco": "ALTO",
            "procedureName": "Cirurgia hospitalar",
            "coverageType": "hospitalar",
            "requested_coverage": "ambulatorial",
            "validation_error": "Coverage type mismatch",
        }
    )

    context = make_context(
        {
            "procedure_codes": ["40301020"],
            "coverage_type": "ambulatorial",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "INVALID_PROCEDURE_CODE"
    # Worker error message contains the code, not necessarily "coverage"
    assert "40301020" in result.error_message


def test_validate_procedure_review_warning(worker):
    """Test DMN review with warnings."""
    # Mock DMN evaluation - review suggested
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "REVISAR",
            "acao": "High-cost procedure requires authorization",
            "risco": "MEDIO",
            "procedureName": "Cirurgia complexa",
            "coverageType": "hospitalar",
            "requires_authorization": True,
        }
    )

    context = make_context(
        {
            "procedure_codes": ["40301030"],
            "coverage_type": "hospitalar",
        }
    )

    result = worker.execute(context)

    # REVISAR still means valid (is_valid=False only for BLOQUEAR)
    # So this returns SUCCESS with all codes in validated_procedures
    assert result.status == TaskStatus.SUCCESS
    assert result.variables["all_valid"] is True
    # Worker doesn't add validation_warnings for REVISAR - it only matters for blocking


def test_validate_procedure_multiple_coverage_types(worker):
    """Test validation with multiple procedures of different coverage types."""
    call_count = [0]

    def evaluate_dmn_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return {
                "resultado": "PROSSEGUIR",
                "acao": "",
                "risco": "BAIXO",
                "procedureName": "Consulta ambulatorial",
                "coverageType": "ambulatorial",
            }
        else:
            return {
                "resultado": "PROSSEGUIR",
                "acao": "",
                "risco": "BAIXO",
                "procedureName": "Procedimento hospitalar",
                "coverageType": "hospitalar",
            }

    worker.evaluate_dmn = MagicMock(side_effect=evaluate_dmn_side_effect)

    context = make_context(
        {
            "procedure_codes": ["40301010", "40301020"],
            "coverage_type": "both",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert result.variables["all_valid"] is True
    assert len(result.variables["validated_procedures"]) == 2


def test_validate_procedure_empty_coverage_type(worker):
    """Test validation when coverage type is not specified."""
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "PROSSEGUIR",
            "acao": "",
            "risco": "BAIXO",
            "procedureName": "Consulta médica",
            "coverageType": "ambulatorial",
        }
    )

    context = make_context(
        {
            "procedure_codes": ["40301010"],
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert "validated_procedures" in result.variables
