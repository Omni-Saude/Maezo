"""Tests for CheckAuthorizationWorker (v2)."""
from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus
from healthcare_platform.revenue_cycle.production.workers.check_authorization_worker_v2 import (
    CheckAuthorizationWorker,
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
    """Create CheckAuthorizationWorker."""
    worker = CheckAuthorizationWorker()
    worker.logger = MagicMock()
    return worker


def test_check_authorization_happy_path_authorized(worker):
    """Test successful authorization check."""
    # Mock DMN evaluation - all procedures authorized
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "PROSSEGUIR",
            "acao": "",
            "risco": "BAIXO",
            "authorization_required": True,
            "authorization_number": "AUTH-12345",
        }
    )

    context = make_context(
        {
            "enrichedProcedures": [
                {
                    "code": "40301010",
                    "description": "Consulta médica",
                }
            ],
            "patient_reference": "Patient/pat-123",
            "payer_id": "payer-456",
            "existing_auth_number": "AUTH-12345",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.SUCCESS
    assert "authorizationResults" in result.variables
    assert result.variables["allAuthorized"] is True
    assert len(result.variables["authorizationResults"]) == 1


def test_check_authorization_no_procedures_error(worker):
    """Test error when no procedures provided."""
    worker.evaluate_dmn = MagicMock()

    context = make_context(
        {
            "enrichedProcedures": [],
            "patient_reference": "Patient/pat-123",
            "payer_id": "payer-456",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "CODING_ERROR"
    assert "no procedures" in result.error_message.lower()


def test_check_authorization_auth_denied(worker):
    """Test authorization denied."""
    # Mock DMN evaluation - authorization blocked
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "BLOQUEAR",
            "acao": "Authorization required but not provided",
            "risco": "ALTO",
            "authorization_required": True,
            "authorization_number": None,
        }
    )

    context = make_context(
        {
            "enrichedProcedures": [
                {
                    "code": "40301010",
                    "description": "Consulta médica",
                }
            ],
            "patient_reference": "Patient/pat-123",
            "payer_id": "payer-456",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "AUTH_DENIED"
    assert "authorization required" in result.error_message.lower()


def test_check_authorization_review_denied(worker):
    """Test authorization requiring review."""
    # Mock DMN evaluation - requires manual review
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "REVISAR",
            "acao": "High-cost procedure requires manual review",
            "risco": "MEDIO",
            "authorization_required": True,
            "authorization_number": "AUTH-12345",
            "requires_review": True,
        }
    )

    context = make_context(
        {
            "enrichedProcedures": [
                {
                    "code": "40301010",
                    "description": "Cirurgia cardíaca",
                    "estimated_cost": 50000.00,
                }
            ],
            "patient_reference": "Patient/pat-123",
            "payer_id": "payer-456",
            "existing_auth_number": "AUTH-12345",
        }
    )

    result = worker.execute(context)

    # REVISAR means not authorized, so it returns BPMN_ERROR
    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "AUTH_DENIED"


def test_check_authorization_exception_handling(worker):
    """Test handling of unexpected exceptions."""
    worker.evaluate_dmn = MagicMock(
        side_effect=Exception("DMN service unavailable")
    )

    context = make_context(
        {
            "enrichedProcedures": [{"code": "40301010"}],
            "patient_reference": "Patient/pat-123",
            "payer_id": "payer-456",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "AUTH_NOT_FOUND"
    assert "dmn service unavailable" in result.error_message.lower()


def test_check_authorization_not_found(worker):
    """Test when authorization number not found."""
    # Mock DMN evaluation - auth required but not found
    worker.evaluate_dmn = MagicMock(
        return_value={
            "resultado": "BLOQUEAR",
            "acao": "Authorization number not found in system",
            "risco": "ALTO",
            "authorization_required": True,
            "authorization_found": False,
        }
    )

    context = make_context(
        {
            "enrichedProcedures": [{"code": "40301010"}],
            "patient_reference": "Patient/pat-123",
            "payer_id": "payer-456",
            "existing_auth_number": "AUTH-99999",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert result.error_code == "AUTH_DENIED"
    assert "not found" in result.error_message.lower()


def test_check_authorization_mixed_results(worker):
    """Test with multiple procedures - some authorized, some not."""
    # Return different results per procedure call
    call_count = [0]

    def evaluate_dmn_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return {
                "resultado": "PROSSEGUIR",
                "acao": "",
                "risco": "BAIXO",
                "authorization_required": False,
            }
        else:
            return {
                "resultado": "BLOQUEAR",
                "acao": "Authorization required",
                "risco": "ALTO",
                "authorization_required": True,
                "authorization_number": None,
            }

    worker.evaluate_dmn = MagicMock(side_effect=evaluate_dmn_side_effect)

    context = make_context(
        {
            "enrichedProcedures": [
                {"code": "40301010", "description": "Consulta"},
                {"code": "40301020", "description": "Cirurgia"},
            ],
            "patient_reference": "Patient/pat-123",
            "payer_id": "payer-456",
        }
    )

    result = worker.execute(context)

    assert result.status == TaskStatus.BPMN_ERROR
    assert "authorizationResults" in result.variables
    assert "deniedCodes" in result.variables
