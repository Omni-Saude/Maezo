"""Tests for ValidateCompatibilityWorker (v2)."""
from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.revenue_cycle.production.workers.validate_compatibility_worker_v2 import (
    ValidateCompatibilityWorker,
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
    """Create ValidateCompatibilityWorker."""
    worker = ValidateCompatibilityWorker()
    worker.logger = MagicMock()
    return worker


def test_validate_compatibility_happy_path(worker):
    """Test successful compatibility validation."""
    # Mock DMN evaluation - all procedures compatible
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "PROSSEGUIR",
            "acao": "",
            "risco": "BAIXO",
            "compatibility_issues": [],
        }
    )

    context = make_context(
        {
            "priced_procedures": [
                {
                    "code": "40301010",
                    "description": "Consulta médica",
                    "quantity": 1,
                    "unit_price": "150.00",
                },
                {
                    "code": "20101012",
                    "description": "Raio X",
                    "quantity": 1,
                    "unit_price": "200.00",
                },
            ],
            "patient_gender": "M",
            "patient_age_years": 45,
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert "compatible_procedures" in result.variables
    assert result.variables["all_compatible"] is True
    assert len(result.variables["compatible_procedures"]) == 2


def test_validate_compatibility_no_procedures_error(worker):
    """Test error when no procedures provided."""
    worker.evaluate_dmn = MagicMock()

    context = make_context(
        {
            "priced_procedures": [],
            "patient_gender": "M",
            "patient_age_years": 45,
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "CODING_ERROR"
    assert "no procedures" in result.error_message.lower()


def test_validate_compatibility_incompatible_block(worker):
    """Test DMN blocking due to incompatibility."""
    # Mock DMN evaluation - compatibility issues found
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "BLOQUEAR",
            "acao": "Gender-specific procedure incompatible with patient",
            "risco": "ALTO",
            "compatibility_issues": [
                {
                    "code": "31201016",
                    "issue": "Procedure is female-specific but patient is male",
                }
            ],
        }
    )

    context = make_context(
        {
            "priced_procedures": [
                {
                    "code": "31201016",
                    "description": "Papanicolau",
                }
            ],
            "patient_gender": "M",
            "patient_age_years": 45,
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "INCOMPATIBLE_CODES"
    assert "gender-specific" in result.error_message.lower()


def test_validate_compatibility_review_warning(worker):
    """Test DMN review with compatibility warnings."""
    # Mock DMN evaluation - review suggested but not blocked
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "REVISAR",
            "acao": "Age-specific procedure requires verification",
            "risco": "MEDIO",
            "compatibility_issues": [],
            "compatibility_warnings": [
                {
                    "code": "40301010",
                    "warning": "Procedure typically for older patients",
                }
            ],
        }
    )

    context = make_context(
        {
            "priced_procedures": [
                {
                    "code": "40301010",
                    "description": "Geriatric assessment",
                }
            ],
            "patient_gender": "M",
            "patient_age_years": 35,
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert "compatibility_warnings" in result.variables
    assert len(result.variables["compatibility_warnings"]) > 0
    assert result.variables["all_compatible"] is True


def test_validate_compatibility_duplicate_codes_warning(worker):
    """Test handling of duplicate procedure codes."""
    # Mock DMN evaluation - duplicates found
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "REVISAR",
            "acao": "Duplicate procedure codes detected",
            "risco": "MEDIO",
            "compatibility_issues": [],
            "duplicate_codes": ["40301010"],
        }
    )

    context = make_context(
        {
            "priced_procedures": [
                {"code": "40301010", "description": "Consulta médica"},
                {"code": "40301010", "description": "Consulta médica"},
            ],
            "patient_gender": "M",
            "patient_age_years": 45,
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert "compatibility_warnings" in result.variables
    assert any("duplicate" in w.lower() for w in result.variables["compatibility_warnings"])


def test_validate_compatibility_age_restriction(worker):
    """Test age-based compatibility validation."""
    # Mock DMN evaluation - age restriction violation
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "BLOQUEAR",
            "acao": "Procedure not authorized for patient age",
            "risco": "ALTO",
            "compatibility_issues": [
                {
                    "code": "40301010",
                    "issue": "Patient under minimum age for procedure",
                    "minimum_age": 18,
                    "patient_age": 15,
                }
            ],
        }
    )

    context = make_context(
        {
            "priced_procedures": [
                {"code": "40301010", "description": "Adult procedure"}
            ],
            "patient_gender": "M",
            "patient_age_years": 15,
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "INCOMPATIBLE_CODES"
    assert "age" in result.error_message.lower()


def test_validate_compatibility_exception_handling(worker):
    """Test handling of unexpected exceptions."""
    worker.evaluate_dmn = MagicMock(
        side_effect=Exception("DMN service unavailable")
    )

    context = make_context(
        {
            "priced_procedures": [{"code": "40301010"}],
            "patient_gender": "M",
            "patient_age_years": 45,
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "CODING_ERROR"
    assert "dmn service unavailable" in result.error_message.lower()


def test_validate_compatibility_multiple_issues(worker):
    """Test validation with multiple compatibility issues."""
    # Mock DMN evaluation - multiple issues detected
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "BLOQUEAR",
            "acao": "Multiple compatibility issues found",
            "risco": "ALTO",
            "compatibility_issues": [
                {
                    "code": "31201016",
                    "issue": "Gender incompatibility",
                },
                {
                    "code": "40301020",
                    "issue": "Age restriction violation",
                },
            ],
        }
    )

    context = make_context(
        {
            "priced_procedures": [
                {"code": "31201016", "description": "Papanicolau"},
                {"code": "40301020", "description": "Pediatric procedure"},
            ],
            "patient_gender": "M",
            "patient_age_years": 65,
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "INCOMPATIBLE_CODES"
    # Worker returns 'codes' and 'risk' in variables
    assert "codes" in result.variables
    assert "risk" in result.variables
