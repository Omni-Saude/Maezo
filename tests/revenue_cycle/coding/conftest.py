"""Shared fixtures for Phase 2.2 Coding & Audit worker tests."""

import pytest
from unittest.mock import MagicMock, AsyncMock


@pytest.fixture
def mock_task():
    """Creates a MagicMock ExternalTask with standard Camunda methods."""
    task = MagicMock()
    task.get_task_id.return_value = "test-task-123"
    task.get_business_key.return_value = "ENC-001"
    task.get_variables.return_value = {
        "encounter_id": "ENC-001",
        "tenant_id": "hospital-alpha",
    }
    task.get_variable = MagicMock(side_effect=lambda key, default=None: {
        "encounter_id": "ENC-001",
        "tenant_id": "hospital-alpha",
    }.get(key, default))
    task.complete = MagicMock()
    task.bpmn_error = MagicMock()
    task.failure = MagicMock()
    return task


@pytest.fixture
def mock_tenant_context():
    """Creates a mock tenant context for multi-tenant operations."""
    ctx = MagicMock()
    ctx.tenant_id = "hospital-alpha"
    ctx.get_config.return_value = {
        "coding_engine": "auto",
        "audit_threshold": 0.85,
        "fraud_detection_enabled": True,
    }
    ctx.get_table_reference.return_value = {
        "cid10": "tuss_cid10_v2024",
        "tuss": "tuss_procedures_v2024",
    }
    return ctx


@pytest.fixture
def mock_ans_client():
    """Creates a stub ANS client for procedure/code validation."""
    client = MagicMock()
    client.validate_cid10 = AsyncMock(
        return_value={"valid": True, "description": "Diabetes mellitus tipo 2"}
    )
    client.validate_tuss = AsyncMock(
        return_value={"valid": True, "description": "Consulta em consultorio"}
    )
    client.check_compatibility = AsyncMock(
        return_value={"compatible": True, "warnings": []}
    )
    client.get_procedure_details = AsyncMock(return_value={
        "code": "10101012",
        "description": "Consulta em consultorio",
        "requires_auth": False,
    })
    return client


@pytest.fixture
def sample_clinical_data():
    """Sample clinical data for coding tests."""
    return {
        "encounter_id": "ENC-001",
        "patient_id": "PAT-001",
        "diagnoses": [
            {"code": "E11.9", "description": "Diabetes mellitus tipo 2", "type": "primary"},
            {"code": "I10", "description": "Hipertensao essencial", "type": "secondary"},
        ],
        "procedures": [
            {"code": "10101012", "description": "Consulta em consultorio", "quantity": 1},
        ],
        "clinical_notes": "Paciente com diabetes tipo 2 descompensado. HbA1c 9.2%.",
        "attending_physician": "CRM-12345",
    }


@pytest.fixture
def sample_coding_result():
    """Sample coding result after suggestion and validation."""
    return {
        "cid10_codes": [
            {"code": "E11.9", "confidence": 0.95, "source": "nlp"},
            {"code": "I10", "confidence": 0.88, "source": "nlp"},
        ],
        "tuss_codes": [
            {"code": "10101012", "confidence": 0.97, "source": "mapping"},
        ],
        "complexity_score": 0.42,
        "audit_score": 0.91,
        "fraud_risk": 0.05,
        "status": "approved",
    }
